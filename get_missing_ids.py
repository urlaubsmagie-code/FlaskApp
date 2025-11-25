#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Get missing Hotel IDs with their codes
"""

import json
import os
import re

JSON_FOLDER_PATH = r"C:\Users\admin\n8n-docker\files"
BOOKING_JSON_FILE_NAME = "DatasetScrBooking.json"
IDB_FILE = r"C:\Users\admin\Desktop\IDB.txt"

# Load IDB mappings
url_to_code = {}
with open(IDB_FILE, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line and line.startswith('https://www.booking.com'):
            match = re.match(r'(https://[^\s]+)\s+\(([^)]+)\)', line)
            if match:
                url = match.group(1)
                code = match.group(2)
                url_to_code[url] = code

# Missing IDs to find
missing_ids = {
    8542178, 9749369, 9749456, 9749646, 9749677,
    10238214, 10489923, 10756628, 12409006, 12413642,
    13298314, 13946693, 13984941
}

# Load dataset
json_file_path = os.path.join(JSON_FOLDER_PATH, BOOKING_JSON_FILE_NAME)
with open(json_file_path, 'r', encoding='utf-8') as f:
    reviews_data = json.load(f)

# Find missing IDs and their codes
missing_with_codes = {}
for review in reviews_data:
    hotel_id = review.get('hotelId')
    if hotel_id in missing_ids:
        if hotel_id not in missing_with_codes:
            url = review.get('startUrl', '')
            
            # Try to find code from URL
            code = "UNKNOWN"
            if url:
                # Try exact match
                if url in url_to_code:
                    code = url_to_code[url]
                else:
                    # Try normalized match
                    url_base = url.rstrip('/').split('?')[0]
                    for idb_url, idb_code in url_to_code.items():
                        if idb_url.rstrip('/').split('?')[0] == url_base:
                            code = idb_code
                            break
            
            missing_with_codes[hotel_id] = code

print("❌ HOTEL IDs FALTANTES EN IDB.txt\n")
print(f"{'HOTEL_ID':<12} {'CÓDIGO':<10}")
print(f"{'-'*22}")

for hotel_id in sorted(missing_with_codes.keys()):
    code = missing_with_codes[hotel_id]
    print(f"{hotel_id:<12} {code:<10}")

print(f"\n\n✅ LINEAS PARA AGREGAR AL IDB.txt:\n")
for hotel_id in sorted(missing_with_codes.keys()):
    code = missing_with_codes[hotel_id]
    print(f"{hotel_id} ({code})")
