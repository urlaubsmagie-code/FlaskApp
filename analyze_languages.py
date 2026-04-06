import json
from pathlib import Path
from collections import Counter

def analyze_languages():
    data_dir = Path(r'C:\Users\admin\Server\FlaskApp\data\DataProblemListing')
    
    # Obtener todos los archivos
    airbnb_files = list(data_dir.glob('Airbnb*.json'))
    booking_files = list(data_dir.glob('Booking*.json'))
    
    print(f"Analizando {len(airbnb_files)} archivos de Airbnb...")
    print(f"Analizando {len(booking_files)} archivos de Booking...")
    print()
    
    # Contadores
    airbnb_languages = Counter()
    booking_languages = Counter()
    
    # Analizar Airbnb
    total_airbnb_reviews = 0
    for file in airbnb_files:
        try:
            with open(file, 'r', encoding='utf-8') as f:
                reviews = json.load(f)
                total_airbnb_reviews += len(reviews)
                for review in reviews:
                    lang = review.get('language', 'unknown')
                    if lang:
                        airbnb_languages[lang] += 1
        except Exception as e:
            print(f"Error en {file.name}: {e}")
    
    # Analizar Booking
    total_booking_reviews = 0
    for file in booking_files:
        try:
            with open(file, 'r', encoding='utf-8') as f:
                reviews = json.load(f)
                total_booking_reviews += len(reviews)
                for review in reviews:
                    lang = review.get('reviewLanguage', 'unknown')
                    if lang:
                        booking_languages[lang] += 1
        except Exception as e:
            print(f"Error en {file.name}: {e}")
    
    # Mostrar resultados
    print("=" * 70)
    print("ANÁLISIS DE IDIOMAS EN REVIEWS")
    print("=" * 70)
    print()
    
    print(f"📊 AIRBNB")
    print(f"Total de reviews: {total_airbnb_reviews}")
    print(f"Idiomas únicos: {len(airbnb_languages)}")
    print()
    print("Distribución por idioma:")
    for lang, count in airbnb_languages.most_common():
        percentage = (count / total_airbnb_reviews) * 100
        print(f"  {lang:15} {count:5} reviews ({percentage:5.2f}%)")
    
    print()
    print("-" * 70)
    print()
    
    print(f"📊 BOOKING.COM")
    print(f"Total de reviews: {total_booking_reviews}")
    print(f"Idiomas únicos: {len(booking_languages)}")
    print()
    print("Distribución por idioma:")
    for lang, count in booking_languages.most_common():
        percentage = (count / total_booking_reviews) * 100
        print(f"  {lang:15} {count:5} reviews ({percentage:5.2f}%)")
    
    print()
    print("=" * 70)
    print()
    
    # Todos los idiomas combinados
    all_languages = set(airbnb_languages.keys()) | set(booking_languages.keys())
    print(f"🌍 RESUMEN GENERAL")
    print(f"Total de reviews analizadas: {total_airbnb_reviews + total_booking_reviews}")
    print(f"Idiomas únicos encontrados: {len(all_languages)}")
    print()
    print("Idiomas encontrados:")
    for lang in sorted(all_languages):
        airbnb_count = airbnb_languages.get(lang, 0)
        booking_count = booking_languages.get(lang, 0)
        total = airbnb_count + booking_count
        print(f"  {lang:15} Total: {total:5} (Airbnb: {airbnb_count:4}, Booking: {booking_count:4})")
    
    print()
    print("=" * 70)
    
    # Mapeo de códigos de idioma a nombres
    language_names = {
        'de': 'Alemán',
        'en': 'Inglés',
        'es': 'Español',
        'fr': 'Francés',
        'it': 'Italiano',
        'nl': 'Holandés',
        'pl': 'Polaco',
        'cs': 'Checo',
        'pt': 'Portugués',
        'ru': 'Ruso',
        'da': 'Danés',
        'sv': 'Sueco',
        'no': 'Noruego',
        'fi': 'Finlandés',
        'hu': 'Húngaro',
        'ro': 'Rumano',
        'sk': 'Eslovaco',
        'sl': 'Esloveno',
        'bg': 'Búlgaro',
        'hr': 'Croata',
        'lt': 'Lituano',
        'lv': 'Letón',
        'et': 'Estonio',
        'zh': 'Chino',
        'ja': 'Japonés',
        'ko': 'Coreano',
        'ar': 'Árabe',
        'he': 'Hebreo',
        'tr': 'Turco',
        'uk': 'Ucraniano',
    }
    
    print()
    print("📝 NOMBRES DE IDIOMAS")
    print()
    for lang in sorted(all_languages):
        name = language_names.get(lang, 'Desconocido')
        total = airbnb_languages.get(lang, 0) + booking_languages.get(lang, 0)
        print(f"  {lang} = {name} ({total} reviews)")

if __name__ == '__main__':
    analyze_languages()
