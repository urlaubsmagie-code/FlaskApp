# 🎯 Guía de Uso - Airbnb Reviews Scraper

## 📦 Instalación

### Paso 1: Instalar Playwright
```bash
pip install -r requirements_scraper.txt
```

### Paso 2: Instalar navegadores de Playwright
```bash
playwright install chromium
```

## 🚀 Uso Rápido

### Opción A: Usar el script de ejemplo (Recomendado)

1. Edita `ejemplo_uso_scraper.py` y agrega tus URLs:
```python
ROOM_URLS = [
    "https://www.airbnb.com/rooms/12937",
    "https://www.airbnb.com/rooms/54321",
    # Agrega más aquí
]
```

2. Ejecuta:
```bash
python ejemplo_uso_scraper.py
```

### Opción B: Uso desde código

```python
from airbnb_scraper_robust import AirbnbReviewsScraper

# Scraping simple
with AirbnbReviewsScraper(headless=False) as scraper:
    result = scraper.scrape_room("https://www.airbnb.com/rooms/12937")
    print(f"Reviews obtenidas: {result['total_reviews']}")
    
    # Ver reviews
    for review in result['reviews']:
        print(f"{review['author']}: {review['text'][:100]}...")
```

## ⚙️ Configuración

### Parámetros del Scraper

```python
AirbnbReviewsScraper(
    headless=False,  # True = invisible, False = ver navegador
    timeout=30000    # Timeout en milisegundos (30 segundos)
)
```

### Parámetros de scrape_room()

```python
scraper.scrape_room(
    room_url="https://...",
    max_scrolls=10,          # Scrolls para cargar contenido
    max_show_more_clicks=15  # Clics en "Mostrar más"
)
```

## 📊 Formato de Salida

El scraper genera un archivo JSON con esta estructura:

```json
{
  "url": "https://www.airbnb.com/rooms/12937",
  "scraped_at": "2025-10-22T12:30:00",
  "success": true,
  "room_title": "Beautiful apartment in Madrid",
  "total_reviews": 45,
  "reviews": [
    {
      "id": 1,
      "text": "Great place! Very clean and comfortable...",
      "author": "John Doe",
      "date": "October 2024",
      "rating": "5.0 stars",
      "extracted_at": "2025-10-22T12:30:05"
    }
  ]
}
```

## 🔧 Solución de Problemas

### Error: "playwright not found"
```bash
pip install playwright
playwright install chromium
```

### Error: "No reviews found"
- Verifica que la URL sea correcta
- Asegúrate de que la habitación tenga reviews
- Aumenta `max_scrolls` a 15-20
- Ejecuta con `headless=False` para ver qué está pasando

### Error: "Timeout"
- Aumenta el timeout: `AirbnbReviewsScraper(timeout=60000)`
- Verifica tu conexión a internet
- Airbnb puede estar lento o bloqueando requests

### Muy pocas reviews obtenidas
- Aumenta `max_scrolls` (por ejemplo, a 20)
- Aumenta `max_show_more_clicks` (por ejemplo, a 30)
- Añade delays más largos editando el código

## 💡 Consejos para Máxima Efectividad

1. **Usa headless=False primero** para ver qué está haciendo el scraper
2. **Espera entre requests** si scrapeando muchas URLs (ya incluido automáticamente)
3. **Guarda logs** - revisa `airbnb_scraper.log` si hay errores
4. **No abuses** - demasiados requests seguidos pueden resultar en bloqueo temporal

## 📈 Uso Avanzado

### Scraping masivo con reintentos

```python
from airbnb_scraper_robust import AirbnbReviewsScraper
import time

urls = ["url1", "url2", "url3", ...]
failed_urls = []

with AirbnbReviewsScraper(headless=True) as scraper:
    for url in urls:
        result = scraper.scrape_room(url, max_scrolls=15)
        
        if not result['success']:
            failed_urls.append(url)
            print(f"❌ Falló: {url}")
        else:
            print(f"✅ OK: {result['total_reviews']} reviews")
        
        time.sleep(5)  # Pausa entre requests

# Reintentar URLs fallidas
if failed_urls:
    print(f"\n🔄 Reintentando {len(failed_urls)} URLs fallidas...")
    with AirbnbReviewsScraper() as scraper:
        for url in failed_urls:
            result = scraper.scrape_room(url)
            print(f"Reintento: {result['success']}")
```

### Exportar a CSV

```python
import json
import csv

# Leer JSON
with open('mis_reviews_airbnb.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Escribir CSV
with open('reviews.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['URL', 'Título', 'Autor', 'Fecha', 'Rating', 'Texto'])
    
    for room in data:
        for review in room['reviews']:
            writer.writerow([
                room['url'],
                room.get('room_title', ''),
                review.get('author', ''),
                review.get('date', ''),
                review.get('rating', ''),
                review.get('text', '')
            ])

print("✅ CSV creado: reviews.csv")
```

## 🎓 Para Proyectos Universitarios

### Análisis de Sentimientos
```python
# Extraer solo textos de reviews para análisis
texts = []
for result in results:
    for review in result['reviews']:
        texts.append(review['text'])

# Ahora puedes usar estos textos con:
# - NLTK para análisis de sentimientos
# - TextBlob para polaridad
# - spaCy para NLP avanzado
```

### Estadísticas Básicas
```python
# Contar reviews por habitación
for result in results:
    print(f"{result['room_title']}: {result['total_reviews']} reviews")

# Palabras más comunes
from collections import Counter
import re

all_text = ' '.join([r['text'] for result in results for r in result['reviews']])
words = re.findall(r'\w+', all_text.lower())
common_words = Counter(words).most_common(20)
print(common_words)
```

## ⚠️ Consideraciones Legales

- ✅ Los datos públicos de Airbnb se pueden scraper para uso académico
- ✅ Respeta el rate limiting (pausas entre requests)
- ❌ No uses datos personales indebidamente
- ❌ No redistribuyas datos comercialmente sin permiso

---

## 📞 Ayuda

Si tienes problemas:
1. Revisa `airbnb_scraper.log`
2. Ejecuta con `headless=False` para debug visual
3. Verifica que tu versión de Python sea ≥ 3.8
