"""READ-ONLY dry run: what would today's Booking matcher do with the pending
email backfill candidates?

Re-fetches each pending Booking candidate's original email from Gmail, re-parses
it with the CURRENT parser, and asks the CURRENT tier matcher
(`email_matches_conversation`) which chat it belongs to. Writes NOTHING to the
DB or Gmail — it only prints what a rescue sweep would do.

Why this exists: the pending candidates were scored in June by the fuzzy
`score_conversation_match`, whose apartment soft-veto (-0.50) cancels the
Booking exact-name bonus (+0.50) and files emails onto a stranger in the same
apartment. The July tier matcher fixes that but only runs on the on-open live
fetch, so the backlog never got re-judged.

    cd C:\\Users\\admin\\Documents\\FlaskApp
    set PYTHONIOENCODING=utf-8
    python -m ChatBotAI.scripts.booking_rescue_dryrun          # first 25
    python -m ChatBotAI.scripts.booking_rescue_dryrun --all
    python -m ChatBotAI.scripts.booking_rescue_dryrun --smoobu # allow tier 2
"""
import re
import sys
import unicodedata

from ChatBotAI.app import create_app
from ChatBotAI.models import Conversation, EmailBackfillCandidate, Guest
from ChatBotAI.services import email_reconcile as er
from ChatBotAI.services.gmail_service import get_gmail_service


class _NoSmoobu:
    """Stub so conversation_booking_ref stays on tier 1 (guest note) and never
    makes 137 live Smoobu calls. Pass --smoobu to use the real service."""

    def get_reservation(self, _reservation_id):
        return None


def norm_name(s):
    """Order- and accent-insensitive name key. 'Vaghela Hardik' == 'Hardik Vaghela'."""
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().lower()
    return ' '.join(sorted(re.sub(r'[^a-z ]', ' ', s).split()))


def short(v, width=44):
    if v is None:
        return '<none>'
    s = str(v).replace('\n', ' / ')
    return s if len(s) <= width else s[:width] + '…'


def main():
    limit = None if '--all' in sys.argv else 25
    smoobu = _NoSmoobu() if '--smoobu' not in sys.argv else None

    app = create_app()
    with app.app_context():
        gmail = get_gmail_service()
        if not gmail.is_authenticated():
            print('Gmail not authenticated — connect it in Settings first.')
            return

        # Name index over Booking conversations only; the tier-3 fallback assumes
        # the guest name is already established, exactly as the live path does.
        by_name = {}
        for conv in Conversation.query.all():
            if er.resolve_channel(conv) != 'booking':
                continue
            guest = Guest.query.get(conv.guest_id)
            if guest and guest.name:
                by_name.setdefault(norm_name(guest.name), []).append(conv)

        pending = (EmailBackfillCandidate.query
                   .filter_by(status='pending', platform='booking')
                   .order_by(EmailBackfillCandidate.confidence.desc())
                   .all())
        if limit:
            pending = pending[:limit]

        print(f'Booking conversations indexed : {sum(len(v) for v in by_name.values())}')
        print(f'Pending candidates examined   : {len(pending)}')
        print(f'Tier 2 (Smoobu reference-id)  : {"OFF (tier 1 + 3 only)" if smoobu else "ON"}\n')

        tally = {'rescued': 0, 'same': 0, 'ambiguous': 0, 'no_name': 0,
                 'no_tier_match': 0, 'unfetchable': 0, 'unauthentic': 0}

        for cand in pending:
            email = gmail.get_email_by_id(cand.gmail_message_id)
            if not email:
                tally['unfetchable'] += 1
                print(f'[{cand.id}] email gone from Gmail ({cand.gmail_message_id})')
                continue

            ok, auth = er.verify_sender_authenticity(email, 'booking')
            if not ok:
                tally['unauthentic'] += 1
                print(f'[{cand.id}] FAILED DKIM/DMARC gate: dmarc={auth["dmarc"]} '
                      f'dkim_aligned={auth["dkim_aligned"]}')
                continue

            notif = er.parse_notification(email)
            if notif is None:
                tally['no_tier_match'] += 1
                print(f'[{cand.id}] parser returned nothing')
                continue

            convs = by_name.get(norm_name(notif.guest_name), [])
            if not convs:
                tally['no_name'] += 1
                print(f'[{cand.id}] no Booking chat for {short(notif.guest_name, 30)!r}')
                continue

            matches = [c for c in convs
                       if er.email_matches_conversation(
                           notif, c, er.conversation_booking_ref(c, smoobu_service=smoobu))]

            if len(matches) == 1:
                target = matches[0]
                verdict = 'SAME as stored' if target.id == cand.guessed_conversation_id else 'RESCUE'
                tally['same' if target.id == cand.guessed_conversation_id else 'rescued'] += 1
                print(f'[{cand.id}] {verdict:<14} {short(notif.guest_name, 22):<24} '
                      f'stored=#{cand.guessed_conversation_id} -> #{target.id}  '
                      f'ref={notif.booking_ref or "-"}  {short(notif.message_text, 34)}')
            elif matches:
                tally['ambiguous'] += 1
                print(f'[{cand.id}] AMBIGUOUS      {short(notif.guest_name, 22):<24} '
                      f'-> {[c.id for c in matches]}')
            else:
                tally['no_tier_match'] += 1
                print(f'[{cand.id}] no tier match  {short(notif.guest_name, 22):<24} '
                      f'ref={notif.booking_ref or "-"} '
                      f'dates={er._iso_date(notif.check_in)}..{er._iso_date(notif.check_out)} '
                      f'candidates={[c.id for c in convs]}')

        print('\n--- summary (nothing was written) ---')
        for k, v in tally.items():
            print(f'  {k:<14}: {v}')
        print(f'\n  would move to the correct chat: {tally["rescued"]}')


if __name__ == '__main__':
    main()
