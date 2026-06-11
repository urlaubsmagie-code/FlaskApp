# Wohnungsproblemeliste — Optimized Data Pipeline

Redesign of the n8n workflow that turns raw Booking + Airbnb reviews into the
per-apartment problem list shown at `/apartment-issues` (reads `GeneralReviews.json`).

## Goals
- **Stop dropping reviews** — merge in code (lossless), never in an LLM.
- **One LLM step**, per apartment, with a strict JSON schema (no second model to "structure").
- **No truncation** — small per-apartment calls instead of one giant call.
- Stays **drop-in compatible** with the existing page.

## Target pipeline
```
Read DatasetScrBookingAN.json + DatasetScrAN.json   (C:\n8n_Docker\Files)
  → [Node 1] Merge & Normalize (Code)   → one item per apartment {wohnung, reviews[]}
  → [Node 2] Per-apartment problem detection (LLM, strict schema)
  → validate vs schema (retry once)
  → [Node 3] Assemble + wrap envelope → write GeneralReviews.json
```

## Output contract (must not change — the Flask page depends on it)
`api_apartment_issues` reads `GeneralReviews.json` as `data[0].message.content.wohnungen`:
```json
[ { "message": { "content": { "wohnungen": [
   { "wohnung": "B5", "probleme": [
       { "beschreibung": "Zu wenige Handtücher", "erwähnungen": 1,
         "ids": ["cec28a56c8991383"], "kategorie": "Bad" }
   ]}
]}}, "finish_reason": "stop" } ]
```
`erwähnungen` is computed in code as `len(unique ids)` — never by the model.

---

## Node 1 — Merge & Normalize (n8n Code node, "Run Once for All Items")

Wire the two file readers (Booking + Airbnb JSON) into this node. It auto-detects
platform per record, maps each review to an apartment code using the corrected
`ID.txt` / `IDB.txt` mappings, and emits **one item per apartment**.

> Maintenance: the two maps below are generated from `ID.txt` (Airbnb) and
> `IDB.txt` (Booking). Regenerate them whenever listings change.

