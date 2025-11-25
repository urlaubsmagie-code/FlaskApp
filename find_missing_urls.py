#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Find URLs for missing Hotel IDs
"""

import json
import os

JSON_FOLDER_PATH = r"C:\Users\admin\n8n-docker\files"
BOOKING_JSON_FILE_NAME = "DatasetScrBooking.json"

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

print("❌ URLS DE HOTEL IDS FALTANTES\n")

found_urls = {}
for review in reviews_data:
    hotel_id = review.get('hotelId')
    if hotel_id in missing_ids and hotel_id not in found_urls:
        url = review.get('startUrl', '')
        found_urls[hotel_id] = url
        print(f"{url}")

print(f"\n\n✅ TOTAL ENCONTRADAS: {len(found_urls)}")
