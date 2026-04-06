#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verify that all apartment Hotel IDs from dataset are in IDB.txt
"""

import json
import os
import re

JSON_FOLDER_PATH = r"C:\n8n_Docker\Files"
BOOKING_JSON_FILE_NAME = "DatasetScrBooking.json"
IDB_FILE = r"C:\n8n_Docker\Files\IDB.txt"

# Load dataset
json_file_path = os.path.join(JSON_FOLDER_PATH, BOOKING_JSON_FILE_NAME)
with open(json_file_path, 'r', encoding='utf-8') as f:
    reviews_data = json.load(f)

# Extract unique Hotel IDs from dataset
dataset_hotel_ids = set()
for review in reviews_data:
    hotel_id = review.get('hotelId')
    if hotel_id:
        dataset_hotel_ids.add(hotel_id)

# Load IDB Hotel IDs
idb_hotel_ids = set()
with open(IDB_FILE, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('https') and not line.startswith('#'):
            # Format: "12412050 (B6)"
            match = re.match(r'(\d+)\s+\(([^)]+)\)', line)
            if match:
                hotel_id = int(match.group(1))
                idb_hotel_ids.add(hotel_id)

print(f"📊 VERIFICACIÓN DE HOTEL IDs\n")
print(f"Dataset - Hotel IDs únicos: {len(dataset_hotel_ids)}")
print(f"IDB.txt - Hotel IDs: {len(idb_hotel_ids)}\n")

# Find missing
missing = dataset_hotel_ids - idb_hotel_ids
extra = idb_hotel_ids - dataset_hotel_ids

if missing:
    print(f"❌ FALTANTES en IDB.txt ({len(missing)}):")
    for hotel_id in sorted(missing):
        print(f"   {hotel_id}")
else:
    print(f"✅ Todos los Hotel IDs del dataset están en IDB.txt")

if extra:
    print(f"\n⚠️ EXTRA en IDB.txt ({len(extra)}):")
    for hotel_id in sorted(extra):
        print(f"   {hotel_id}")

if not missing and not extra:
    print(f"\n✅ ¡PERFECTO! Todos los Hotel IDs coinciden.")