```javascript
// ---- apartment-code maps (generated from ID.txt / IDB.txt) ----
const AIRBNB_ID_TO_CODE = {
  "609172560881241855":"UT","940339949730055972":"F3","649153494847068923":"H4",
  "1400686172947505650":"L7","1400553304457299600":"L4","623764180368706654":"H5",
  "53213498":"R2","978296040019088348":"HW2B","1234047782495519188":"B7",
  "1192577221925368063":"B8","1117325665633761027":"B3","1086740196036624350":"HW1B",
  "1115927896352466530":"B1","1086704295178791370":"H2","1086254381830942280":"HW3B",
  "1084714536578087959":"UO3","1075934362566482474":"ZI2","1017948205748585910":"L8",
  "1015289627772010369":"L6","1015251077590567237":"L5","1013703015432494927":"W4",
  "978070304262743292":"F4","930516325391043836":"F1","863189441921549381":"HW2",
  "628058692756552966":"H6","608542931074344396":"UO1","606355177074778177":"W3",
  "605776327027186134":"FAMZI","52516668":"R1","1116870560177253155":"B2",
  "1018794394545297732":"HW1","618595100423444684":"R3","1262986403695976977":"S2",
  "1262897033775851757":"HW4B","1262842711427107306":"FO","1086815255956233349":"S3",
  "1262363357740087161":"ZI1","1262792970209710657":"W2","1262898891754516292":"W5",
  "1263568439469285894":"B6","1263665955205447166":"HW3","1264408905915626460":"B5",
  "50811734":"H1","858114269646172631":"L1","933775634493143720":"F2",
  "960598313742984703":"S1","1396132758505914603":"F1B","1294142559492486330":"UO0",
  "1577677687712837455":"HW13","1635498749834060491":"GK2","1635512594422600121":"GK3",
  "1635524215842396248":"BA2","1315965129922105720":"L9"
};
const BOOKING_SLUG_TO_CODE = {
  "gemutliche-urlaubsoase-mit-pool-sauna-terrasse-uo":"UO",
  "b2-urlaubsmagie-mit-terrasse-amp-grill-direkt-am-wanderweg":"B2",
  "grosse-helle-wohnung-mit-garten-pool-amp-sauna-hw2":"HW2",
  "sommerparadies-mit-terrasse-garten-pool-h6":"H6",
  "gemutliche-urlaubsoase-mit-garten-grill-pool-amp-sauna-uo3":"UO3",
  "gemutliche-grosse-wohnung-mit-pool-garten-amp-terrasse-hw1":"HW1",
  "hw3b-urlaubsmagie-grosses-wohnzimmer-amp-2-schlafzimmer":"HW3B",
  "kleine-wohnung-im-elbi-l6":"L6",
  "wohlfuhlwohnung-mit-gemeinschaftsgarten-mit-pool-terrasse-amp-sauna-hw2b":"HW2B",
  "grosse-helle-wohnung-fur-bis-zu-10p-mit-gemeinschaftsgarten-mit-pool-sauna-amp-t":"F4",
  "fusslaufig-ins-kirnitzschtal-b3":"S3",
  "idyllische-erholung-sauna-garten-pool-amp-fluss-zi1":"Zi1",
  "grosse-helle-wohnung-mit-gemeinschaftsgarten-pool-und-sauna":"HW3",
  "f0-urlaubsmagie-kleine-voll-ausgestattete-wohnung-mit-gemeinschaftsgarten-pool-a":"F0",
  "kleine-gemutliche-wohnung-l5":"L5",
  "urlaubsmagie-zentral-mit-gemeinschaftsgarten-pool-sauna-amp-whirlpool-hw4b":"HW4B",
  "mitten-in-der-sachsischen-schweiz-gemutliche-wohnung-fur-bis-zu-4p-b1":"S1",
  "urlaubsmagie-urlaubstraum-mit-whirl-pool-amp-sauna-ut":"UT",
  "direkt-loswandern-mit-balkon-l8":"L8",
  "hw1b-urlaubsmagie-gemeinschaftsgarten-mit-pool-sauna-amp-terrasse":"HW1B",
  "b6-urlaubsmagie-inmitten-der-sachsischen-schweiz-mit-balkon-mit-ausblick-auf-die":"B6",
  "uo0-urlaubsmagie-gemutliche-wohnung-fur-bis-zu-6p":"UO0",
  "w2-urlaubsmagie-im-herzen-des-elbsandsteingebirges":"W2",
  "50m-bis-zum-wanderweg-25min-fussweg-bis-zum-lichtenhainer-wasserfall-b2":"S2",
  "familienwohnung-fur-3-mit-sauna-pool-terrasse-famzi":"FAMZI",
  "inmitten-der-sachsischen-schweiz-l9":"L9",
  "helle-wohnung-mit-gemeinschaftsgarten-pool-und-sauna-g1":"F1",
  "l4-urlaubsmagie-kleine-wohnung-am-wanderweg":"L4",
  "b5-urlaubsmagie-gemutliche-wohnung-inmitten-der-sachsischen-schweiz-sebnitz":"B5",
  "urlaubsmagie-flussblickwohnung-mit-whirl-pool-amp-sauna-zi2":"Zi2",
  "l7-urlaubsmagie-kleine-wohnung-am-wanderweg":"L7",
  "w6-gemutliche-wohnung-in-lichtenhain":"W6",
  "f1b-uralubsmagie-helle-wohnung-mit-sauna-und-pool":"F1B",
  "gemutliche-wohnung-fur-2-mit-pool-und-terrasse-h1":"H1",
  "helle-wohnung-fur-bis-zu-4p-mit-gemeinschaftsgarten-pool-amp-terasse-f3":"F3",
  "b8-urlaubsmagie-bergsteigerwohnung-mit-balkon-mit-aussicht-aufs-elbsandsteingebi":"B8",
  "maritime-wohnung-fur-2-mit-pool-und-terrasse-h4":"H4",
  "helle-gemutliche-wohnung-mit-terrasse-und-pool-h2":"H2",
  "urlaubsmagie-helle-wohnung-mit-vollausgestatteter-kuche-fur-4p":"GK2",
  "urlaubsmagie-gemutliche-lichtdurchflutete-wohnung-bis-zu-6p":"GK3",
  "urlaubsmagie-helle-gemutliche-wohnung-am-bach-fur-bis-zu-6p":"BA2",
  "urlaubsmagie-fur-bis-zu-10p-gemeinschaftsgarten-mit-sauna-amp-pool":"HW13",
  "maisonette-wohnung-mit-balkon":"B7",
  "b1-urlaubsmagie-einzimmerwohnung-direkt-am-wanderweg":"B1",
  "urlaubsmagie-kleine-wohnung-fur-4p-direkt-am-wanderweg-mit-eigener-terrasse-b3":"B3",
  "urlaubsmagie-sauna-whirl-pool-amp-garten-f2":"F2",
  "gemutliche-wohlfuhloase-mit-pool-garten-amp-terrasse-h5":"H5",
  "urlaubsmagie-bad-schandau-fusslaufig-garten-r1":"R1",
  "urlaubsmagie-5-fussminuten-zur-elbe-pool-r2":"R2",
  "wohlfuhloase-mit-pool-garten-grill-und-ausblick-r3":"R3",
  "maisonette-wohnung-mit-pool-terrasse-am-wanderweg-w3":"W3",
  "urlaubsidylle-mit-pool-terrasse-am-wanderweg-w4":"W4",
  "helle-wohnung-mit-grillgelegenheit-und-pool-w5":"W5"
};

// ---- helpers ----
function airbnbCode(url) {
  const m = (url || "").match(/\/rooms\/(\d+)/);
  return m ? (AIRBNB_ID_TO_CODE[m[1]] || null) : null;
}
function bookingCode(url) {
  const m = (url || "").match(/\/hotel\/de\/(.+?)\.(?:de|es)\.html/);
  return m ? (BOOKING_SLUG_TO_CODE[m[1]] || null) : null;
}
// Flatten inputs: accept single-review items OR items whose json holds an array.
function collectRaw(items) {
  const out = [];
  for (const it of items) {
    const j = it.json;
    if (Array.isArray(j)) { out.push(...j); continue; }
    let pushed = false;
    for (const v of Object.values(j)) {
      if (Array.isArray(v) && v.length && typeof v[0] === "object" &&
          ("startUrl" in v[0] || "listingUrl" in v[0] || "reviewId" in v[0] || "hotelId" in v[0])) {
        out.push(...v); pushed = true;
      }
    }
    if (!pushed) out.push(j);
  }
  return out;
}

// ---- normalize ----
const raw = collectRaw($input.all());
const byApt = {};
const dropped = [];

for (const r of raw) {
  const isAirbnb = ("listingUrl" in r) || ("reviewId" in r);
  const isBooking = ("startUrl" in r) || ("hotelId" in r);
  let norm = null;

  if (isAirbnb) {
    const code = airbnbCode(r.listingUrl);
    const text = (r.reviewText || r.localizedText || "").trim();
    if (code && text) norm = {
      id: String(r.reviewId ?? r.id ?? ""),
      plattform: "Airbnb",
      datum: (r.reviewDate || "").slice(0, 10),
      rating: (r.rating != null ? `${r.rating}/5` : ""),
      text,
      wohnung: code,
    };
    if (!code) dropped.push(r.listingUrl);
  } else if (isBooking) {
    const code = bookingCode(r.startUrl);
    const parts = [];
    if (r.reviewTitle)  parts.push(`Titel: ${r.reviewTitle}`);
    if (r.likedText)    parts.push(`Positiv: ${r.likedText}`);
    if (r.dislikedText) parts.push(`Negativ: ${r.dislikedText}`);
    const text = parts.join("\n").trim();
    if (code && text) norm = {
      id: String(r.id ?? ""),
      plattform: "Booking",
      datum: (r.reviewDate || "").slice(0, 10),
      rating: (r.rating != null ? `${r.rating}/10` : ""),
      text,
      wohnung: code,
    };
    if (!code) dropped.push(r.startUrl);
  }

  if (norm) (byApt[norm.wohnung] ||= []).push(norm);
}

// dedupe reviews by id within each apartment
for (const code of Object.keys(byApt)) {
  const seen = new Set();
  byApt[code] = byApt[code].filter(rv => {
    if (!rv.id) return true;
    if (seen.has(rv.id)) return false;
    seen.add(rv.id); return true;
  });
}

if (dropped.length) {
  console.log(`[merge] ${dropped.length} reviews had no apartment code (NOT silently lost):`,
              dropped.slice(0, 10));
}

// one item per apartment for the per-apartment detection step
return Object.entries(byApt).map(([wohnung, reviews]) => ({ json: { wohnung, reviews } }));
```

