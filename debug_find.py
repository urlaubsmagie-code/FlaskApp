import json

with open('C:/Users/admin/Server/FlaskApp/HRFinal.json', encoding='utf-8') as f:
    data = json.load(f)

wohnungen = data[0]['message']['content']['wohnungen']

for w in wohnungen:
    for p in w['probleme']:
        if 'Inventar ist nicht stabil' in p.get('beschreibung', ''):
            print(f"Apartamento: {w['wohnung']}")
            print(f"Problema: {p['beschreibung']}")
            print(f"Names: {p.get('names', [])}")
            break
