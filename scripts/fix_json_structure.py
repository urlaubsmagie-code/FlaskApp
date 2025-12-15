import json
import os
import glob

DATA_DIR = r"c:\Users\admin\Server\FlaskApp\ProblemListingData"

def fix_json_structure():
    files = glob.glob(os.path.join(DATA_DIR, "*.json"))
    print(f"Found {len(files)} JSON files.")

    for file_path in files:
        filename = os.path.basename(file_path)
        apartment_code = os.path.splitext(filename)[0]
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check if it's already in the correct format
            if isinstance(data, list) and len(data) > 0:
                content = data[0].get('message', {}).get('content', {})
                if 'wohnungen' in content:
                    print(f"Skipping {filename}: Already has 'wohnungen' key.")
                    continue
                
                # Extract 'probleme'
                probleme = content.get('probleme', [])
                
                if not probleme:
                    print(f"Warning {filename}: No 'probleme' found or empty.")
                    # Even if empty, we might want to restructure it? 
                    # Let's assume we still want to restructure it.
                
                # Create new structure
                new_structure = [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": {
                                "wohnungen": [
                                    {
                                        "wohnung": apartment_code,
                                        "probleme": probleme
                                    }
                                ]
                            }
                        },
                        "refusal": None,
                        "annotations": []
                    }
                ]
                
                # Write back to file
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(new_structure, f, ensure_ascii=False, indent=None) # indent=None to keep it compact like original? Or indent=2 for readability? Original was compact.
                
                print(f"Fixed {filename}")
            else:
                print(f"Skipping {filename}: Unexpected root structure (not a list or empty).")

        except Exception as e:
            print(f"Error processing {filename}: {e}")

if __name__ == "__main__":
    fix_json_structure()
