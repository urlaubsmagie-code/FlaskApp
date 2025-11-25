# Airbnb Reviews Scraper

Este Actor scrapes reviews de listados de Airbnb usando Crawlee y Cheerio.

## Características

- 🏠 Extrae reviews de múltiples listados de Airbnb
- 📝 Captura nombre del reviewer, fecha, texto del review y rating
- 🔄 Soporte para paginación de reviews
- 🛡️ Usa Apify Proxy para evitar bloqueos
- 📊 Exporta datos en JSON, CSV, Excel o XML

## Uso

### Input

El Actor acepta los siguientes parámetros de entrada:

- **Listing URLs** (requerido): Array de URLs de listados de Airbnb
  - Ejemplo: `https://www.airbnb.com/rooms/12345678`
  
- **Max Reviews Per Listing** (opcional): Número máximo de reviews a extraer por listado
  - Default: 100
  - Rango: 1-1000

- **Proxy Configuration** (opcional): Configuración de proxy
  - Default: Usa Apify Proxy

### Ejemplo de Input JSON

```json
{
  "listingUrls": [
    "https://www.airbnb.com/rooms/12345678",
    "https://www.airbnb.com/rooms/87654321"
  ],
  "maxReviewsPerListing": 50,
  "proxyConfiguration": {
    "useApifyProxy": true
  }
}
```

## Output

El Actor devuelve un dataset con los siguientes campos:

```json
{
  "listingId": "12345678",
  "listingTitle": "Beautiful apartment in downtown",
  "listingLocation": "Barcelona, Spain",
  "listingUrl": "https://www.airbnb.com/rooms/12345678",
  "reviewerName": "John Doe",
  "reviewDate": "March 2024",
  "reviewText": "Great place, highly recommended!",
  "rating": "5 stars",
  "scrapedAt": "2024-03-15T10:30:00.000Z"
}
```

## Instalación Local

Para ejecutar el Actor localmente:

```bash
# Instalar dependencias
npm install

# Ejecutar localmente
npm start
```

## Notas Importantes

⚠️ **Airbnb actualiza frecuentemente su estructura HTML**, por lo que los selectores pueden necesitar ajustes.

⚠️ **Uso de Proxy**: Se recomienda usar Apify Proxy para evitar rate limiting y bloqueos.

⚠️ **Reviews dinámicas**: Airbnb carga muchos reviews dinámicamente con JavaScript. Para mejores resultados, considera usar `PlaywrightCrawler` en lugar de `CheerioCrawler`.

## Mejoras Sugeridas

Para obtener más reviews y mejor rendimiento:

1. **Usar PlaywrightCrawler**: Para sitios con contenido dinámico
2. **Manejar paginación**: Implementar scroll infinito o click en "Show more"
3. **Agregar delays**: Entre requests para evitar detección
4. **Extraer más datos**: Rating detallado, fotos del reviewer, respuestas del host

## Troubleshooting

Si no se extraen reviews:
1. Verifica que la URL sea correcta
2. Inspecciona el HTML de Airbnb (puede haber cambiado)
3. Usa Playwright en lugar de Cheerio para contenido dinámico
4. Revisa los logs del Actor para errores específicos

## Licencia

ISC
