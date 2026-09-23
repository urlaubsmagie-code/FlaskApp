# Problem Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the team log problems/ideas they notice while using the app; reports collect on an admin-only page for triage, with a badge showing the open count.

**Architecture:** New `ProblemReport` table (migration p20). A single native `<dialog>` modal in `base.html` (reused by every entry point) POSTs to `/chatbot/api/problem-reports`. Entry points: a drawer/sidebar nav item, and a per-chat button in the conversation header (pre-fills `conversation_id` + `page_url`). Admin review page lists reports with a resolve toggle; a badge mirrors the E-Mail-Abgleich pattern.

**Tech Stack:** Flask + SQLAlchemy + Flask-Migrate (Alembic), Jinja2, vanilla JS, pytest. No new dependencies.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-08-problem-report-design.md`.
- German-first UI (English via i18n). Store stable category KEYS, translate in UI.
- **Fixed 4 categories, no admin config:** `missing_message` · `bug` · `idea` · `other`.
- **Status values:** `open` (default) / `resolved`.
- Migration p20: `revision = 'p20_problem_report'`, `down_revision = 'p19_notion_source'` (current head, verified via `flask db heads`).
- FK targets: `user.id`, `conversation.id` (verified table names).
- **Reuse the native `<dialog class="edit-modal">` + `.showModal()` pattern** already used in `guest_profile.html`, `knowledge.html`, `settings.html` — do NOT hand-roll a modal or add modal CSS; `.edit-modal` / `.modal-header` / `.modal-body` / `.modal-footer` already exist in `style.css`.
- Route guards: `@login_required` (submit + pending-count), `@admin_required` (`routes.py:18`) (review page + resolve).
- Badge: clone the `refreshEmailReviewBadge` pattern in `base.html` (trailing `<script>`, ~line 258 after Task-1 drawer edits) against `/chatbot/api/problem-reports/pending-count`.
- Admin nav items go inside the existing `{% if current_user.is_authenticated and current_user.is_admin %}` block in `base.html` (where Debug lives).
- Bump `i18n.js` cache `?v=28` → `?v=29` when i18n keys are added. No `style.css` bump (no CSS added).
- Test file: `tests/test_problem_report.py`, following `tests/test_playtest_routes.py` fixtures (the `app` + authed `client` fixture that sets `s['_user_id']`).

---

### Task 1: `ProblemReport` model + p20 migration

**Files:**
- Modify: `models.py` (add class after `KnowledgeEntry`, which ends ~line 690)
- Create: `migrations/versions/p20_problem_report.py`
- Create: `tests/test_problem_report.py`

**Interfaces:**
- Produces: `ProblemReport` model with `CATEGORIES = ['missing_message','bug','idea','other']`, columns `id, created_at, user_id, conversation_id, category, message, page_url, status, resolved_at, resolved_by`, `.to_dict()`, and relationships `reporter` / `resolver` / `conversation`. Later tasks import it from `.models`.

- [ ] **Step 1: Write the failing test** — create `tests/test_problem_report.py`:

```python
"""Problem Report feature — model + route tests."""
import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, ProblemReport, User


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    user = User(username='reporter', display_name='Reporter', is_admin=True)
    user.set_password('pw')
    db.session.add(user)
    db.session.commit()
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(user.id)
        s['_fresh'] = True
    return c


def test_problem_report_roundtrip(app):
    u = User(username='u1', display_name='U One')
    u.set_password('pw')
    db.session.add(u)
    db.session.commit()
    r = ProblemReport(user_id=u.id, category='bug', message='Suche ist langsam')
    db.session.add(r)
    db.session.commit()
    got = ProblemReport.query.first()
    assert got.status == 'open'
    assert got.category == 'bug'
    assert got.reporter.display_name == 'U One'
    assert got.to_dict()['reporter_name'] == 'U One'
