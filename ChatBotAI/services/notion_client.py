"""Thin adapter over the official notion-client SDK. The ONLY Notion-sync file
that performs network I/O. Read-only: lists pages and renders block trees.
"""
import logging

logger = logging.getLogger(__name__)


def _rich_text(items):
    return ''.join(i.get('plain_text') or i.get('text', {}).get('content', '') for i in (items or []))


def blocks_to_text(blocks):
    """Render a flat Notion block list to plain markdown-ish text."""
    lines = []
    for b in blocks or []:
        t = b.get('type')
        data = b.get(t, {}) if t else {}
        rt = _rich_text(data.get('rich_text'))
        if t in ('heading_1',):
            lines.append(f"# {rt}")
        elif t in ('heading_2',):
            lines.append(f"## {rt}")
        elif t in ('heading_3',):
            lines.append(f"### {rt}")
        elif t in ('bulleted_list_item', 'numbered_list_item'):
            lines.append(f"- {rt}")
        elif t == 'paragraph':
            if rt:
                lines.append(rt)
        # child_page / images / unsupported blocks contribute no text
    return '\n'.join(lines)


class NotionClient:
    def __init__(self, token, sdk_client=None):
        if sdk_client is not None:
            self._sdk = sdk_client
        else:
            from notion_client import Client
            self._sdk = Client(auth=token)

    def _children(self, block_id):
        results, cursor = [], None
        while True:
            resp = self._sdk.blocks.children.list(block_id=block_id, start_cursor=cursor) \
                if cursor else self._sdk.blocks.children.list(block_id=block_id)
            results.extend(resp.get('results', []))
            if not resp.get('has_more'):
                break
            cursor = resp.get('next_cursor')
        return results

    def list_descendant_pages(self, root_id):
        """DFS over child_page blocks under root_id. Returns deduped page ids
        (excluding the root itself)."""
        seen, out, stack = set(), [], [root_id]
        while stack:
            current = stack.pop()
            for child in self._children(current):
                if child.get('type') == 'child_page':
                    cid = child['id']
                    if cid not in seen:
                        seen.add(cid)
                        out.append(cid)
                        stack.append(cid)
        return out

    def _page_title(self, page_id):
        page = self._sdk.pages.retrieve(page_id=page_id)
        props = page.get('properties', {})
        title_prop = props.get('title') or next(
            (v for v in props.values() if v.get('type') == 'title'), None)
        if title_prop:
            return _rich_text(title_prop.get('title'))
        return ''

    def get_page(self, page_id, parent_title=None):
        blocks = self._children(page_id)
        resolved_parent_title = parent_title
        if resolved_parent_title is None:
            try:
                page_data = self._sdk.pages.retrieve(page_id=page_id)
                parent = page_data.get('parent', {})
                if parent.get('type') == 'page_id':
                    resolved_parent_title = self._page_title(parent['page_id'])
            except Exception:
                logger.debug("notion-client: could not resolve parent_title for %s", page_id)
        return {
            'id': page_id,
            'title': self._page_title(page_id),
            'parent_title': resolved_parent_title,
            'text': blocks_to_text(blocks),
        }
