"""One-time backfill: link Smoobu conversations stuck on "Reservation <id>".

Conversations created by the real-time webhook were born without a property_id,
so the inbox shows the bare reservation number instead of the apartment name.
This resolves each one via its Smoobu reservation -> apartment -> Property and
sets property_id. Only touches conversations where property_id IS NULL and a
match is found; never overwrites an existing link.

Usage (from FlaskApp parent dir):
    python -u -m ChatBotAI.scripts.backfill_conversation_property          # dry-run
    python -u -m ChatBotAI.scripts.backfill_conversation_property --apply  # write
"""
import sys
import time

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map


def main(apply: bool) -> None:
    # Use the production DB/API key but with DEBUG=True so the blueprint's
    # daemon guard does NOT spawn a background Smoobu sync thread — this script
    # must be the sole API consumer to avoid rate-limit contention.
    prod = config_map['production']

    class _NoDaemonConfig(prod):
        DEBUG = True

    app = create_app(_NoDaemonConfig)
    with app.app_context():
        from sqlalchemy.exc import OperationalError
        from ChatBotAI.models import db, Conversation
        from ChatBotAI.services.smoobu_service import get_smoobu_service_for

        # Let the live server's writes settle; wait on locks instead of failing.
        db.session.execute(db.text('PRAGMA busy_timeout=30000'))

        convs = (Conversation.query
                 .filter(Conversation.platform == 'smoobu',
                         Conversation.property_id.is_(None),
                         Conversation.smoobu_reservation_id.isnot(None))
                 .all())
        print(f"Candidates (NULL property + reservation id): {len(convs)}")

        resolved = skipped = errors = 0
        for c in convs:
            rid = c.smoobu_reservation_id
            # Per-conversation account: a Sonnenhof reservation is invisible to
            # the primary account's key, and apartment ids repeat across accounts.
            svc = get_smoobu_service_for(c)
            if not svc:
                skipped += 1
                print(f"  conv {c.id} res {rid}: no Smoobu service for account "
                      f"{c.smoobu_account_id}")
                continue
            try:
                rd = svc.get_reservation(rid)
            except Exception as e:  # network/API hiccup — keep going
                errors += 1
                print(f"  conv {c.id} res {rid}: API error {e}")
                continue
            if not rd:
                skipped += 1
                print(f"  conv {c.id} res {rid}: no reservation detail")
                continue
            pid = svc._resolve_property_id(rd)
            if not pid:
                skipped += 1
                apt = rd.get('apartment')
                print(f"  conv {c.id} res {rid}: unresolved apartment={apt}")
                continue
            apt_name = (rd.get('apartment') or {}).get('name')
            print(f"  conv {c.id} res {rid}: -> property {pid} ({apt_name})")
            resolved += 1
            if apply:
                c.property_id = pid
                for attempt in range(3):
                    try:
                        db.session.commit()
                        break
                    except OperationalError:
                        db.session.rollback()
                        time.sleep(1)
                        c.property_id = pid
                else:
                    errors += 1
                    print(f"  conv {c.id}: commit failed after retries")

        print(f"\n{'APPLIED' if apply else 'DRY-RUN'} | resolved={resolved} "
              f"skipped={skipped} errors={errors}")


if __name__ == '__main__':
    main(apply='--apply' in sys.argv)
