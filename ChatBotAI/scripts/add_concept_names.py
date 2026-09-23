"""One-off: add `concept_name` to apartment_config.json from the Notion table.

Keyed on UPPERCASE code. Idempotent. Run from anywhere:
    python -m ChatBotAI.scripts.add_concept_names
Prints which codes were set and which config apartments had no mapping.
"""
import json
import os

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "apartment_config.json",
)

# UPPERCASE code -> concept name (Notion "Neuer Name" table, 2026-07-01).
# NOTE: config code "fO" uppercases to "FO"; it is the F0 unit -> Felsenfreund.
CONCEPT_BY_CODE = {
    "F0": "Felsenfreund", "FO": "Felsenfreund",
    "F1": "Felsenpfad", "F1F": "Felsenpfad",
    "F1B": "Fledermaus", "F2": "Forellensprung", "F3": "Frischluft", "F4": "Farngrün",
    "UT": "Moosgrund", "FAMZI": "Morgenlicht", "ZI1": "Malerblick", "ZI2": "Mühlrad",
    "UO0": "Unterholz", "UO1": "Uferhang", "UO3": "Uhunest",
    "HW1": "Höhenzug", "HW2": "Honigfels", "HW3": "Haselmaus", "HW1B": "Hirschkäfer",
    "HW2B": "Himmelblau", "HW3B": "Heidelbeere", "HW4B": "Hochgefühl", "HW13": "Himmelsleiter",
    "GK2": "Gipfelpfad", "GK3": "Glühwürmchen", "BA2": "Bachrauschen",
    "W2": "Wasseramsel", "W3": "Wanderfalke", "W4": "Wildblume", "W5": "Waldweg", "W6": "Wiesengrün",
    "L4": "Lichtung", "L5": "Libelle", "L6": "Luchs", "L7": "Lerchenlied", "L8": "Lichtblick", "L9": "Laubfrosch",
    "H1": "Tagpfauenauge", "H2": "Tautropfen", "H4": "Tagtraum", "H5": "Talruhe", "H6": "Turmfalke",
    "S1": "Sandsteinidyll", "S2": "Sonnenfels", "S3": "Steinpfad",
    "B1": "Blattwerk", "B2": "Blütenmeer", "B3": "Buntspecht", "B5": "Brombeere",
    "B6": "Butterblume", "B7": "Biberburg", "B8": "Bergsteigersuite",
    "R1": "Rotmilan", "R2": "Ruheort", "R3": "Rothirsch",
}


def main():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    set_codes, unmapped = [], []
    for entry in config.get("apartments", {}).values():
        code = (entry.get("code") or "").strip().upper()
        if code in CONCEPT_BY_CODE:
            entry["concept_name"] = CONCEPT_BY_CODE[code]
            set_codes.append(code)
        else:
            unmapped.append(entry.get("code"))

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)
        f.write("\n")

    print(f"Set concept_name on {len(set_codes)} apartments: {sorted(set_codes)}")
    print(f"No mapping for {len(unmapped)} config apartments: {sorted(c for c in unmapped if c)}")


if __name__ == "__main__":
    main()
