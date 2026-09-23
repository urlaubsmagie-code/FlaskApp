import pytest
from datetime import datetime
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, KnowledgeEntry, ReplyTemplate, AISettings


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def test_knowledge_entry_has_source_columns(app):
    e = KnowledgeEntry(category='faq', label='L', value='V',
                       source='notion', notion_page_id='pg1',
                       synced_at=datetime(2026, 6, 17, 12, 0))
    db.session.add(e); db.session.commit()
    got = KnowledgeEntry.query.filter_by(notion_page_id='pg1').first()
    assert got.source == 'notion'
    assert got.to_dict()['source'] == 'notion'


def test_reply_template_has_source_columns(app):
    t = ReplyTemplate(name='N', content='C', source='notion', notion_page_id='pg2')
    db.session.add(t); db.session.commit()
    got = ReplyTemplate.query.filter_by(notion_page_id='pg2').first()
    assert got.source == 'notion'
    assert got.to_dict()['source'] == 'notion'


from ChatBotAI.services.notion_client import NotionClient, blocks_to_text


def _txt(content):
    return {"type": "text", "text": {"content": content}, "plain_text": content}


def test_blocks_to_text_renders_heading_and_bullets():
    blocks = [
        {"type": "heading_2", "heading_2": {"rich_text": [_txt("Extrakosten")]}},
        {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [_txt("Sauna: 5€")]}},
        {"type": "paragraph", "paragraph": {"rich_text": [_txt("Handtücher inklusive")]}},
    ]
    out = blocks_to_text(blocks)
    assert "## Extrakosten" in out
    assert "- Sauna: 5€" in out
    assert "Handtücher inklusive" in out


class _FakeSDK:
    """Minimal stand-in for notion_client.Client."""
    def __init__(self, pages):
        self._pages = pages  # {id: {"title","parent_title","children":[ids],"blocks":[...]}}
        self.blocks = self._Blocks(self)
        self.pages = self._Pages(self)

    class _Blocks:
        def __init__(self, outer): self.children = self._Children(outer)
        class _Children:
            def __init__(self, outer): self.outer = outer
            def list(self, block_id, **kw):
                p = self.outer._pages[block_id]
                results = [{"id": c, "type": "child_page",
                            "child_page": {"title": self.outer._pages[c]["title"]}}
                           for c in p.get("children", [])]
                results += p.get("blocks", [])
                return {"results": results, "has_more": False, "next_cursor": None}

    class _Pages:
        def __init__(self, outer): self.outer = outer
        def retrieve(self, page_id, **kw):
            p = self.outer._pages[page_id]
            return {"id": page_id,
                    "properties": {"title": {"title": [_txt(p["title"])]}}}


def test_list_descendant_pages_recurses():
    sdk = _FakeSDK({
        "root": {"title": "HUB", "children": ["a", "b"], "blocks": []},
        "a": {"title": "A", "children": ["c"], "blocks": []},
        "b": {"title": "B", "children": [], "blocks": []},
        "c": {"title": "C", "children": [], "blocks": []},
    })
    client = NotionClient(token="x", sdk_client=sdk)
    ids = set(client.list_descendant_pages("root"))
    assert ids == {"a", "b", "c"}


def test_get_page_returns_fixture_shape():
    sdk = _FakeSDK({
        "root": {"title": "HUB", "children": ["a"], "blocks": []},
        "a": {"title": "Extrakosten", "children": [], "blocks": [
            {"type": "heading_2", "heading_2": {"rich_text": [_txt("Preise")]}},
        ]},
    })
    client = NotionClient(token="x", sdk_client=sdk)
    page = client.get_page("a")
    assert page["id"] == "a"
    assert page["title"] == "Extrakosten"
    assert "## Preise" in page["text"]


def test_get_page_resolves_parent_title_from_sdk():
    """Part B fix: get_page must resolve parent_title from the SDK when not provided."""
    sdk = _FakeSDK({
        "parent-page": {"title": "Vorlagen", "children": ["child-page"], "blocks": []},
        "child-page": {"title": "Begrüßung", "parent_title": "Vorlagen", "children": [], "blocks": []},
    })
    # Extend _FakeSDK.pages.retrieve to include parent info for child-page
    original_retrieve = sdk.pages.retrieve

    def retrieve_with_parent(page_id, **kw):
        result = original_retrieve(page_id, **kw)
        if page_id == "child-page":
            result["parent"] = {"type": "page_id", "page_id": "parent-page"}
        return result

    sdk.pages.retrieve = retrieve_with_parent

    client = NotionClient(token="x", sdk_client=sdk)
    page = client.get_page("child-page")
    assert page["parent_title"] == "Vorlagen"


# ---------------------------------------------------------------------------
# Orchestrator tests (Task 6)
# ---------------------------------------------------------------------------


class _FakeClient:
    """Returns a fixed page set; root listing returns all page ids."""
    def __init__(self, pages):
        self._pages = {p["id"]: p for p in pages}

    def list_descendant_pages(self, root_id):
        return list(self._pages.keys())

    def get_page(self, page_id, parent_title=None):
        p = self._pages[page_id]
        return {"id": p["id"], "title": p["title"],
                "parent_title": p["parent_title"], "text": p["text"]}


