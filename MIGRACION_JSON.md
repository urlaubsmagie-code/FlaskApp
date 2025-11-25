# 🔄 Migración a Nueva Estructura JSON - DatasetScr.json

## 📋 Resumen de Cambios

La aplicación Flask ha sido actualizada para funcionar con la **nueva estructura JSON** (`DatasetScr.json`) en lugar de la estructura antigua (`Dokument.json`).

## 🆚 Comparación de Estructuras

### Estructura Antigua (Dokument.json)
```json
[
  {
    "id": "1525283109400813725",
    "text": "Wir hatten eine schöne Zeit...",
    "localizedText": "We had a lovely time...",
    "rating": 4,
    "reviewer": {
      "firstName": "Caroline",
      "profilePicture": "https://..."
    },
    "reviewee": {
      "firstName": "Anna-Lena"
    },
    "createdAt": "2025-10-05T11:45:15Z",
    "localizedDate": "2 weeks ago",
    "localizedReviewerLocation": "1 year on Airbnb",
    "startUrl": "https://www.airbnb.de/rooms/..."
  }
]
```

### Estructura Nueva (DatasetScr.json)
```json
[
  {
    "apartmentId": "1018794394545297732",
    "url": "https://www.airbnb.de/rooms/1018794394545297732",
    "totalExtracted": 3,
    "totalAvailable": 34,
    "extractedAt": "2025-10-24T09:17:49.827Z",
    "reviews": [
      {
        "apartmentId": "1018794394545297732",
        "reviewerName": "Sharareh",
        "date": "Juli 2025",
        "rating": 4,
        "comment": "Wir waren eine Nacht hier..."
      }
    ]
  }
]
```

## ✅ Cambios Implementados

### 1. **Archivo: `app.py`**

#### Variables de Configuración
```python
# Nueva variable añadida
JSON_FILE_NAME = "DatasetScr.json"
```

#### Función `load_reviews()` - Completamente reescrita
- ✅ Lee el archivo `DatasetScr.json`
- ✅ Procesa la estructura anidada (apartamentos → reviews)
- ✅ Genera IDs únicos para cada review
- ✅ Maneja apartamentos excluidos
- ✅ Proporciona estadísticas detalladas por apartamento
- ❌ **Eliminada**: Función `is_review_from_2025()` (ya no necesaria)
- ❌ **Eliminado**: Filtrado por año 2025 (se asume que DatasetScr solo contiene datos actuales)

#### Mapeo de Campos
| Campo Antiguo | Campo Nuevo | Notas |
|--------------|-------------|-------|
| `id` | Generado dinámicamente | `apartmentId_reviewerName_date` |
| `text` / `localizedText` | `comment` | Texto del comentario |
| `rating` | `rating` | Sin cambios |
| `localizedDate` | `date` | Formato más simple |
| `reviewer.firstName` | `reviewerName` | Directo, sin objeto anidado |
| `reviewer.profilePicture` | ❌ No disponible | Se usa placeholder |
| `localizedReviewerLocation` | ❌ No disponible | Valor por defecto |
| `startUrl` | `url` | URL del apartamento |

#### Nuevas Rutas API
```python
@app.route('/reviews')          # Vista con filtros (index.html)
@app.route('/slideshow')        # Ruta alternativa para slideshow
@app.route('/api/reviews')      # API JSON de todas las reviews
```

### 2. **Archivos: Templates HTML**

#### `slideshow.html`
- ✅ Manejo de fotos de perfil faltantes con placeholder
- ✅ Avatar con inicial del nombre cuando no hay foto
- ✅ Validación condicional de campos opcionales

#### `index.html`
- ✅ Mismo manejo de placeholders para avatares
- ✅ Texto "Airbnb-Gast" cuando no hay ubicación

### 3. **Archivo: `static/css/slideshow.css`**

