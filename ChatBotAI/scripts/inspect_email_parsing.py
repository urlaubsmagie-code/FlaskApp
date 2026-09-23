"""Read-only inspection of what the email reconciler extracts from REAL
Airbnb/Booking notification emails. Fetches from Gmail and parses; writes
NOTHING to the DB or Gmail. Run:

    cd C:\\Users\\admin\\Documents\\FlaskApp
    set PYTHONIOENCODING=utf-8
    python -m ChatBotAI.scripts.inspect_email_parsing
"""
from ChatBotAI.app import create_app
from ChatBotAI.services.gmail_service import get_gmail_service
from ChatBotAI.services import email_reconcile as er

MAX_PER_PLATFORM = 8


def show(label, value, width=60):
    if value is None:
        print(f"    {label:<14}: <none>")
    else:
        s = str(value).replace("\n", " / ")
        if len(s) > width:
            s = s[:width] + "…"
        print(f"    {label:<14}: {s}")


def main():
    app = create_app()
    with app.app_context():
        gmail = get_gmail_service()
        if not gmail.is_authenticated():
            print("Gmail NOT connected — cannot inspect.")
            return
        print(f"Connected as: {gmail.get_user_email()}\n")

        for platform, query in er.platform_queries(er.get_reconcile_config()['days']).items():
            print("=" * 78)
            print(f"PLATFORM: {platform.upper()}   (Gmail query: {query})")
            print("=" * 78)
            emails = gmail.get_recent_emails(
                max_results=MAX_PER_PLATFORM, query=query, apply_filter=False)
            print(f"fetched {len(emails)} emails\n")

            try:
                views = er._candidate_views(platform)
            except Exception as e:
                views = []
                print(f"(could not build candidate views for matching: {e})\n")

            for i, email in enumerate(emails, 1):
                print(f"--- {platform} email #{i} ---")
                show("From", email.get("sender_email"))
                show("Reply-To", email.get("reply_to"))
                show("Subject", email.get("subject"))
                show("Date", email.get("date"))

                cls = er.classify_notification(email)
                print(f"    classified as : {cls}")

                notif = er.parse_notification(email)
                if not notif:
                    print("    >>> NOT a guest-message notification (skipped)\n")
                    continue

                print("    --- EXTRACTED ---")
                show("guest_name", notif.guest_name)
                show("message_text", notif.message_text, width=90)
                show("sent_at", notif.sent_at)
                show("property_name", notif.property_name)
                show("check_in", notif.check_in)
                show("check_out", notif.check_out)
                show("booking_ref", notif.booking_ref)

                # Read-only match preview against existing conversations
                if notif.message_text and notif.sent_at and views:
                    best, score = er.pick_best_match(notif, views)
                    if best:
                        print(f"    match preview : conv #{best.get('conversation_id')} "
                              f"(guest={best.get('guest_name')!r}) score={score:.2f}")
                    else:
                        print("    match preview : no matching conversation")
                print()


if __name__ == "__main__":
    main()
