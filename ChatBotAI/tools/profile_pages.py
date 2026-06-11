"""One-shot profiler: report query count + timing for key pages.

Usage (from FlaskApp/ parent dir):
    python -m ChatBotAI.tools.profile_pages

What it does:
- Boots the Flask app
- Logs in as the first admin user via the test client
- Hits inbox (/chatbot/), API conversations (/chatbot/api/conversations),
  the most-recent conversation page, and the "Mehr Laden" page 2 endpoint
- For each: prints query count, total time, top 5 slowest queries

Does NOT modify the DB. Read-only.
"""
import os
import sys
import time
from collections import defaultdict

# Make this importable from FlaskApp/ parent
HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PARENT)

# Force UTF-8 for stdout (avoid Windows cp1252 explosions on guest names)
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from sqlalchemy import event

from ChatBotAI.app import create_app
from ChatBotAI.models import db, User, Conversation


class QueryRecorder:
    def __init__(self):
        self.queries = []
        self._t0 = None

    def before(self, conn, cursor, statement, parameters, context, executemany):
        context._t0 = time.perf_counter()

    def after(self, conn, cursor, statement, parameters, context, executemany):
        elapsed = time.perf_counter() - getattr(context, '_t0', time.perf_counter())
        self.queries.append((elapsed, statement))

    def reset(self):
        self.queries = []

    def report(self, label):
        n = len(self.queries)
        total = sum(q[0] for q in self.queries)
        print(f"\n=== {label} ===")
        print(f"  Total queries : {n}")
        print(f"  Total SQL time: {total*1000:.1f} ms")
        if n == 0:
            return
        # Aggregate identical statements
        buckets = defaultdict(lambda: {'count': 0, 'time': 0.0})
        for elapsed, stmt in self.queries:
            key = stmt[:120]
            buckets[key]['count'] += 1
            buckets[key]['time'] += elapsed
        # Top 5 by time
        top = sorted(buckets.items(), key=lambda kv: -kv[1]['time'])[:5]
        print(f"  Top 5 statements by total time:")
        for key, info in top:
            print(f"    {info['count']}x ({info['time']*1000:.1f} ms total): {key}")


def main():
    app = create_app()
    rec = QueryRecorder()

    with app.app_context():
        event.listen(db.engine, 'before_cursor_execute', rec.before)
        event.listen(db.engine, 'after_cursor_execute', rec.after)
        first_admin = User.query.filter_by(is_admin=True).order_by(User.id).first()
        if not first_admin:
            print("No admin user found in DB. Aborting.")
            return
        latest_conv = (
            Conversation.query
            .filter(Conversation.platform != 'playtest')
            .order_by(Conversation.last_message_at.desc())
            .first()
        )

    client = app.test_client()

    # Log in by setting the Flask-Login session cookie
    with client.session_transaction() as s:
        s['_user_id'] = str(first_admin.id)
        s['_fresh'] = True

    print(f"Profiling as user id={first_admin.id} (admin)")
    print(f"Latest non-playtest conversation: id={latest_conv.id if latest_conv else 'NONE'}")

    # --- 1. Inbox page ---
    rec.reset()
    t0 = time.perf_counter()
    r = client.get('/chatbot/')
    wall = (time.perf_counter() - t0) * 1000
    print(f"\n[GET /chatbot/]  HTTP {r.status_code}  wall: {wall:.0f} ms")
    rec.report("inbox /chatbot/")

    # --- 2. API conversations (used by polling + Mehr Laden) ---
    rec.reset()
    t0 = time.perf_counter()
    r = client.get('/chatbot/api/conversations?page=1&per_page=20')
    wall = (time.perf_counter() - t0) * 1000
    print(f"\n[GET /chatbot/api/conversations?page=1]  HTTP {r.status_code}  wall: {wall:.0f} ms")
    rec.report("api conversations page 1")

    # --- 3. Mehr Laden (page 2) ---
    rec.reset()
    t0 = time.perf_counter()
    r = client.get('/chatbot/api/conversations?page=2&per_page=20')
    wall = (time.perf_counter() - t0) * 1000
    print(f"\n[GET /chatbot/api/conversations?page=2]  HTTP {r.status_code}  wall: {wall:.0f} ms")
    rec.report("api conversations page 2 (Mehr Laden)")

    # --- 4. Conversation view ---
    if latest_conv:
        rec.reset()
        t0 = time.perf_counter()
        r = client.get(f'/chatbot/conversation/{latest_conv.id}')
        wall = (time.perf_counter() - t0) * 1000
        print(f"\n[GET /chatbot/conversation/{latest_conv.id}]  HTTP {r.status_code}  wall: {wall:.0f} ms")
        rec.report(f"conversation/{latest_conv.id}")

        rec.reset()
        t0 = time.perf_counter()
        r = client.get(f'/chatbot/api/conversations/{latest_conv.id}/messages')
        wall = (time.perf_counter() - t0) * 1000
        print(f"\n[GET /chatbot/api/conversations/{latest_conv.id}/messages]  HTTP {r.status_code}  wall: {wall:.0f} ms")
        rec.report(f"api messages for conv {latest_conv.id}")

    print("\nDone.")


if __name__ == '__main__':
    main()
