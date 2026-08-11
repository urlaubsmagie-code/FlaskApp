"""The p23 seed must carry over every keyword the hardcoded list used to match.

MessageRouter._URGENT_KEYWORDS is deleted in a later task, so this file keeps a
frozen copy of it as of 2026-08-11. If a word is missing from the seed, a guest
message that escalated yesterday would stop escalating after the migration.
"""

import importlib.util
from pathlib import Path

MIGRATION = (Path(__file__).resolve().parents[1]
             / 'migrations' / 'versions' / 'p23_knowledge_trigger_words.py')

# Frozen copy of MessageRouter._URGENT_KEYWORDS as of 2026-08-11.
LEGACY_KEYWORDS = (
    'notfall', 'notarzt', 'feuer', 'brennt', 'polizei', 'rettungsdienst',
    'einbruch', 'unfall', 'verletzt', 'gasgeruch',
    'wasserschaden', 'überschwemmt', 'überflutet', 'rohrbruch', 'schimmel',
    'kein warmwasser', 'kein wasser', 'kein strom', 'stromausfall',
    'heizung defekt', 'heizung geht nicht', 'heizung kaputt', 'kaputt',
    'funktioniert nicht', 'defekt',
    'ausgesperrt', 'eingesperrt', 'komme nicht rein', 'schlüssel verloren',
    'code funktioniert nicht', 'türe geht nicht', 'tür geht nicht',
    'anwalt', 'rechtsanwalt', 'beschwerde', 'beschweren', 'rückerstattung',
    'geld zurück', 'stornieren', 'storno', 'abbrechen',
    'lärm', 'laut', 'polizei gerufen', 'dreckig', 'schmutzig', 'ungeziefer',
    'bettwanzen', 'kakerlaken',
    'emergency', 'urgent', 'asap', 'fire', 'police', 'ambulance', 'injured',
    'flood', 'flooded', 'water damage', 'leak', 'mold', 'no hot water',
    'no water', 'no power', 'no electricity', 'heating not working',
    'broken', 'not working', 'locked out', 'lost the key', 'lost my key',
    'code does not work', "code doesn't work",
    'lawyer', 'complaint', 'refund', 'money back', 'cancel my booking',
    'bed bugs', 'cockroach', 'filthy', 'dirty',
)


def _seed_topics():
    spec = importlib.util.spec_from_file_location('p23_seed', MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.SEED_TOPICS


def test_seed_has_nine_topics():
    assert len(_seed_topics()) == 9


def test_every_topic_has_a_category_label_and_words():
    for category, label, words in _seed_topics():
        assert category.startswith('esc'), category
        assert label.strip(), category
        assert [w.strip() for w in words.split(',') if w.strip()], label


def test_no_legacy_keyword_is_lost():
    seeded = set()
    for _category, _label, words in _seed_topics():
        seeded.update(w.strip().lower() for w in words.split(',') if w.strip())
    assert set(LEGACY_KEYWORDS) - seeded == set()


def test_no_keyword_is_seeded_twice():
    seen, duplicates = set(), set()
    for _category, _label, words in _seed_topics():
        for word in (w.strip().lower() for w in words.split(',') if w.strip()):
            if word in seen:
                duplicates.add(word)
            seen.add(word)
    assert duplicates == set()
