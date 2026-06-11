"""Merge duplicate Guest rows. See docs/superpowers/specs/2026-06-08-guest-dedup-design.md.

Usage (from C:\\Users\\admin\\Documents\\FlaskApp):
    python -m ChatBotAI.scripts.dedup_guests --dry-run
    python -m ChatBotAI.scripts.dedup_guests --apply
"""
import argparse
import shutil
from datetime import datetime

from ..models import db, Guest, Conversation, GuestDetail
from ..services.guest_matching import (
    normalize_email, normalize_phone, build_merge_groups,
)


def choose_winner(guests):
    """Richest profile wins: has email/phone, then most conversations, then lowest id."""
    def score(g):
        has_contact = 1 if (normalize_email(g.email) or normalize_phone(g.phone)) else 0
        return (has_contact, g.conversations.count(), -g.id)
    return max(guests, key=score)


def merge_group(ids):
    """Merge the given guest ids into one survivor. Caller commits.

    Returns (winner_id, loser_ids). Losers are deleted BEFORE the winner's
    contact fields are set, so backfilling a unique email cannot clash.
    """
    guests = Guest.query.filter(Guest.id.in_(ids)).all()
    winner = choose_winner(guests)
    losers = [g for g in guests if g.id != winner.id]
    loser_ids = sorted(g.id for g in losers)

    # Gather consolidated values from the whole group BEFORE deleting losers.
    email = winner.email or next((g.email for g in losers if g.email), None)
    phone = winner.phone or next((g.phone for g in losers if g.phone), None)
    notes = winner.notes or next((g.notes for g in losers if g.notes), None)
    first_contacts = [g.first_contact for g in guests if g.first_contact]
    last_contacts = [g.last_contact for g in guests if g.last_contact]
    total_stays = sum((g.total_stays or 0) for g in guests)

    # Reassign foreign keys to the winner.
    Conversation.query.filter(Conversation.guest_id.in_(loser_ids)).update(
        {"guest_id": winner.id}, synchronize_session=False)
    GuestDetail.query.filter(GuestDetail.guest_id.in_(loser_ids)).update(
        {"guest_id": winner.id}, synchronize_session=False)
    db.session.flush()

    # Delete losers first to free the unique email before backfilling it.
    for g in losers:
        db.session.delete(g)
    db.session.flush()

    winner.email = email
    winner.phone = phone
    winner.notes = notes
    if first_contacts:
        winner.first_contact = min(first_contacts)
    if last_contacts:
        winner.last_contact = max(last_contacts)
    winner.total_stays = total_stays
    db.session.flush()

    # Dedupe identical details now consolidated on the winner.
    seen = set()
    for d in (GuestDetail.query.filter_by(guest_id=winner.id)
              .order_by(GuestDetail.id).all()):
        key = (d.detail_type, d.detail_key, d.detail_value)
        if key in seen:
            db.session.delete(d)
        else:
            seen.add(key)
    db.session.flush()

    return winner.id, loser_ids


def run_dedup(apply=False):
    """Compute groups and (optionally) merge them. Caller manages app context.

    Returns a summary dict: {groups, deleted, conflicts, conflict_detail, samples}.
    Does NOT commit when apply=False; commits per group when apply=True.
    """
    guests = Guest.query.all()
    groups, conflicts = build_merge_groups(guests)

    samples = []
    for g in groups[:10]:
        first = Guest.query.get(g[0])
        samples.append({"name": first.name, "rows": len(g)})

    deleted = 0
    if apply:
        for ids in groups:
            _, loser_ids = merge_group(ids)
            deleted += len(loser_ids)
            db.session.commit()

    return {
        "groups": len(groups),
        "deleted": deleted if apply else sum(len(g) - 1 for g in groups),
        "conflicts": len(conflicts),
        "conflict_detail": conflicts,
        "samples": samples,
    }


def _print_report(summary, applied):
    print(f"{'APPLIED' if applied else 'DRY-RUN'} guest dedup")
    print(f"  merge groups        : {summary['groups']}")
    print(f"  rows {'deleted' if applied else 'to delete'} : {summary['deleted']}")
    print(f"  conflict groups skipped: {summary['conflicts']}")
    if summary["samples"]:
        print("  largest groups:")
        for s in summary["samples"]:
            print(f"    {s['rows']:>4}  {s['name']}")
    if summary["conflict_detail"]:
        print("  SKIPPED (conflicting email/phone — review manually):")
        for c in summary["conflict_detail"]:
            print(f"    {c['name']}: ids={c['ids']} emails={c['emails']} phones={c['phones']}")


def main():
    parser = argparse.ArgumentParser(description="Deduplicate Guest rows.")
    parser.add_argument("--apply", action="store_true",
                        help="Actually merge (default is dry-run).")
    args = parser.parse_args()

    from ..app import create_app
    from ..config import config as config_map
    import os

    app = create_app(config_map[os.environ.get("FLASK_ENV", "production")])
    with app.app_context():
        if args.apply:
            db_path = app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
            db.session.execute(db.text("PRAGMA wal_checkpoint(TRUNCATE)"))
            ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
            backup = f"{db_path}.bak-pre-dedup-{ts}"
            shutil.copyfile(db_path, backup)
            print(f"Backup written: {backup}")

        summary = run_dedup(apply=args.apply)
        _print_report(summary, applied=args.apply)


if __name__ == "__main__":
    main()
