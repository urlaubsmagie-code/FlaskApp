# 🛠️ Guía de Desarrollo - Slideshow HW3B

Esta guía te explica cómo personalizar y editar el slideshow de reseñas usando Sublime Text y ver los cambios en tiempo real.

## 📁 Estructura de Archivos

```
FlaskApp/
├── app.py                          # Aplicación Flask principal
├── templates/
│   └── slideshow.html             # HTML del slideshow (estructura)
├── static/
│   ├── css/
│   │   └── slideshow.css          # 🎨 EDITA ESTE ARCHIVO - Todos los estilos
│   └── js/
│       └── slideshow.js           # ⚙️ EDITA ESTE ARCHIVO - Toda la funcionalidad
├── start_server.bat               # Script para iniciar el servidor
├── README.md                      # Documentación general
└── DESARROLLO.md                  # Esta guía de desarrollo
```

## 🎨 Editando CSS con Sublime Text

### 1. Abrir el archivo CSS
```bash
# En Sublime Text, abre:
C:\Users\admin\Server\FlaskApp\static\css\slideshow.css
```

### 2. Secciones principales del CSS:

#### 🎯 **Personalización Fácil (Líneas 378-400)**
```css
/* PERSONALIZACIÓN FÁCIL - EDITA AQUÍ */

/* Para cambiar colores principales */
:root {
    --color-primary: #667eea;     /* Azul principal */
    --color-secondary: #764ba2;   /* Púrpura secundario */
    --color-accent: #ffc107;      /* Amarillo de estrellas */
    --color-text: #333;           /* Texto principal */
    --color-text-light: #666;     /* Texto secundario */
}
```

#### 📱 **Responsive Design**
- **Móvil/Tablet**: Líneas 253-295
- **Laptop**: Líneas 298-333  
- **TV/Monitor**: Líneas 336-376

### 3. Cambios comunes:

#### Cambiar colores del apartamento HW3B:
```css
.apartment-info {
    background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%); /* Rojo-naranja */
    /* O cambia a tu color preferido: */
    /* background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); */ /* Verde */
}
```

#### Cambiar tamaños de texto:
```css
.apartment-name {
    font-size: 3rem; /* Más grande */
    /* O más pequeño: font-size: 1.8rem; */
}
```

## ⚙️ Editando JavaScript con Sublime Text

### 1. Abrir el archivo JavaScript
```bash
# En Sublime Text, abre:
C:\Users\admin\Server\FlaskApp\static\js\slideshow.js
```

### 2. Configuraciones principales (Líneas 9-11):

```javascript
// PUEDES EDITAR ESTOS VALORES
this.slideDuration = 30000;  // 30 segundos por diapositiva
this.loadingDuration = 2000; // 2 segundos de pantalla de carga
```

### 3. Ajustar umbrales de texto (Líneas 112-125):

```javascript
// PUEDES MODIFICAR ESTOS VALORES PARA CAMBIAR LOS UMBRALES
if (textLength > 800) {        // Textos muy largos
    // ...
} else if (textLength > 500) { // Textos medianos  
    // ...
} else if (textLength > 300) { // Textos normales
    // ...
}
```

### 4. Funciones útiles para debugging:

#### En la consola del navegador puedes usar:
```javascript
pauseSlideshow()           // Pausar presentación
resumeSlideshow()          // Reanudar presentación  
changeSpeed(10)            // Cambiar a 10 segundos por slide
goToSlide(5)              // Ir a la diapositiva 5
slideshow.getCurrentInfo() // Ver información actual
```

## 🔄 Ver Cambios en Tiempo Real

### Método 1: Recarga Automática con Flask Debug Mode

Flask ya está configurado en modo debug, así que:

1. **Guarda** cualquier cambio en CSS o JS
2. **Recarga** la página en el navegador (F5 o Ctrl+R)
3. ¡Los cambios aparecen inmediatamente!

### Método 2: Live Reload con Extensión de Browser

1. **Instala extensión "Live Reload"** en tu navegador
2. **Activa** la extensión en la página del slideshow
3. Los cambios en CSS/JS se reflejan automáticamente

### Método 3: Sublime Text con Build System

