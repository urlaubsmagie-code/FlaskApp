#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import app

def test_apartment_info():
    """Probar que la información de apartamentos se está extrayendo correctamente"""
    print("🔍 Probando extracción de información de apartamentos (solo 2025)...\n")
    
    reviews = app.load_reviews()
    print(f"Total reviews cargadas: {len(reviews)}")
    
    print("\n🏠 Apartamentos detectados en los primeros 10 comentarios (2025):")
    for i, review in enumerate(reviews[:10], 1):
        apartment_name = review.get('apartment_name', 'No disponible')
        apartment_id = review.get('apartment_id', 'No disponible')
        reviewer_name = review.get('reviewer_name', 'Anónimo')
        rating = review.get('rating', 0)
        created_at = review.get('created_at', '')
        date_display = review.get('date', '')
        
        print(f"{i:2d}. {apartment_name}")
        print(f"     ID: {apartment_id}")
        print(f"     Reviewer: {reviewer_name} ({rating}⭐)")
        print(f"     Fecha: {date_display} ({created_at[:10] if created_at else 'N/A'})")
        print()

    # Contar apartamentos únicos
    apartments = {}
    for review in reviews:
        apt_id = review.get('apartment_id')
        apt_name = review.get('apartment_name')
        if apt_id and apt_name:
            if apt_id not in apartments:
                apartments[apt_id] = {'name': apt_name, 'count': 0}
            apartments[apt_id]['count'] += 1

    print(f"📊 Resumen de apartamentos únicos encontrados: {len(apartments)}")
    for apt_id, info in apartments.items():
        print(f"   🏡 {info['name']}: {info['count']} comentarios (ID: ...{apt_id[-6:]})")

if __name__ == "__main__":
    test_apartment_info()