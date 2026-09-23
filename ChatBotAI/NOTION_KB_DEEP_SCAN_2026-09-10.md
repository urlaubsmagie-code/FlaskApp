# Notion ↔ Wissensdatenbank — Deep Scan (2026-09-10)

Read-only audit. Nothing in UMI or Notion was changed.

**Sources compared**
- Notion: **HANDBUCH ZUR GÄSTEBETREUUNG** (27 pages, rendered in full incl. tables and nested blocks), **Allgemeines** (1 page, ~45 facts), **Sonnenhof** (1 page)
- UMI: all 104 `knowledge_entry` rows, 13 reply templates, 67 properties
- Evidence: 3,985 real guest messages since 2026-03-01 (topic counts), sampled guest questions with the team's actual answers, and the 14 most-sent automated Smoobu messages

> No codes or passwords appear in this file on purpose — the repo is public. Entries are referenced by KB id (`#nn`) and Notion page name.

---

## TL;DR

| | Count | Worst example |
|---|---|---|
| 🔴 Security | 6 | Compensation rules (#109) are **in the guest-reply prompt right now** |
| 🔴 Wrong in the KB | 11 | UMI tells L4/L7 and Sonnenhof guests they have a full kitchen |
| 🟠 Sources contradict each other | 9 | Early check-in from 12:30 or from 13:00? |
| 🟠 Damage from the 2026-09-07 import | 4 | Sebnitztal table shifted one column: "Hund: 1.OG" |
| 🟢 Missing but useful | ~20 | Parking per house, pool/sauna, Müll, check-out duties, Sonnenhof basics |
| ❓ Only the team can answer | 14 | Sonnenhof parking, sauna hours, smoking rule |

**Coverage (measured).** Notion split into lines and table rows; noise and repeated lines dropped; 288 internal/secret lines set aside. Each of the 199 guest-relevant lines was matched against its best single guest-facing KB entry (≥75 % of content words = covered, 40–75 % = partial).

| Source | Guest lines | Covered | Partial | Missing | Missing by text volume |
|---|---|---|---|---|---|
| Handbuch | 150 | 61 % | 25 % | 15 % | 18 % |
| Allgemeines | 25 | 72 % | 12 % | 16 % | 19 % |
| Sonnenhof | 24 | **0 %** | 25 % | **75 %** | **91 %** |
| **All** | **199** | **55 %** | **23 %** | **22 %** | **33 %** |

- Ausstattung table: **260 of 541 filled cells (48 %) are not in the KB**. Stockwerk, Parkplatz, Pool, Sauna and Ort were dropped.
- Message templates: 94 % already in Vorlagen.
- "Covered" includes about 5 outdated or wrong facts (L1–L6 kitchen, freezer list, business travellers pay no Kurtaxe, early check-in 12:30, Kurtaxe cash only).
- Word matching misses some rewordings, so treat the figures as ±5 points.

**Budget constraint:** the guest-facing KB is 70 entries / **24.3k chars** of the 30k `KB_FULL_BUDGET_CHARS`. Above 30k UMI falls back to top-N keyword picking — the starvation bug from 2026-09-04. **Clean up before adding.**

---

## ✅ Applied 2026-09-10 11:35 — steps 1 + 2

User decision: codes and internal procedures **stay in the KB, flagged internal**, so the team doesn't need Notion for them. Nothing was deleted for security reasons.

| Step | Change |
|---|---|
| 1 | #109 compensation rules → internal. #117–#123 verified internal, unchanged. |
| 1 | Mixed entries split. Guest part stays visible; internal sentence moved to a new internal row: #15 → **#125**, #16 → **#126**, #20 → **#127** (current contact list from the Handbuch start page), #23 → **#128**, #44 → **#129** |
| 2 | #107 L4/L7/L8/L9 without kitchen (no "L1"), plus Sonnenhof has no kitchen · #124 adds Sonnenhof to the kitchen exceptions · #50 scoped "außer Sonnenhof" · **#130** new Sonnenhof key-box entry (street-scoped, no codes) · #113 column shift undone · #22 business travellers split Sebnitz/Rathmannsdorf · #26 → "Kurtaxe Rathmannsdorf (Preisliste)" · #25 label adds Hinterhermsdorf/Sonnenhof |
| 2 | Deleted #24 (cash only), #104 (code 24 h before arrival), #75 (unsourced) |
| Protect | All 14 `source='notion'` rows → `manual`, so a sync can no longer overwrite or re-create them. **`notion_sync_enabled` → false** (re-enabling would re-add the old June versions as duplicates). |

Verified afterwards: no internal phrase in any guest-facing row; guest-facing KB 23.8k chars (was 24.3k); 19 internal rows.

**Rollback:** full DB backup `instance/chatbot_backup_before_kb_fixes_20260910_1133.db`; before-rows of every touched id in `instance/kb_fixes_20260910_before_113514.json`.

**Not done yet (team):** the house code in template "Waschmaschine und Trockner" (S3), logins out of the Notion Sonnenhof/Passwörter pages (S4), the WLAN label (S5), the freezer list (W8), Sonnenhof room data in Smoobu (W10), and the §7 questions.

## ✅ Applied 2026-09-10 11:55 — step 4 (import what was missing)

**Guest-facing (11 new, 7 extended):**
- Sonnenhof, visible only to Sonnenhof chats: **#131** rooms & equipment · **#132** surroundings & shopping · **#133** check-in/out, fees, dogs, Kurtaxe
- **#134** pool & sauna per house · **#136** check-out duties · **#137** bed linen, towels & basics (absorbed the English #29) · **#138** dogs: where allowed & costs · **#139** check-in help (right door, key box, Nuki) · **#140** grill & garden · **#141** extension offer (30–50 %) · **#143** trip tips (WhatsApp channel, Instagram)
- **#106** parking for BA2, GK, H, L, S, B, W2/W6 · **#111/#112/#114–#116** floor per apartment; the UT "intern" note moved to **#135** · **#16** free early arrival without guarantee

**Internal (10 new, 4 extended), copied verbatim from Notion:**
- **#144** Airbnb bookings · **#145** Booking bookings (+ extranet notes and customer-service number, no logins) · **#146** direct bookings · **#147** WLAN · **#148** apartment codes ↔ names · **#149** Smoobu & cleaning plan (no login) · **#150** Sonnenhof room list with codes · **#151** how to answer reported problems · **#142** extension-offer calculation
- **#120** full phone-call guide · **#109** full complaint guideline · **#128** Rathmannsdorf print troubleshooting · **#119** Am Anger 11 storage/spare key

**Verified:** guest-facing KB **64 entries / 29.9k chars** (a Sonnenhof chat sees 29.9k, an apartment chat 26.9k); none of the 57 internal codes, no password text and no "intern" note in any guest-facing entry; no English guest-facing entries left. KB total 114 rows, 29 internal.

**Coverage after (word-match, ±5):** guest-relevant Notion lines missing from UMI **22 % → 12 %** (6 % counting internal entries); Sonnenhof missing **75 % → 33 %** (the rest is listing marketing text and the emergency phone number, left out on purpose). Rewritten or merged entries word-match their source worse, so "covered" understates.

**Deliberately not imported (waiting on the team or sources disagree):** HW and Sonnenhof parking, sauna hours, Rathmannsdorf pool, Aufbettung prices (C3), early check-in 12:30 vs 13:00 (C1), bin locations, smoking rule, freezer list, Wanderpass shipping (C4). **Never imported:** account logins (Passwörter page, Sonnenhof callout, Pykobello).

**Rollback:** `instance/chatbot_backup_before_kb_import_20260910_1152.db`, `instance/kb_import_20260910_before_115510.json`.

## ✅ Applied 2026-09-10 11:47 — step 3 (merge duplicates) + budget raised

| Topic | Before | After |
|---|---|---|
| Gästekarte | #22, #23, #27, #41, #42, #48 | **#48** Allgemein · **#41** Sebnitz, Lichtenhain & Hinterhermsdorf · **#42** Rathmannsdorf (incl. the online check-in reminder text; printer lines moved out of #26) |
| Bezahlen | #5, #6, #32, #35, #89 | **#5** Bankverbindung & PayPal · **#89** Kurtaxe & Zusatzkosten bezahlen (bar / Überweisung; ask number of people + ages before quoting an amount) |
| Gästemappe | #36, #37, #39, #40 (English) | **#36** Digitale Gästemappe & Online Check-in (incl. check spam) |
| Other | #18 stub, #31 dog fee (EN), #55 TV channels, #58 luggage L | deleted; the TV sentence went into #108 |

- 13 rows deleted, 8 rewritten. Guest-facing KB now **54 entries / 22.6k chars** (was 67 / 23.8k); KB total 94 rows, 19 internal.
- One English guest-facing entry remains: #29 "Bringing your own items".
- **`ContextFilter.KB_FULL_BUDGET_CHARS` 30000 → 45000.** `test_trigger_words_rank_an_entry_the_wording_would_miss` now sizes its over-budget KB from the constant instead of a hard-coded 90 rows. **Takes effect after a Flask restart**; the KB changes are live immediately.
- **Rollback:** `instance/chatbot_backup_before_kb_merge_20260910_1144.db`, `instance/kb_merge_20260910_before_114655.json`.

## 1. 🔴 Security — fix first

| # | Finding | Evidence | Fix |
|---|---|---|---|
| S1 | **Complaint compensation rules reach the guest prompt.** Amounts per season/apartment size and the "1. free night / 2. voucher / 3. money" order. UMI could offer money or reveal the negotiation strategy. | KB **#109** `is_internal=0` (verified in DB) | Flag internal, or delete (it lives in Notion) |
| S2 | **Every key-box code, spare/general key code, the TV PIN and a storage lock code are in the KB.** Protected only by the `is_internal` checkbox. UMI never needs them — guests get their code from the Gästemappe. One unticked box or one new loader that forgets the filter sends them to the model. | KB **#117, #118, #119, #121, #122, #123** | **Delete from the KB.** They stay in Notion. |
| S3 | **Template "Waschmaschine und Trockner" gives out a house code that opens other houses.** The same code is listed in Notion as the front door for B5–B8, W6 and the W storage room in Lichtenhain. KB #123 itself says "nicht allgemein herausgeben". | Template **#11**, Allgemeines, Check-in page | Team decision: separate code for Haus 26, or drop the code from the template |
| S4 | **Account logins are readable by UMI's Notion integration.** The Sonnenhof page opens with a login callout (Smoobu / Airbnb / Extranet); the Passwörter page (all accounts, incl. Google, website, GitHub) sits inside the Handbuch tree. Today's sync excludes Passwörter by id, but the Sonnenhof page is not on that list. | Notion: Sonnenhof, Passwörter | Move all logins to a page **outside** anything connected to the UMI integration |
| S5 | **WLAN page: the password labelled "Admin" was given to a guest.** Either the label is wrong or the admin password is out. | Notion WLAN; team reply in BA2 chat, 2026-06-14 | Ask the team which password is guest-facing |
| S6 | Smaller internal notes still reach the prompt: Meldeschein printer e-mail (#23), "Sebastian oder Marcel fragen" (#20), "bei unangenehmen Gästen Early-Checkout möglich" (#16), "in den Cleaning-Plan schreiben" (#15), Pykobello step (#44) | `is_internal=0` on all | Flag internal or trim the sentence |

## 2. 🔴 Wrong in the KB (UMI would state something false)

| # | KB says | Truth (source) | Fix |
|---|---|---|---|
| W1 | **#107** "L1–L6 komplett ausgestattet, L8 + L9 keine Küche" | **L4, L7, L8, L9** have no kitchen; there is no L1 (Ausstattung table, Basics). The bullet is outdated on the Notion "Standorte" page. | Correct #107 — and the Notion bullet |
| W2 | **#124** kitchen exceptions: S, L4, L7–L9 | **Sonnenhof has no kitchen either** — fridge without freezer, mini oven, kettle, Tassimo (Basics, Sonnenhof page) | Add Sonnenhof |
| W3 | **#50** key box: "C-Taste, Code, Hebel nach unten" — general scope, so also used for Sonnenhof | Sonnenhof boxes: red **CLEAR** lever → code → turn knob towards the green dot (Sonnenhof page) | Sonnenhof-scoped entry; say "(nicht Sonnenhof)" in #50 |
| W4 | **#113** Sebnitztal: "Hund: 1.OG / 2.OG" | **Import column shift.** That Notion table merges "Küche mit TK-Fach" into one column. Real: dogs **yes**, floor 1.OG/2.OG | Re-import row data |
| W5 | **#22** "wenn geschäftlich da: keine Kurtaxe" | True in **Gemeinde Sebnitz** (Monteure 0 €). In **Rathmannsdorf business travellers are liable** (Kurtaxe page) | Split by town |
| W6 | **#26** label "Preisliste" | It is the **Rathmannsdorf** tariff; only the value's first word says so. Next to #25 (Sebnitz) UMI can mix the rates. | Rename "Kurtaxe Rathmannsdorf" |
| W7 | **#104** (AI-extracted) "Zugangscode 24 Stunden vor Anreise" | Automated messages: main account sends the Gästemappe "ab morgen" (day before); **Sonnenhof sends the code on arrival day** | Scope per account or remove |
| W8 | **#47** freezer exceptions "R2, B2, B3, F4, UO, UO2, HW1, W4" | Old names (UO0/UO1 now); **Sonnenhof has no freezer**; the table is blank for F1B, HW3, GK2, GK3, BA2, W2–W6, all L, B5–B8 → UMI answers "yes" for those | Needs team input (Q7) |
| W9 | **#24** "Kurtaxe Kosten" = "Bezahlung in Bar vor Ort." | Contradicts #32 / #35 / #89 (transfer is OK) | Delete #24 |
| W10 | Sonnenhof rooms in UMI: `max_guests = 1` on 13 of 14 rooms | Notion: DBZ = 3, DZ = 2, EZ = 1. Room 108 is "DZ Goldene Auszeit" in Smoobu but "DZ Sonnenstern" in Notion | Smoobu data entry |
| W11 | **#75** (AI-generated, Sonnenhof) "keine separaten Kinderbetten, Kinder schlafen im Bett der Gäste" | No source anywhere | Verify or delete |

## 3. 🟠 Sources contradict each other — team decides

| # | Topic | Version A | Version B |
|---|---|---|---|
| C1 | Early check-in start | 12:30 (Extrakosten → KB #16) | **13:00** (Basics, Sonnenhof listing) |
| C2 | Late check-out price | 20 € flat (Basics) | 10 € winter / 20 € summer (Extrakosten, Sonnenhof) — plus **unannounced** late check-out fees on the Sonnenhof page. Apartments too? |
| C3 | Aufbettung price | 20 € per person/night (Telefonate page) | Airbnb 20 €/night/person; Booking +20 % / +40 % (Extrakosten). **KB #15 lost all prices** — nested bullets were dropped by the sync |
| C4 | Wanderpass shipping | Notion template: one pass shipped for 8,80 € | Allgemeines: "nicht nur einen — erst ab 2 Stück" (KB #44 follows this) |
| C5 | Cancellation | Kurtaxe-Beschwerde templates: "kostenlos bis 1 Tag vor Anreise" | KB #49 / #83: no free cancellation. Depends on the Booking rate plan → should escalate, not answer |
| C6 | Extension offer | Basics: "(intern)", 50 % | Automated message sent ~1,169× since June: "**30–50 %**". It is public — and the KB has nothing on it |
| C7 | Parking F-Wohnungen | KB #106: "keine eigenen Parkplätze" | Ausstattung table: F4 Parkplatz **ja** |
| C8 | Hochstuhl | Notion: "in jedem Haus gibt es einen Hochstuhl" | KB #76 (Sonnenhof): "nicht überall — immer nachfragen" |
| C9 | Pool in Rathmannsdorf | Ausstattung table: R1–R3 Pool **ja** | Nothing else mentions a pool there — confirm |

## 4. 🟠 Damage from the 2026-09-07 manual import

1. **#111–#116 dropped five table columns:** Stockwerk, **Parkplatz, Pool, Sauna**, Ort — the most-asked topics after Kurtaxe.
2. **#113 column shift** (W4).
3. **#110** omits S2 (its Notion row has no label: ": 2/3") and lists a non-existent L1.
4. **Duplicates.** The old Notion-sync rows (#15–#26, `source='notion'`) and the manual rows (#106–#124) cover the same pages. The sync only ever touches `source='notion'`, so both copies survive every "Sync now". Also duplicated: Gästekarte ×5 (#22, #27, #41, #42, #48), Online check-in ×2 (#36, #39), Kurtaxe payment ×4 (#5, #32, #35, #89).

## 5. 🟢 Missing and useful — ranked by real guest demand

Guest messages since 2026-03-01 mentioning the topic, out of 3,985.

| Demand | Topic | What to add | Source |
|---|---|---|---|
| 241 | Kurtaxe | Hinterhermsdorf/Sonnenhof belongs to the **Sebnitz** tariff (label #25 lists only Sebnitz + Lichtenhain). The team's move is to ask for number of people + ages first (#95, #96). | Sonnenhof listing, corrections |
| 190 | Dogs | One-line rule: allowed everywhere **except L and UO**; Sonnenhof yes (10 €, 8 € from night 8) | Basics, Sonnenhof listing |
| 176 | Check-in time | "Kostenlos früher schauen, ob die Wohnung fertig ist — ohne Garantie" (dropped from #16 by the sync) | Extrakosten, Basics |
| 162 | Keys / code | Gästemappe not found → search mail incl. **spam**, link is in the first confirmation. Guest-safe troubleshooting: right door (W: the two ramps / white house with red window frames; HW entrance via the outside stairs at the end of the house, F at the street), press C only briefly, listen for the click, the **box** opens not the door, the Booking code is Booking-internal, Nuki blink patterns (wrong code vs. empty battery) | Basics, Telefonate page (guest-safe parts only) |
| 140 | Hiking / trips | Sonnenhof: hikes start at the door (Kirnitzschtal, Obere Schleuse). Tip sources the team already uses: **WhatsApp channel** (link sent ~1,900× in automated messages), Instagram @Urlaubsmagie | Sonnenhof listing, automated messages, team replies |
| 138 | **Parking** | Missing: **BA2** (no own space, street parking), B (yes, public), L (L4 + L7 none, L5/L6/L8/L9 yes), S + H (yes), W2 + W6 (none), GK (yes, signposted), **HW (Notion sentence is cut off — Q1)**, **Sonnenhof (unknown — Q2)** | Ausstattung table, Allgemeines |
| 133 | Online check-in / Gästemappe | Spam folder; one guest card with one name + number of persons | Basics, team reply 2026-09-07 |
| 118 | Bus / train | "Gästekarte mit beiden Namen ausfüllen, Personenzahl eintragen → kostenlos Bus" | Team reply 2026-09-07 |
| 108 | Towels / bathroom | Linen and towels free (buried in #16); **amenities list** missing: Föhn, Duschgel, Seife, Shampoo, Spüli, Salz, Pfeffer; Sonnenhof: Föhn, Duschbad/Shampoo | Basics, Sonnenhof page |
| 101 | Kitchen | Fix W1/W2. UO1 has no microwave (Herd + Backofen). Sonnenhof: only a small starter supply of capsules | Team replies |
| 81 | Grill / garden | L: grill in the inner courtyard for all L guests. F4/Seb: grill with grate, **bring your own charcoal**. H5 Talruhe: garden shared by 5 small apartments, fenced except the small stairs down to the creek. **Sonnenhof terrace grills: asked twice, never answered (Q3)** | Allgemeines, team replies |
| 73 | **Sauna / pool** | Which apartments have them (table): pool + sauna at F / UT / Famzi / Zi / UO / HW; pool without sauna at H, W, R(?); none at GK, BA2, L, S, B. Sauna 5 €/day/person — **a guest complained the fee was never announced**. Hours unknown (Q4). Pool is seasonal. | Ausstattung table, Extrakosten, team replies |
| 51 | **Müll** | Check-out message asks guests to take the trash out; bins are at the parking spaces (F2 answer). A GK3 guest complained about no marked containers. Per-house bin locations (Q5). | Automated message, team replies |
| 46 | Late check-out | Needs C2 resolved | — |
| 43 | **Smoking** | No rule anywhere. The team allowed the balcony (UT). (Q6) | Team reply |
| ~1,300 automated | **Check-out duties** | Linen off, trash out, start the dishwasher / wash up, guest card + Kurtaxe in cash on the table | Automated check-out message |
| — | Apartment names | Booking mails use marketing names ("Wanderfalke", "Frischluft"); 55 code↔name pairs are in Notion and in the parent app's `apartment_config.json`, not in UMI | Wohnungen Namensübersicht |
| — | Behaviour rules for the prompt (not KB facts) | Never ask guests for photos of a complaint. Never imply we already knew about a defect ("wir hören davon zum ersten Mal"). Compensation is always a team decision. | Vorgehen bei Beschwerden, Allgemeines |

## 6. Sonnenhof — what UMI should know (all guest-safe)

UMI knows almost nothing about Sonnenhof today: four AI-extracted street entries (#71, #72, #75, #76), one unverified.

- Former hotel, Hinteres Räumicht 12, Hinterhermsdorf (Gemeinde Sebnitz). 14 self-catering rooms: **101–107 on the 1st floor, 108–114 on the 2nd**. DBZ sleeps 3, DZ 2, EZ 1.
- Room: private bathroom with shower, fridge **without freezer**, mini oven, kettle, **Tassimo** capsule machine (starter capsules only), dishes, hair dryer, shower gel/shampoo. **No kitchen.**
- Outdoor area and **roof terrace** shared by all guests.
- Shopping: small general store in Hinterhermsdorf; supermarkets, bakeries, pharmacy, banks in Sebnitz (~8 km).
- Check-in: front-door code in the digital Gästemappe **on arrival day**; key boxes on a board to the right of the stairs, numbered 101–114; CLEAR lever → code → turn the knob to the green dot.
- Early check-in from **13:00** (20 € summer / 10 € winter), late check-out until 12:00 (same prices), fees for unannounced late check-out.
- Dogs 10 €/night (8 € from night 8). Kurtaxe 2,50 € (reduced 2,00 €) per person/night, cash.
- Check-out: linen off, trash out, wash the dishes.

## 7. ❓ Questions only the team can answer

1. HW parking — the Notion sentence stops at "Parkplatz bei …". Where, and why "außer HW4B"?
2. Sonnenhof parking — where do guests park? (asked 2026-08-13, never answered)
3. Sonnenhof roof-terrace grills — may guests use them, what fuel, bring your own? (asked twice)
4. Sauna — hours, how to book/pay, which houses?
5. Müll — bin location and separation rules per house.
6. Smoking — inside never? balcony / terrace OK?
7. Freezer — for all rooms the table leaves blank (see W8).
8. Early check-in — from 12:30 or 13:00? Late check-out — seasonal price everywhere?
9. Unannounced late check-out fees — Sonnenhof only, or all houses?
10. Aufbettung price — 20 €/person/night flat, or the Airbnb/Booking split?
11. Wanderpass — can a single pass be shipped?
12. WLAN — which password is guest-facing, and why is one labelled "Admin"?
13. Rathmannsdorf pool — real?
14. Package delivery to Sonnenhof — allowed?

## 8. How to import — recommendation

**Do not** point the existing Notion sync at this:
- every page mixes guest facts with secrets, so page-level allow/deny fails (see `NOTION_HANDBOOK_CLASSIFICATION.md`);
- `blocks_to_text` drops tables and nested blocks, which is where most of the value is;
- it reads one root only, and Allgemeines and Sonnenhof are separate roots.

**Do** a curated import:
1. Security fixes (S1–S6).
2. Correct W1–W11 where the source is unambiguous.
3. Merge duplicates and delete #24 and the empty #18 stub — frees budget.
4. Draft the new entries from §5 and §6 into a review file (short, one fact per entry, scoped to property/street where it applies, `trigger_words` filled), approve, then write.
5. Fill the rest from the team's answers to §7.

Re-check the guest-facing total against the 30k budget after step 3 and again after step 4. If it no longer fits after cleanup, raise `KB_FULL_BUDGET_CHARS` — the cloud model's context is far larger — rather than letting the top-N filter return.
