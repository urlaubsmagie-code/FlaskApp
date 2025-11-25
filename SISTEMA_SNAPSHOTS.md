# Sistema de Snapshots Automático

## ✅ Estado: **IMPLEMENTADO Y FUNCIONANDO**

---

## 📋 Resumen

El sistema crea automáticamente copias (snapshots) del archivo `DatasetScr.json` cada vez que detecta cambios. Esto permite mantener un historial completo para análisis comparativos en la página de Analytics.

---

## 🔧 Cómo Funciona

### Detección Automática de Cambios
1. **Cada vez que se carga cualquier página** (slideshow, reviews, rankings, etc.), el sistema:
   - Calcula el hash MD5 del archivo `DatasetScr.json` actual
   - Compara con el último hash guardado
   - Si son diferentes → **crea un snapshot automáticamente**

2. **El archivo original NUNCA se modifica** - solo se hacen copias

### Estructura de Archivos

```
C:\Users\admin\n8n-docker\files\
└── DatasetScr.json  ← ORIGINAL (nunca se toca)

C:\Users\admin\Server\FlaskApp\data\
├── snapshots\
│   ├── dataset_001_2025-11-05_102644.json  ← Primera copia
│   ├── dataset_002_2025-11-08_000530.json  ← Segunda copia (lunes)
│   ├── dataset_003_2025-11-15_000445.json  ← Tercera copia (lunes)
│   └── ...
├── snapshots_metadata.json  ← Info de cada snapshot
└── last_dataset_hash.txt    ← Hash del último dataset procesado
```

### Numeración Automática
- Los snapshots se numeran secuencialmente: `001`, `002`, `003`, etc.
- Cada snapshot incluye timestamp: `YYYY-MM-DD_HHMMSS`
- Ejemplo: `dataset_015_2025-12-25_143022.json`

---

## 📊 Información de Snapshots

Cada snapshot guarda:
- **Copia completa** del `DatasetScr.json`
- **Metadata** en `snapshots_metadata.json`:
  ```json
  {
    "id": 1,
    "filename": "dataset_001_2025-11-05_102644.json",
    "created_at": "2025-11-05T10:26:44.640960",
    "total_reviews": 1836,
    "apartments_count": 49,
    "hash": "91319c3a7031f1a5e36975c7c6dd11db"
  }
  ```

---

## 🎯 Casos de Uso

### Actualizaciones Programadas (Lunes 00:00)
- El sistema detectará automáticamente cuando el dataset se actualice
- Creará un snapshot nuevo con numeración secuencial
- Todo sucede sin intervención manual

### Actualizaciones Manuales (Pruebas)
- Si modificas el dataset manualmente para pruebas
- Al cargar cualquier página, se creará un nuevo snapshot automáticamente
- Mantienes historial completo de todas las versiones

---

## 🔌 API Endpoints Disponibles

### 1. Listar Todos los Snapshots
```
GET /api/snapshots
```
Devuelve JSON con metadata de todos los snapshots creados.

### 2. Crear Snapshot Manual (Forzado)
```
POST /api/create-snapshot
```
Crea un snapshot inmediatamente, incluso si no hubo cambios.

**Ejemplo de uso:**
```bash
curl -X POST http://127.0.0.1:5000/api/create-snapshot
```

---

## ⚙️ Configuración

Las siguientes constantes están definidas en `app.py`:

```python
# Directorio donde se guardan snapshots
SNAPSHOTS_DIR = 'data/snapshots/'

# Archivo con metadata de snapshots
SNAPSHOTS_METADATA_FILE = 'data/snapshots_metadata.json'

# Archivo con hash del último dataset procesado
LAST_HASH_FILE = 'data/last_dataset_hash.txt'
```

---

## 🛡️ Seguridad y Reversión

### El Archivo Original Está Protegido
- `DatasetScr.json` **NUNCA se modifica**
- Solo se hacen copias en `data/snapshots/`

### Cómo Revertir a un Snapshot Anterior
Si necesitas volver a una versión anterior:

```powershell
# 1. Ir al directorio de snapshots
cd C:\Users\admin\Server\FlaskApp\data\snapshots

# 2. Copiar el snapshot deseado al directorio original
Copy-Item "dataset_003_2025-11-15_000445.json" -Destination "C:\Users\admin\n8n-docker\files\DatasetScr.json"
```

### Cómo Desactivar el Sistema (Si es Necesario)
En `app.py`, línea 393, comentar la verificación:

```python
def load_reviews():
    # ...
    try:
        # check_and_create_snapshot()  ← Comentar esta línea
        
        # Construir path del archivo JSON principal
        json_file_path = os.path.join(JSON_FOLDER_PATH, JSON_FILE_NAME)
```

---

## 📈 Integración con Analytics

Los snapshots se pueden usar en la página de Analytics para:
- Comparar estadísticas entre semanas
- Ver evolución de ratings por apartamento
- Detectar tendencias temporales
- Graficar cambios históricos

**Próximos pasos sugeridos:**
- Actualizar `/analytics` para leer snapshots automáticamente
- Crear gráficos comparativos semanales
- Mostrar línea de tiempo de cambios

---

## ✅ Estado Actual

**Snapshot #001 Creado:**
- Archivo: `dataset_001_2025-11-05_102644.json`
- Reviews: 1,836
- Apartamentos: 49
- Hash: `91319c3a...`

**Siguiente snapshot se creará automáticamente:**
- Cuando el `DatasetScr.json` cambie (ej: próximo lunes 00:00)
- O cuando lo fuerces con `POST /api/create-snapshot`

---

## 🎉 Ventajas del Sistema

✅ **Automático** - No requiere intervención manual
✅ **Seguro** - El archivo original nunca se modifica  
✅ **Completo** - Guarda historial completo de todas las versiones
✅ **Eficiente** - Solo crea snapshot cuando hay cambios reales
✅ **Reversible** - Puedes volver a cualquier versión anterior
✅ **Informativo** - Metadata detallada de cada snapshot

---

## 📝 Notas Importantes

1. **Los snapshots NO se borran automáticamente** - Se acumulan indefinidamente
2. **Cada snapshot es una copia completa** del dataset (~1-2 MB por snapshot)
3. **Con 52 semanas/año**, tendrás ~52 snapshots al año (~50-100 MB total)
4. Si necesitas limpiar snapshots antiguos, hacerlo manualmente eliminando archivos en `data/snapshots/`

---

## 🔍 Verificación

Para verificar que todo funciona:

```powershell
# Ver snapshots creados
dir C:\Users\admin\Server\FlaskApp\data\snapshots

# Ver metadata
cat C:\Users\admin\Server\FlaskApp\data\snapshots_metadata.json

# Ver hash actual
cat C:\Users\admin\Server\FlaskApp\data\last_dataset_hash.txt

# Ver lista vía API
curl http://127.0.0.1:5000/api/snapshots
```

---

**Fecha de implementación:** 05 de Noviembre 2025  
**Versión:** 1.0  
**Estado:** ✅ Producción
