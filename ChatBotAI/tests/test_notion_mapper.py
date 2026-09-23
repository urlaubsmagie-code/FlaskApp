from ChatBotAI.services.notion_mapper import (
    infer_category, split_sections, page_to_kb_entries,
    page_to_templates, is_template_page,
)
from ChatBotAI.tests.fixtures.notion_pages import (
    EXTRAKOSTEN_PAGE, PROPERTY_PAGE, VORLAGE_PAGE,
)


def test_infer_category_checkin():
    assert infer_category("Check-in Information", "...") == "checkin_checkout"


def test_infer_category_defaults_faq():
    assert infer_category("Random topic", "body") == "faq"


def test_split_sections_on_headings():
    text = "## A\nline a\n### B\nline b\n"
    assert split_sections(text) == [("A", "line a"), ("B", "line b")]


def test_extrakosten_maps_to_multiple_entries():
    entries = page_to_kb_entries(EXTRAKOSTEN_PAGE, property_names={})
    labels = [e["label"] for e in entries]
    assert "Extrakosten Allgemein" in labels
    assert "Check-in & Check-Out" in labels
    # all global (no property match)
    assert all(e["property_id"] is None for e in entries)
    assert all(e["notion_page_id"] == EXTRAKOSTEN_PAGE["id"] for e in entries)


def test_property_page_sets_property_id():
    entries = page_to_kb_entries(PROPERTY_PAGE, property_names={"sonnenhof": 42})
    assert entries
    assert all(e["property_id"] == 42 for e in entries)


def test_is_template_page_true_for_vorlagen_parent():
    assert is_template_page(VORLAGE_PAGE) is True


def test_page_to_templates_no_headings_single_template():
    ts = page_to_templates(VORLAGE_PAGE)
    assert len(ts) == 1
    assert ts[0]["name"] == "Begrüßung"
    assert "{guest_name}" in ts[0]["content"]
    assert ts[0]["notion_page_id"] == VORLAGE_PAGE["id"]


def test_page_to_templates_splits_multiple_templates_by_heading():
    page = {
        "id": "p1", "title": "Nachrichtenvorlagen", "parent_title": "Vorlagen",
        "text": ("Drucker RD: x@print.com\n"
                 "### Wanderpass\nHallo, ein Wanderpass kostet 5€.\n"
                 "## Kurtaxe Beschwerde\nVielen Dank für deine Nachricht.\n"),
    }
    ts = page_to_templates(page)
    names = [t["name"] for t in ts]
    assert "Wanderpass" in names
    assert "Kurtaxe Beschwerde" in names
    # the pre-heading printer line becomes its own (page-named) template
    assert "Nachrichtenvorlagen" in names
    wander = next(t for t in ts if t["name"] == "Wanderpass")
    assert "5€" in wander["content"]
    assert "Kurtaxe" not in wander["content"]  # not merged with the next section
