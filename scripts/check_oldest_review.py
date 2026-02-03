#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Find the oldest review date in DataProblemListing"""

import os
import json
from datetime import datetime

data_folder = r'C:\Users\admin\Server\FlaskApp\data\DataProblemListing'

oldest_airbnb = None
oldest_booking = None
oldest_airbnb_file = None
oldest_booking_file = None

# Check all files
for filename in os.listdir(data_folder):
    if not filename.endswith('.json'):
        continue
    
    file_path = os.path.join(data_folder, filename)
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reviews = json.load(f)
        
        for review in reviews:
            date_str = review.get('reviewDate', '')
            if not date_str:
                continue
            
            try:
                # Parse ISO date
                date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                
                if filename.startswith('Airbnb'):
                    if oldest_airbnb is None or date < oldest_airbnb:
                        oldest_airbnb = date
                        oldest_airbnb_file = filename
                elif filename.startswith('Booking'):
                    if oldest_booking is None or date < oldest_booking:
                        oldest_booking = date
                        oldest_booking_file = filename
            except:
                continue
                
    except Exception as e:
        print(f"Error reading {filename}: {e}")

print("=" * 70)
print("OLDEST REVIEWS IN DATAPROBLEM LISTING")
print("=" * 70)

if oldest_airbnb:
    print(f"\nAirbnb:")
    print(f"  Oldest date: {oldest_airbnb.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Found in: {oldest_airbnb_file}")
else:
    print("\nAirbnb: No reviews found")

if oldest_booking:
    print(f"\nBooking:")
    print(f"  Oldest date: {oldest_booking.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Found in: {oldest_booking_file}")
else:
    print("\nBooking: No reviews found")

print("\n" + "=" * 70)