```

- [ ] **Step 2: Run it to verify it fails** —

Run: `python -m pytest ChatBotAI/tests/test_problem_report.py::test_problem_report_roundtrip -q` (from `C:\Users\admin\Documents\FlaskApp`)
Expected: FAIL — `ImportError: cannot import name 'ProblemReport'`.

- [ ] **Step 3: Add the model** — in `models.py`, after the `KnowledgeEntry` class (follow its style; `datetime` is already imported at top of file):

```python
class ProblemReport(db.Model):
    """Team-reported problems/ideas noticed while using the app.
    Collected on an admin-only review page for triage."""
    __tablename__ = 'problem_report'

    CATEGORIES = ['missing_message', 'bug', 'idea', 'other']

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=True, index=True)
    category = db.Column(db.String(30), nullable=False)
    message = db.Column(db.Text, nullable=False)
    page_url = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='open', server_default='open', index=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    reporter = db.relationship('User', foreign_keys=[user_id])
    resolver = db.relationship('User', foreign_keys=[resolved_by])
    conversation = db.relationship('Conversation')

    def __repr__(self):
        return f'<ProblemReport {self.id}: [{self.category}] {self.status}>'

    def to_dict(self):
        return {
            'id': self.id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'user_id': self.user_id,
            'reporter_name': self.reporter.display_name if self.reporter else None,
            'conversation_id': self.conversation_id,
            'category': self.category,
            'message': self.message,
            'page_url': self.page_url,
            'status': self.status,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
        }
```

- [ ] **Step 4: Run the test to verify it passes** —

Run: `python -m pytest ChatBotAI/tests/test_problem_report.py::test_problem_report_roundtrip -q`
Expected: PASS (1 passed). The testing config builds tables via `create_all`, so no migration needed for tests.

- [ ] **Step 5: Write the p20 migration** (for prod schema) — create `migrations/versions/p20_problem_report.py`, following `p19_notion_source.py` style:

```python
"""Add problem_report table for team-reported problems/ideas.

Revision ID: p20_problem_report
Revises: p19_notion_source
Create Date: 2026-07-08

Additive only — new table, no changes to existing tables.
"""
from alembic import op
import sqlalchemy as sa

