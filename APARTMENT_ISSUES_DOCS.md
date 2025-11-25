# 🔧 Aufgabenliste für Wohnungsprobleme - Dokumentation

## Übersicht

Eine neue Seite wurde hinzugefügt, um häufig erwähnte Probleme in Gästebewertungen zu verwalten. Diese Seite dient als Aufgabenliste zur Verfolgung und Behebung von Wohnungsproblemen.

## Neue Komponenten

### 1. Template: `apartment_issues.html`
- **Pfad**: `/templates/apartment_issues.html`
- **Route**: `/apartment-issues`
- **Funktion**: Zeigt eine interaktive Liste aller Wohnungen mit deren Problemen

### 2. Flask-Routen in `app.py`

#### Route: `/apartment-issues`
- **Methode**: GET
- **Funktion**: Rendert das HTML-Template für die Aufgabenliste
- **Rückgabewert**: Vollständiges HTML mit UI

#### Route: `/api/apartment-issues`
- **Methode**: GET
- **Funktion**: API-Endpoint zur Abfrage der Probleme
- **Datenquelle**: `C:\Users\admin\n8n-docker\files\GeneralReviews.json`
- **Rückgabewert**: JSON mit Array von Wohnungen und deren Problemen

### 3. Datenquelle
- **Datei**: `GeneralReviews.json`
- **Pfad**: `C:\Users\admin\n8n-docker\files\GeneralReviews.json`
- **Format**: JSON mit verschachtelter Struktur
  ```json
  [{
    "index": 0,
    "message": {
      "content": {
        "wohnungen": [
          {
            "wohnung": "S1",
            "probleme": [
              {
                "beschreibung": "Sauberkeit: Allgemeine Mängel",
                "erwähnungen": 11
              }
            ]
          }
        ]
      }
    }
  }]
  ```

## Features

### ✨ Hauptfunktionen

1. **Automatisches Laden von Daten**
   - Lädt Probleme automatisch aus der JSON-Datei
   - Zeigt alle Wohnungen mit ihren Problemen

2. **Interaktive Aufgabenverwaltung**
   - Probleme als Checkbox markierbar
   - Status persistiert im Browser (localStorage)
   - Visuelles Feedback: abgeschlossene Probleme werden durchgestrichen

3. **Filteroptionen**
   - **Alle**: Zeigt alle Probleme
   - **Ausstehend**: Zeigt nur unvollendete Probleme
   - **Erledigt**: Zeigt nur abgeschlossene Probleme

4. **Priorisierung nach Häufigkeit**
   - Zeigt die Anzahl der Erwähnungen für jedes Problem
   - Farbcodierung nach Schweregrad:
     - 🔴 **Hoch** (≥5 Erwähnungen)
     - 🟠 **Mittel** (3-4 Erwähnungen)
     - 🟡 **Niedrig** (<3 Erwähnungen)

5. **Statistiken**
   - Gesamtzahl der Wohnungen
   - Gesamtzahl der Probleme
   - Anzahl der erledigten Probleme

### 🎨 Design-Features

- **Responsive Layout**: Optimiert für Handy, Tablet, Laptop und Desktop
- **Deutsche Benutzeroberfläche**: Vollständig auf Deutsch
- **Modernes Design**: Gradient-Header, runde Ecken, Schatten
- **Navigation**: Verlinkung zur Bewertungsseite

### 💾 Persistenz

- **localStorage**: Abgeschlossene Probleme werden lokal gespeichert
- **Keine Serverseite**: Der Status wird nicht auf dem Server gespeichert (nur im Browser)
- **Export-Funktion**: Erlaubt Export der Problemliste als JSON

### 🔄 Aktionen

1. **Checkbox anklicken**: Problem als erledigt/ausstehend markieren
2. **Löschen (X-Button)**: Problem aus der abgeschlossenen Liste entfernen
3. **Exportieren**: Aktuelle Problemliste als JSON-Datei herunterladen
4. **Alle zurücksetzen**: Setzt alle Probleme auf ausstehend zurück

