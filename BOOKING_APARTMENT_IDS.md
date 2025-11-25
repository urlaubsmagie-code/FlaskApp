# 🏠 Mapeo Completo de Apartamentos Booking

## 📊 Resumen General

**Total de Apartments encontrados**: 25  
**Total de Reviews analizadas**: 180  
**Rango de Rating**: 7.0 - 9.4/10  
**Reviews por Apartamento**: 4-61

---

## 🔍 Tabla Completa - Todos los Apartamentos

| CÓDIGO | HOTEL_ID | REVIEWS | RATING | HABITACIONES | URL |
|--------|----------|---------|--------|--------------|-----|
| **UNKNOWN** | 13298314 | **61** | 8.38 | 1BR, 1 Sala, 2BR | W6 - gemutliche-wohnung-in-lichtenhain |
| **F0** | 12249141 | 5 | **9.2** | 1BR | Pequeña wohnung |
| **UO0** | 13130996 | 5 | **9.4** | 2BR | Uo0 - wohnung fur bis zu 6p |
| **HW2B** | 10758425 | 5 | 9.0 | 1 Sala | Wohlfuhlwohnung |
| **W2** | 12941184 | 5 | 9.0 | 1BR | Im herzen des elbsandsteingebirges |
| **B6** | 12412050 | 5 | 8.8 | 1BR | Mit balkon mit ausblick |
| **S3** | 10649367 | 5 | 8.8 | 1 Sala | Fusslaufig ins kirnitzschtal |
| **HW4B** | 11623852 | 5 | 8.4 | 2BR | Zentral mit pool/sauna/whirlpool |
| **UNKNOWN** | 13298314 | 61 | 8.38 | - | W6 - gemutliche-wohnung |
| **H6** | 8542367 | 5 | 7.6 | 1 Sala | Sommerparadies mit terrasse |
| **HW3B** | 12209855 | 5 | 7.6 | 2BR | Urlaubsmagie - großes wohnzimmer |
| **UO3** | 10057058 | 5 | 7.6 | 1 Sala | Urlaubsoase mit garten |
| **S2** | 10649329 | 5 | 8.0 | 1 Sala | 50m bis zum wanderweg |
| **Zi2** | 11558797 | 5 | 8.0 | 1BR | Flussblickwohnung mit whirlpool |
| **FAMZI** | 8539276 | 5 | 8.0 | 1 Sala | Familienwohnung fur 3 |
| **UO** | 8539982 | 5 | 8.0 | 1 Sala | Gemutliche urlaubsoase |
| **HW1** | 10056636 | 5 | 8.0 | 1 Sala | Grosse wohnung mit pool |
| **HW1B** | 12217644 | 5 | 7.8 | 2BR | Gemeinschaftsgarten mit pool |
| **S1** | 10649298 | 5 | 7.8 | 1 Sala | Mitten in der sachsischen schweiz |
| **UT** | 11557943 | 5 | 7.4 | 2BR | Urlaubstraum mit whirlpool |
| **HW2** | 9870792 | 5 | 7.4 | 1 Sala | Grosse helle wohnung |
| **H2** | 8542044 | 5 | 7.4 | 1 Sala | Helle gemutliche wohnung |
| **Zi1** | 8535194 | 5 | 7.0 | 1 Sala | Idyllische erholung |
| **F1** | 10404036 | 5 | 7.2 | 1 Sala | Helle wohnung mit pool |
| **L7** | 13986842 | 4 | 8.0 | 1BR | Kleine wohnung am wanderweg |
| **H1** | 8541308 | 5 | 7.2 | 1 Sala | Gemutliche wohnung fur 2 |

---

## 📋 Formato JSON (Para Programas)

Disponible en: `booking_apartments_map.json`

```json
[
  {
    "code": "F0",
    "hotel_id": 12249141,
    "hotel_id_from_url": "12249141",
    "url": "https://www.booking.com/hotel/de/...",
    "review_count": 5,
    "avg_rating": 9.2,
    "room_types": ["One-Bedroom Apartment"],
    "total_reviews_analyzed": 180
  },
  // ... más apartamentos
]
```

---

## 📊 Formato CSV (Para Excel/Analytics)

Disponible en: `booking_apartments_map.csv`

```csv
código,hotel_id,url,reviews,rating_promedio
UNKNOWN,13298314,https://www.booking.com/...,61,8.38
F0,12249141,https://www.booking.com/...,5,9.2
UO0,13130996,https://www.booking.com/...,5,9.4
...
```

---

## 🏆 Ranking por Rating (Mejor a Peor)

### Top 5 - Mejores Calificados ⭐⭐⭐⭐⭐

