"""Real Notion page content captured 2026-06-17 for offline testing.
Text is the plain-text rendering NotionClient.get_page() produces.
"""

EXTRAKOSTEN_PAGE = {
    "id": "363149d2-d08e-809a-8997-e5d5aee523c7",
    "title": "Extrakosten",
    "parent_title": "HANDBUCH ZUR GÄSTEBETREUUNG",
    "text": (
        "## Extrakosten Allgemein:\n"
        "- Haustier: 10€ pro Nacht/pro Haustier (ab der 8. Nacht nur 8€ pro Haustier)\n"
        "- Sauna: 5€ pro Tag pro Person\n"
        "- Kinderbetten: 10€ pro Aufenthalt (immer vorher prüfen, ob verfügbar)\n"
        "### Check-in & Check-Out:\n"
        "- regulär: 10 Uhr Check-out, 16 Uhr Check-in\n"
        "- Early Check In: ab 12:30 Uhr: 10€ Winter (01.11 - 31.03), 20€ Sommer (01.04 - 31.10)\n"
        "- Late Checkout: bis 12Uhr: 10€ Winter, 20€ Sommer\n"
        "Sonstiges: Handtücher und Bettwäsche sind kostenlos im Preis mit inbegriffen\n"
    ),
}

# MUST be blocked: title keyword + "Schlüsselbox Codes" heading + dense codes.
SCHLUESSELCODES_PAGE = {
    "id": "363149d2-d08e-8045-9c58-eb82a106ef53",
    "title": "Check-in Information und Schlüsselcodes",
    "parent_title": "HANDBUCH ZUR GÄSTEBETREUUNG",
    "text": (
        "Schlüsselbox Codes:\n"
        "B1 - Code 162981\n"
        "B5 - Haustür: 162333 - C 9875 Pfeil\n"
        "W2 - 162392\n"
        "UT - 1623\n"
        "F0 - 9850\n"
    ),
}

# A per-property page (mapper should set property_id by matching "Sonnenhof").
PROPERTY_PAGE = {
    "id": "37b149d2-d08e-80ac-bc06-d46a470863a7",
    "title": "Sonnenhof",
    "parent_title": "HANDBUCH ZUR GÄSTEBETREUUNG",
    "text": (
        "## Early Check-in\n"
        "Ein früher Check-in ist je nach Verfügbarkeit und nach vorheriger "
        "Absprache bereits ab 13:00 Uhr möglich.\n"
    ),
}

# A template page under a "Vorlagen" parent.
VORLAGE_PAGE = {
    "id": "aaaa1111-0000-0000-0000-000000000001",
    "title": "Begrüßung",
    "parent_title": "Vorlagen",
    "text": "Hallo {guest_name}, willkommen in {property_name}! Schön, dass du da bist.\n",
}
