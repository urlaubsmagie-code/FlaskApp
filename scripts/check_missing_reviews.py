#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check how many problems in GeneralReviews have missing review data"""

import json

# Load files
with open(r'C:\n8n_Docker\Files\GeneralReviews.json', 'r', encoding='utf-8') as f:
    gr = json.load(f)

with open(r'C:\n8n_Docker\Files\DatasetScr.json', 'r', encoding='utf-8') as f:
    ds = json.load(f)

with open(r'C:\n8n_Docker\Files\DatasetScrBooking.json', 'r', encoding='utf-8') as f:
    dsb = json.load(f)

# Create sets of available IDs and names
airbnb_ids = set(str(r.get('reviewId', '')) for r in ds)
booking_ids = set(str(r.get('id', '')) for r in dsb)
booking_names = set(r.get('userName', '') for r in dsb if r.get('userName'))

total = 0
missing = 0
missing_examples = []

wohnungen = gr[0]['message']['content']['wohnungen']

for apt in wohnungen:
    apt_code = apt.get('wohnung')
    for prob in apt.get('probleme', []):
        total += 1
        prob_id = prob.get('id')
        prob_names = prob.get('names', [])
        has_match = False
        
        # Check IDs
        if prob_id:
            if isinstance(prob_id, list):
                has_match = any(str(i) in airbnb_ids or str(i) in booking_ids for i in prob_id)
            else:
                has_match = str(prob_id) in airbnb_ids or str(prob_id) in booking_ids
        
        # Check names
        if not has_match and prob_names:
            has_match = any(name in booking_names for name in prob_names)
        
        if not has_match:
            missing += 1
            if len(missing_examples) < 5:
                missing_examples.append({
                    'apartment': apt_code,
                    'problem': prob.get('beschreibung')[:50],
                    'mentions': prob.get('erwähnungen'),
                    'id': prob_id,
                    'names': prob_names
                })

print(f'Total problemas: {total}')
print(f'Sin reviews encontradas: {missing}')
print(f'Porcentaje sin datos: {missing/total*100:.1f}%')
print(f'\nReviews disponibles en DatasetScr: {len(airbnb_ids)}')
print(f'Reviews disponibles en DatasetScrBooking: {len(booking_ids)}')
print(f'\nEjemplos de problemas sin datos:')
for ex in missing_examples:
    print(f"  - {ex['apartment']}: {ex['problem']} ({ex['mentions']} menciones)")
    print(f"    ID: {ex['id']}, Names: {ex['names']}")
