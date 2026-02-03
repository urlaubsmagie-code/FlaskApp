import json

with open('C:/Users/admin/Server/FlaskApp/HRFinal.json', encoding='utf-8') as f:
    data = json.load(f)

wohnungen = data[0]['message']['content']['wohnungen']
f1 = [w for w in wohnungen if w['wohnung'] == 'F1'][0]

print(f"F1: {len(f1['probleme'])} problemas\n")

for i, p in enumerate(f1['probleme'][:15]):
    has_ids = 'ids' in p
    has_names = 'names' in p
    desc = p['beschreibung'][:50]
    print(f"{i+1:2d}. {desc:52s} | erwähnungen:{p['erwähnungen']} | ids:{has_ids} | names:{has_names}")
    if has_ids:
        print(f"     IDs: {p['ids']}")
    if has_names:
        print(f"     Names: {p['names']}")
