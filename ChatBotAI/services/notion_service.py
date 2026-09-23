"""Notion → KnowledgeEntry/ReplyTemplate sync orchestrator.

Wires the read-only NotionClient through the safety scrubber and mapper, then
idempotently upserts results. Touches ONLY source='notion' rows.
See docs/superpowers/specs/2026-06-17-notion-knowledge-sync-design.md.
"""
import logging
from datetime import datetime
from typing import Optional

from ..models import db, KnowledgeEntry, ReplyTemplate, Property, AISettings
from . import notion_scrubber as scrub
from . import notion_mapper as mapper
from .notion_client import NotionClient

logger = logging.getLogger(__name__)


def _as_bool(val, default=False):
    if val is None:
        return default
    return str(val).strip().lower() in ('1', 'true', 'yes', 'on')


def _norm_id(page_id):
    """Normalize a Notion page id for comparison: strip dashes, lowercase.
    The SDK returns dashed UUIDs; config lists may be pasted either way."""
    return (page_id or '').replace('-', '').strip().lower()


def get_notion_config():
    return {
        'enabled': _as_bool(AISettings.get('notion_sync_enabled', 'false'), False),
        'token': AISettings.get('notion_integration_token', '') or '',
        'root_page_id': AISettings.get('notion_root_page_id', '') or '',
        'block_keywords': scrub.parse_csv_setting(
            AISettings.get('notion_block_keywords'), scrub.DEFAULT_BLOCK_KEYWORDS),
        # ID lists are normalized (dash-insensitive) so config matches the SDK's
        # dashed UUIDs regardless of how the operator pasted them.
        'force_exclude_ids': {_norm_id(i) for i in scrub.parse_csv_setting(AISettings.get('notion_force_exclude_ids'), [])},
        'force_include_ids': {_norm_id(i) for i in scrub.parse_csv_setting(AISettings.get('notion_force_include_ids'), [])},
        'template_page_ids': {_norm_id(i) for i in scrub.parse_csv_setting(AISettings.get('notion_template_page_ids'), [])},
    }


