import json
import os
import glob
import re

DATA_DIR = r"c:\Users\admin\Server\FlaskApp\ProblemListingData"
OUTPUT_FILE = os.path.join(DATA_DIR, "HistoryReviews.json")

def get_apartment_code(filename):
    base = os.path.splitext(filename)[0]
    # Remove AB or BK prefix
    if base.startswith("AB"):
        return base[2:]
    elif base.startswith("BK"):
        return base[2:]
    return base

def aggregate_reviews():
    files = glob.glob(os.path.join(DATA_DIR, "*.json"))
    print(f"Found {len(files)} JSON files.")
    
    aggregated_data = {} # {apartment_code: [problems]}

    for file_path in files:
        if file_path == OUTPUT_FILE:
            continue
            
        filename = os.path.basename(file_path)
        apt_code = get_apartment_code(filename)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Expecting the structure we fixed earlier
            if isinstance(data, list) and len(data) > 0:
                content = data[0].get('message', {}).get('content', {})
                wohnungen = content.get('wohnungen', [])
                
                for apt in wohnungen:
                    probleme = apt.get('probleme', [])
                    if apt_code not in aggregated_data:
                        aggregated_data[apt_code] = []
                    
                    # Add source info to description if needed, or just extend?
                    # For now, just extend.
                    aggregated_data[apt_code].extend(probleme)
                    
        except Exception as e:
            print(f"Error reading {filename}: {e}")

    # Construct final JSON
    final_wohnungen = []
    for code, problems in aggregated_data.items():
        if not problems:
            continue
            
        final_wohnungen.append({
            "wohnung": code,
            "probleme": problems
        })
    
    # Sort by apartment code for consistency
    final_wohnungen.sort(key=lambda x: x['wohnung'])

    final_structure = [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": {
                    "wohnungen": final_wohnungen
                }
            },
            "refusal": None,
            "annotations": []
        }
    ]

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_structure, f, ensure_ascii=False, indent=None)
    
    print(f"Successfully created {OUTPUT_FILE} with {len(final_wohnungen)} apartments.")

if __name__ == "__main__":
    aggregate_reviews()
