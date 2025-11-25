"""
Ejemplo de uso del Airbnb Scraper
Ejecuta este archivo para empezar a extraer reviews
"""

from airbnb_scraper_robust import AirbnbReviewsScraper

# ============================================
# CONFIGURACIÓN - Edita esta sección
# ============================================

# Lista de URLs de habitaciones de Airbnb
ROOM_URLS = [
    "https://www.airbnb.com/rooms/12937",
    # Agrega más URLs aquí, una por línea
]

# Nombre del archivo de salida
OUTPUT_FILE = "mis_reviews_airbnb.json"

# Configuración del scraper
HEADLESS = False  # False = ver el navegador, True = modo invisible
MAX_SCROLLS = 10  # Número de scrolls para cargar más contenido
MAX_CLICKS = 15   # Máximo de clics en "Mostrar más"

# ============================================
# EJECUCIÓN - No necesitas editar abajo
# ============================================

def main():
    print("🚀 Iniciando scraper de Airbnb...")
    print(f"📋 URLs a procesar: {len(ROOM_URLS)}")
    print(f"💾 Archivo de salida: {OUTPUT_FILE}\n")
    
    # Crear y ejecutar scraper
    with AirbnbReviewsScraper(headless=HEADLESS) as scraper:
        results = scraper.scrape_multiple_rooms(
            room_urls=ROOM_URLS,
            output_file=OUTPUT_FILE
        )
        
        # Mostrar resumen
        print("\n" + "="*70)
        print("📊 RESUMEN FINAL")
        print("="*70)
        
        total_reviews = 0
        successful = 0
        failed = 0
        
        for result in results:
            if result['success']:
                successful += 1
                total_reviews += result['total_reviews']
                title = result.get('room_title', 'Sin título')
                print(f"  ✓ {title[:50]}: {result['total_reviews']} reviews")
            else:
                failed += 1
                print(f"  ✗ {result['url']}: {result['error']}")
        
        print(f"\n{'='*70}")
        print(f"✅ Exitosos: {successful}/{len(results)}")
        print(f"❌ Fallidos: {failed}/{len(results)}")
        print(f"📝 Total de reviews extraídas: {total_reviews}")
        print(f"💾 Datos guardados en: {OUTPUT_FILE}")
        print("="*70)
        
        # Mostrar muestra de una review
        if total_reviews > 0:
            print("\n📄 EJEMPLO DE REVIEW EXTRAÍDA:")
            print("-"*70)
            first_review = None
            for result in results:
                if result['success'] and result['reviews']:
                    first_review = result['reviews'][0]
                    break
            
            if first_review:
                print(f"Autor: {first_review.get('author', 'N/A')}")
                print(f"Fecha: {first_review.get('date', 'N/A')}")
                print(f"Rating: {first_review.get('rating', 'N/A')}")
                print(f"Texto: {first_review.get('text', 'N/A')[:200]}...")
                print("-"*70)

if __name__ == "__main__":
    main()
