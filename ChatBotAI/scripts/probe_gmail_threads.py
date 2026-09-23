"""Read-only Gmail probe — inspect what the API actually returns, OUTSIDE the app.

Answers the question: for a real guest conversation, does the Gmail thread
contain BOTH the guest's incoming message AND our host reply? Each message is
labeled guest / HOST using the exact same host-address logic the email-thread
backfill feature uses (services/email_thread_backfill.classify_direction), so
what you see here is what the feature would see. Writes NOTHING to the DB or Gmail.

Usage (from FlaskApp root, so the ChatBotAI package resolves):
    cd C:\\Users\\admin\\Documents\\FlaskApp
    set PYTHONIOENCODING=utf-8

    # 1. Who are we connected as, and list recent inbox threads (two-sided?):
    python -m ChatBotAI.scripts.probe_gmail_threads

    # 2. Dump full two-sided threads matching any Gmail search query:
    python -m ChatBotAI.scripts.probe_gmail_threads --query "from:someguest@example.com"
    python -m ChatBotAI.scripts.probe_gmail_threads --query "subject:Buchung newer_than:180d"

    # 3. Dump one specific thread by id:
    python -m ChatBotAI.scripts.probe_gmail_threads --thread 1899abc...

    # --limit N   how many threads to fetch (default 10)
    # --full      print full message bodies instead of a 6-line preview
"""
import argparse

from ChatBotAI.app import create_app
from ChatBotAI.services.gmail_service import get_gmail_service
from ChatBotAI.services.email_thread_backfill import (
    get_host_addresses, classify_direction,
)


def _preview(body: str, full: bool) -> list:
    lines = (body or "").splitlines()
    if full:
        return lines
    lines = [ln for ln in lines if ln.strip()]  # drop blank lines for the preview
    return lines[:6] + (["    ... (+%d more lines)" % (len(lines) - 6)] if len(lines) > 6 else [])


def dump_thread(gmail, thread_id: str, host_addresses: set, full: bool):
    msgs = gmail.get_thread(thread_id)
    if not msgs:
        print(f"  (thread {thread_id} returned no messages)")
        return

    directions = [classify_direction(m, host_addresses) for m in msgs]
    n_guest = directions.count("guest")
    n_host = directions.count("owner")
    two_sided = n_guest > 0 and n_host > 0

    print("=" * 90)
    print(f"THREAD {thread_id}   messages={len(msgs)}  guest={n_guest}  host={n_host}  "
          f"{'✔ TWO-SIDED' if two_sided else '✘ one-sided'}")
    print(f"SUBJECT: {msgs[0].get('subject')}")
    print("=" * 90)
    for i, (m, direction) in enumerate(zip(msgs, directions), 1):
        tag = "HOST " if direction == "owner" else "guest"
        print(f"\n  [{i}] {tag} | {m.get('date')}")
        print(f"      from: {m.get('from')}")
        print(f"      to  : {m.get('to')}")
        if m.get("reply_to"):
            print(f"      reply-to: {m.get('reply_to')}")
        print(f"      unread: {m.get('is_unread')}  labels: {m.get('labels')}")
        for ln in _preview(m.get("body"), full):
            print(f"      | {ln}")
    print()


def list_recent_threads(gmail, query: str, limit: int, host_addresses: set):
    emails = gmail.get_recent_emails(max_results=limit, query=query, apply_filter=False)
    seen = []
    for e in emails:
        if e["thread_id"] not in seen:
            seen.append(e["thread_id"])
    print(f"\nFound {len(seen)} distinct thread(s) for query: {query!r}\n")
    print(f"{'#':>2}  {'msgs':>4}  {'g/h':>5}  two-sided  subject")
    print("-" * 90)
    rows = []
    for tid in seen:
        msgs = gmail.get_thread(tid)
        dirs = [classify_direction(m, host_addresses) for m in msgs]
        g, h = dirs.count("guest"), dirs.count("owner")
        two = "✔" if (g and h) else " "
        subj = (msgs[0].get("subject") if msgs else "") or ""
        rows.append((tid, len(msgs), g, h, two, subj))
    for i, (tid, n, g, h, two, subj) in enumerate(rows, 1):
        print(f"{i:>2}  {n:>4}  {g}/{h:<3}    {two:^7}  {subj[:60]}")
        print(f"      thread id: {tid}")
    print("\nRe-run with --thread <id> (or --query) to see full two-sided bodies.\n")


def main():
    ap = argparse.ArgumentParser(description="Read-only Gmail thread probe")
    ap.add_argument("--query", help="Gmail search query (e.g. 'from:x@y.com newer_than:180d')")
    ap.add_argument("--thread", help="Dump one specific thread id")
    ap.add_argument("--limit", type=int, default=10, help="How many threads to fetch (default 10)")
    ap.add_argument("--full", action="store_true", help="Print full bodies, not a preview")
    args = ap.parse_args()

    app = create_app()
    with app.app_context():
        gmail = get_gmail_service()
        status = gmail.get_status()
        print("Gmail status:", status)
        if not status.get("authenticated"):
            print("\nNOT AUTHENTICATED — connect via Settings → Gmail first (needs instance/gmail_token.json).")
            return
        host_addresses = get_host_addresses()
        print("Host (owner) addresses used for direction labeling:", sorted(host_addresses))

        if args.thread:
            dump_thread(gmail, args.thread, host_addresses, args.full)
        elif args.query:
            emails = gmail.get_recent_emails(max_results=args.limit, query=args.query, apply_filter=False)
            seen = []
            for e in emails:
                if e["thread_id"] not in seen:
                    seen.append(e["thread_id"])
            print(f"\n{len(seen)} distinct thread(s) for {args.query!r}\n")
            for tid in seen:
                dump_thread(gmail, tid, host_addresses, args.full)
        else:
            # No query: show recent inbox threads so the user can pick one.
            list_recent_threads(gmail, "in:inbox newer_than:180d", args.limit, host_addresses)


if __name__ == "__main__":
    main()