def _enable_notion():
    AISettings.set('notion_sync_enabled', 'true')
    AISettings.set('notion_integration_token', 'tok')
    AISettings.set('notion_root_page_id', 'root')


def _service_with(pages):
    from ChatBotAI.services.notion_service import NotionService
    return NotionService(client_factory=lambda token: _FakeClient(pages))


def test_sync_disabled_returns_zero(app):
    from ChatBotAI.tests.fixtures.notion_pages import EXTRAKOSTEN_PAGE
    svc = _service_with([EXTRAKOSTEN_PAGE])
    stats = svc.sync()
    assert stats['kb_upserted'] == 0
    assert KnowledgeEntry.query.count() == 0


def test_sync_imports_safe_page_and_blocks_sensitive(app):
    from ChatBotAI.tests.fixtures.notion_pages import (
        EXTRAKOSTEN_PAGE, SCHLUESSELCODES_PAGE,
    )
    _enable_notion()
    svc = _service_with([EXTRAKOSTEN_PAGE, SCHLUESSELCODES_PAGE])
    stats = svc.sync()
    assert stats['pages_blocked'] == 1
    assert 'Check-in Information und Schlüsselcodes' in stats['blocked_titles']
    # safe page produced entries, all source='notion'
    notion_rows = KnowledgeEntry.query.filter_by(source='notion').all()
    assert len(notion_rows) >= 2
    # no door code leaked into any value
    assert all('162981' not in r.value and '162333' not in r.value for r in notion_rows)


def test_sync_is_idempotent(app):
    from ChatBotAI.tests.fixtures.notion_pages import EXTRAKOSTEN_PAGE
    _enable_notion()
    svc = _service_with([EXTRAKOSTEN_PAGE])
    svc.sync()
    count_after_first = KnowledgeEntry.query.filter_by(source='notion').count()
    svc.sync()
    count_after_second = KnowledgeEntry.query.filter_by(source='notion').count()
    assert count_after_first == count_after_second


def test_sync_deletes_vanished_pages_but_keeps_manual(app):
    from ChatBotAI.tests.fixtures.notion_pages import EXTRAKOSTEN_PAGE
    _enable_notion()
    # a manual entry that sync must never touch
    manual = KnowledgeEntry(category='faq', label='ManualL', value='ManualV', source='manual')
    db.session.add(manual)
    db.session.commit()
    svc = _service_with([EXTRAKOSTEN_PAGE])
    svc.sync()
    assert KnowledgeEntry.query.filter_by(source='notion').count() >= 2
    # second sync with the page gone -> notion rows deleted, manual kept
    svc_empty = _service_with([])
    svc_empty.sync()
    assert KnowledgeEntry.query.filter_by(source='notion').count() == 0
    assert KnowledgeEntry.query.filter_by(source='manual').count() == 1


def test_sync_imports_vorlage_as_template(app):
    from ChatBotAI.tests.fixtures.notion_pages import VORLAGE_PAGE
    _enable_notion()
    svc = _service_with([VORLAGE_PAGE])
    stats = svc.sync()
    assert stats['templates_upserted'] == 1
    t = ReplyTemplate.query.filter_by(source='notion').first()
    assert t is not None and '{guest_name}' in t.content


# ---------------------------------------------------------------------------
# Route tests (Task 7)
# ---------------------------------------------------------------------------

import pytest as _pytest
from ChatBotAI.models import User


@_pytest.fixture
def client(app):
    user = User(username='admin', display_name='Admin', is_admin=True)
    user.set_password('pw')
    db.session.add(user); db.session.commit()
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True
    return c


def test_settings_put_then_get_hides_token(app, client):
    resp = client.put('/chatbot/api/settings/notion', json={
        'notion_sync_enabled': 'true',
        'notion_integration_token': 'secret-tok',
        'notion_root_page_id': 'root123',
    })
    assert resp.status_code == 200
    got = client.get('/chatbot/api/settings/notion').get_json()
    assert got['token_set'] is True
    assert 'secret-tok' not in str(got)  # token value never returned
    assert got['root_page_id'] == 'root123'


def test_sync_route_requires_enabled(app, client):
    resp = client.post('/chatbot/api/notion/sync')
    assert resp.status_code == 400
    assert 'error' in resp.get_json()


# --- Post-audit tuning: dash-insensitive exclude + explicit template pages ---

def test_force_exclude_is_dash_insensitive(app):
    # Page id is a dashed UUID (as the SDK returns); config lists it WITHOUT dashes.
    page = {"id": "363149d2-d08e-80f3-a3ef-f4af676e5c90", "title": "Pykobello",
            "parent_title": "HANDBUCH", "text": "admin@pykobello.test testadmin123"}
    _enable_notion()
    AISettings.set('notion_force_exclude_ids', '363149d2d08e80f3a3eff4af676e5c90')
    stats = _service_with([page]).sync()
    assert stats['pages_blocked'] == 1
    assert 'Pykobello' in stats['blocked_titles']
    assert KnowledgeEntry.query.filter_by(source='notion').count() == 0


