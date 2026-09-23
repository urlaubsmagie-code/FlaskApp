# Handbuch zur Gästebetreuung — Content Classification (audit 2026-06-17)

Read-only audit of every page under **HANDBUCH ZUR GÄSTEBETREUUNG**, classifying each into:
- **UMI** — guest-safe; feed UMI's knowledge base (incl. guest-facing secrets: guest WiFi password, where/how guests pay).
- **VORLAGEN** — team message templates; load into the ReplyTemplate DB, NOT UMI.
- **FORBIDDEN** — must never reach UMI **or** the public website (account passwords, door/key codes, spare-key locations, internal tools, pricing/refund strategy).

Rule nuance (from user): *internet/guest WiFi password = OK; account/admin passwords = forbidden. Where guests pay = OK; account/payment login creds = forbidden.*

---

## 🔴 Active problems in the CURRENT import (sync already ran)

| Page | Problem | Action |
|---|---|---|
| **Pykobello** | Imported to UMI **with a login**: `admin@pykobello.test` / `testadmin123`. The scrubber missed it (not a door-code/"Passwort" pattern). | **force_exclude + re-sync now** |
| **Buchungen Airbnb / Booking / über uns** | Internal **pricing & refund strategy** imported to UMI (e.g. "if the price rises, tell them we gave a discount"; refund tactics). UMI could reveal negotiation strategy to a guest. | **force_exclude** |
| **Smoobu** | Internal tool how-to (+ "Gastdaten aufrufen" sub-page) imported to UMI. | **force_exclude** |
| **Wohnungen Namensübersicht / Ausstattung** | Expose internal apartment codes (F0, HW1B…) and an "intern" note. | exclude or scrub codes |

The earlier no-leak check only looked for door-code/`Passwort` patterns, so these slipped through. **The keyword/code scrubber both under-blocks (above) and over-blocks (below) — this real handbook proves a pure keyword approach is not enough; an explicit allow/deny curation is needed.**

## 🟡 Over-blocked (guest-useful, currently withheld — you want some of these)

| Page | Why blocked | Want for UMI? |
|---|---|---|
| **Basics** | word "Code" (check-in concept) | **Yes** — but strip the "Verlängerungen & Sonderangebote (intern)" section (50% deal is internal) |
| **WLAN** | word "Passwort" | **Partly** — guest WiFi (UM_guest / Urlaubsmagie2 / GKS network) = OK; the "WlanPassword **Admin**: ImUrlaubWohnen" = forbidden. Mixed page → needs surgery |
| **Fernseher** | word "Pin" | Borderline — TV setup help is useful; "Pin Fernseher: 1643" + internal Google-Doc link should be stripped |

## 🟢 Correctly handled today

- **UMI (correct):** Extrakosten, Kurtaxe Kosten, Gästekarte (guest part), Lagermöglichkeiten für Gepäck, Bankverbindung (IBAN + PayPal = guest payment).
- **Blocked (correct):** Passwörter, Check-in Information und Schlüsselcodes, Standorte und Ersatzschlüssel, Telefonate mit Gästen (has Ersatzschlüssel Code 747), Vorgehen bei Beschwerden (refund strategy).

---

## Full per-page classification

### Alltägliches
| Page | Bucket | Notes |
|---|---|---|
| Smoobu (+ Gastdaten aufrufen) | **FORBIDDEN** | internal tool ops / guest-data access |
| Basics | **UMI** (strip intern section) | check-in, pets, amenities, check-out = great UMI content |
| Passwörter | **FORBIDDEN** | all account credentials |
| Pykobello | **FORBIDDEN** | cleaning tool + login creds |
| Nachrichtenvorlagen (+ Kurtaxe sub) | **VORLAGEN** | guest-reply templates (Wanderpass, Kurtaxe). Contains IBAN = guest payment, fine in a template |
| Bankverbindung | **UMI** | IBAN + PayPal for guest payment |

