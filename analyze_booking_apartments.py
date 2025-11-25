#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analyze DatasetScrBooking.json to extract apartment IDs and information
"""

import json
import os
from collections import defaultdict
import re

JSON_FOLDER_PATH = r"C:\Users\admin\n8n-docker\files"
BOOKING_JSON_FILE_NAME = "DatasetScrBooking.json"
IDB_MAPPING_FILE = r"C:\Users\admin\Desktop\IDB.txt"

def extract_hotel_id_from_url(url):
    """Extract hotel ID from Booking URL"""
    if not url:
        return None
    # Format: https://www.booking.com/hotel/de/XXXXXX or /hotel/en/xxxxx
    match = re.search(r'/hotel/[a-z]{2}/([a-z0-9\-]+)', url)
    if match:
        return match.group(1)
    return None

def load_idb_mapping():
    """Load apartment code mapping from IDB.txt"""
    idb_mapping = {}
    try:
        with open(IDB_MAPPING_FILE, 'r', encoding='utf-8') as file:
            for line in file:
                line = line.strip()
                if not line or not line.startswith('https://www.booking.com'):
                    continue
                # Format: "https://www.booking.com/hotel/de/... (CODE)"
                match = re.match(r'(https://[^\s]+)\s+\(([^)]+)\)', line)
                if match:
                    booking_url = match.group(1)
                    apt_code = match.group(2)
                    idb_mapping[booking_url] = apt_code
        return idb_mapping
    except Exception as e:
        print(f"⚠️  Error cargando IDB.txt: {e}")
        return {}

def analyze_booking_apartments():
    """Analyze Booking dataset and extract apartment information"""
    
    json_file_path = os.path.join(JSON_FOLDER_PATH, BOOKING_JSON_FILE_NAME)
    
    if not os.path.exists(json_file_path):
        print(f"❌ Archivo no encontrado: {json_file_path}")
        return
    
    with open(json_file_path, 'r', encoding='utf-8') as file:
        reviews_data = json.load(file)
    
    print(f"\n📊 ANÁLISIS DE APARTAMENTOS BOOKING")
    print(f"{'='*80}")
    print(f"📁 Dataset: {BOOKING_JSON_FILE_NAME}")
    print(f"📄 Total reviews: {len(reviews_data)}\n")
    
    # Load IDB mapping
    idb_mapping = load_idb_mapping()
    print(f"📍 Códigos de apartamentos cargados: {len(idb_mapping)}\n")
    
    # Collect unique apartments
    apartments = {}
    
    for review in reviews_data:
        url = review.get('startUrl', '')
        hotel_id = review.get('hotelId')
        
        # Extract from URL if not in field
        if not hotel_id and url:
            hotel_id_str = extract_hotel_id_from_url(url)
        else:
            hotel_id_str = str(hotel_id) if hotel_id else None
        
        if not url:
            continue
        
        # Get code from IDB mapping
        apt_code = idb_mapping.get(url, 'UNKNOWN')
        
        # Store apartment info
        if apt_code not in apartments:
            apartments[apt_code] = {
                'code': apt_code,
                'hotel_id': hotel_id,
                'hotel_id_from_url': hotel_id_str,
                'url': url,
                'review_count': 0,
                'room_types': set(),
                'avg_rating': 0,
                'ratings': []
            }
        
        apartments[apt_code]['review_count'] += 1
        
        room_info = review.get('roomInfo', '')
        if room_info:
            apartments[apt_code]['room_types'].add(room_info)
        
        rating = review.get('rating', 0)
        if rating > 0:
            apartments[apt_code]['ratings'].append(rating)
    
    # Calculate averages
    for apt_code, data in apartments.items():
        if data['ratings']:
            data['avg_rating'] = sum(data['ratings']) / len(data['ratings'])
        data['room_types'] = ', '.join(sorted(data['room_types']))
    
    # Sort by review count
    sorted_apts = sorted(apartments.items(), key=lambda x: x[1]['review_count'], reverse=True)
    
    print(f"🏠 APARTAMENTOS ENCONTRADOS: {len(apartments)}\n")
    print(f"{'CÓDIGO':<12} {'HOTEL_ID':<15} {'REVIEWS':<10} {'RATING':<8} {'TIPOS DE HABITACIÓN':<40}")
    print(f"{'-'*80}")
    
    for apt_code, data in sorted_apts:
        print(f"{apt_code:<12} {str(data['hotel_id']):<15} {data['review_count']:<10} {data['avg_rating']:.1f}     {data['room_types']:<40}")
    
    # Export to JSON format
    print(f"\n\n📋 MAPEO COMPLETO (Formato JSON)")
    print(f"{'='*80}\n")
    
    export_data = []
    for apt_code, data in sorted_apts:
        export_data.append({
            'code': data['code'],
            'hotel_id': data['hotel_id'],
            'hotel_id_from_url': data['hotel_id_from_url'],
            'url': data['url'],
            'review_count': data['review_count'],
            'avg_rating': round(data['avg_rating'], 2),
            'room_types': data['room_types'].split(', ') if data['room_types'] else [],
            'total_reviews_analyzed': len(reviews_data)
        })
    
    # Print as JSON
    print(json.dumps(export_data, indent=2, ensure_ascii=False))
    
    # Save to file
    output_file = os.path.join(os.path.dirname(__file__), 'booking_apartments_map.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Saved to: {output_file}")
    
    # Also create a simple CSV format
    print(f"\n\n📊 FORMATO CSV (para otros proyectos)")
    print(f"{'='*80}\n")
    print(f"código,hotel_id,url,reviews,rating_promedio")
    for apt_code, data in sorted_apts:
        print(f"{data['code']},{data['hotel_id']},{data['url']},{data['review_count']},{data['avg_rating']:.1f}")
    
    # Save CSV
    csv_file = os.path.join(os.path.dirname(__file__), 'booking_apartments_map.csv')
    with open(csv_file, 'w', encoding='utf-8') as f:
        f.write("código,hotel_id,url,reviews,rating_promedio\n")
        for apt_code, data in sorted_apts:
            f.write(f"{data['code']},{data['hotel_id']},{data['url']},{data['review_count']},{data['avg_rating']:.1f}\n")
    print(f"\n✅ Saved to: {csv_file}")

if __name__ == '__main__':
    analyze_booking_apartments()
