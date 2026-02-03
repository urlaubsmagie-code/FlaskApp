import json
import re
from pathlib import Path
from datetime import datetime
from deep_translator import GoogleTranslator
import time

# Patrones ESPECÍFICOS sobre VOLVER/REGRESAR (multiidioma)
# Solo comentarios que mencionan explícitamente que volverían
POSITIVE_PATTERNS = [
    # Alemán - Volver/Regresar
    r'gerne\s+wieder',
    r'wieder\s+kommen',
    r'wieder\s+buchen',
    r'wieder\s+zurück',
    r'jederzeit\s+wieder',
    r'immer\s+wieder\s+(gern|kommen)',
    r'gerne\s+zurück',
    r'würden?\s+wieder\s+(kommen|buchen)',
    r'kommen\s+(gerne|sicher|bestimmt)\s+wieder',
    r'auf\s+jeden\s+Fall\s+wieder',
    
    # Inglés - Come back/Return
    r'(would|will)\s+(definitely|gladly|surely|certainly)?\s*(come|be)\s+back',
    r'(would|will)\s+(definitely|gladly|surely)?\s*return',
    r'come\s+back\s+again',
    r'coming\s+back',
    r'stay\s+again',
    r'book\s+again',
    r'visit\s+again',
    r'back\s+again',
    r'return\s+(any\s+time|anytime)',
    r'happy\s+to\s+(return|come\s+back)',
    r'love\s+to\s+(return|come\s+back)',
    r"we'(ll|d)\s+(definitely\s+)?(be\s+back|return|come\s+back)",
    
    # Español - Volver/Regresar
    r'volver(ía|ía|emos|é|án)?',
    r'regres(ar|aré|aría|aríamos|aremos|arán)',
    r'(sin\s+duda|definitivamente|seguro)\s+(volver|regresar)',
    r'encantad(o|a|os|as)\s+(de|para)\s+(volver|regresar)',
    r'volveré\s+seguro',
    r'repetir(ía|emos|é)?',
    r'otra\s+vez',
    
    # Francés - Revenir/Retourner  
    r'(je|nous)\s+(re)?viendra(i|is|ons)',
    r'revenir\s+(avec\s+plaisir|volontiers|sûrement)',
    r'retourner\s+(avec\s+plaisir|volontiers)',
    r'retour\s+sans\s+hésiter',
    r'revenir\s+ici',
    
    # Italiano - Tornare/Ritornare
    r'torner(ei|ò|emmo|ebbe|ebbero)\s+(sicuramente|volentieri|certamente)?',
    r'ritorn(are|erò|erebbe|eremmo)',
    r'tornare\s+(sicuramente|di\s+sicuro)',
    r'senza\s+dubbio\s+torner',
    
    # Holandés - Terugkomen
    r'(zeker|graag|weer)\s+(terug)?komen',
    r'weer\s+terug',
    r'terug\s+(komen|gaan)',
    r'komen\s+terug',
    
    # Polaco - Wrócić
    r'wrócić\s+(na\s+pewno|chętnie|znowu)?',
    r'wróc(ę|imy|i)',
    r'przyjad(ę|ziemy)\s+(ponownie|znowu)',
    r'powróc(ę|imy)',
    
    # Checo - Vrátit
    r'vrát(it|ím|íme)\s+(se)?',
    r'určitě\s+(se\s+)?vrát',
    r'rád(a|i)?\s+(se\s+)?vrát',
    r'vrátíme\s+se',
    
    # Danés - Komme tilbage
    r'komme\s+tilbage',
    r'vende\s+tilbage',
    
    # Ruso - Вернуться (transliterado)
    r'верн(усь|емся|уться)',
    r'приед(у|ем)\s+(снова|опять)',
]

def extract_apartment_code(file_path):
    """
    Extrae el código del apartamento del nombre del archivo
    Ejemplos: AirbnbB2.json -> B2, BookingF3.json -> F3
    """
    file_name = Path(file_path).stem  # Obtiene nombre sin extensión
    if file_name.startswith('Airbnb'):
        return file_name.replace('Airbnb', '')
    elif file_name.startswith('Booking'):
        return file_name.replace('Booking', '')
    return 'UNKNOWN'

