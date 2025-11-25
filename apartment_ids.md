# Mapeo de IDs de Apartamentos

## Lista de apartamentos con sus identificadores únicos

| Archivo JSON | ID del Apartamento | Nombre/Código Correcto | Descripción |
|--------------|-------------------|------------------------|-------------|
| `Dokument.json` | `649153494847068923` | **H4** | Apartamento con vista al bach (arroyo) |
| `Dokument2.json` | `940339949730055972` | **F3** | Apartamento céntrico con jardín |
| `Dokument3.json` | `609172560881241855` | **UT** | Apartamento con sauna y whirlpool |

## Detalles adicionales extraídos de las reseñas:

### H4 (649153494847068923)
- **Características mencionadas**: Bach (arroyo) bajo la ventana, pequeño apartamento en ático, maritima decoración
- **Ubicación**: Sebnitz, Sächsische Schweiz
- **Particularidades**: Sonido del arroyo, apartamento pequeño pero completo

### F3 (940339949730055972) 
- **Características mencionadas**: Jardín comunitario, apartamento espacioso y luminoso, cocina bien equipada
- **Ubicación**: Centro de Sebnitz
- **Particularidades**: Sin parking propio, apartamento en planta alta

### UT (609172560881241855)
- **Características mencionadas**: Sauna tipo barril, whirlpool, balcón con vista al río, baños fuera del apartamento
- **Ubicación**: Sebnitz, junto al río
- **Particularidades**: Instalaciones spa compartidas, apartamento con muchas luces LED

## Para uso en código JavaScript:

```javascript
const APARTMENT_MAP = {
    "649153494847068923": {
        code: "H4",
        name: "H4 Apartment",
        file: "Dokument.json"
    },
    "940339949730055972": {
        code: "F3", 
        name: "F3 Apartment",
        file: "Dokument2.json"
    },
    "609172560881241855": {
        code: "UT",
        name: "UT Apartment", 
        file: "Dokument3.json"
    }
};
```

## Método de extracción del ID:

El ID se extrae del campo `startUrl` de cada comentario:
```
"startUrl": "https://www.airbnb.de/rooms/[ID_DEL_APARTAMENTO]"
```

Por ejemplo:
- `https://www.airbnb.de/rooms/649153494847068923` → ID: `649153494847068923`