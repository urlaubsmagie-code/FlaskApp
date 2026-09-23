# Wissensdatenbank aus den Chats — Scan 2026-09-11

**Read-only scan. Nothing in the KB or the code was changed.**
Approve by number (e.g. "A1 = 13 Uhr, A2 = PayPal raus, B1–B20 ok, C ok, D skip") and I apply it with a DB backup first.

## What was scanned

| Source | Size | Used for |
|---|---|---|
| Hand-written team answers, each paired with the guest message(s) it answered | **1,982 pairs** (Dec 2024 – Sep 2026) | ad-hoc knowledge (sauna, parking, bins …) |
| Smoobu automatic messages | **13,423 sends from 42 template families**, one example per apartment variant | official info every guest receives |
| Current KB | 114 entries (53 guest-facing = 29.6k chars, 29 internal) | comparison |

8 parallel read-only agents → **285 raw findings**, merged here into ~120 proposals. Guest names were masked before the scan; codes, passwords and phone numbers are `[CODE]`/`[TEL]` — none are in this file.

**Evidence** in brackets: `n` = supporting answers (or template sends), date = last time the team said it.

---

## ⚠️ Prerequisite before any building-scoped entry (B/C items marked 🏠)

Building-scoped KB rows match `property.street` **by exact string**. The streets are inconsistent, so an entry for one spelling silently misses flats with the other:

| Building | Spellings in `property.street` |
|---|---|
| Hertigswalder 27 | `Hertigswalder Str. 27` (F0–F4, HW1B–HW4B) · `Hertigswalder Straße 27` (HW1, HW3) · `Hertigswalder Straße` (HW2 — no number) |
| Hertigswalder 26 | `Hertigswalder Str. 26` (UT, Famzi) · `Hertigswalder Straße 26` (Zi1, Zi2) |
| Hertigswalder 22 | `Hertigswalder Str. 22` (UO1) · `Hertigswalder Str.22` (UO0) · `Hertigswalder Straße 22` (UO3) |
| HW13 | `Hertigswalder Str.13` |
| Neue Straße 4 | `Neue Str. 4` (W3–W5) · `Neue Straße 4` (W2, W6) |

The Smoobu property sync rewrites `street` from the listing, so fixing the DB alone gets undone. Two options:
- **P1 (recommended):** normalize in code — `Straße`→`Str.`, one space before the number — on sync and in the scope match, plus a one-time backfill. Small change + test.
- **P2:** fix the addresses in the Smoobu listings (HW2 also needs its house number there).

Until then I would write building facts per apartment, or globally with the building named in the text.

---

## A. The team must decide (contradictions)

UMI gives whatever the KB says, so each of these currently risks a wrong answer. My recommendation in *italics*.

