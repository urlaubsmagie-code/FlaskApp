#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify if review IDs from GeneralReviews actually exist in datasets"""

import json

# Load files
print("Loading files...")
with open(r'C:\n8n_Docker\Files\GeneralReviews.json', 'r', encoding='utf-8') as f:
    gr = json.load(f)

with open(r'C:\n8n_Docker\Files\DatasetScr.json', 'r', encoding='utf-8') as f:
    ds = json.load(f)

with open(r'C:\n8n_Docker\Files\DatasetScrBooking.json', 'r', encoding='utf-8') as f:
    dsb = json.load(f)

print(f"Loaded {len(ds)} Airbnb reviews")
print(f"Loaded {len(dsb)} Booking reviews\n")

# Analyze Airbnb reviews
print("=== AIRBNB REVIEWS (DatasetScr.json) ===")
airbnb_review_ids = []
for review in ds[:3]:  # Show first 3
    rid = review.get('reviewId')
    print(f"Review ID: {rid}")
    print(f"  Type: {type(rid)}")
    print(f"  Name: {review.get('reviewerName')}")
    print(f"  Text: {review.get('reviewText', '')[:60]}...")
    airbnb_review_ids.append(rid)

print(f"\nAll Airbnb review ID types:")
id_types = {}
for review in ds:
    rid = review.get('reviewId')
    t = type(rid).__name__
    id_types[t] = id_types.get(t, 0) + 1
print(id_types)

# Analyze Booking reviews
print("\n=== BOOKING REVIEWS (DatasetScrBooking.json) ===")
booking_review_ids = []
for review in dsb[:3]:  # Show first 3
    rid = review.get('id')
    print(f"Review ID: {rid}")
    print(f"  Type: {type(rid)}")
    print(f"  Name: {review.get('userName')}")
    title = review.get('reviewTitle') or ''
    print(f"  Title: {title[:60] if title else 'N/A'}...")
    booking_review_ids.append(rid)

print(f"\nAll Booking review ID types:")
id_types = {}
for review in dsb:
    rid = review.get('id')
    t = type(rid).__name__
    id_types[t] = id_types.get(t, 0) + 1
print(id_types)

# Now check the problematic IDs from GeneralReviews
print("\n=== CHECKING PROBLEMATIC IDs ===")
problematic_ids = ['ca2b5af6b3fd40ec', '23e9c3e62ab0cbf2', '2d454fec22b676d2', 
                   'fd8ad07a8a449ef5', '885cfa1ad3737371', 'e6eb38a86ca9e468']

print("\nSearching in Airbnb reviews...")
for pid in problematic_ids:
    found = False
    for review in ds:
        rid = review.get('reviewId')
        # Try different comparison methods
        if rid == pid:
            found = True
            print(f"✓ Found {pid} (exact match)")
            break
        if str(rid) == pid:
            found = True
            print(f"✓ Found {pid} (string match)")
            break
        if str(rid) == str(pid):
            found = True
            print(f"✓ Found {pid} (both string)")
            break
    if not found:
        print(f"✗ NOT found: {pid}")

print("\nSearching in Booking reviews...")
for pid in problematic_ids:
    found = False
    for review in dsb:
        rid = review.get('id')
        # Try different comparison methods
        if rid == pid:
            found = True
            print(f"✓ Found {pid} (exact match)")
            break
        if str(rid) == pid:
            found = True
            print(f"✓ Found {pid} (string match)")
            break
        if str(rid) == str(pid):
            found = True
            print(f"✓ Found {pid} (both string)")
            break
    if not found:
        print(f"✗ NOT found: {pid}")

# Check what IDs are actually in GeneralReviews
print("\n=== SAMPLE IDs FROM GENERALREVIEWS ===")
wohnungen = gr[0]['message']['content']['wohnungen']
count = 0
for apt in wohnungen:
    for prob in apt.get('probleme', []):
        prob_id = prob.get('id')
        if prob_id and count < 5:
            print(f"Problem: {prob.get('beschreibung')[:40]}")
            print(f"  ID: {prob_id} (type: {type(prob_id).__name__})")
            if isinstance(prob_id, list):
                print(f"  List contents: {prob_id}")
            count += 1
