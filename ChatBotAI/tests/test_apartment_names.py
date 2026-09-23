from ChatBotAI.services.apartment_names import (
    build_lookups, codes_in_text,
)

FIXTURE = {
    "apartments": {
        "111": {"code": "B7", "name": "B7 - Ferienwohnung", "concept_name": "Biberburg"},
        "222": {"code": "F1", "name": "F1 - Ferienwohnung", "concept_name": "Felsenpfad"},
        "333": {"code": "F1F", "name": "F1F - Ferienwohnung", "concept_name": "Felsenpfad"},
        "444": {"code": "L4", "name": "L4 - Ferienwohnung", "concept_name": "Lichtung"},
        "555": {"code": "L8", "name": "L8 - Ferienwohnung", "concept_name": "Lichtblick"},
        "666": {"code": "L1", "name": "L1 - Ferienwohnung"},  # no concept_name
    },
    "default_apartment": {"code": "UNK", "name": "Unbekannt"},
}


def test_build_lookups_maps_concept_to_uppercase_codes():
    concept_to_codes, smoobu_id_to_code = build_lookups(FIXTURE)
    assert concept_to_codes["biberburg"] == {"B7"}
    assert smoobu_id_to_code["111"] == "B7"


def test_build_lookups_one_name_two_codes():
    concept_to_codes, _ = build_lookups(FIXTURE)
    assert concept_to_codes["felsenpfad"] == {"F1", "F1F"}


def test_build_lookups_skips_apartments_without_concept_name():
    concept_to_codes, smoobu_id_to_code = build_lookups(FIXTURE)
    assert "L1" not in {c for codes in concept_to_codes.values() for c in codes}
    assert smoobu_id_to_code["666"] == "L1"  # still resolvable by id


def test_codes_in_text_detects_concept_from_unterkunftsname():
    concept_to_codes, _ = build_lookups(FIXTURE)
    text = "Urlaubsmagie - Ferienwohnung Biberburg - mit Balkon"
    assert codes_in_text(text, concept_to_codes) == {"B7"}


def test_codes_in_text_distinguishes_similar_names():
    # "Lichtung" (L4) must not match "Lichtblick" (L8) and vice versa.
    concept_to_codes, _ = build_lookups(FIXTURE)
    assert codes_in_text("... Ferienwohnung Lichtung ...", concept_to_codes) == {"L4"}
    assert codes_in_text("... Ferienwohnung Lichtblick ...", concept_to_codes) == {"L8"}


def test_codes_in_text_no_partial_word_match():
    # "Licht" alone is not a concept name → no match.
    concept_to_codes, _ = build_lookups(FIXTURE)
    assert codes_in_text("nur Licht hier", concept_to_codes) == set()


def test_codes_in_text_empty_or_none():
    concept_to_codes, _ = build_lookups(FIXTURE)
    assert codes_in_text("", concept_to_codes) == set()
    assert codes_in_text(None, concept_to_codes) == set()


def test_code_from_smoobu_id_delegates_to_cache(monkeypatch):
    import ChatBotAI.services.apartment_names as an
    an.reset_lookups()
    monkeypatch.setattr(an, "_lookups", ({"biberburg": {"B7"}}, {"111": "B7"}))
    assert an.code_from_smoobu_id("111") == "B7"
    assert an.code_from_smoobu_id("missing") is None
    an.reset_lookups()


def test_codes_from_property_text_delegates_to_cache(monkeypatch):
    import ChatBotAI.services.apartment_names as an
    an.reset_lookups()
    monkeypatch.setattr(an, "_lookups", ({"biberburg": {"B7"}}, {"111": "B7"}))
    assert an.codes_from_property_text("Ferienwohnung Biberburg mit Balkon") == {"B7"}
    an.reset_lookups()


from ChatBotAI.services.apartment_names import (
    codes_from_property_text, code_from_smoobu_id,
)


def test_real_config_resolves_biberburg_to_b7():
    # Verified against a live Booking Unterkunftsname string.
    assert "B7" in codes_from_property_text(
        "Urlaubsmagie - Ferienwohnung Biberburg - mit Balkon"
    )


def test_real_config_resolves_lichtung_to_l4():
    assert "L4" in codes_from_property_text("... Ferienwohnung Lichtung ...")


def test_real_config_smoobu_id_resolves_to_code():
    # 1234047782495519188 is B7 in apartment_config.json.
    assert code_from_smoobu_id("1234047782495519188") == "B7"
    assert code_from_smoobu_id("does-not-exist") is None
    assert code_from_smoobu_id(None) is None