| # | Topic | KB says | Team / templates say | Evidence |
|---|---|---|---|---|
| **A1** | Early check-in time (#16) | ab 12:30 | ab **13:00** — since March; on 2026-08-29 a 12:30 offer was corrected as "Versehen, offiziell 13 Uhr"; Sonnenhof #133 already 13:00 | ~30 answers, 4 batches · *13:00* |
| **A2** | PayPal (#5, #15, #89) | PayPal accepted | since **2026-06-24** "Paypal geht momentan nicht"; every later PayPal request got the bank account | n≈11, last 08-28 · *remove PayPal* |
| **A3** | Pet fee over 7 nights (#138, #15, #133) | only nights 8+ cost 8 € | booking confirmation: "bei mehr als 7 Nächten 8 €/Nacht" → reads as the whole stay (10 nights: 80 € vs 94 €) | 1,026 sends · *decide, then align template or KB* |
| **A4** | Kinderbett price (#15) | 10 € pro Aufenthalt | 10 € **pro Nacht** (07-29 R2, 08-17 GK2); "pro Aufenthalt" in Feb | n=4 · *decide* |
| **A5** | Extension discount (#141 guest, #142 internal) | #141 30–50 % · #142 half price | templates: 50 % until 07-12, **30–50 % since 07-14**; team answers still say 50 %; Sonnenhof: "Aktion ist vorbei" (08-10) | 536 sends + 20 answers · *30–50 %, #142 update; confirm Sonnenhof excluded* |
| **A6** | Sauna price unit (#134) | 5 € pro Person pro **Tag** | 14 answers per day; 1 answer "pro Saunagang" (07-22) | *keep per day* |
| **A7** | Aufbettung in B3 and H4 (#113, #114) | "keine Aufbettung" | team offered one for 20 €/Nacht (B3 05-26, H4 06-09) | n=1 each · *check occupancy* |
| **A8** | W5 occupancy (#110) | 4 / 6 | "Preis gleich bis 6 Personen, erst 7./8. teurer"; W5 has 3 bedrooms | n=1 (08-18) · *likely 6/8* |
| **A9** | Luggage before check-in, B and W6 (#19) | B: nein · W: nein | B7 hallway allowed (05-22), W6 hallway allowed (07-12) | n=1 each · *decide* |
| **A10** | F4 parking (#106) | F flats: no parking | F4 has a signed "F4" space (08-02, 08-14); F0, F2 confirmed none | n=3 · *F4 exception* |
| **A11** | HW13 parking | — | 05-10: "kein eigener Parkplatz" (after a same-day correction); 09-01: "gehört ein Parkplatz" | n=3 · *check* |
| **A12** | Kurtaxe when leaving early (#89) | — | 3 answers: only nights stayed, overpayment refunded (08-15); 2 answers: "pro Aufenthalt" (06-17, 07-05) | *nights stayed* |
| **A13** | Gästekarte validity (#48) | "Bus & Bahn kostenlos" | 06-29: not valid for the train to Dresden or the Elbe ships; 07-26: "Bus & Bahn kostenlos" | *check VVO zone, then precise text* |
| **A14** | Kurtaxe rate Sebnitztal (H flats) | nowhere | team charged 2,00 € (Rathmannsdorf rate), #25 Sebnitz is 2,50 € | n=1 · *which municipality?* |
| **A15** | Trampoline Sebnitz (#140) | "darf gerne genutzt werden" | 08-10: private (neighbours), kids sent away, team apologised | n=2 · *remove from #140* |
| **A16** | Forgotten items fee | — | 3 answers: 10 € + postage; 6 answers: postage only; food is thrown away | *decide the fee* |
| **A17** | Emergency / WhatsApp contact | no guest-facing entry | team tells guests to call even at night and to prefer WhatsApp (Booking messages arrive late) | n=6 · *may UMI give the number?* |
| **A18** | GK Wi-Fi credentials (#147, internal) | internal | team sends network name + password to GK guests directly | n=4 · *guest-facing for GK?* |
| **A19** | Key return Hertigswalder 26 (#33) | key box | guest folder: key box · door sign: key in the door | n=3 · *align folder and sign* |
| **A20** | Washing price (#45, #15) | 3 € | once 2,50 € (04-02) | n=1 · *probably keep 3 €* |
| **A21** | Street parking Hertigswalder 27 (#106) | Parkscheibe 3 Std. | once "2 h" (06-16, text copied from BA2) | n=1 · *keep 3 h* |
| **A22** | Vacuum cleaner Bergblick | — | 03-06: "kann angefragt werden" · 04-22: "nicht für Gäste" | *newer = none* |
| **A23** | S flats access | — | "kein Schlüssel, 6-stelliges Codeschloss" (06-28) vs "Schlüsselbox neben der Tür, beschriftet" (09-09) | *per flat?* |
| **A24** | Parcel address | — | team gave Hertigswalder Str. **22**; office is **26** (#59) | n=1 · *which one?* |
| **A25** | Whirlpool | — | "gibt es nicht mehr" (Feb) — check listings / guest folder still mention it | — |

Not a conflict, no change: student Kurtaxe age (one team answer said 25, KB's official list says up to 27 — KB right), Lichtenhain Kurtaxe once charged at the Rathmannsdorf rate (mistake; #25 right), "Prossener Str. 34" given to Sebnitz guests twice (copy error; that is Rathmannsdorf).

---

## B. Changes to existing entries

Clear additions, no decision needed (only where marked). Guest-facing unless noted. 🏠 = building-scoped, needs the street prerequisite.

**B1 — #16 Späte Anreise** (most frequent gap; 1,026 template sends + ~35 answers)
> Der Check-in ist ein Self-Check-in per Code und Schlüsselbox bzw. Codeschloss – niemand muss vor Ort sein. Ab 16 Uhr könnt ihr jederzeit anreisen, auch spät abends oder nachts; eine Ankunftszeit müsst ihr uns nicht mitteilen. Eine Angabe wie „Check-in bis 18 Uhr" auf der Buchungsplattform gilt nicht. Eine persönliche Schlüsselübergabe gibt es nicht.

**B2 — #16 Früher rein ohne Buchung** (n=10)
> Ohne gebuchten Early Check-in können wir nichts zusagen. Kommt ihr vor 16 Uhr, dürft ihr kostenlos rein, wenn die Wohnung schon fertig ist – erkennbar daran, dass der Schlüssel bereits in der Schlüsselbox hängt. Vor 13 Uhr geht es nie, weil die Vorgäste bis 10 Uhr (mit Late Check-out bis 12 Uhr) bleiben dürfen. Wer es sicher will, bucht den Early Check-in. + time per **A1**.

**B3 — #15 / #110 Aufbettung & Bettwäsche** (n=12; price so far only in internal #120)
> Eine Aufbettung kostet 20 € pro Person pro Nacht inkl. Bettwäsche und Handtüchern, bar bei Abreise mit der Kurtaxe. Bettwäsche, Decken und Handtücher liegen genau für die gebuchte Personenzahl bereit – Babys und Kleinkinder, die die Plattform nicht mitzählt, sind nicht eingeplant. Bringt ein Gast eigene Luftmatratze und Bettzeug mit, kostet die zusätzliche Person nichts (Kurtaxe fällt trotzdem an). Immer vorher anfragen.

**B4 — #134 Pool & Sauna Sebnitz** (n=30 + 662 sends) 🏠 or global with houses named
> Pool, Fasssauna, Grill und Feuerschale liegen im Gemeinschaftsgarten am Haupthaus Hertigswalder Str. 26 – direkt gegenüber der Nr. 27, einen kurzen Fußweg von den Wohnungen in der Nr. 22, 27 und der HW13. Die Sauna braucht keine Anmeldung: selbst mit Holz anheizen, Anleitung vor Ort. Brennholz liegt unter dem Balkon, Anzünder, Pellets und Streichhölzer im kleinen Schrank neben der Sauna. 5 € pro Person pro Tag, beliebig oft, bar bei Abreise mit der Kurtaxe. Der Pool ist ein kleiner Aufstellpool, geöffnet Juni bis September. Einen Whirlpool gibt es nicht mehr.
> Also: **add HW13** to the list in #134.

**B5 — Feuerschale** (new line in #134; n=1)
> Die Feuerschale im Gemeinschaftsgarten dürft ihr nutzen; wer unser Holz nimmt, legt 10 € pro Feuer bei Abreise auf den Tisch.

**B6 — #106 Parken** — split the long entry into per-building rows (each only reaches chats in that building):
- 🏠 **Hertigswalder Str. 27, HW flats** (n=20): eigener beschilderter Stellplatz pro Wohnung — Straße etwas runter, hinter Haus 28 rechts auf den Schotterparkplatz, parallel zur Mauer; Parkkarte aus der Wohnung sichtbar ins Auto (darf man behalten); Parken am Anreisetag ab 12 Uhr. Platz belegt → vorerst freien Platz nehmen und Bescheid geben. Zweites Auto: kleiner kostenloser Parkplatz links am Ende der Hertigswalder Straße, oben an der Straße mit Parkscheibe (3 Std., 18–8 Uhr frei), oder großer kostenloser Parkplatz an der tschechischen Grenze (ca. 10 Min. zu Fuß). In der Kurve nur Anwohner; der seitliche beschilderte Platz ist für Mitarbeiter.
- 🏠 **Hertigswalder Str. 27, F flats**: keine eigenen Plätze (F4 → **A10**); Alternativen wie oben.
- 🏠 **Hertigswalder Str. 22 (UO)**: beschriftete Plätze (UO1, UO3), Parkkarte.
- **BA2** (apartment): kein Parkplatz; gegenüber mit Parkscheibe 1 Std., 18–8 Uhr frei (abends auf 8 Uhr stellen); umliegende Straßen bis 2 Std.; unbegrenzt an der tschechischen Grenze. Wir verleihen keine Parkscheiben (z. B. bei „Conny's" kaufen).
- 🏠 **Hohnsteiner Str. 11 (H)**: genau 1 Platz pro Wohnung, zweites Auto im Ort.
- 🏠 **Bergblick 11**: kostenloser öffentlicher Parkplatz direkt gegenüber, kein zugeteilter Platz.
- 🏠 **Am Anger 11**: L4/L7 ohne eigenen Platz — zum Ausladen in den Hof, dann kostenlos im Dorf (z. B. gegenüber Pension Bergblick). *(one answer said "5 Plätze" for L6 — per-flat detail, check)*
- 🏠 **Hainersdorfer Weg 8 (GK)**: auf der Waldseite parken; mit zweitem Auto die zwei Plätze ganz rechts zur Straße.
- 🏠 **Neue Straße 4 (W6, W2)**: kein eigener Platz, die Rampe gehört zu einer anderen Wohnung; Parkplätze gegenüber dem Kindergarten (eine Straße weiter) oder öffentlicher Parkplatz ca. 200 m.
- **W5** (apartment): direkt vor dem Eingang im markierten Bereich.
- 🏠 **Gartenstraße 3**: Weg zum Parkplatz Prossener Str. 34 — aus der Gartenstraße raus, Hauptstraße kreuzen, unter der Brücke durch, rechts großer Schotterparkplatz.
- 🏠 **Sonnenhof**: Parkplätze für Gäste vorhanden.
- **HW13** → **A11**.

**B7 — #36 Gästemappe, Schlüssel-Code, Online Check-in** (n=30)
> Den Schlüssel-Code gibt es nicht per Nachricht: Er erscheint am Anreisetag (ca. 24 Std. vorher) in der digitalen Gästemappe unter „Schlüssel-Code", mit Beschreibung wohin und wie. Den Online Check-in (Button oben links) jederzeit vor der Anreise ausfüllen – er dient nur der Anmeldung für Kurtaxe und Gästekarte, nicht der Anreisezeit. Kennzeichen und Kinder kann man später nachtragen; ist das Kennzeichen noch unbekannt, eine 0 eintragen. Ein per SMS erhaltener Code ist nicht der Schlüsselcode. Öffnet der Link nicht: Seite neu laden oder anderen Browser nehmen; zeigt der Check-in nur eine leere Seite, App/Browser ganz schließen und neu versuchen – sonst meldet euch, dann schicken wir den Link neu oder machen den Check-in für euch (vollständige Namen und Geburtsdaten aller Reisenden). Die Gästemappe gibt es in der Sprache der Buchungsplattform; die gedruckte Mappe hat hinten eine englische Version.

**B8 — #36/#130 Sonnenhof-Ausnahme** (336 sends)
> Im Sonnenhof kommt der Link zur Gästemappe mit dem persönlichen Code erst am Anreisetag – vorher gibt es noch keinen Link, das ist normal. (#36 currently tells Sonnenhof guests to search their spam folder.)

**B9 — #138 Haustiere** (n=12)
> Die Gebühr von 10 € pro Tier und Nacht gilt für jeden Hund, egal wie klein, und auch für Katzen. Sie ist nicht im Plattformpreis und nicht auf der Airbnb/Booking-Rechnung enthalten und wird bar bei Abreise mit der Kurtaxe gezahlt. + per **A3**. *(Open: are cats also excluded in L and UO flats?)*
> Only if a guest questions the fee: Sie deckt den zusätzlichen Reinigungsaufwand (Haare, Böden, Polster); anderswo sind bis zu 20 € pro Tier üblich.

**B10 — #141 Verlängerung** (n=35)
> Das Angebot kommt automatisch an alle Gäste und gilt nur, wenn dieselbe Wohnung direkt davor oder danach frei ist – das ist oft nicht der Fall. Das Team prüft die Verfügbarkeit und nennt den Preis; UMI sagt keine Verlängerung zu. Bei Umzug in eine andere Wohnung gibt es keinen Rabatt; die Hundegebühr wird nicht reduziert. Wer nicht verlängert, bekommt nichts erstattet. Die automatische Abreisenachricht kommt trotzdem mit dem alten Datum und kann ignoriert werden. Late Check-out gibt es höchstens bis 12 Uhr; wer länger bleiben will, bucht die nächste Nacht und reist trotzdem am Abend ab. + percentage per **A5**.

**B11 — #136 Check-out** (n=6 + 182 sends)
> Putzen müsst ihr nicht. Benutzte Betten abziehen (die Wäsche darf auf dem Bett liegen bleiben), unbenutzte Betten nicht abziehen, Müll rausbringen; leere Glasflaschen dürfen stehen bleiben, Altpapier bitte mit raus.
> 🏠 **Sonnenhof:** es gibt keine Spülmaschine – benutztes Geschirr abwaschen (#136 says "Spülmaschine starten").

**B12 — #19 Gepäck** (n=8)
> Gepäck ins Innere der Wohnung vor 16 Uhr gilt als früher Check-in (kostenlos nur, wenn zufällig schon fertig geputzt). 🏠 Rathmannsdorf: Hausflur an der Hintertür. 🏠 H-Wohnungen: im Gastraum hinter der linken Schiebetür neben dem Ofen (nicht abschließbar). 🏠 Sonnenhof: ab 10 Uhr vor das Zimmer. 🏠 Am Anger 11: Fahrräder oben im 2. OG im Flur. Alles ohne Haftung. + **A9**.

**B13 — #139 Zugang je Wohnung** (n=12)
- 🏠 Am Anger 11: zwei Codes — einer für das Haus, einer für die Schlüsselbox der Wohnung; der Haus-Code steht ganz unten in der Gästemappe.
- B1: Codeschloss an der Tür (rechte Tür im UG, beschriftet „B1"), Code eingeben, Griff nach links drehen.
- B2: Codeschloss an der Tür, öffnet nach Code-Eingabe selbst; von außen abschließen mit dem kleinen Pfeil unten rechts.
- F2 (maybe all F): Schlüssel hängt in den Schlüsselboxen im Haus gegenüber (Nr. 26, links an der Wand), dann in Nr. 27 im 1. OG die Tür „F2".
- 🏠 Hertigswalder Str. 27: gemeinsamer Hauseingang, alle Wohnungstüren mit Kürzel beschriftet, Straßenbeleuchtung.
- Global: Schlüsselbox wieder schließen — C-Taste drücken und Code erneut eingeben. Die Box darf während des Aufenthalts offen bleiben. Pro Wohnung gibt es nur einen Schlüssel; getrennt unterwegs → Schlüssel in die Box legen.
- S-Wohnungen → **A23**.

**B14 — #33 Schlüsselrückgabe** (n=3)
> Bis 10 Uhr zurück in die Schlüsselbox (Box offen lassen). Klappt die Box nicht, Schlüssel von außen in die Tür stecken und kurz schreiben. + **A19**.

**B15 — #48 / #41 / #89 Kurtaxe & Gästekarte** (n≈30)
> Es gibt ein Formular für alle Personen der Wohnung; der Durchschlag ist die Gästekarte. Anleitung und Preise stehen auf dem gelben Zettel auf dem Tisch. Kurtaxe nur für die tatsächlich anwesenden Personen und Nächte (+ **A12**); bei früherer Abreise das tatsächliche Datum eintragen. Fehlt die Gästekarte, Bescheid geben. Ohne Bargeld: an Urlaubsmagie GmbH überweisen, voller Name + „Kurtaxe" im Verwendungszweck — vorher fragen wir nach Personenzahl und Alter und schicken zu jeder Überweisung eine Rechnung. Kartenzahlung gibt es nicht; die Übernachtung selbst läuft über die Plattform, bar nehmen wir dafür nichts.
> 🏠 Rathmannsdorf: die Gästekarten liegen im Drucker im Treppenhaus EG; dafür brauchen wir beim Online Check-in auch die Geburtsdaten der Kinder.
> 🏠 Sebnitz: wer vor dem Check-in schon Bus und Bahn nutzen will, fragt in der Zentrale (Nr. 26, Personaltür) nach einer Gästekarte.

**B16 — #45 Waschküche & Handtücher** (n=8)
> Die Waschküche in der Hertigswalder Str. 26 (Keller) dürfen Gäste aller Häuser täglich 18–22 Uhr nutzen, ganzjährig; in Rathmannsdorf gibt es keine Waschmaschine. Einen täglichen Handtuchwechsel gibt es nicht; in Sebnitz holt ihr frische Handtücher im Keller von Nr. 26 und legt die benutzten links in den Wäschekorb. (Weg durch die Haustür mit Code — code stays internal per #123.) + **A20**.

**B17 — #44 Wanderpass** (n=10)
> 9 vorgeschlagene Touren, pro Tour ein Stempel; wer alle hat, bekommt von uns die Wandernadel der Sächsischen Schweiz. Nur auf Deutsch. 5 € bar bei Abreise. Spontan kaufen im Büro Hertigswalder Str. 26 (werktags ab 9 Uhr) oder in der Touristeninformation Sebnitz (Markt 9); das Team kann ihn auch vorbeibringen.

**B18 — #54 + new: Rechnung** (n=15 + 152 sends)
> Eine Rechnung schicken wir auf Wunsch per E-Mail, auch auf eine Firma (Anschrift, USt-IdNr.). Sie enthält nur die Übernachtung; Hundegebühr, Kurtaxe und Early/Late Check-out stehen nicht darauf, weil sie sich im Urlaub noch ändern – wer eine Rechnung mit diesen Posten braucht, sagt kurz Bescheid.
> Internal note: Booking.com "Rechnung per E-Mail beim Check-out" requests were missed once (guest complained 2 weeks later).

**B19 — #131 / #72 / #76 Sonnenhof** (n=14)
> Im Sonnenhof gibt es aktuell kein Restaurant, kein Frühstück und kein Abendessen – die ehemalige Hotelküche wird noch renoviert. Die Zimmer haben Kühlschrank, Mini-Backofen, Wasserkocher und Kaffeemaschine, aber keine Herdplatte und keine Gemeinschaftsküche. Tipps: Frühstück in der Ottendorfer Hütte, Abendessen in der Kräuterbaude. Einen Kinderstuhl gibt es nicht. Das WLAN-Passwort steht im Zimmer. Fahrradverleih in Rathen und Bad Schandau.
> **Fix #72:** it says none of our places is in Hinterhermsdorf — the Sonnenhof is.

**B20 — #108 Fernseher** (n=3)
> Wir stellen keine Streaming-Accounts mehr bereit – bitte mit dem eigenen Account anmelden (auch wenn noch jemand eingeloggt ist). B8: kein Fire TV Stick mehr, nur SAT; eine noch ausliegende Fire-TV-Anleitung ist veraltet.

**B21 — #147 WLAN erste Hilfe** (n=3)
> Router ausstecken, 5 Sekunden warten, wieder einstecken. Wird das Netz nicht angezeigt, manuell hinzufügen („Netzwerk hinzufügen"). Hilft das nicht, melden. + **A18** for GK.

**B22 — #81 Probleme sofort melden** (n=3)
> Bitte Probleme direkt während des Aufenthalts melden (Sauberkeit, Lärm, Rauch von Nachbarn, Defekte, Hitze) – dann können wir sofort nachreinigen, Nachbarn ansprechen, reparieren oder z. B. einen Ventilator bringen. Nach der Abreise gemeldete Punkte können wir vor Ort nicht mehr lösen.

**B23 — #52 / #144 / #145 Umbuchen & Stornieren** (n=11)
> Stornieren oder Daten ändern macht der Gast selbst über Airbnb bzw. Booking.com nach seinen Stornobedingungen – wir können das nicht für ihn tun, und storniert der Gastgeber, gibt es eine Strafe. Ist die Wohnung im neuen Zeitraum belegt, suchen wir gern eine andere und fragen, was wichtig ist (Schlafzimmer, Küche, Parkplatz, Garten, Balkon, Ort, Haustiere).

**B24 — smaller extensions**
- #70: Toilettenspülung läuft dauernd → Betätigungsplatte vorsichtig abnehmen, klemmende Taste prüfen; sonst Hausmeister.
- #57: Richtige Badeseen gibt es kaum; Alternativen Hallenbad Neustadt, Elbe, Kiesgrube Leuben (Dresden).
- #143: Top-Ziele (Bastei + Schwedenlöcher, Kuhstall + Himmelsleiter, Festung Königstein, Hockstein/Wolfsschlucht, Felsenlabyrinth Langenhennersdorf, Lilienstein, Dresden). Der WhatsApp-Kanal ist nur auf Deutsch.
- #43: Fahrräder/E-Bikes auch im Touristenzentrum Bad Schandau; Auto für einen Tag mieten geht nur in Dresden.
- #49 (internal, n=1): Hitze im Dachgeschoss ist kein Grund für kostenlosen Umzug/Storno (Lage ist aus Inserat ersichtlich); Tipps: nachts lüften, abdunkeln, Ventilator.
- #17: Hochstuhl 5 € — only one mention (Feb), **check before adding**.

---

## C. New guest-facing entries

**C1 Rauchverbot** (n=2) — In allen Unterkünften gilt striktes Rauchverbot, auch am geöffneten Fenster. *(KB has no smoking rule at all.)*

**C2 Zerbrochenes & Schäden** (n=10) — Geht ein Glas oder Geschirr kaputt, kostet das nichts – kurz Bescheid geben (und sagen, ob Scherben z. B. im Teppich gelandet sind). Bei größeren Gegenständen (z. B. Lampe) klärt das Team eine Erstattung.

**C3 Vergessene Gegenstände** (n=15) — Das Team schaut nach, bevor etwas zugesagt wird. Abholen bis 10 Uhr am Abreisetag oder im Büro Hertigswalder Str. 26, werktags 9–15 Uhr. Versand per Post gegen Überweisung (Gebühr → **A16**). Lebensmittel werden bei der Reinigung entsorgt.

**C4 Preis & Personenzahl** (n=4) — Der Preis gilt für die ganze Wohnung: Kommen weniger Personen, gibt es keinen Rabatt; innerhalb der Grundbelegung ändert sich nichts. Die gebuchte Personenzahl gilt für den ganzen Aufenthalt. Tagesbesuch ohne Übernachtung kostet nichts. Eine Reinigungsgebühr vor Ort gibt es nicht.

**C5 Automatische Nachrichten** (n=11) — Die Abreise-Infos kommen automatisch am Tag vor der gebuchten Abreise (bei einer Nacht also schon am Anreisetag, nach einer Verlängerung trotzdem mit dem alten Datum); das Verlängerungsangebot geht an alle. Passt eine Nachricht nicht, einfach ignorieren.

**C6 Kontakt** (n=9 + 188 sends) — Bei Fragen erreicht ihr uns am schnellsten per WhatsApp (Booking.com-Nachrichten kommen manchmal verspätet) oder per E-Mail an buchungsanfrage.urlaubsmagie@googlemail.com. Number / emergency line → **A17**.

**C7 Mülltonnen** 🏠 (n=8)
- Bergblick 11: links neben dem Haus.
- Hainersdorfer Weg 8: im braunen Schuppen, extra Schlüssel am Bund (fehlt er, darf der Müll in der Wohnung bleiben).
- Hertigswalder Str. 26: links neben dem Schuppen beim Parkplatz.
- Hertigswalder Str. 27: bei den Parkplätzen.
- Hertigswalder Str. 22: direkt beim Parkplatz.

**C8 Fahrräder** 🏠 (n=4) — Am Anger 11: nicht in die Wohnung (Teppich), draußen oder im Garten anschließen. Sebnitz: im Gemeinschaftsgarten anschließen. Rathmannsdorf: hinter dem Haus. GK2: kein Stellplatz. Alles ohne Gewähr.

**C9 Staubsauger & Putzzeug** (n=3) — In den Wohnungen gibt es keinen Staubsauger, nur einen Besen. 🏠 Sebnitz: Akku-Staubsauger im Vorraum vom Lager im Haupthaus Nr. 26, ab 16 Uhr, danach zurückhängen; Wischeimer im Flurschrank vor dem Kellerabgang.

**C10 Lebensmittel vor dem Check-in** (n=3) — Ausnahmsweise dürft ihr Einkäufe vorab in den Kühlschrank stellen, wenn der Schlüssel schon wieder in der Box hängt – danach bitte gleich wieder raus, damit geputzt werden kann.

**C11 Anreise ohne Auto** (n=6)
- Sebnitz (Nr. 22/26/27): Haltestelle „Sebnitz Busbahnhof", ca. 5 Min. zu Fuß.
- W-Wohnungen: S-Bahn Dresden → Bad Schandau, Bus 260 Richtung Sebnitz bis „Ulbersdorfer Weg", 2 Min. zu Fuß.
- B-Wohnungen: Kirnitzschtalbahn bis Lichtenhainer Wasserfall, dann zu Fuß (mit Gepäck nicht zu empfehlen).
- Lichtenhain: Bushaltestelle an der Neuen Straße; fast alle Wanderparkplätze kosten Geld, der Bus ist mit der Gästekarte kostenlos (→ **A13**).
- Ab Sebnitz: Bus 268 in den Nationalpark, Bus 260 nach Bad Schandau.

**C12 Ausflugstipps** (n≈15) — merge into one "Tipps" entry:
- Wetter: Nieselregen → Wald/Kuhstall (Baude oben); starker Regen → Schwimmbad, Indoor-Hochseilgarten, Festung Königstein, Besucherbergwerk Marie Louise Stolln. Hitze → Schwedenlöcher (schattig, Jacke mit).
- Beste Aussicht: Carolafelsen (hoch durch die Wilde Hölle, runter über die Heilige Stiege; nachmittags starten).
- Kinder: Felsenlabyrinth Langenhennersdorf, Papststein/Gohrisch.
- Mit Hund: Kuhstall, Abkühlen in der Kirnitzsch; Urlaubsmagie hat einen Hundestiegen-Guide mit hundefreundlichen Touren, den wir auf Wunsch in die Wohnung legen.
- 🏠 Ab Lichtenhain: Kuhstall & Himmelsleiter (ca. 10 km, 3–4 Std.), Großer Lichtenhainer Rundweg (ca. 15 km). Ab Sebnitz: Bastei ca. 25 Min., Kirnitzschtal ca. 12 Min. mit dem Auto. Ab Sebnitztal: Sebnitztal/Schwarzbachtal direkt ab der Unterkunft.
- Dresden: Auto nach Bad Schandau, Schiff nach Dresden, S1 zurück (Fahrplan prüfen).
- Wegsperrungen: aktuell auf nationalpark-saechsische-schweiz.de/wegeservice.
- Kahnfahrt Obere Schleuse: 9–16:30 Uhr ohne feste Uhrzeit *(seasonal — check)*.
- Tschechien: Tankstelle direkt hinter dem Grenzübergang Sebnitz (Dolní Poustevna); rund ums Prebischtor meist Kartenzahlung, Wechselstuben in Hřensko mit schlechtem Kurs.

**C13 Einkaufen & Essen abends** (n=3) — Geschäfte meist bis 20 Uhr, sonntags kein Supermarkt offen. Sebnitz: Lidl, Aldi, Edeka, Penny. Rathmannsdorf: Dorfladen (So/Mo zu). Nach 20 Uhr: Osaka Sushi (bis 22), Selale Döner (bis 22), Kirchklause (bis 21), Gasthaus Zum Wanderstübel Hinterhermsdorf (bis 22). *(Stand Juni 2026)*

**C14 Wohnungs-Details** (apartment-scoped, n=1–3 each)
- HW13: bis 10 Personen — 3 Schlafzimmer mit Doppelbett, Schlafcouch in einem Schlafzimmer und im Wohnzimmer; Esstisch für 10 (ausziehbar). Nutzung von Pool & Sauna (B4).
- H6: Dusche, keine Badewanne.
- L5: Filterkaffeemaschine; kleines Gefrierfach, keine Gefriertruhe.
- GK3: Backofen, keine Mikrowelle. UO1: Herd und Backofen, keine Mikrowelle.
- F2: Spülmaschinentabs und Kaffee im Flurschrank dürfen benutzt werden.
- F4: keine Teekanne.
- S2: 3 Sätze Bettwäsche, das kleine Sofa ist ausklappbar.
- HW1: 3 Töpfe, 2 Pfannen, Backofen.
- W6: Kinderbett im Flur (vom Haupteingang rechts), Matratze oben auf dem Kleiderschrank.
- 🏠 Am Anger 11: im Dunkeln schwer zu finden — vorher die kleine Zufahrtsstraße auf Google Maps ansehen.
- 🏠 Hertigswalder Str. 27: Treppenhaus und Eingang reinigt die Hausverwaltung, nicht wir.
- 🏠 Grills: BA2 Holzkohlegrill im Garten (nicht auf dem Balkon, Kohle mitbringen; *exact spot unknown to the team*), S-Wohnungen/S3 Grill auf der Terrasse, H-Wohnungen Grill (Kohle mitbringen), W-Wohnungen Feuerstelle (Holz mitbringen) + Holzkohlegrill erlaubt, Bergblick Grill + Gemeinschaftsgarten für alle B, Sebnitz Grillplatz auf der Terrasse am Haupthaus.

**C15 Pakete** (n=1) — Vor der Anreise darf ein Paket an uns geschickt werden (z. H. Gastname + Wohnung); bitte kurz Bescheid geben. Address → **A24**.

**C16 Ostereiersuche** (seasonal, n=6 + 36 sends) — Jedes Jahr zu Ostern kostenlose Ostereiersuche im Gemeinschaftsgarten Hertigswalder Str. 26 für Gäste aller Häuser; Anmeldung mit Anzahl und Alter. *Only add around Easter, with that year's date.*

**C17 Unsure — check before adding:** Leitungswasser trinkbar (only L8), Ventilator in allen Wohnungen (only HW4B, H1), Parken am Anreisetag schon morgens (UO0) vs "ab 12 Uhr" (B6).

---

## D. New internal entries (team only, never in the guest prompt)

- **D1 Airbnb full refund:** easiest via AirCover — guest files it, gets everything incl. Airbnb fee; then ask when they leave (cleaning plan). Guest leaves at once and refuses the offered alternative → refer to Airbnb support/AirCover, no own refund.
- **D2 Airbnb pre-approval:** guest can't book / asks first (e.g. dog) → send pre-approval; valid 24 h; dog fee stays cash on site.
- **D3 Allergy "was a dog here before?"** → check previous booking in Smoobu; inform the guest if a dog booking is added before arrival.
- **D4 Pet fee complaints:** explain Booking.com only allows "Gebühren können anfallen", the amount is in the listing and confirmation, free cancellation may still be possible. Goodwill max. the 8 € rate; full waiver happened once (02-21) — team decides, UMI never offers.
- **D5 Kurtaxe not found after departure:** first ask whether paid another way / business trip; otherwise ask for transfer of the exact amount with booking name (template exists).
- **D6 Parking space taken:** ask for the licence plate; meanwhile the guest may use an HW space that is free that day (check Smoobu). Haupthaus 26: 4 spaces for guests with a parking card — ask which cards are in the cars.
- **D7 Guest folder unreachable:** team sends check-in info (key box, code, parking) in the chat — a human, after checking name and booking, never UMI.
- **D8 Long-stay / workers inquiry:** ask number of persons, exact dates, phone number, shared beds ok?
- **D9 Mattress protectors:** washed weekly, in between only when visibly dirty (may change after a complaint).
- **D10 Review request:** sent automatically after departure (Booking 10 points, Airbnb 5 stars, Sonnenhof own text); a critical reply to it is a post-departure complaint (#109).
- **D11 Airbnb percentage discounts** apply to the payout after commission, not the guest price — name a fixed amount.
- **D12 Emergency bedding bags:** W flats behind the W6 entrance at the cupboard; H flats downstairs in the guest room behind the counter; Sebnitz laundry basement Nr. 26. Report every use in the cleaning plan. *(W6 door code: #123 vs #119 disagree — check.)*
- **D13 Codes missing from the code list:** GK2 key box (in #118 under GK), B1 door lock description.
- **D14 BA2 Wi-Fi** runs over the Giga Cube (#147 lists Giga Cubes only for UO2/UO3).

---

## E. Do not add (temporary or unverified)

- R3 bathtub broken (Apr 2026), UT awning off (Jul 2026), HW13 bedroom ceiling light broken (Mar 2026), H2 fridge clicking — state, not knowledge; check whether fixed.
- Trail closures status (Sep 2026) — only the Wegeservice link (C12).
- Easter 2026 dates.
- "Whirlpool" — see A25.

## Follow-ups outside the KB

- **Template vs KB pet fee (A3)** and **extension %** (A5): whichever wins, one side needs editing in Smoobu.
- Guest folder: Famzi folder shows the TV guide where the Kurtaxe price list should be; GK Wi-Fi details differ between room and folder; Hertigswalder 26 key-return sign vs folder.
- B2 door lock didn't engage twice in July. BA2 grill location unknown to the team. Sauna pellets ran out once.
- PayPal requests in June–August got no answer on PayPal at all — confirm A2 so UMI stops offering it.

## Budget

Guest-facing global KB today: **26.6k chars** (29.6k incl. the 7 scoped rows) of the 45k full-KB budget. B+C global text adds roughly **8–10k** → ~36k, still under the budget. Building/apartment rows (🏠) only enter the prompt for chats in that building, so they don't count against the global size — which is why the prerequisite matters.