#### Nuevos Estilos Añadidos
```css
.reviewer-avatar-placeholder {
    width: 80px;
    height: 80px;
    border-radius: 50%;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    display: flex;
    align-items: center;
    justify-content: center;
}

.reviewer-avatar-placeholder span {
    font-size: 2rem;
    font-weight: 700;
    color: white;
    text-transform: uppercase;
}
```

## 📊 Campos No Disponibles en Nueva Estructura

Los siguientes campos **NO están disponibles** en `DatasetScr.json`:

| Campo | Workaround |
|-------|-----------|
| `reviewer_picture` | Avatar placeholder con inicial |
| `reviewer_location` | Texto por defecto: "Airbnb-Gast" |
| `created_at` (ISO format) | Se usa `date` (formato legible) |
| `language` | Por defecto: "de" |
| `host_name` | Por defecto: "Anna-Lena" |

## 🚀 Cómo Usar

### 1. Verificar que existe el archivo
```bash
# Debe existir:
C:\Users\admin\n8n-docker\files\DatasetScr.json
```

### 2. Iniciar el servidor
```bash
cd C:\Users\admin\Server\FlaskApp
python app.py
```

### 3. Acceder a las vistas
- **Slideshow**: http://127.0.0.1:5000/
- **Vista con filtros**: http://127.0.0.1:5000/reviews
- **API Reviews**: http://127.0.0.1:5000/api/reviews
- **API Stats**: http://127.0.0.1:5000/api/stats

## 📝 Salida de Consola Esperada

```
📁 Cargando archivo: DatasetScr.json
✅ 47 apartamentos encontrados
⚠️  Apartamento excluido: 50587278 (X comentarios)
⚠️  Apartamento excluido: 814427016412775340 (Y comentarios)

📊 Resumen de carga:
   🏠 Total apartamentos procesados: 47
   📄 Total comentarios encontrados: 150
   🚫 Apartamentos excluidos: 25 comentarios
   ⭐ Comentarios finales: 125

🏠 Apartamentos con comentarios:
   🏡 H4 - Appartment im maritimen Stil (ID: ...923): 15 comentarios
   🏡 F3 - Gemütliche Ferienwohnung (ID: ...972): 20 comentarios
   ...
```

## ⚠️ Notas Importantes

1. **Archivo DatasetScr.json debe existir**: La aplicación busca específicamente este archivo.
2. **Sin filtrado por año**: Se asume que DatasetScr.json ya contiene solo reviews actuales.
3. **IDs de apartamentos excluidos**: Los IDs en `EXCLUDED_APARTMENT_IDS` siguen funcionando.
4. **Placeholders**: Todas las reviews sin foto mostrarán la inicial del nombre del reviewer.

## 🔧 Personalización

### Cambiar nombre del archivo JSON
```python
# En app.py línea 15
JSON_FILE_NAME = "TuArchivo.json"
```

### Cambiar apartamentos excluidos
```python
# En app.py líneas 17-20
EXCLUDED_APARTMENT_IDS = {
    '50587278',
    '814427016412775340',
    '123456789'  # Agregar más IDs aquí
}
```

## 🐛 Solución de Problemas

### Error: "Archivo no encontrado"
```
❌ Archivo no encontrado: C:\Users\admin\n8n-docker\files\DatasetScr.json
```
**Solución**: Verificar que el archivo existe y tiene el nombre correcto.

### Error: "Formato inválido"
```
⚠️  Formato inválido: se esperaba una lista de apartamentos
```
**Solución**: Verificar que el JSON tiene la estructura correcta (array de apartamentos).

### No se muestran reviews
**Posibles causas**:
1. Todos los apartamentos están excluidos
2. El archivo JSON está vacío
3. El campo `reviews` está vacío en todos los apartamentos

## 📞 Contacto y Soporte

Si tienes problemas con la migración, revisa:
1. Los logs de la consola al iniciar el servidor
2. El formato del archivo `DatasetScr.json`
3. La configuración de `EXCLUDED_APARTMENT_IDS`

---

✅ **Migración completada con éxito**