1. **UO0** - 9.4/10 (2BR, 5 reviews)
   - 🔗 https://www.booking.com/hotel/de/uo0-urlaubsmagie-gemutliche-wohnung-fur-bis-zu-6p.de.html
   
2. **F0** - 9.2/10 (1BR, 5 reviews)
   - 🔗 https://www.booking.com/hotel/de/f0-urlaubsmagie-kleine-voll-ausgestattete-wohnung...
   
3. **HW2B** - 9.0/10 (1 Sala, 5 reviews)
   - 🔗 https://www.booking.com/hotel/de/wohlfuhlwohnung-mit-gemeinschaftsgarten...
   
4. **W2** - 9.0/10 (1BR, 5 reviews)
   - 🔗 https://www.booking.com/hotel/de/w2-urlaubsmagie-im-herzen-des-elbsandsteingebirges...
   
5. **B6** - 8.8/10 (1BR, 5 reviews)
   - 🔗 https://www.booking.com/hotel/de/b6-urlaubsmagie-inmitten-der-sachsischen-schweiz...

### Más Reviews 📊

1. **UNKNOWN (W6)** - 61 reviews, 8.38/10
   - Mayor cantidad de reviews (detalle: no estaba en IDB.txt)

---

## 🔑 IDs Disponibles para tu Proyecto

### Por Tipo de Búsqueda

**Si buscas por CÓDIGO (2-5 caracteres)**:
```
AB, B6, F0, F1, FAMZI, H1, H2, H6, HW1, HW1B, HW2, HW2B, HW3B, HW4B
L7, S1, S2, S3, UT, UO, UO0, UO3, W2, Zi1, Zi2, UNKNOWN
```

**Si buscas por HOTEL_ID (número)**:
```
8535194, 8539276, 8539982, 8541308, 8542044, 8542367
9870792, 10056636, 10057058, 10404036, 10649298, 10649329, 10649367
10758425, 11557943, 11558797, 11623852, 12209855, 12217644, 12249141
12412050, 12941184, 13130996, 13298314, 13986842
```

---

## 🔍 Cómo Usar Esta Información

### 1. En Python
```python
apartments = {
    'F0': {'hotel_id': 12249141, 'rating': 9.2},
    'UO0': {'hotel_id': 13130996, 'rating': 9.4},
    # ... etc
}

# Buscar por código
apt = apartments.get('F0')

# Buscar por hotel_id
for code, data in apartments.items():
    if data['hotel_id'] == 12249141:
        print(f"Encontrado: {code}")
```

### 2. En SQL/Base de Datos
```sql
CREATE TABLE booking_apartments (
    code VARCHAR(10) PRIMARY KEY,
    hotel_id INT,
    url TEXT,
    review_count INT,
    avg_rating DECIMAL(3,1)
);

INSERT INTO booking_apartments VALUES
('F0', 12249141, 'https://...', 5, 9.2),
('UO0', 13130996, 'https://...', 5, 9.4),
-- ... etc
```

### 3. En Excel
- Importar `booking_apartments_map.csv`
- Usa como referencia para análisis

---

## 📝 Observaciones Importantes

1. **UNKNOWN (W6)**
   - Este apartamento tiene 61 reviews pero su URL no estaba en IDB.txt
   - Requiere añadir a IDB.txt: `https://www.booking.com/hotel/de/w6-gemutliche-wohnung-in-lichtenhain.de.html (W6)`

2. **Consistencia**
   - Todos los `hotel_id` extraídos de la URL coinciden con el campo `hotelId` del dataset
   - Útil para validar datos

3. **Tipos de Habitación**
   - 1BR = One-Bedroom Apartment
   - 1 Sala = Single Room
   - 2BR = Two-Bedroom Apartment

4. **Rating**
   - Basado en promedio de todas las reviews del apartamento
   - Rango: 7.0 - 9.4/10

---

## 📂 Archivos Generados

| Archivo | Formato | Uso |
|---------|---------|-----|
| `booking_apartments_map.json` | JSON | Programas, APIs, Node.js |
| `booking_apartments_map.csv` | CSV | Excel, Google Sheets, Analytics |
| `BOOKING_APARTMENT_IDS.md` | Markdown | Documentación (este archivo) |

---

## 🔄 Cómo Regenerar

Si quieres actualizar con nuevos datos:

```bash
python analyze_booking_apartments.py
```

Esto regenerará todos los mapeos basado en el DatasetScrBooking.json actual.

---

**Generado**: 2025-11-11  
**Actualización Automática**: Ejecutar script cuando DatasetScrBooking.json cambie
