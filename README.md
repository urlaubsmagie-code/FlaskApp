# Gästebewertungen Slideshow - Apartment HW3B

Automatische Slideshow-Präsentation der Airbnb-Gästebewertungen für das Apartment HW3B in deutscher Sprache.

## Funktionen

- **Automatische Slideshow**: Zeigt jeden Kommentar für 30 Sekunden
- **Vollbild-Präsentation**: Optimiert für TV/Raspberry Pi
- **Keine Bedienung erforderlich**: Komplett automatisch
- **HW3B-Branding**: Deutlich sichtbare Apartment-Identifikation am Ende jeder Bewertung
- **Adaptiver Text**: Passt Schriftgröße automatisch an Textlänge UND Bildschirmgröße an
- **Vollständige Anzeige**: Alle Inhalte (Text, Datum) immer komplett sichtbar
- **Vollresponsiv**: Optimiert für Handy, Tablet, Laptop und TV-Bildschirme
- **Deutsche Benutzeroberfläche**

## Technische Details

- **Backend**: Flask (Python)
- **Frontend**: HTML5, Bootstrap 5, JavaScript
- **Datenquelle**: JSON-Datei mit Airbnb-Bewertungen
- **Stil**: Font Awesome Icons, Custom CSS

## Installation und Ausführung

1. **Voraussetzungen**: Flask muss installiert sein
   ```bash
   pip install flask
   ```

2. **Anwendung starten**:
   ```bash
   cd C:\Users\admin\Server\FlaskApp
   python app.py
   ```

3. **Zugriff**: 
   - Lokal: http://127.0.0.1:5000
   - Netzwerk: http://192.168.178.188:5000
   
   Die Slideshow startet automatisch beim Zugriff.

## Dateistruktur

```
FlaskApp/
│
├── app.py                 # Haupt-Flask-Anwendung
├── templates/
│   └── index.html        # HTML-Template (Deutsch)
├── README.md             # Diese Dokumentation
└── (static/)             # Für zusätzliche CSS/JS-Dateien (optional)
```

## Datenquelle

Die Bewertungsdaten werden aus folgender Datei gelesen:
`C:\Users\admin\n8n-docker\files\datos.json`

## Funktionsübersicht

### Hauptfunktionen:
- **Bewertungsstatistiken**: Durchschnittsbewertung, Gesamtanzahl, Verteilung
- **Filterfunktionen**: Nach Bewertung und Suchbegriff
- **Sortieroptionen**: Datum (neu/alt), Bewertung (hoch/niedrig)
- **Responsive Layout**: Optimiert für Desktop und Mobile

### Endpunkte:
- `GET /`: Automatische Slideshow-Präsentation
- `GET /api/reviews`: JSON-API für alle Bewertungen
- `GET /api/stats`: JSON-API für Statistiken

## Slideshow-Details

Die Anwendung zeigt automatisch alle Bewertungen als Slideshow:

### Eigenschaften:
- **Automatischer Wechsel**: Alle 30 Sekunden
- **Vollbild-Design**: Optimiert für TV/Raspberry Pi
- **Fortschrittsbalken**: Zeigt verbleibende Zeit der aktuellen Folie
- **HW3B-Apartment-Info**: Deutlich sichtbar bei jeder Bewertung
- **Intelligente Textanpassung**: Passt sich an Textlänge UND Bildschirmgröße an
- **Multi-Device-Unterstützung**: 
  - Handy/Tablet (bis 768px): Kompakte Darstellung
  - Laptop (769px-1399px): Ausgewogene Größe
  - TV/Große Monitore (ab 1400px): Optimale TV-Darstellung
- **Keine Bedienung**: Komplett automatisch, keine Buttons oder Menüs

## Anpassungen

Um andere JSON-Dateien zu verwenden, ändern Sie die `JSON_FILE_PATH` Variable in `app.py`:

```python
JSON_FILE_PATH = r"C:\Pfad\zu\Ihrer\datei.json"
```

## Erweiterte Konfiguration

Für Produktionsumgebungen:
- Verwenden Sie einen WSGI-Server (z.B. Gunicorn)
- Konfigurieren Sie entsprechende Firewall-Regeln
- Aktivieren Sie HTTPS
- Verwenden Sie Umgebungsvariablen für Konfiguration

## Hinweise

- Die Anwendung läuft standardmäßig im Debug-Modus
- Alle Bewertungen werden in deutscher Sprache angezeigt
- Bilder der Reviewer werden automatisch geladen (mit Fallback)
- Die Anwendung ist für den lokalen/internen Gebrauch optimiert