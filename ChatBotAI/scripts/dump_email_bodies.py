"""Read-only: dump raw bodies of representative Airbnb/Booking notification
emails so we can see the real structure the parser must handle. Writes nothing.

    cd C:\\Users\\admin\\Documents\\FlaskApp
    set PYTHONIOENCODING=utf-8
    python -m ChatBotAI.scripts.dump_email_bodies
"""
from ChatBotAI.app import create_app
from ChatBotAI.services.gmail_service import get_gmail_service
from ChatBotAI.services import email_reconcile as er


def dump(email):
    print("#" * 80)
    print("FROM   :", email.get("sender_email"))
    print("SUBJECT:", email.get("subject"))
    print("CLASS  :", er.classify_notification(email))
    print("-" * 80)
    body = email.get("body") or ""
    for ln in body.splitlines():
        print("|", ln)
    print("#" * 80)
    print()


def main():
    app = create_app()
    with app.app_context():
        gmail = get_gmail_service()
        # Booking: grab several so we see empty-message + English variants
        bk = gmail.get_recent_emails(max_results=8,
                                     query='from:guest.booking.com newer_than:90d',
                                     apply_filter=False)
        # Airbnb: grab several so we see the failing (#2/#4) vs working (#3/#5)
        ab = gmail.get_recent_emails(max_results=8,
                                     query='from:airbnb.com newer_than:90d',
                                     apply_filter=False)

        print("\n\n=================== BOOKING BODIES ===================\n")
        for e in bk:
            dump(e)
        print("\n\n=================== AIRBNB BODIES ===================\n")
        for e in ab:
            # skip the obvious non-message ones to save space
            if er.classify_notification(e) is None:
                print(f"(skipped non-message: {e.get('subject')})\n")
                continue
            dump(e)


if __name__ == "__main__":
    main()
