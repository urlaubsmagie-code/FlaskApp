#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extract Hotel IDs from DatasetScrBooking.json and match with IDB.txt URLs
"""

import json
import os
import re

JSON_FOLDER_PATH = r"C:\Users\admin\n8n-docker\files"
BOOKING_JSON_FILE_NAME = "DatasetScrBooking.json"
IDB_FILE = r"C:\Users\admin\Desktop\IDB.txt"

def load_idb_urls():
    """Load URL to code mappings from IDB.txt"""
    url_to_code = {}
    try:
        with open(IDB_FILE, 'r', encoding='utf-8') as file:
            for line in file:
                line = line.strip()
                if not line or not line.startswith('https://www.booking.com'):
                    continue
                # Format: "https://www.booking.com/hotel/de/... (CODE)"
                match = re.match(r'(https://[^\s]+)\s+\(([^)]+)\)', line)
                if match:
                    url = match.group(1)
                    code = match.group(2)
                    url_to_code[url] = code
                    # Also try without trailing slash variations
                    url_base = url.rstrip('/')
                    url_to_code[url_base] = code
        return url_to_code
    except Exception as e:
        print(f"❌ Error loading IDB.txt: {e}")
        return {}

def normalize_url(url):
    """Normalize URL for comparison"""
    if not url:
        return None
    # Remove trailing slashes and query params
    url = url.split('?')[0].rstrip('/')
    return url

def extract_hotel_ids():
    """Extract Hotel IDs from Booking dataset and match with IDB.txt"""
    
    json_file_path = os.path.join(JSON_FOLDER_PATH, BOOKING_JSON_FILE_NAME)
    
    if not os.path.exists(json_file_path):
        print(f"❌ File not found: {json_file_path}")
        return {}
    
    with open(json_file_path, 'r', encoding='utf-8') as file:
        reviews_data = json.load(file)
    
    # Load IDB mappings
    url_to_code = load_idb_urls()
    print(f"📁 URLs loaded from IDB.txt: {len(url_to_code)}")
    print(f"📄 Reviews in dataset: {len(reviews_data)}\n")
    
    # Extract Hotel IDs and match with codes
    hotel_id_to_code = {}
    
    for review in reviews_data:
        start_url = review.get('startUrl', '')
        hotel_id = review.get('hotelId')
        
        if not start_url or not hotel_id:
            continue
        
        # Normalize both URLs for comparison
        normalized_url = normalize_url(start_url)
        
        # Try exact match
        if normalized_url in url_to_code:
            code = url_to_code[normalized_url]
            if hotel_id not in hotel_id_to_code:
                hotel_id_to_code[hotel_id] = code
        else:
            # Try to find partial match
            for idb_url, code in url_to_code.items():
                normalized_idb = normalize_url(idb_url)
                if normalized_idb and normalized_url and normalized_idb == normalized_url:
                    if hotel_id not in hotel_id_to_code:
                        hotel_id_to_code[hotel_id] = code
                    break
    
    print(f"✅ Hotel IDs matched: {len(hotel_id_to_code)}\n")
    
    # Sort by code for better readability
    sorted_hotels = sorted(hotel_id_to_code.items(), key=lambda x: x[1])
    
    print("📋 HOTEL ID MAPPINGS (formato para IDB.txt)\n")
    print(f"{'HOTEL_ID':<12} {'CÓDIGO':<10}")
    print(f"{'-'*22}")
    
    output_lines = []
    for hotel_id, code in sorted_hotels:
        line = f"{hotel_id} ({code})"
        output_lines.append(line)
        print(f"{hotel_id:<12} {code:<10}")
    
    return output_lines

if __name__ == '__main__':
    lines = extract_hotel_ids()
    
    if lines:
        print(f"\n\n✅ LINEAS PARA AGREGAR AL IDB.txt:\n")
        for line in lines:
            print(line)
        
        print(f"\n\n📝 Total de líneas: {len(lines)}")
