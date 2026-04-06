import os
import json

def verify():
    # Mimic the logic in app.py
    base_dir = r'c:\Users\admin\Server\FlaskApp'
    local_data_path = os.path.join(base_dir, 'ProblemListingData')
    history_reviews_path = os.path.join(local_data_path, 'HistoryReviews.json')
    
    print(f"Checking path: {history_reviews_path}")
    if os.path.exists(history_reviews_path):
        print("File exists!")
        with open(history_reviews_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            print(f"Data loaded. Type: {type(data)}")
            if isinstance(data, list) and len(data) > 0:
                wohnungen = data[0].get('message', {}).get('content', {}).get('wohnungen', [])
                print(f"Found {len(wohnungen)} apartments in history.")
                for w in wohnungen:
                    print(f" - {w.get('wohnung')}: {len(w.get('probleme', []))} problems")
    else:
        print("File NOT found!")

if __name__ == "__main__":
    verify()