1. En Sublime Text: `Tools` → `Build System` → `New Build System`
2. Pega este contenido:
```json
{
    "cmd": ["python", "app.py"],
    "working_dir": "C:/Users/admin/Server/FlaskApp",
    "shell": true
}
```
3. Guarda como `FlaskApp.sublime-build`
4. Usa `Ctrl+B` para reiniciar el servidor

## 🎛️ Debugging en el Navegador

### 1. Abrir Developer Tools:
- **Chrome/Edge**: F12 o Ctrl+Shift+I
- **Firefox**: F12 o Ctrl+Shift+I

### 2. Usar la consola:
```javascript
// Ver información del slideshow
console.log(slideshow.getCurrentInfo());

// Cambiar velocidad temporalmente
slideshow.slideDuration = 5000; // 5 segundos

// Probar funciones
pauseSlideshow();
goToSlide(10);
```

### 3. Inspeccionar elementos:
- Clic derecho → "Inspeccionar elemento"
- Modifica CSS directamente para probar
- Copia los cambios que te gusten al archivo .css

## 📝 Ejemplos de Personalizaciones Comunes

### 🎨 Cambiar esquema de colores completo:

```css
/* En slideshow.css */
:root {
    --color-primary: #2c3e50;    /* Azul oscuro */
    --color-secondary: #34495e;  /* Gris azulado */
    --color-accent: #e74c3c;     /* Rojo */
}

.apartment-info {
    background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
}
```

### ⏱️ Cambiar velocidad de las diapositivas:

```javascript
// En slideshow.js línea 10
this.slideDuration = 45000; // 45 segundos por diapositiva
```

### 📱 Ajustar para pantallas específicas:

```css
/* Para pantallas de 1920px exactamente */
@media (width: 1920px) {
    .slide {
        padding: 80px;
    }
    
    .apartment-name {
        font-size: 3.5rem;
    }
}
```

### 🎭 Cambiar animaciones:

```css
/* Animación más lenta */
.slide.active {
    animation: slideIn 2s ease-out; /* Era 1s */
}

/* Animación diferente */
@keyframes slideIn {
    from {
        opacity: 0;
        transform: scale(0.8); /* En lugar de translateX */
    }
    to {
        opacity: 1;
        transform: scale(1);
    }
}
```

## 🚀 Flujo de Trabajo Recomendado

1. **Abre Sublime Text** con los archivos CSS y JS
2. **Inicia el servidor** (`python app.py` o `start_server.bat`)
3. **Abre el navegador** en http://127.0.0.1:5000
4. **Abre Developer Tools** (F12)
5. **Experimenta** con cambios directamente en el navegador
6. **Copia** los cambios que te gusten a los archivos en Sublime Text
7. **Guarda** y recarga para confirmar los cambios

## ⚠️ Cosas Importantes a Recordar

- ✅ **Flask debug mode está activado** - los cambios se reflejan al recargar
- ✅ **Guarda siempre** antes de recargar el navegador
- ✅ **Usa la consola** del navegador para debugging
- ⚠️ **No modifiques** el archivo HTML a menos que sea necesario
- ⚠️ **Haz backup** antes de cambios grandes
- ⚠️ **Prueba en diferentes tamaños** de pantalla

## 🆘 Solución de Problemas

### El CSS no se aplica:
1. Verifica que guardaste el archivo
2. Recarga con Ctrl+Shift+R (recarga forzada)
3. Revisa la consola del navegador por errores

### El JavaScript no funciona:
1. Abre Developer Tools → Console
2. Busca errores en rojo
3. Verifica sintaxis de JavaScript

### La página no carga:
1. Verifica que el servidor Flask esté corriendo
2. Revisa la consola de Python por errores
3. Asegúrate de que los archivos CSS/JS existan

## 📞 Comandos Útiles

```bash
# Iniciar servidor
python app.py

# Detener servidor (en PowerShell)
Get-Process | Where-Object {$_.ProcessName -eq "python"} | Stop-Process -Force

# Ver archivos de la carpeta
Get-ChildItem -Force
```

¡Con esta configuración puedes personalizar completamente el slideshow usando Sublime Text y ver todos los cambios en tiempo real! 🎉