## API-Referenz

### GET `/api/apartment-issues`

**Response (200 OK)**:
```json
{
  "wohnungen": [
    {
      "wohnung": "S1",
      "probleme": [
        {
          "beschreibung": "Sauberkeit: Allgemeine Mängel",
          "erwähnungen": 11
        },
        {
          "beschreibung": "Defekte/Mängel an Geräten/Möbeln",
          "erwähnungen": 6
        }
      ]
    }
  ]
}
```

**Response (404 Not Found)**:
```json
{
  "error": "GeneralReviews.json nicht gefunden",
  "wohnungen": []
}
```

**Response (500 Server Error)**:
```json
{
  "error": "Fehlermeldung",
  "wohnungen": []
}
```

## JavaScript-Funktionen

### Kern-Funktionen

- `loadData()`: Lädt Probleme von der API
- `renderContent()`: Rendert die UI basierend auf aktuellem Filter
- `toggleIssue(issueId)`: Markiert Problem als erledigt/ausstehend
- `exportData()`: Exportiert die aktuelle Problemliste als JSON
- `resetAll()`: Setzt alle Probleme zurück
- `getCompletedIssues()`: Abrufen abgeschlossener Probleme aus localStorage

### Storage-Management

- **Storage-Key**: `apartment_issues_completed`
- **Format**: JSON-Array von Issue-IDs
- **Struktur**: `["wohnung_base64EncodedDescription", ...]`

## Styling

### CSS-Klassen

- `.apartment-section`: Container für jede Wohnung
- `.problem-item`: Einzelnes Problemelement
- `.problem-item.completed`: Stil für erledigte Probleme
- `.problem-checkbox`: Checkbox-Styling
- `.apartment-code`: Wohnungskennzeichen-Badge
- `.badge-severity`: Schweregrad-Badge

### Farben

- **Primär**: #667eea (Lila)
- **Sekundär**: #764ba2 (Dunkelviolett)
- **Hintergrund**: Weiß mit Gradient-Header
- **Erfolg**: #27ae60 (Grün)
- **Fehler**: #e74c3c (Rot)

## Browser-Kompatibilität

- ✅ Chrome/Chromium (empfohlen)
- ✅ Firefox
- ✅ Safari
- ✅ Edge
- ⚠️ IE nicht unterstützt

## Bekannte Limitationen

1. **Nur im Browser persistiert**: Daten werden nicht auf dem Server gespeichert
2. **Nicht synchronisiert**: Änderungen werden nicht zwischen Geräten synchronisiert
3. **Statische Daten**: Neue Probleme müssen manuell in der JSON-Datei aktualisiert werden

## Zukünftige Verbesserungen

- [ ] Datenbank-Backend für Persistenz
- [ ] Multi-User-Synchronisation
- [ ] Zeitstempel für erledigte Probleme
- [ ] Notizen hinzufügen pro Problem
- [ ] Fälligkeitsdaten setzen
- [ ] Zuweisungen an Benutzer
- [ ] Benachrichtigungen bei hohen Prioritäten

## Installation/Setup

Die Seite ist bereits installiert und sofort einsatzbereit:

1. Starten Sie Flask: `python app.py`
2. Öffnen Sie `http://localhost:5000/apartment-issues` im Browser
3. Die Probleme werden automatisch aus der GeneralReviews.json geladen

## Fehlerbehandlung

Falls die Seite nicht ladet:

1. **GeneralReviews.json nicht gefunden**
   - Überprüfen Sie den Pfad: `C:\Users\admin\n8n-docker\files\GeneralReviews.json`
   - Stellen Sie sicher, dass die Datei existiert

2. **API-Fehler**
   - Überprüfen Sie die Browser-Konsole (F12) für Fehler
   - Prüfen Sie, ob Flask läuft

3. **Daten laden sich nicht**
   - Aktualisieren Sie die Seite (F5)
   - Löschen Sie den Browser-Cache

## Kontakt/Support

Für Fragen oder Probleme: Überprüfen Sie die Logs in der Flask-Konsole.
