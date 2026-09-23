"""Notion page → KnowledgeEntry / ReplyTemplate mapping. Pure functions.
See docs/superpowers/specs/2026-06-17-notion-knowledge-sync-design.md §5.
"""
import re

_TEMPLATE_PARENTS = ('vorlagen', 'vorlage', 'templates', 'template', 'nachrichtenvorlagen')

_CATEGORY_RULES = [
    ('checkin_checkout', ('check-in', 'check in', 'checkin', 'check-out', 'schlüssel', 'anreise')),
    ('house_rules', ('regel', 'rules', 'hausordnung')),
    ('emergency', ('notfall', 'emergency', 'feuer', 'arzt')),
    ('nearby', ('umgebung', 'restaurant', 'sehenswürdig', 'ausflug')),
]


def infer_category(title, text):
    hay = f"{title}\n{text}".lower()
    for category, needles in _CATEGORY_RULES:
        if any(n in hay for n in needles):
            return category
    return 'faq'


def split_sections(text):
    """Split markdown text on ## / ### headings into (label, body) pairs.
    Content before the first heading is returned with label ''."""
    sections = []
    current_label = ''
    current_body = []
    for line in (text or '').splitlines():
        m = re.match(r'\s*#{2,3}\s+(.*?):?\s*$', line)
        if m:
            if current_body:
                sections.append((current_label, '\n'.join(current_body).strip()))
                current_body = []
            current_label = m.group(1).strip()
        else:
            current_body.append(line)
    if current_body:
        sections.append((current_label, '\n'.join(current_body).strip()))
    return [(lbl, body) for (lbl, body) in sections if body]


def _match_property_id(title, property_names):
    """property_names: {lowercased_property_name: property_id}."""
    t = (title or '').lower()
    for name, pid in property_names.items():
        if name and name in t:
            return pid
    return None


def page_to_kb_entries(page, property_names):
    pid = _match_property_id(page.get('title'), property_names or {})
    category = infer_category(page.get('title', ''), page.get('text', ''))
    sections = split_sections(page.get('text', ''))
    if not sections:
        sections = [(page.get('title', '').strip() or 'Info', (page.get('text') or '').strip())]
    entries = []
    for label, body in sections:
        entries.append({
            'label': (label or page.get('title') or 'Info')[:200],
            'value': body,
            'category': category,
            'property_id': pid,
            'notion_page_id': page.get('id'),
        })
    return entries


def is_template_page(page):
    return (page.get('parent_title') or '').strip().lower() in _TEMPLATE_PARENTS


def page_to_templates(page):
    """Split a template page into one ReplyTemplate per heading section, so a
    page holding several templates (e.g. '### Wanderpass', '## Kurtaxe
    Beschwerde') does not collapse into one merged entry. A page with no
    headings yields a single template named after the page. Content before the
    first heading becomes its own template named after the page."""
    title = (page.get('title') or 'Vorlage').strip()
    sections = split_sections(page.get('text', ''))
    if not sections:
        sections = [('', (page.get('text') or '').strip())]
    out = []
    for label, body in sections:
        body = (body or '').strip()
        if not body:
            continue
        out.append({
            'name': (label or title or 'Vorlage')[:200],
            'content': body,
            'category': 'general',
            'notion_page_id': page.get('id'),
        })
    return out