Notes:
- Feeds **all** of an apartment's reviews (not just low-rated) so complaints inside
  otherwise-positive reviews are caught. The prompt extracts only the negatives.
- Unmapped reviews are **logged, not dropped silently** — if any appear, add the
  listing to `ID.txt` / `IDB.txt` and regenerate the maps.
- Optional: add a date cutoff here if the list should only reflect recent reviews.

---

## Node 2 — Per-apartment problem detection (LLM, strict schema)

### JSON Schema (model output)
```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["wohnung", "probleme"],
  "properties": {
    "wohnung": { "type": "string" },
    "probleme": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["beschreibung", "kategorie", "ids"],
        "properties": {
          "beschreibung": { "type": "string", "description": "Kurze, sachliche Beschreibung auf Deutsch (max. ~15 Wörter)" },
          "kategorie": { "type": "string", "enum": ["Bad","Bett","Geräte","Geruch","Heizung","Küche","Lage","Lärm","Möbel","Sauberkeit","TV/WLAN","Sonstiges"] },
          "ids": { "type": "array", "items": { "type": "string" }, "description": "Exakte IDs aller Bewertungen, die dieses Problem erwähnen" }
        }
      }
    }
  }
}
```

### System prompt
```
Du bist ein Analyst für Gästebewertungen von Ferienwohnungen. Deine Aufgabe ist es,
aus den Bewertungen EINER Wohnung ausschließlich die NEGATIVEN Punkte (Probleme und
Mängel) zu extrahieren und als JSON gemäß Schema zurückzugeben.

Regeln:
1. Erfasse nur echte Beschwerden oder Mängel an Wohnung, Ausstattung, Sauberkeit,
   Lage oder Service. Ignoriere Lob, neutrale Aussagen und Faktoren außerhalb der
   Kontrolle des Gastgebers (z. B. Wetter) – außer sie betreffen direkt die Wohnung.
2. Auch in überwiegend positiven Bewertungen können einzelne Kritikpunkte stecken –
   diese ebenfalls erfassen.
3. Fasse gleiche oder sehr ähnliche Beschwerden aus mehreren Bewertungen zu EINEM
   Problem zusammen und liste in "ids" ALLE zugehörigen Bewertungs-IDs auf.
4. "beschreibung": kurz und sachlich, IMMER auf Deutsch (englische Bewertungen übersetzen).
5. "kategorie": wähle die SPEZIFISCHSTE passende Kategorie. Nutze "Sonstiges" nur,
   wenn wirklich keine andere zutrifft.
6. "ids": verwende ausschließlich die exakt angegebenen IDs – niemals welche erfinden.
7. Gibt es keine Probleme, gib eine leere "probleme"-Liste zurück.
8. Antworte ausschließlich mit JSON gemäß Schema, ohne weiteren Text.

Kategorien-Leitfaden:
- Bad: Badezimmer, Dusche, WC, Handtücher
- Bett: Betten, Matratzen, Schlafkomfort
- Geräte: Elektrogeräte, Defekte (Kaffeemaschine, Spülmaschine, …)
- Geruch: unangenehme Gerüche
- Heizung: Heizung, Temperatur, Klimatisierung
- Küche: Küchenausstattung, Geschirr, Kochmöglichkeiten
- Lage: Lage, Anfahrt, Parken, Umgebung
- Lärm: Lärm, Hellhörigkeit
- Möbel: Möbel, Einrichtung, Abnutzung
- Sauberkeit: Sauberkeit, Reinigung, Hygiene
- TV/WLAN: WLAN, Internet, Fernseher
- Sonstiges: Kommunikation, Check-in, Preis o. Ä.
```

### User prompt
```
Wohnung: {{ $json.wohnung }}

Bewertungen:
{{ JSON.stringify($json.reviews, null, 2) }}
```

### Vendor wiring (use ONE model)
- OpenAI: `response_format: { type: "json_schema", json_schema: { name: "wohnung_probleme", strict: true, schema: {…} } }`
- Gemini: `generationConfig: { responseMimeType: "application/json", responseSchema: {…} }` (drop `additionalProperties`).
- Validate each response against the schema; retry once on failure.

---

## Node 3 — Assemble + write (to be drafted next)
Collect all per-apartment results, set `erwähnungen = unique(ids).length`, drop
apartments with no problems, wrap as `[{ "message": { "content": { "wohnungen": [...] }}}]`,
and write `C:\n8n_Docker\Files\GeneralReviews.json` (UTF-8, no BOM — eliminates the
`erw??hnungen` corruption that `normalize_probleme` currently patches).