def search_positive_reviews(file_path, source_type='airbnb'):
    """
    Busca reviews con patrones positivos en un archivo JSON
    """
    try:
        apartment_code = extract_apartment_code(file_path)
        
        with open(file_path, 'r', encoding='utf-8') as f:
            reviews = json.load(f)
        
        positive_reviews = []
        
        for review in reviews:
            # Obtener el texto del review según la fuente
            if source_type == 'airbnb':
                text = review.get('reviewText', '')
                review_data = {
                    'source': 'Airbnb',
                    'apartmentCode': apartment_code,
                    'reviewId': review.get('reviewId'),
                    'listingUrl': review.get('listingUrl'),
                    'reviewerName': review.get('reviewerName'),
                    'reviewDate': review.get('reviewDate'),
                    'rating': review.get('rating'),
                    'reviewText': text,
                    'language': review.get('language'),
                    'response': review.get('response'),
                }
            else:  # booking
                liked = review.get('likedText', '') or ''
                disliked = review.get('dislikedText', '') or ''
                text = f"{liked} {disliked}".strip()
                review_data = {
                    'source': 'Booking.com',
                    'apartmentCode': apartment_code,
                    'reviewId': review.get('id'),
                    'hotelId': review.get('hotelId'),
                    'userName': review.get('userName'),
                    'reviewDate': review.get('reviewDate'),
                    'rating': review.get('rating'),
                    'likedText': liked,
                    'dislikedText': disliked,
                    'travelerType': review.get('travelerType'),
                    'language': review.get('reviewLanguage'),
                    'checkInDate': review.get('checkInDate'),
                    'checkOutDate': review.get('checkOutDate'),
                }
            
            # Buscar patrones positivos
            if text:
                matched_patterns = []
                for pattern in POSITIVE_PATTERNS:
                    if re.search(pattern, text, re.IGNORECASE):
                        matched_patterns.append(pattern)
                
                if matched_patterns:
                    review_data['matched_patterns'] = matched_patterns
                    review_data['full_text'] = text
                    review_data['original_language'] = review_data.get('language', 'unknown')
                    
                    # Traducir al alemán si no está en alemán
                    if review_data['original_language'] != 'de' and text:
                        try:
                            # Limitar longitud para traducción (máximo 5000 caracteres)
                            text_to_translate = text[:4500] if len(text) > 4500 else text
                            translator = GoogleTranslator(source='auto', target='de')
                            translated = translator.translate(text_to_translate)
                            review_data['translated_text'] = translated
                            time.sleep(0.5)  # Pausa para no sobrecargar la API
                        except Exception as e:
                            print(f"  Error traduciendo: {e}")
                            review_data['translated_text'] = text  # Mantener original si falla
                    else:
                        review_data['translated_text'] = text  # Ya está en alemán
                    
                    positive_reviews.append(review_data)
        
        return positive_reviews
    
    except Exception as e:
        print(f"Error procesando {file_path}: {e}")
        return []

def main():
    # Ruta de los archivos
    data_dir = Path(r'C:\Users\admin\Server\FlaskApp\data\DataProblemListing')
    
    # Obtener todos los archivos
    airbnb_files = list(data_dir.glob('Airbnb*.json'))
    booking_files = list(data_dir.glob('Booking*.json'))
    
    print(f"Encontrados {len(airbnb_files)} archivos de Airbnb")
    print(f"Encontrados {len(booking_files)} archivos de Booking")
    print()
    
    # Extraer reviews positivas de todos los archivos de Airbnb
    print("Extrayendo reviews positivas de Airbnb...")
    airbnb_reviews = []
    for i, file in enumerate(airbnb_files, 1):
        print(f"  Procesando {file.name} ({i}/{len(airbnb_files)})")
        reviews = search_positive_reviews(file, 'airbnb')
        airbnb_reviews.extend(reviews)
    
    print(f"\nExtrayendo reviews positivas de Booking...")
    booking_reviews = []
    for i, file in enumerate(booking_files, 1):
        print(f"  Procesando {file.name} ({i}/{len(booking_files)})")
        reviews = search_positive_reviews(file, 'booking')
        booking_reviews.extend(reviews)
    
    # Combinar resultados
    all_positive_reviews = {
        'extraction_date': datetime.now().isoformat(),
        'total_positive_reviews': len(airbnb_reviews) + len(booking_reviews),
        'airbnb_count': len(airbnb_reviews),
        'booking_count': len(booking_reviews),
        'patterns_searched': POSITIVE_PATTERNS,
        'reviews': {
            'airbnb': airbnb_reviews,
            'booking': booking_reviews
        }
    }
    
    # Guardar resultados
    output_file = Path(r'C:\Users\admin\Server\FlaskApp\positive_reviews_report.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_positive_reviews, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"RESUMEN DE EXTRACCIÓN")
    print(f"{'='*60}")
    print(f"Total de reviews positivas encontradas: {all_positive_reviews['total_positive_reviews']}")
    print(f"  - Airbnb: {len(airbnb_reviews)}")
    print(f"  - Booking: {len(booking_reviews)}")
    print(f"\nResultados guardados en: {output_file}")
    
    # Mostrar algunos ejemplos
    print(f"\n{'='*60}")
    print(f"EJEMPLOS DE REVIEWS POSITIVAS")
    print(f"{'='*60}")
    
    for i, review in enumerate(airbnb_reviews[:3], 1):
        print(f"\n[Airbnb #{i}]")
        print(f"Nombre: {review['reviewerName']}")
        print(f"Rating: {review['rating']}/5")
        print(f"Fecha: {review['reviewDate']}")
        print(f"Patrones encontrados: {', '.join(review['matched_patterns'])}")
        print(f"Texto: {review['full_text'][:200]}...")
    
    for i, review in enumerate(booking_reviews[:3], 1):
        print(f"\n[Booking #{i}]")
        print(f"Nombre: {review['userName']}")
        print(f"Rating: {review['rating']}/10")
        print(f"Fecha: {review['reviewDate']}")
        print(f"Patrones encontrados: {', '.join(review['matched_patterns'])}")
        print(f"Texto positivo: {review['likedText'][:200]}...")

if __name__ == '__main__':
    main()