def test_template_page_id_routes_to_reply_template(app):
    # A page whose parent is NOT "Vorlagen" still becomes a template when its id
    # is in notion_template_page_ids.
    page = {"id": "363149d2-d08e-8063-848b-c32fb1496ea9", "title": "Nachrichtenvorlagen",
            "parent_title": "HANDBUCH ZUR GÄSTEBETREUUNG",
            "text": "Hallo {guest_name}, ein Wanderpass kostet 5€."}
    _enable_notion()
    AISettings.set('notion_template_page_ids', '363149d2d08e8063848bc32fb1496ea9')
    stats = _service_with([page]).sync()
    assert stats['templates_upserted'] == 1
    assert KnowledgeEntry.query.filter_by(source='notion').count() == 0
    t = ReplyTemplate.query.filter_by(source='notion').first()
    assert t is not None and '{guest_name}' in t.content


def test_partial_fetch_failure_preserves_all_existing_knowledge_and_templates(app):
    from ChatBotAI.services.notion_service import NotionService
    from ChatBotAI.tests.fixtures.notion_pages import EXTRAKOSTEN_PAGE, VORLAGE_PAGE
    _enable_notion()
    _service_with([EXTRAKOSTEN_PAGE, VORLAGE_PAGE]).sync()
    before_kb = [(r.id, r.value) for r in KnowledgeEntry.query.order_by(KnowledgeEntry.id)]
    before_templates = [(r.id, r.content) for r in ReplyTemplate.query.order_by(ReplyTemplate.id)]
    class PartialFailure(_FakeClient):
        def get_page(self, page_id, parent_title=None):
            if page_id == VORLAGE_PAGE['id']:
                raise TimeoutError('temporary upstream failure')
            page = super().get_page(page_id, parent_title)
            page['text'] = 'Changed upstream content'
            return page
    svc = NotionService(client_factory=lambda token: PartialFailure([EXTRAKOSTEN_PAGE, VORLAGE_PAGE]))
    stats = svc.sync()
    assert stats['errors'] == 1
    assert stats['kb_deleted'] == stats['templates_deleted'] == 0
    assert stats['kb_upserted'] == stats['templates_upserted'] == 0
    assert [(r.id, r.value) for r in KnowledgeEntry.query.order_by(KnowledgeEntry.id)] == before_kb
    assert [(r.id, r.content) for r in ReplyTemplate.query.order_by(ReplyTemplate.id)] == before_templates


def test_configured_sync_route_has_initialized_service(app, client, monkeypatch):
    from ChatBotAI.services.notion_service import get_notion_service
    _enable_notion()
    service = get_notion_service()
    assert service is not None
    monkeypatch.setattr(service, '_client_factory', lambda token: _FakeClient([]))
    response = client.post('/chatbot/api/notion/sync')
    assert response.status_code == 200
    assert response.get_json()['stats']['errors'] == 0


def test_new_and_changed_notion_knowledge_needs_review(app):
    from ChatBotAI.tests.fixtures.notion_pages import EXTRAKOSTEN_PAGE
    _enable_notion()
    svc = _service_with([EXTRAKOSTEN_PAGE])
    svc.sync()
    row = KnowledgeEntry.query.filter_by(source='notion').first()
    assert row.is_internal is True
    row.is_internal = False
    db.session.commit()
    svc.sync()
    assert row.is_internal is False  # unchanged source preserves team classification
    entry = {'notion_page_id':row.notion_page_id, 'label':row.label,
             'value':row.value + '\nChanged upstream', 'category':row.category,
             'property_id':row.property_id}
    svc._upsert_kb(entry)
    db.session.commit()
    assert row.is_internal is True


def test_mapping_failure_rolls_back_partial_import(app, monkeypatch):
    from ChatBotAI.tests.fixtures.notion_pages import EXTRAKOSTEN_PAGE
    _enable_notion()
    svc = _service_with([EXTRAKOSTEN_PAGE])
    original = svc._upsert_kb
    def fail_after_write(entry):
        original(entry)
        db.session.flush()
        raise ValueError('failed after a partial write')
    monkeypatch.setattr(svc, '_upsert_kb', fail_after_write)
    stats = svc.sync()
    assert stats['errors'] == 1
    assert stats['kb_upserted'] == 0
    assert KnowledgeEntry.query.count() == 0


def test_sync_route_reports_upstream_failure_instead_of_success(app, client, monkeypatch):
    from ChatBotAI.services.notion_service import get_notion_service
    _enable_notion()
    class Unavailable(_FakeClient):
        def list_descendant_pages(self, root_id):
            raise TimeoutError('unavailable')
    monkeypatch.setattr(get_notion_service(), '_client_factory', lambda token: Unavailable([]))
    response = client.post('/chatbot/api/notion/sync')
    assert response.status_code == 502
    assert response.get_json()['success'] is False