class NotionService:
    def __init__(self, client_factory=None):
        # client_factory(token) -> NotionClient. Default builds a real one.
        self._client_factory = client_factory or (lambda token: NotionClient(token=token))

    def _property_names(self):
        return {p.name.lower(): p.id for p in Property.query.all() if p.name}

    def sync(self):
        stats = {'pages_scanned': 0, 'pages_blocked': 0, 'kb_upserted': 0,
                 'kb_deleted': 0, 'templates_upserted': 0, 'templates_deleted': 0,
                 'values_scrubbed': 0, 'errors': 0, 'blocked_titles': []}
        cfg = get_notion_config()
        if not cfg['enabled'] or not cfg['token'] or not cfg['root_page_id']:
            return stats

        prop_names = self._property_names()

        seen_kb_keys = set()       # (notion_page_id, label)
        seen_tpl_keys = set()      # (notion_page_id, name)

        try:
            client = self._client_factory(cfg['token'])
            page_ids = client.list_descendant_pages(cfg['root_page_id'])
        except Exception:
            logger.exception("notion-sync: failed to list pages")
            stats['errors'] += 1
            return stats

        # Fetch the complete source before changing local rows. Missing pages
        # after a transient failure must not be mistaken for deleted knowledge.
        pages = []
        for page_id in page_ids:
            try:
                page = client.get_page(page_id)
                pages.append((page_id, page))
            except Exception:
                logger.exception("notion-sync: failed to fetch %s", page_id)
                stats['errors'] += 1
                continue

        if stats['errors']:
            return stats

        # Import and deletion form one transaction: any mapping/DB failure
        # rolls back the whole attempt rather than leaving a partial import.
        try:
            for page_id, page in pages:
                stats['pages_scanned'] += 1
                title, text = page.get('title', ''), page.get('text', '')
                nid = _norm_id(page_id)

                if nid in cfg['force_exclude_ids']:
                    stats['pages_blocked'] += 1
                    stats['blocked_titles'].append(title)
                    continue

                if nid not in cfg['force_include_ids'] and \
                        scrub.is_blocked_page(title, text, cfg['block_keywords']):
                    stats['pages_blocked'] += 1
                    stats['blocked_titles'].append(title)
                    continue

                # A page is a template if explicitly listed OR under a Vorlagen parent.
                # One page may hold several templates (split by heading section).
                if nid in cfg['template_page_ids'] or mapper.is_template_page(page):
                    for tpl in mapper.page_to_templates(page):
                        tpl['content'] = scrub.scrub_value(tpl['content'])
                        if not tpl['content'].strip():
                            continue
                        self._upsert_template(tpl)
                        seen_tpl_keys.add((page_id, tpl['name']))
                        stats['templates_upserted'] += 1
                    continue

                for entry in mapper.page_to_kb_entries(page, prop_names):
                    cleaned = scrub.scrub_value(entry['value'])
                    if cleaned != entry['value']:
                        stats['values_scrubbed'] += 1
                    if not cleaned.strip():
                        continue
                    entry['value'] = cleaned
                    self._upsert_kb(entry)
                    seen_kb_keys.add((page_id, entry['label']))
                    stats['kb_upserted'] += 1

            stats['kb_deleted'] = self._delete_stale_kb(seen_kb_keys)
            stats['templates_deleted'] = self._delete_stale_templates(seen_tpl_keys)
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("notion-sync: import failed; rolled back")
            for key in ('kb_upserted', 'kb_deleted', 'templates_upserted', 'templates_deleted'):
                stats[key] = 0
            stats['errors'] += 1
            return stats
        logger.info("notion-sync: %s", {k: v for k, v in stats.items() if k != 'blocked_titles'})
        return stats

    def _upsert_kb(self, entry):
        row = KnowledgeEntry.query.filter_by(
            source='notion', notion_page_id=entry['notion_page_id'],
            label=entry['label']).first()
        if row is None:
            row = KnowledgeEntry(source='notion', notion_page_id=entry['notion_page_id'],
                                 label=entry['label'], is_internal=True)
            db.session.add(row)
        elif (row.value, row.category, row.property_id) != (entry['value'], entry['category'], entry['property_id']):
            # Changed/new Notion text needs human classification before it is
            # allowed into guest replies. Unchanged syncs preserve that choice.
            row.is_internal = True
        row.category = entry['category']
        row.value = entry['value']
        row.property_id = entry['property_id']
        row.synced_at = datetime.utcnow()

    def _upsert_template(self, tpl):
        # Keyed on (page_id, name) so several templates from one page coexist.
        row = ReplyTemplate.query.filter_by(
            source='notion', notion_page_id=tpl['notion_page_id'],
            name=tpl['name']).first()
        if row is None:
            row = ReplyTemplate(source='notion', notion_page_id=tpl['notion_page_id'],
                                name=tpl['name'])
            db.session.add(row)
        row.content = tpl['content']
        row.category = tpl['category']

    def _delete_stale_kb(self, seen_keys):
        deleted = 0
        for row in KnowledgeEntry.query.filter_by(source='notion').all():
            if (row.notion_page_id, row.label) not in seen_keys:
                db.session.delete(row)
                deleted += 1
        return deleted

    def _delete_stale_templates(self, seen_keys):
        deleted = 0
        for row in ReplyTemplate.query.filter_by(source='notion').all():
            if (row.notion_page_id, row.name) not in seen_keys:
                db.session.delete(row)
                deleted += 1
        return deleted


_notion_service: Optional[NotionService] = None


def init_notion_service(app):
    global _notion_service
    _notion_service = NotionService()
    logger.info("Notion Service initialized")
    return _notion_service


def get_notion_service():
    return _notion_service
