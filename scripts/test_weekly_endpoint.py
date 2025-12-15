import requests

data = requests.get('http://192.168.178.188/api/analytics-weekly').json()

print('Backups found:', data.get('backup_count'))
print('Date range:', data.get('date_range'))
print('Apartments with timeline:', len(data.get('timeline', [])))
print('Trends calculated:', len(data.get('trends', [])))

print('\nTop 5 mejores tendencias:')
for t in data.get('trends', [])[:5]:
    print(f"  {t['code']}: {t['change']:+.2f} ({t['first_rating']} → {t['last_rating']}) - {t['trend']}")

print('\nTop 5 peores tendencias:')
for t in data.get('trends', [])[-5:]:
    print(f"  {t['code']}: {t['change']:+.2f} ({t['first_rating']} → {t['last_rating']}) - {t['trend']}")