revision = 'p20_problem_report'
down_revision = 'p19_notion_source'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'problem_report',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=True),
        sa.Column('category', sa.String(length=30), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('page_url', sa.String(length=500), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='open'),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversation.id']),
        sa.ForeignKeyConstraint(['resolved_by'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_problem_report_status', 'problem_report', ['status'])
    op.create_index('ix_problem_report_created_at', 'problem_report', ['created_at'])
    op.create_index('ix_problem_report_user_id', 'problem_report', ['user_id'])
    op.create_index('ix_problem_report_conversation_id', 'problem_report', ['conversation_id'])


def downgrade():
    op.drop_index('ix_problem_report_conversation_id', table_name='problem_report')
    op.drop_index('ix_problem_report_user_id', table_name='problem_report')
    op.drop_index('ix_problem_report_created_at', table_name='problem_report')
    op.drop_index('ix_problem_report_status', table_name='problem_report')
    op.drop_table('problem_report')
```

- [ ] **Step 6: Verify the migration is well-formed** —

Run: `python -m flask db heads` (from `ChatBotAI/`, or the parent per project convention)
Expected: prints `p20_problem_report (head)`. If it still shows `p19_notion_source`, the new file's `revision`/`down_revision` is wrong — fix. Do NOT run `db upgrade` against the prod DB here; that is a deploy step the user runs.

- [ ] **Step 7: Commit**

```bash
git add models.py migrations/versions/p20_problem_report.py tests/test_problem_report.py
git commit -m "feat(problem-report): ProblemReport model + p20 migration

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Submit + badge API routes

**Files:**
- Modify: `routes.py` (add routes near the other `/api/*` routes; `jsonify`, `request`, `current_user`, `login_required`, `db`, `datetime` all already imported)
- Modify: `tests/test_problem_report.py` (add route tests)

**Interfaces:**
- Consumes: `ProblemReport` from `.models` (add to the existing models import line, `routes.py:34`).
- Produces: `POST /chatbot/api/problem-reports` → 201 `{id}` or 400 `{error}`; `GET /chatbot/api/problem-reports/pending-count` → `{count}`.

- [ ] **Step 1: Write failing tests** — append to `tests/test_problem_report.py`:

```python
def test_create_rejects_empty_message(client):
    resp = client.post('/chatbot/api/problem-reports',
                       json={'message': '   ', 'category': 'bug'})
    assert resp.status_code == 400


def test_create_rejects_bad_category(client):
    resp = client.post('/chatbot/api/problem-reports',
                       json={'message': 'x', 'category': 'nonsense'})
    assert resp.status_code == 400


def test_create_persists_and_counts(client, app):
    resp = client.post('/chatbot/api/problem-reports',
                       json={'message': 'Gast schrieb, kein Chat', 'category': 'missing_message',
                             'page_url': '/chatbot/'})
    assert resp.status_code == 201
    from ChatBotAI.models import ProblemReport
    row = ProblemReport.query.first()
    assert row.status == 'open'
    assert row.message == 'Gast schrieb, kein Chat'
    assert row.category == 'missing_message'

    count = client.get('/chatbot/api/problem-reports/pending-count').get_json()['count']
    assert count == 1
```

- [ ] **Step 2: Run to verify they fail** —

Run: `python -m pytest ChatBotAI/tests/test_problem_report.py -q`
Expected: the 3 new tests FAIL with 404 (routes not defined yet).

- [ ] **Step 3: Add `ProblemReport` to the models import** — in `routes.py:34`, add `ProblemReport` to the `from .models import ...` list.

- [ ] **Step 4: Implement the routes** — add to `routes.py` (e.g. near the email-review pending-count route, ~line 4764):

```python
@chatbot_bp.route('/api/problem-reports', methods=['POST'])
@login_required
def api_create_problem_report():
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    category = (data.get('category') or '').strip()
    if not message:
        return jsonify({'error': 'message required'}), 400
    if category not in ProblemReport.CATEGORIES:
        return jsonify({'error': 'invalid category'}), 400
    conv_id = data.get('conversation_id')
    report = ProblemReport(
        user_id=current_user.id,
        category=category,
        message=message,
        conversation_id=int(conv_id) if conv_id else None,
        page_url=(data.get('page_url') or None),
    )
    db.session.add(report)
    db.session.commit()
    return jsonify({'id': report.id}), 201


@chatbot_bp.route('/api/problem-reports/pending-count')
@login_required
def api_problem_report_pending_count():
    count = ProblemReport.query.filter_by(status='open').count()
    return jsonify({'count': count})
```

- [ ] **Step 5: Run tests to verify they pass** —

Run: `python -m pytest ChatBotAI/tests/test_problem_report.py -q`
Expected: PASS (all tests green).

- [ ] **Step 6: Commit**

```bash
git add routes.py tests/test_problem_report.py
git commit -m "feat(problem-report): submit + pending-count API routes

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Admin review route + resolve toggle + review template

**Files:**
- Modify: `routes.py` (2 admin routes)
- Create: `templates/chatbot/problem_reports.html`
- Modify: `tests/test_problem_report.py` (resolve + page render + non-admin guard tests)

**Interfaces:**
- Consumes: `ProblemReport` (already imported in Task 2).
- Produces: `GET /chatbot/problem-reports` (admin) renders the review page; `POST /chatbot/api/problem-reports/<id>/resolve` (admin) toggles `open`↔`resolved`.

- [ ] **Step 1: Write failing tests** — append to `tests/test_problem_report.py`:

```python
def _non_admin_client(app):
    u = User(username='plain', display_name='Plain', is_admin=False)
    u.set_password('pw')
    db.session.add(u)
    db.session.commit()
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u.id)
        s['_fresh'] = True
    return c


def test_resolve_toggles_status(client, app):
    from ChatBotAI.models import ProblemReport
    client.post('/chatbot/api/problem-reports', json={'message': 'x', 'category': 'idea'})
    rid = ProblemReport.query.first().id
    resp = client.post(f'/chatbot/api/problem-reports/{rid}/resolve')
    assert resp.status_code == 200
    row = ProblemReport.query.get(rid)
    assert row.status == 'resolved'
    assert row.resolved_at is not None
    # toggle back
    client.post(f'/chatbot/api/problem-reports/{rid}/resolve')
    assert ProblemReport.query.get(rid).status == 'open'
    assert ProblemReport.query.get(rid).resolved_at is None


def test_review_page_renders_for_admin(client):
    assert client.get('/chatbot/problem-reports').status_code == 200


def test_review_page_forbidden_for_non_admin(app):
    c = _non_admin_client(app)
    assert c.get('/chatbot/problem-reports').status_code in (302, 403)
```

- [ ] **Step 2: Run to verify they fail** —

Run: `python -m pytest ChatBotAI/tests/test_problem_report.py -q`
Expected: the 3 new tests FAIL (404 / template missing).

- [ ] **Step 3: Implement the routes** — add to `routes.py` (near Task 2's routes):

```python
@chatbot_bp.route('/problem-reports')
@admin_required
def problem_reports_page():
    reports = ProblemReport.query.order_by(
        ProblemReport.status.asc(),  # 'open' before 'resolved'
        ProblemReport.created_at.desc()).all()
    return render_template('chatbot/problem_reports.html', reports=reports)


@chatbot_bp.route('/api/problem-reports/<int:report_id>/resolve', methods=['POST'])
@admin_required
def api_resolve_problem_report(report_id):
    report = ProblemReport.query.get_or_404(report_id)
    if report.status == 'open':
        report.status = 'resolved'
        report.resolved_at = datetime.utcnow()
        report.resolved_by = current_user.id
    else:
        report.status = 'open'
        report.resolved_at = None
        report.resolved_by = None
    db.session.commit()
    return jsonify({'status': report.status})
```

- [ ] **Step 4: Create the review template** — create `templates/chatbot/problem_reports.html`. Follow the structure of an existing simple page template (e.g. the top of `email_review.html`): `{% extends "chatbot/base.html" %}`, a `page-header`, then a list. Categories/status are translated client-side via `data-i18n` where a key exists; the reporter name and message are server-rendered.

```html
{% extends "chatbot/base.html" %}
{% block content %}
<div class="page-header">
    <h1><i class="fas fa-exclamation-triangle"></i> <span data-i18n="problem.reports">Problem-Berichte</span></h1>
</div>

{% if not reports %}
<p class="erc-count" data-i18n="problem.empty">Keine Berichte.</p>
{% else %}
<div class="email-review-list">
    {% for r in reports %}
    <div class="email-review-card {% if r.status == 'resolved' %}erc-removing-none{% endif %}" id="pr-{{ r.id }}"
         style="{% if r.status == 'resolved' %}opacity:.6;{% endif %}">
        <div class="erc-head">
            <span class="erc-conf {% if r.status == 'open' %}erc-conf-mid{% else %}erc-conf-high{% endif %}">
                {{ 'OFFEN' if r.status == 'open' else 'GELÖST' }}
            </span>
            <span class="erc-sender"><i class="fas fa-user"></i> {{ r.reporter.display_name if r.reporter else '—' }}</span>
            <span class="erc-time"><i class="fas fa-clock"></i> {{ r.created_at.strftime('%d.%m.%Y %H:%M') if r.created_at else '' }}</span>
        </div>
        <div class="erc-match">
            <span class="erc-conf erc-conf-low">{{ r.category }}</span>
            {% if r.conversation_id %}
            · <a class="erc-conv-link" href="{{ url_for('chatbot.conversation', conversation_id=r.conversation_id) }}">Chat #{{ r.conversation_id }}</a>
            {% endif %}
        </div>
        <p class="erc-text">{{ r.message }}</p>
        <div class="erc-actions">
            <button class="btn btn-secondary" onclick="toggleProblemReport({{ r.id }})">
                {{ 'Als gelöst markieren' if r.status == 'open' else 'Wieder öffnen' }}
            </button>
        </div>
    </div>
    {% endfor %}
</div>
{% endif %}

<script>
function toggleProblemReport(id) {
    fetch('/chatbot/api/problem-reports/' + id + '/resolve', {method: 'POST'})
        .then(function (r) { return r.json(); })
        .then(function () { location.reload(); })
        .catch(function () {});
}
</script>
{% endblock %}
```

Note: the `conversation` route endpoint name — confirm it is `chatbot.conversation` by checking `routes.py` (`grep "def conversation("`); adjust `url_for` if the endpoint differs.

- [ ] **Step 5: Run tests to verify they pass** —

Run: `python -m pytest ChatBotAI/tests/test_problem_report.py -q`
Expected: PASS (all green).

- [ ] **Step 6: Commit**

```bash
git add routes.py templates/chatbot/problem_reports.html tests/test_problem_report.py
git commit -m "feat(problem-report): admin review page + resolve toggle

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Frontend — nav items, shared modal, submit JS, badge, i18n

**Files:**
- Modify: `templates/chatbot/base.html`
- Modify: `static/js/i18n.js`

**Interfaces:**
- Consumes: `POST /api/problem-reports` + `GET /api/problem-reports/pending-count` (Tasks 2), `GET /problem-reports` (Task 3).
- Produces: global `window.openProblemModal(conversationId)` used by Task 5; a `<dialog id="problemReportModal">`; a `⚠ Problem melden` nav item and an admin `⚠ Problem-Berichte` nav item; a `#problemReportBadge`.

- [ ] **Step 1: Add the two nav items** — in `templates/chatbot/base.html`, in the `.nav-menu` (`<ul class="nav-menu">`, ~line 35):
  - After the Hilfe `<li>` (~line 73), add a general item (visible to everyone), a button-style link that opens the modal:

```html
                <li class="nav-item">
                    <a href="#" class="nav-link" onclick="event.preventDefault(); openProblemModal(null);">
                        <i class="fas fa-exclamation-triangle"></i>
                        <span data-i18n="problem.report">Problem melden</span>
                    </a>
                </li>
```

  - Inside the existing `{% if current_user.is_authenticated and current_user.is_admin %}` block (where Debug lives, ~line 74), add the review link with a badge:

```html
                <li class="nav-item">
                    <a href="{{ url_for('chatbot.problem_reports_page') }}" class="nav-link {% if request.endpoint == 'chatbot.problem_reports_page' %}active{% endif %}">
                        <i class="fas fa-clipboard-list"></i>
                        <span data-i18n="problem.reports">Problem-Berichte</span>
                        <span id="problemReportBadge" class="nav-badge" style="display:none"></span>
                    </a>
                </li>
```

- [ ] **Step 2: Add the shared modal** — in `templates/chatbot/base.html`, just before the closing `</div>` of `.app-container` (after the drawer backdrop, ~line 155), add a native `<dialog>` reusing `edit-modal`:

```html
        <!-- Problem Report modal (shared; opened from nav + per-chat button) -->
        <dialog id="problemReportModal" class="edit-modal" aria-labelledby="problemReportTitle">
            <div class="modal-header">
                <h2 id="problemReportTitle" data-i18n="problem.report">Problem melden</h2>
                <button type="button" class="modal-close" onclick="document.getElementById('problemReportModal').close()">&times;</button>
            </div>
            <form method="dialog" id="problemReportForm">
                <div class="modal-body">
                    <input type="hidden" id="problemConversationId">
                    <label>
                        <span data-i18n="problem.categoryLabel">Kategorie</span>
                        <select id="problemCategory" required>
                            <option value="missing_message" data-i18n="problem.category.missing_message">Nachricht fehlt</option>
                            <option value="bug" data-i18n="problem.category.bug">Fehler</option>
                            <option value="idea" data-i18n="problem.category.idea">Idee</option>
                            <option value="other" data-i18n="problem.category.other">Sonstiges</option>
                        </select>
                    </label>
                    <label>
                        <span data-i18n="problem.messageLabel">Was ist passiert?</span>
                        <textarea id="problemMessage" rows="4" required
                                  data-i18n-placeholder="problem.placeholder"
                                  placeholder="Beschreibe kurz, was du bemerkt hast…"></textarea>
                    </label>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" onclick="document.getElementById('problemReportModal').close()" data-i18n="common.cancel">Abbrechen</button>
                    <button type="submit" class="btn btn-primary" data-i18n="problem.submit">Senden</button>
                </div>
            </form>
        </dialog>
```

  (If `.modal-close` isn't a known class, the `&times;` button still works via its `onclick`; the class is only cosmetic. Match whatever the other `edit-modal` dialogs use for their close button — check `knowledge.html`.)

- [ ] **Step 3: Add the modal JS + badge refresh** — in `templates/chatbot/base.html`, in the trailing `<script>` block (the one containing `refreshEmailReviewBadge` and `initNavDrawer`, ~line 258), append:

```javascript
    window.openProblemModal = function (conversationId) {
      var modal = document.getElementById('problemReportModal');
      if (!modal) return;
      document.getElementById('problemConversationId').value = conversationId || '';
      document.getElementById('problemMessage').value = '';
      modal.showModal();
    };

    (function initProblemReportForm() {
      var form = document.getElementById('problemReportForm');
      if (!form) return;
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        var convId = document.getElementById('problemConversationId').value;
        var payload = {
          message: document.getElementById('problemMessage').value,
          category: document.getElementById('problemCategory').value,
          page_url: window.location.pathname
        };
        if (convId) payload.conversation_id = parseInt(convId, 10);
        fetch('/chatbot/api/problem-reports', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payload)
        }).then(function (r) {
          if (!r.ok) throw new Error('failed');
          document.getElementById('problemReportModal').close();
          if (window.showNotification) {
            showNotification(i18n.t('problem.thanks'), 'success', 4000);
          } else {
            alert(i18n.t('problem.thanks'));
          }
        }).catch(function () {
          alert('Fehler / Error');
        });
      });
    })();

    (function refreshProblemReportBadge() {
      fetch('/chatbot/api/problem-reports/pending-count')
        .then(function (r) { return r.ok ? r.json() : {count: 0}; })
        .then(function (d) {
          var b = document.getElementById('problemReportBadge');
          if (!b) return;
          if (d.count > 0) { b.textContent = d.count; b.style.display = ''; }
          else { b.style.display = 'none'; }
        }).catch(function () {});
      setTimeout(refreshProblemReportBadge, 60000);
    })();
```

  Confirm `i18n.t(...)` is the correct accessor (check how `i18n` is used elsewhere in `base.html`/`app.js`); if the accessor differs, match it.

- [ ] **Step 4: Add i18n keys** — in `static/js/i18n.js`, add to BOTH the `de:` block (~line 7) and the `en:` block (~line 512), near the other `nav.*`/feature keys:

German (`de`):
```javascript
        'problem.report': 'Problem melden',
        'problem.reports': 'Problem-Berichte',
        'problem.categoryLabel': 'Kategorie',
        'problem.messageLabel': 'Was ist passiert?',
        'problem.placeholder': 'Beschreibe kurz, was du bemerkt hast…',
        'problem.submit': 'Senden',
        'problem.thanks': 'Danke, gemeldet!',
        'problem.empty': 'Keine Berichte.',
        'problem.category.missing_message': 'Nachricht fehlt',
        'problem.category.bug': 'Fehler',
        'problem.category.idea': 'Idee',
        'problem.category.other': 'Sonstiges',
```

English (`en`):
```javascript
        'problem.report': 'Report a problem',
        'problem.reports': 'Problem Reports',
        'problem.categoryLabel': 'Category',
        'problem.messageLabel': 'What happened?',
        'problem.placeholder': 'Briefly describe what you noticed…',
        'problem.submit': 'Send',
        'problem.thanks': 'Thanks, reported!',
        'problem.empty': 'No reports.',
        'problem.category.missing_message': 'Missing message',
        'problem.category.bug': 'Bug',
        'problem.category.idea': 'Idea',
        'problem.category.other': 'Other',
```

  If `common.cancel` doesn't exist, add `'common.cancel': 'Abbrechen'` / `'Cancel'` too (grep first).

- [ ] **Step 5: Bump the i18n cache version** — in `templates/chatbot/base.html`, change `js/i18n.js') }}?v=28` to `?v=29`.

- [ ] **Step 6: Verify (static + optional live)** — no unit test for this task (DOM/template). Static check: `openProblemModal`, `problemReportModal`, `problemReportForm`, `problemCategory`, `problemMessage`, `problemConversationId`, `problemReportBadge` ids all match between markup and JS; i18n keys present in both `de` and `en`. If the dev server is up, the user verifies: nav item opens modal → submit → "Danke, gemeldet!" toast → badge appears for admin.

- [ ] **Step 7: Commit**

```bash
git add templates/chatbot/base.html static/js/i18n.js
git commit -m "feat(problem-report): nav items, shared modal, submit + badge, i18n

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Per-chat entry point

**Files:**
- Modify: `templates/chatbot/conversation.html`

**Interfaces:**
- Consumes: `window.openProblemModal(conversationId)` (Task 4).

- [ ] **Step 1: Add the desktop header button** — in `templates/chatbot/conversation.html`, in the header actions row next to the sync button (~line 87, after the `recoverEmails`/`import-email-thread` buttons, before the guest-profile link):

```html
            <button class="btn btn-icon" onclick="openProblemModal({{ conversation.id }})" data-i18n-title="problem.report" title="Problem melden">
                <i class="fas fa-exclamation-triangle"></i>
            </button>
```

- [ ] **Step 2: Add the mobile overflow menu item** — in `templates/chatbot/conversation.html`, inside `.mobile-overflow-menu` (~line 129, alongside the other `.overflow-menu-item` buttons):

```html
            <button class="overflow-menu-item" onclick="document.getElementById('mobileOverflowMenu').classList.remove('open'); openProblemModal({{ conversation.id }});">
                <i class="fas fa-exclamation-triangle"></i>
                <span data-i18n="problem.report">Problem melden</span>
            </button>
```

- [ ] **Step 3: Verify (static + optional live)** — confirm `openProblemModal` is defined globally in `base.html` (Task 4) and `conversation.html` extends `base.html` so the modal is present. If the dev server is up, the user opens a conversation → clicks the ⚠ button → modal opens pre-filled with this `conversation_id` → submit → report links to `Chat #<id>` on the review page.

- [ ] **Step 4: Commit**

```bash
git add templates/chatbot/conversation.html
git commit -m "feat(problem-report): per-chat report button (header + mobile overflow)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage:** table/migration p20 (Task 1) · 4 categories (model + modal) · shared modal in base.html (Task 4) · 3 entry points — sidebar/drawer nav item + per-chat header + mobile overflow (Tasks 4–5; mobile global entry = the drawer nav item per the mobile-nav-drawer spec, NOT an account-panel button, which no longer exists) · admin review page + resolve toggle (Task 3) · badge cloned from email-review (Task 4) · 4 routes with correct guards (Tasks 2–3) · i18n keys de+en (Task 4) · the spec's one check — empty→400, valid→201+persisted, pending-count reflects open (Task 2 tests) plus resolve toggle (Task 3). All covered.
- **Placeholder scan:** none — every step has concrete code/commands. Three "confirm the accessor/endpoint/class name" notes are deliberate verification steps against existing code, not placeholders.
- **Type/id consistency:** DOM ids (`problemReportModal`, `problemReportForm`, `problemCategory`, `problemMessage`, `problemConversationId`, `problemReportBadge`), route paths (`/api/problem-reports`, `/api/problem-reports/<id>/resolve`, `/api/problem-reports/pending-count`, `/problem-reports`), endpoint name `chatbot.problem_reports_page`, and `ProblemReport.CATEGORIES` are used identically across tasks. `openProblemModal` defined in Task 4, consumed in Task 5.
