# Analytics Dashboard - Sistema de Snapshots

## 📊 ¿Qué es esto?

El **Analytics Dashboard** es una página que muestra la evolución temporal de las estadísticas de tus apartamentos mediante gráficos interactivos.

## 🎯 Características

- **Gráficos de líneas** que muestran la evolución del rating promedio de cada apartamento
- **Gráfico de porcentaje de 5 estrellas** para ver qué apartamentos mantienen mejor calidad
- **Tabla comparativa** con el estado actual de todos los apartamentos
- **Sin scrolling necesario** - todo visible en una sola página

## 📸 ¿Cómo funciona?

El sistema funciona con **snapshots semanales**:

1. Cada semana ejecutas un script que guarda las estadísticas actuales
2. Estos snapshots se acumulan en un archivo JSON
3. La página de analytics lee estos snapshots y genera gráficos

## 🚀 Uso

### Paso 1: Crear snapshot inicial (YA HECHO ✅)

Ya creamos el primer snapshot con los datos actuales (2025-11-04).

### Paso 2: Crear snapshots semanales

Cada semana, ejecuta:

```bash
cd C:\Users\admin\Server\FlaskApp
python create_snapshot.py
```

**Recomendación**: Hazlo el mismo día de cada semana (ej: cada lunes a las 9 AM)

### Paso 3: Ver los gráficos

Accede a: **http://localhost:5000/analytics**

## 📅 Calendario sugerido

- **Semana 1** (4 Nov 2025): ✅ Snapshot inicial creado
- **Semana 2** (11 Nov 2025): Ejecutar `python create_snapshot.py`
- **Semana 3** (18 Nov 2025): Ejecutar `python create_snapshot.py`
- **Semana 4** (25 Nov 2025): Ejecutar `python create_snapshot.py`

A partir de la semana 2, ya verás tendencias en los gráficos.

## 🔧 Automatización (Opcional)

### Opción 1: Windows Task Scheduler

1. Abre "Programador de tareas" (Task Scheduler)
2. Crea una tarea nueva:
   - **Nombre**: "Airbnb Analytics Snapshot"
   - **Desencadenador**: Semanal, cada lunes a las 9:00 AM
   - **Acción**: Iniciar programa
     - **Programa**: `python`
     - **Argumentos**: `create_snapshot.py`
     - **Directorio**: `C:\Users\admin\Server\FlaskApp`

### Opción 2: Script mantenedor

Simplemente crea un recordatorio en tu calendario para ejecutar el script cada semana.

## 📁 Estructura de archivos

```
FlaskApp/
├── app.py                    # Aplicación Flask principal
├── create_snapshot.py        # Script para crear snapshots
├── data/
│   └── snapshots.json        # Historial de snapshots
└── templates/
    └── analytics.html        # Página de gráficos
```

## 📈 ¿Qué se guarda en cada snapshot?

Para cada apartamento:
- Rating promedio
- Total de reviews
- Distribución de estrellas (1-5)
- Porcentaje de 5 estrellas
- Fecha y semana del snapshot

## 🔍 Ejemplo de evolución

Imagina que ves en los gráficos:

```
Semana 1: H2 tiene 4.8 ⭐
Semana 2: H2 baja a 4.5 ⭐ ⬇️
Semana 3: H2 sube a 4.7 ⭐ ⬆️
```

Esto te permite identificar tendencias y actuar rápidamente.

## ⚠️ Notas importantes

- **No edites** el archivo `data/snapshots.json` manualmente
- Si borras el archivo, perderás todo el historial
- Haz backups periódicos del archivo `snapshots.json`
- El primer snapshot ya está creado con 47 apartamentos

## 🆘 Solución de problemas

**Problema**: "No se encontró DatasetScr.json"
- **Solución**: Asegúrate de que el archivo existe en `C:\Users\admin\n8n-docker\files\`

**Problema**: "La página no muestra gráficos"
- **Solución**: Necesitas al menos 1 snapshot. Ejecuta `python create_snapshot.py`

**Problema**: "Los gráficos están vacíos"
- **Solución**: Con 1 solo snapshot verás solo 1 punto. Necesitas 2+ snapshots para ver líneas

## 📞 Páginas disponibles

- **/** - Slideshow (reviews recientes)
- **/reviews** - Lista de reviews
- **/rankings** - Rankings actuales
- **/analytics** - Gráficos temporales ⭐ NUEVO

¡Disfruta monitoreando la evolución de tus apartamentos! 📊✨
