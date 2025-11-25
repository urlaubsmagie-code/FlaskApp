#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify Booking review data extraction improvements
"""

import json
import os

# Rutas
JSON_FOLDER_PATH = r"C:\Users\admin\n8n-docker\files"
BOOKING_JSON_FILE_NAME = "DatasetScrBooking.json"

def test_booking_reviews():
    """Test Booking review extraction"""
    
    json_file_path = os.path.join(JSON_FOLDER_PATH, BOOKING_JSON_FILE_NAME)
    
    if not os.path.exists(json_file_path):
        print(f"❌ Archivo no encontrado: {json_file_path}")
        return
    
    with open(json_file_path, 'r', encoding='utf-8') as file:
        reviews_data = json.load(file)
    
    print(f"\n📊 Análisis de reviews de Booking")
    print(f"📁 Archivo: {BOOKING_JSON_FILE_NAME}")
    print(f"📄 Total de reviews: {len(reviews_data)}\n")
    
    # Estadísticas
    stats = {
        'total': 0,
        'with_title': 0,
        'with_liked': 0,
        'with_disliked': 0,
        'completely_empty': 0,
        'only_rating': 0,
        'has_room_info': 0,
        'has_traveler_type': 0,
        'valid_ratings': 0
    }
    
    # Analizar cada review
    for idx, review in enumerate(reviews_data, 1):
        stats['total'] += 1
        
        title = review.get('reviewTitle')
        liked = review.get('likedText')
        disliked = review.get('dislikedText')
        rating = review.get('rating', 0)
        room_info = review.get('roomInfo', '')
        traveler_type = review.get('travelerType', '')
        
        if title:
            stats['with_title'] += 1
        if liked:
            stats['with_liked'] += 1
        if disliked:
            stats['with_disliked'] += 1
        if rating and rating > 0:
            stats['valid_ratings'] += 1
        if room_info:
            stats['has_room_info'] += 1
        if traveler_type:
            stats['has_traveler_type'] += 1
        
        # Revisar si está completamente vacía
        if not title and not liked and not disliked:
            stats['completely_empty'] += 1
            if rating > 0:
                stats['only_rating'] += 1
            
            # Mostrar ejemplos de reviews vacías
            if stats['completely_empty'] <= 5:
                print(f"   Ejemplo {stats['completely_empty']}: Rating={rating}, Room={room_info}, Traveler={traveler_type}")
    
    # Mostrar estadísticas
    print(f"\n📈 Estadísticas:")
    print(f"   ✅ Reviews con rating válido: {stats['valid_ratings']} ({100*stats['valid_ratings']/stats['total']:.1f}%)")
    print(f"   📝 Con título: {stats['with_title']} ({100*stats['with_title']/stats['total']:.1f}%)")
    print(f"   👍 Con texto positivo: {stats['with_liked']} ({100*stats['with_liked']/stats['total']:.1f}%)")
    print(f"   👎 Con texto negativo: {stats['with_disliked']} ({100*stats['with_disliked']/stats['total']:.1f}%)")
    print(f"   🏠 Con info de habitación: {stats['has_room_info']} ({100*stats['has_room_info']/stats['total']:.1f}%)")
    print(f"   👤 Con tipo de viajero: {stats['has_traveler_type']} ({100*stats['has_traveler_type']/stats['total']:.1f}%)")
    print(f"\n   ⚠️  Completamente vacías (sin title/liked/disliked): {stats['completely_empty']} ({100*stats['completely_empty']/stats['total']:.1f}%)")
    print(f"   🔢 De estas, solo rating: {stats['only_rating']} ({100*stats['only_rating']/stats['total']:.1f}%)")

if __name__ == '__main__':
    test_booking_reviews()