### Buchungen
| Page | Bucket | Notes |
|---|---|---|
| Buchungen Airbnb | **FORBIDDEN** | internal change/pricing procedure + strategy |
| Buchungen Booking | **FORBIDDEN** | same |
| Buchungen über uns | **FORBIDDEN** | internal direct-booking procedure |
| Telefonate mit Gästen | **FORBIDDEN** | phone scripts + Ersatzschlüssel Code 747 |
| Vorgehen bei Beschwerden | **FORBIDDEN** | discount/refund amounts & tactics |
| Extrakosten | **UMI** | fees, check-in/out times (internal Aufbettung table is borderline) |

### Informationen Wohnungen
| Page | Bucket | Notes |
|---|---|---|
| Wohnungen Namensübersicht | **FORBIDDEN** | internal code↔marketing-name map |
| Ausstattung Wohnungen | **UMI (caution)** | per-flat kitchen/parking/pool/sauna facts (guest-useful) but uses internal codes + an "intern" note |
| Check-in Information und Schlüsselcodes | **FORBIDDEN** | all door codes |
| Standorte und Ersatzschlüssel | **FORBIDDEN** | spare-key locations + many codes |
| WLAN | **UMI (guest WiFi only)** | strip "WlanPassword Admin" |
| Aufbettungen/Babybetten/Hochstuhl | **FORBIDDEN** | storage locations + Code 162333 (occupancy facts duplicated safely in Extrakosten/Ausstattung) |
| Lagermöglichkeiten für Gepäck | **UMI** | guest luggage info |
| Fernseher | **UMI (caution)** | TV help; strip "Pin Fernseher: 1643" + internal doc link |
| Sonstiges | **UMI (caution)** | fuse-box reset is guest-helpful; "ask Sebastian/Marcel" is internal |

### Bürokratie
| Page | Bucket | Notes |
|---|---|---|
| Rechnungen | **UMI (caution)** | VAT rates (7/19/0%) guest-relevant; invoicing procedure is internal |
| Gästekarte | **UMI** (+ embedded template → VORLAGEN) | guest card info is UMI; the printer email is internal; the embedded Nachrichtenvorlage → templates |
| Kurtaxe Kosten | **UMI** | tourist-tax rates |

---

## The structural problem: mixed pages

Several pages mix guest-safe + secret content **within one page** (WLAN: guest WiFi + admin pw; Basics: guest info + intern deal; Fernseher: TV help + pin). Page-level allow/deny can't cleanly include one and drop the other. Three ways to resolve, best first:

1. **Notion-side split (recommended, cleanest):** the team moves the secret bits out of guest pages — e.g. move "WlanPassword Admin" to the Passwörter page, move the Basics "(intern)" section to an internal page. Then each page is cleanly one bucket and the sync needs no special-casing.
2. **Explicit allowlist + per-page force_include/exclude** (curate the list once; safest given the keyword scrubber's proven gaps).
3. **Section-level scrubbing** (more code; brittle).

## Proposed sync config (pending approval — NOT yet applied)

- **force_exclude_ids:** Smoobu, Passwörter, Pykobello, Buchungen Airbnb, Buchungen Booking, Buchungen über uns, Telefonate, Vorgehen bei Beschwerden, Check-in/Schlüsselcodes, Standorte/Ersatzschlüssel, Aufbettungen, Wohnungen Namensübersicht.
- **force_include_ids (after Notion-side split or with value-scrub):** Basics, WLAN, Fernseher.
- **Vorlagen → ReplyTemplate:** Nachrichtenvorlagen (+ Kurtaxe sub), Gästekarte embedded template. (Requires the importer to treat these as templates — currently only pages under a parent literally named "Vorlagen" are templated.)
- **Scrubber addition:** redact bare credentials like `user@host / token` and lone admin passwords (the Pykobello-style gap).

## Open decisions for the user
1. Close the live leaks now (force_exclude Pykobello + Buchungen* + Smoobu, re-sync)?
2. Prefer the **Notion-side split** for WLAN/Basics/Fernseher, or have the code force-include + scrub?
3. Route Nachrichtenvorlagen into the ReplyTemplate DB (needs a small importer change)?
