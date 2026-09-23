from ChatBotAI.services.notion_scrubber import (
    parse_csv_setting, DEFAULT_BLOCK_KEYWORDS, is_blocked_page, scrub_value,
)
from ChatBotAI.tests.fixtures.notion_pages import (
    EXTRAKOSTEN_PAGE, SCHLUESSELCODES_PAGE,
)


def test_parse_csv_setting_splits_and_lowercases():
    assert parse_csv_setting("Code, Passwör ,INTERN", []) == ["code", "passwör", "intern"]


def test_parse_csv_setting_falls_back_to_default():
    assert parse_csv_setting(None, ["x"]) == ["x"]
    assert parse_csv_setting("   ", ["x"]) == ["x"]


def test_schluesselcodes_page_is_blocked():
    p = SCHLUESSELCODES_PAGE
    assert is_blocked_page(p["title"], p["text"], DEFAULT_BLOCK_KEYWORDS) is True


def test_extrakosten_page_is_not_blocked():
    p = EXTRAKOSTEN_PAGE
    assert is_blocked_page(p["title"], p["text"], DEFAULT_BLOCK_KEYWORDS) is False


def test_block_by_keyword_in_title():
    assert is_blocked_page("Passwörter", "harmless body", DEFAULT_BLOCK_KEYWORDS) is True


def test_block_by_code_density_even_without_keyword():
    # No blocklist word, but three code-shaped tokens near labels.
    text = "Tür A Code 1111\nTür B Code 2222\nTür C Code 3333"
    assert is_blocked_page("Zugang", text, []) is True


def test_scrub_value_redacts_door_code():
    assert "162333" not in scrub_value("Haustür: 162333 dann hoch")


def test_scrub_value_keeps_normal_prices():
    # Prices like 10€ / times like 16 Uhr must survive — not code-shaped.
    v = "Early Check In ab 12:30 Uhr: 10€ Winter"
    assert scrub_value(v) == v


# --- Layer-2 gap fix: bare apartment-label codes (B5 - 162333, W2 - 162392) ---

def test_scrub_value_redacts_bare_apartment_code():
    assert "162333" not in scrub_value("B5 - 162333")
    assert "162392" not in scrub_value("W2 - 162392")
    assert "1623" not in scrub_value("UT - 1623")
    assert "7913" not in scrub_value("HW13 - 7913")


def test_scrub_value_keeps_prices_and_dates_with_dashes():
    # Must NOT redact guest-safe content that has letters/dashes/numbers.
    assert scrub_value("Erwachsener (ab 16 J.) - 2,50 €") == "Erwachsener (ab 16 J.) - 2,50 €"
    assert scrub_value("Winter (01.11 - 31.03)") == "Winter (01.11 - 31.03)"
    assert scrub_value("regulär: 10 Uhr Check-out, 16 Uhr Check-in") == "regulär: 10 Uhr Check-out, 16 Uhr Check-in"


def test_block_page_of_bare_apartment_codes_without_keyword():
    # No block keyword present, but >=3 apartment-label codes -> blocked by density.
    text = "B5 - 162333\nW2 - 162392\nUT - 1623\nF0 - 9850"
    assert is_blocked_page("Zugang", text, []) is True


def test_extrakosten_still_not_blocked_after_apt_code_rule():
    p = EXTRAKOSTEN_PAGE
    assert is_blocked_page(p["title"], p["text"], DEFAULT_BLOCK_KEYWORDS) is False
