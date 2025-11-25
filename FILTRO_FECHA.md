# 📅 Filtro de Fecha para Reviews

## 🎯 Objetivo

La aplicación ahora **solo muestra reviews de los últimos 30 días** (1 mes) para mantener el contenido fresco y relevante.

## ⚙️ Configuración

### Cambiar el período de tiempo

Edita el archivo `app.py` línea 19:

```python
# Máximo de días de antigüedad para mostrar reviews (30 días = 1 mes)
MAX_REVIEW_AGE_DAYS = 30
```

**Ejemplos:**
- `MAX_REVIEW_AGE_DAYS = 7` → Solo última semana
- `MAX_REVIEW_AGE_DAYS = 14` → Solo últimas 2 semanas
- `MAX_REVIEW_AGE_DAYS = 30` → Solo último mes (default)
- `MAX_REVIEW_AGE_DAYS = 60` → Últimos 2 meses
- `MAX_REVIEW_AGE_DAYS = 90` → Últimos 3 meses
- `MAX_REVIEW_AGE_DAYS = 365` → Último año

## 📋 Formatos de Fecha Soportados

La función `is_review_recent()` reconoce automáticamente los siguientes formatos de fecha en alemán:

### 1. **Formato Relativo - Días**
```
"Vor 2 Tag"
"Vor 5 Tage"
"Vor 1 Tag"
```
✅ **Cálculo:** Compara directamente los días

### 2. **Formato Relativo - Semanas**
```
"Vor 1 Woche"
"Vor 2 Wochen"
"Vor 3 Wochen"
```
✅ **Cálculo:** Convierte semanas a días (semanas × 7)

### 3. **Formato Absoluto - Mes y Año**
```
"Oktober 2025"
"September 2025"
"August 2025"
"Juli 2025"
"Juni 2025"
"Mai 2025"
"April 2025"
"März 2025"
"Februar 2025"
"Januar 2025"
"Dezember 2024"
"November 2024"
```
✅ **Cálculo:** Calcula diferencia desde día 28 del mes indicado hasta hoy

## 🔍 Lógica de Filtrado

```python
if not is_review_recent(review_date, max_days=30):
    # Review filtrada (muy antigua)
    continue
else:
    # Review incluida (reciente)
    processed_reviews.append(review)
```

### Ejemplos (asumiendo hoy es 28 de Octubre 2025):

| Fecha Review | ¿Se incluye? | Razón |
|--------------|--------------|-------|
| "Vor 2 Tag" | ✅ Sí | 2 días < 30 días |
| "Vor 1 Woche" | ✅ Sí | 7 días < 30 días |
| "Vor 4 Wochen" | ✅ Sí | 28 días < 30 días |
| "Vor 5 Wochen" | ❌ No | 35 días > 30 días |
| "Oktober 2025" | ✅ Sí | Mes actual |
| "September 2025" | ✅ Sí | ~30 días atrás |
| "August 2025" | ❌ No | ~60 días atrás |
| "Juli 2025" | ❌ No | ~90 días atrás |
| "Dezember 2024" | ❌ No | ~300 días atrás |

## 📊 Salida de Consola

Al iniciar el servidor, verás:

```
📁 Cargando archivo: DatasetScr.json
✅ 47 apartamentos encontrados

📊 Resumen de carga:
   🏠 Total apartamentos procesados: 47
   📄 Total comentarios encontrados: 350
   🚫 Apartamentos excluidos: 25 comentarios
   📅 Filtrados por fecha (>30 días): 280 comentarios
   ⭐ Comentarios finales (recientes, ≤30 días): 45

🏠 Apartamentos con comentarios recientes:
   🏡 H4 - Appartment im maritimen Stil (ID: ...923): 8 comentarios
   🏡 F3 - Gemütliche Ferienwohnung (ID: ...972): 12 comentarios
   ...
```

## 🛡️ Manejo de Errores

### Fecha no reconocida
Si el formato de fecha no coincide con ninguno de los patrones:
```python
return True  # Incluir por defecto (no filtrar)
```

### Fecha vacía o None
```python
if not date_str:
    return False  # Excluir (no incluir)
```

### Error al parsear
```python
except (ValueError, AttributeError):
    return True  # Incluir por defecto (no filtrar)
```

**Resultado:** La aplicación es **tolerante a fallos** y prefiere incluir reviews dudosas en lugar de filtrarlas incorrectamente.

## 🔧 Personalización Avanzada

### Filtrar solo última semana

```python
MAX_REVIEW_AGE_DAYS = 7
```

### Filtrar por múltiples períodos

Puedes modificar `load_reviews()` para crear diferentes grupos:

```python
# En app.py, crear múltiples listas
recent_reviews = []      # Últimos 7 días
medium_reviews = []      # 8-30 días
old_reviews = []         # 31-90 días

for review in reviews_list:
    days_old = calculate_days(review_date)
    if days_old <= 7:
        recent_reviews.append(review)
    elif days_old <= 30:
        medium_reviews.append(review)
    elif days_old <= 90:
        old_reviews.append(review)
```

## 📝 Testing

Para probar el filtro con diferentes fechas:

```python
# En consola Python
from app import is_review_recent

# Probar diferentes formatos
print(is_review_recent("Vor 2 Tag", max_days=30))        # True
print(is_review_recent("Vor 5 Wochen", max_days=30))    # False
print(is_review_recent("Oktober 2025", max_days=30))    # True (si hoy es Oct/Nov)
print(is_review_recent("Juli 2025", max_days=30))       # False
```

## ⚠️ Notas Importantes

1. **Actualización Automática:** El filtro se aplica cada vez que se carga la página
2. **No modifica el JSON:** El archivo `DatasetScr.json` permanece intacto
3. **Solo afecta la visualización:** Las reviews antiguas siguen en el JSON, solo no se muestran
4. **Case-insensitive:** Funciona con "Oktober", "oktober", "OKTOBER"
5. **Tolerante:** Si hay duda, prefiere incluir la review

## 🚀 Ventajas

✅ **Contenido fresco:** Solo muestra reviews recientes
✅ **Configurable:** Cambia fácilmente el período
✅ **Automático:** No requiere modificar el JSON
✅ **Robusto:** Maneja múltiples formatos de fecha
✅ **Reversible:** Cambia `MAX_REVIEW_AGE_DAYS` a un valor alto para mostrar todo

---

## 📞 Desactivar el Filtro

Para mostrar **todas las reviews** sin importar la fecha:

```python
# Opción 1: Valor muy alto
MAX_REVIEW_AGE_DAYS = 3650  # 10 años

# Opción 2: Comentar la línea del filtro en load_reviews()
# if not is_review_recent(review_date, max_days=MAX_REVIEW_AGE_DAYS):
#     reviews_filtered_by_date += 1
#     continue
```

---

✅ **Filtro implementado y funcionando**
