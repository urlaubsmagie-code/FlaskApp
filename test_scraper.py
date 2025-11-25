"""
Test rápido del scraper - Prueba con una sola habitación
"""

from airbnb_scraper_robust import AirbnbReviewsScraper

print("🧪 TEST DEL SCRAPER DE AIRBNB")
print("="*60)

# URL de prueba (habitación con reviews públicas)
test_url = "https://www.airbnb.com/rooms/12937"

print(f"📍 URL de prueba: {test_url}")
print("🌐 Abriendo navegador (verás Chrome abrirse)...\n")

# Ejecutar scraper
with AirbnbReviewsScraper(headless=False) as scraper:
    print("⏳ Scrapeando... esto puede tomar 20-30 segundos\n")
    
    result = scraper.scrape_room(
        room_url=test_url,
        max_scrolls=5,
        max_show_more_clicks=5
    )

# Mostrar resultados
print("\n" + "="*60)
print("📊 RESULTADOS DEL TEST")
print("="*60)

if result['success']:
    print(f"✅ Estado: ÉXITO")
    print(f"🏠 Habitación: {result.get('room_title', 'N/A')}")
    print(f"📝 Reviews obtenidas: {result['total_reviews']}")
    
    if result['reviews']:
        print(f"\n📄 Primera review como ejemplo:")
        print("-"*60)
        first = result['reviews'][0]
        print(f"👤 Autor: {first.get('author', 'N/A')}")
        print(f"📅 Fecha: {first.get('date', 'N/A')}")
        print(f"⭐ Rating: {first.get('rating', 'N/A')}")
        print(f"💬 Texto: {first.get('text', 'N/A')[:150]}...")
        print("-"*60)
        
        print(f"\n💾 Guardando resultados en 'test_output.json'...")
        import json
        with open('test_output.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print("✅ Archivo guardado!")
        
else:
    print(f"❌ Estado: FALLO")
    print(f"💥 Error: {result['error']}")

print("\n" + "="*60)
print("🎉 Test completado!")
print("="*60)
