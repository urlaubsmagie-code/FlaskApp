from flask import Flask, render_template, jsonify
import json
import os
import random
import re
from datetime import datetime, timedelta
import locale
import hashlib
import shutil
from deep_translator import GoogleTranslator
from deep_translator.exceptions import TranslationNotFound, NotValidPayload

app = Flask(__name__)

# Configuración
JSON_FOLDER_PATH = r"C:\Users\admin\n8n-docker\files"
APARTMENT_CONFIG_FILE = "apartment_config.json"
ID_MAPPING_FILE = r"C:\Users\admin\Desktop\ID.txt"
IDB_MAPPING_FILE = r"C:\Users\admin\Desktop\IDB.txt"

# Nombre de los archivos JSON
JSON_FILE_NAME = "DatasetScr.json"  # Airbnb reviews
BOOKING_JSON_FILE_NAME = "DatasetScrBooking.json"  # Booking reviews
GENERAL_REVIEWS_FILE_NAME = "GeneralReviews.json"  # General problems

# Configuración de snapshots
SNAPSHOTS_DIR = os.path.join(os.path.dirname(__file__), 'data', 'snapshots')
SNAPSHOTS_METADATA_FILE = os.path.join(os.path.dirname(__file__), 'data', 'snapshots_metadata.json')
LAST_HASH_FILE = os.path.join(os.path.dirname(__file__), 'data', 'last_dataset_hash.txt')

# Máximo de días de antigüedad para mostrar reviews (30 días = 1 mes)
MAX_REVIEW_AGE_DAYS = 30

# IDs de apartamentos a excluir (no mostrar comentarios)
EXCLUDED_APARTMENT_IDS = {
    '50587278',
    '814427016412775340'
}

# Cache de traducciones para evitar llamadas repetidas
translation_cache = {}

def load_id_mapping():
    """Cargar mapeo de IDs desde ID.txt (para Airbnb)"""
    id_mapping = {}
    try:
        with open(ID_MAPPING_FILE, 'r', encoding='utf-8') as file:
            for line in file:
                line = line.strip()
                if not line or line.startswith('http'):
                    continue
                # Formato: "609172560881241855 (UT)"
                match = re.match(r'(\d+)\s*\(([^)]+)\)', line)
                if match:
                    apt_id = match.group(1)
                    apt_code = match.group(2)
                    id_mapping[apt_id] = apt_code
        return id_mapping
    except Exception as e:
        print(f"⚠️  Error cargando ID.txt: {e}")
        return {}

def load_idb_mapping():
    """Cargar mapeo de URLs de Booking desde IDB.txt"""
    idb_mapping = {}
    try:
        with open(IDB_MAPPING_FILE, 'r', encoding='utf-8') as file:
            for line in file:
                line = line.strip()
                if not line or not line.startswith('https://www.booking.com'):
                    continue
                # Formato: "https://www.booking.com/hotel/de/... (CODE)"
                match = re.match(r'(https://[^\s]+)\s+\(([^)]+)\)', line)
                if match:
                    booking_url = match.group(1)
                    apt_code = match.group(2)
                    idb_mapping[booking_url] = apt_code
        return idb_mapping
    except Exception as e:
        print(f"⚠️  Error cargando IDB.txt: {e}")
        return {}

def extract_apartment_id_from_url(url):
    """Extraer ID del apartamento de la URL de Airbnb"""
    if not url:
        return None
    match = re.search(r'/rooms/([0-9]+)', url)
    return match.group(1) if match else None

def load_apartment_config():
    """Cargar configuración de apartamentos desde JSON"""
    try:
        config_path = os.path.join(os.path.dirname(__file__), APARTMENT_CONFIG_FILE)
        with open(config_path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except Exception as e:
        print(f"⚠️  Error cargando configuración de apartamentos: {e}")
        # Configuración de respaldo
        return {
            "apartments": {
                '649153494847068923': {'code': 'H4', 'name': 'H4 - Appartment im maritimen Stil'},
                '940339949730055972': {'code': 'F3', 'name': 'F3 - Gemütliche Ferienwohnung'},
                '609172560881241855': {'code': 'UT', 'name': 'UT - Apartment mit Balkon und Flussblick'}
            },
            "default_apartment": {'code': 'UNK', 'name': 'Unbekanntes Apartment'}
        }

def get_apartment_name_from_url(listing_url):
    """Obtener nombre del apartamento desde la URL usando ID.txt (Airbnb)"""
    apartment_id = extract_apartment_id_from_url(listing_url)
    if not apartment_id:
        return 'Wohnung'
    
    # Intentar obtener código del ID.txt
    id_mapping = load_id_mapping()
    if apartment_id in id_mapping:
        code = id_mapping[apartment_id]
        return code  # Solo el código, sin "- Wohnung"
    
    # Si no está en ID.txt, intentar con config
    config = load_apartment_config()
    apartments = config.get('apartments', {})
    if apartment_id in apartments:
        return apartments[apartment_id]['name']
    
    # Valor por defecto
    return f'Wohnung {apartment_id[:6]}...'

def get_apartment_code_from_booking_url(booking_url):
    """Obtener código del apartamento desde URL de Booking usando IDB.txt"""
    if not booking_url:
        return None
    
    # Cargar mapeo de IDB.txt
    idb_mapping = load_idb_mapping()
    
    # Buscar coincidencia exacta primero
    booking_url_clean = booking_url.strip()
    if booking_url_clean in idb_mapping:
        return idb_mapping[booking_url_clean]
    
    # Buscar coincidencia parcial (sin query params o trailing slashes)
    booking_url_base = booking_url_clean.split('?')[0].rstrip('/')
    for mapped_url, code in idb_mapping.items():
        mapped_url_base = mapped_url.split('?')[0].rstrip('/')
        if booking_url_base == mapped_url_base:
            return code
    
    # Si no se encuentra, retornar None
    return None

def calculate_file_hash(file_path):
    """Calcular hash MD5 de un archivo para detectar cambios"""
    try:
        hash_md5 = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        print(f"⚠️  Error calculando hash: {e}")
        return None

def get_last_saved_hash():
    """Obtener el último hash guardado del dataset"""
    try:
        if os.path.exists(LAST_HASH_FILE):
            with open(LAST_HASH_FILE, 'r', encoding='utf-8') as f:
                return f.read().strip()
        return None
    except Exception as e:
        print(f"⚠️  Error leyendo hash guardado: {e}")
        return None

def save_hash(file_hash):
    """Guardar el hash actual del dataset"""
    try:
        os.makedirs(os.path.dirname(LAST_HASH_FILE), exist_ok=True)
        with open(LAST_HASH_FILE, 'w', encoding='utf-8') as f:
            f.write(file_hash)
        return True
    except Exception as e:
        print(f"⚠️  Error guardando hash: {e}")
        return False

def load_snapshots_metadata():
    """Cargar metadata de snapshots existentes"""
    try:
        if os.path.exists(SNAPSHOTS_METADATA_FILE):
            with open(SNAPSHOTS_METADATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {'snapshots': []}
    except Exception as e:
        print(f"⚠️  Error cargando metadata de snapshots: {e}")
        return {'snapshots': []}

def save_snapshots_metadata(metadata):
    """Guardar metadata de snapshots"""
    try:
        os.makedirs(os.path.dirname(SNAPSHOTS_METADATA_FILE), exist_ok=True)
        with open(SNAPSHOTS_METADATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"⚠️  Error guardando metadata de snapshots: {e}")
        return False

def create_snapshot(source_file_path):
    """Crear snapshot del dataset actual"""
    try:
        # Asegurar que existe el directorio de snapshots
        os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
        
        # Cargar metadata existente
        metadata = load_snapshots_metadata()
        snapshots = metadata.get('snapshots', [])
        
        # Calcular siguiente número de snapshot
        next_id = len(snapshots) + 1
        
        # Generar nombre de archivo con timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        snapshot_filename = f"dataset_{next_id:03d}_{timestamp}.json"
        snapshot_path = os.path.join(SNAPSHOTS_DIR, snapshot_filename)
        
        # Copiar archivo
        shutil.copy2(source_file_path, snapshot_path)
        
        # Calcular hash del snapshot
        file_hash = calculate_file_hash(snapshot_path)
        
        # Cargar datos para obtener estadísticas básicas
        with open(snapshot_path, 'r', encoding='utf-8') as f:
            reviews_data = json.load(f)
        
        # Contar apartamentos únicos
        apartments = set()
        for review in reviews_data:
            listing_url = review.get('listingUrl', '')
            apt_id = extract_apartment_id_from_url(listing_url)
            if apt_id:
                apartments.add(apt_id)
        
        # Agregar metadata del nuevo snapshot
        snapshot_info = {
            'id': next_id,
            'filename': snapshot_filename,
            'created_at': datetime.now().isoformat(),
            'total_reviews': len(reviews_data),
            'apartments_count': len(apartments),
            'hash': file_hash
        }
        
        snapshots.append(snapshot_info)
        metadata['snapshots'] = snapshots
        
        # Guardar metadata actualizada
        save_snapshots_metadata(metadata)
        
        print(f"✅ Snapshot creado: {snapshot_filename}")
        print(f"   📊 Reviews: {len(reviews_data)} | Apartamentos: {len(apartments)}")
        
        return snapshot_info
        
    except Exception as e:
        print(f"❌ Error creando snapshot: {e}")
        import traceback
        traceback.print_exc()
        return None

def check_and_create_snapshot():
    """Verificar si el dataset cambió y crear snapshot si es necesario"""
    try:
        json_file_path = os.path.join(JSON_FOLDER_PATH, JSON_FILE_NAME)
        
        if not os.path.exists(json_file_path):
            return False
        
        # Calcular hash actual del dataset
        current_hash = calculate_file_hash(json_file_path)
        if not current_hash:
            return False
        
        # Obtener hash guardado anteriormente
        last_hash = get_last_saved_hash()
        
        # Si el hash es diferente (o es la primera vez), crear snapshot
        if current_hash != last_hash:
            print(f"\n🔍 Dataset modificado detectado (hash: {current_hash[:8]}...)")
            
            # Crear snapshot
            snapshot_info = create_snapshot(json_file_path)
            
            if snapshot_info:
                # Guardar nuevo hash
                save_hash(current_hash)
                return True
        
        return False
        
    except Exception as e:
        print(f"⚠️  Error en verificación de snapshot: {e}")
        return False

def convert_iso_to_display(iso_date_str):
    """Convertir fecha ISO a formato de display (ej: 2025-10-12T13:49:27Z -> Oktober 2025)"""
    if not iso_date_str:
        return ''
    
    try:
        # Parsear fecha ISO
        dt = datetime.fromisoformat(iso_date_str.replace('Z', '+00:00'))
        
        # Calcular diferencia en días desde ahora
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        days_diff = (now - dt).days
        
        # Si es de hace menos de 7 días, usar "Vor X Tag"
        if days_diff == 0:
            return "Heute"
        elif days_diff == 1:
            return "Vor 1 Tag"
        elif days_diff < 7:
            return f"Vor {days_diff} Tage"
        elif days_diff < 30:
            weeks = days_diff // 7
            if weeks == 1:
                return "Vor 1 Woche"
            else:
                return f"Vor {weeks} Wochen"
        else:
            # Usar formato "Monat Jahr"
            month_names_de = [
                'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
                'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'
            ]
            month_name = month_names_de[dt.month - 1]
            return f"{month_name} {dt.year}"
    except Exception as e:
        print(f"⚠️  Error convirtiendo fecha '{iso_date_str}': {e}")
        return iso_date_str

def is_review_recent_iso(iso_date_str, max_days=30):
    """Verificar si una review es reciente basado en fecha ISO"""
    if not iso_date_str:
        return False
    
    try:
        # Parsear fecha ISO
        review_dt = datetime.fromisoformat(iso_date_str.replace('Z', '+00:00'))
        now = datetime.now(review_dt.tzinfo) if review_dt.tzinfo else datetime.now()
        
        # Calcular diferencia en días
        days_diff = (now - review_dt).days
        
        is_recent = days_diff <= max_days
        if days_diff <= 1:
            print(f"   Review: {days_diff} día(s) - INCLUIR")
        
        return is_recent
    except Exception as e:
        print(f"⚠️  Error parseando fecha ISO '{iso_date_str}': {e}")
        return False

def is_review_recent(date_str, max_days=30):
    """Verificar si una review es de los últimos N días (default: 30 días / 1 mes)"""
    if not date_str:
        return False  # Si no hay fecha, NO incluir la review
    
    now = datetime.now()
    date_str_lower = date_str.lower()
    
    try:
        # Formato: "Vor X Tag" o "Vor X Tage"
        if 'vor' in date_str_lower and 'tag' in date_str_lower:
            match = re.search(r'(\d+)', date_str)
            if match:
                days = int(match.group(1))
                is_recent = days <= max_days
                print(f"   Fecha '{date_str}': {days} días - {'INCLUIR' if is_recent else 'FILTRAR'}")
                return is_recent
        
        # Formato: "Vor X Woche" o "Vor X Wochen"
        if 'vor' in date_str_lower and 'woche' in date_str_lower:
            match = re.search(r'(\d+)', date_str)
            if match:
                weeks = int(match.group(1))
                days = weeks * 7
                is_recent = days <= max_days
                print(f"   Fecha '{date_str}': {weeks} semanas ({days} días) - {'INCLUIR' if is_recent else 'FILTRAR'}")
                return is_recent
        
        # Formato: "Oktober 2025", "September 2025", etc.
        month_names_de = {
            'januar': 1, 'februar': 2, 'märz': 3, 'april': 4,
            'mai': 5, 'juni': 6, 'juli': 7, 'august': 8,
            'september': 9, 'oktober': 10, 'november': 11, 'dezember': 12
        }
        
        for month_name, month_num in month_names_de.items():
            if month_name in date_str_lower:
                year_match = re.search(r'(\d{4})', date_str)
                if year_match:
                    year = int(year_match.group(1))
                    # Usar el último día del mes para ser más inclusivo
                    # Si es el mes actual, comparar desde hoy
                    if year == now.year and month_num == now.month:
                        # Es el mes actual - INCLUIR
                        print(f"   Fecha '{date_str}': Mes actual - INCLUIR")
                        return True
                    else:
                        # Calcular diferencia desde el último día del mes
                        # Para mes anterior, usar último día
                        if month_num == 12:
                            next_month = datetime(year + 1, 1, 1)
                        else:
                            next_month = datetime(year, month_num + 1, 1)
                        last_day_of_month = next_month - timedelta(days=1)
                        days_diff = (now - last_day_of_month).days
                        is_recent = days_diff <= max_days
                        print(f"   Fecha '{date_str}': {days_diff} días desde fin de mes - {'INCLUIR' if is_recent else 'FILTRAR'}")
                        return is_recent
        
        # Si no coincide con ningún formato conocido, NO incluir
        print(f"   Fecha '{date_str}': Formato desconocido - FILTRAR")
        return False
        
    except (ValueError, AttributeError) as e:
        print(f"⚠️  Error parseando fecha '{date_str}': {e}")
        return False

def translate_traveler_type(traveler_type):
    """Traducir tipo de viajero de Booking al alemán"""
    if not traveler_type:
        return None
    
    traveler_type_lower = traveler_type.lower().strip()
    
    # Diccionario de traducciones
    translations = {
        'couple': 'Paar',
        'family': 'Familie',
        'family with children': 'Familie mit Kindern',
        'friends': 'Freunde',
        'solo': 'Solo Reisende',
        'solo traveler': 'Solo Reisende',
        'business': 'Geschäftsreise',
        'business traveler': 'Geschäftsreise',
        'group': 'Gruppe',
    }
    
    # Buscar coincidencia exacta
    for en_key, de_value in translations.items():
        if en_key == traveler_type_lower:
            return de_value
    
    # Si no hay coincidencia exacta, devolver el original
    return traveler_type if traveler_type else None

def translate_room_info(room_info):
    """Traducir información de la habitación (ej: '1 room, 2 guests' -> '1 Zimmer, 2 Gäste')"""
    if not room_info:
        return None
    
    result = room_info
    
    # Hacer traducciones de frases completas primero (antes de palabras individuales)
    phrase_translations = {
        'single room': 'Einzelzimmer',
        'double room': 'Doppelzimmer',
        'twin room': 'Zweibettzimmer',
        'family room': 'Familienzimmer',
        'one-bedroom apartment': 'Einschlafzimmer-Wohnung',
        'one bedroom apartment': 'Einschlafzimmer-Wohnung',
        'two-bedroom apartment': 'Zweischlafzimmer-Wohnung',
        'two bedroom apartment': 'Zweischlafzimmer-Wohnung',
        'studio apartment': 'Studio-Wohnung',
        'one-bedroom': 'Einschlafzimmer',
        'two-bedroom': 'Zweischlafzimmer',
    }
    
    for en_phrase, de_phrase in phrase_translations.items():
        result = re.sub(r'\b' + en_phrase + r'\b', de_phrase, result, flags=re.IGNORECASE)
    
    # Luego hacer traducciones de palabras individuales
    word_translations = {
        'room': 'Zimmer',
        'rooms': 'Zimmer',
        'guest': 'Gast',
        'guests': 'Gäste',
        'bedroom': 'Schlafzimmer',
        'bedrooms': 'Schlafzimmer',
    }
    
    for en_word, de_word in word_translations.items():
        # Reemplazar palabras completas (case-insensitive)
        result = re.sub(r'\b' + en_word + r'\b', de_word, result, flags=re.IGNORECASE)
    
    return result

def translate_to_german(text, source_lang='auto'):
    """Traducir texto al alemán si no está en alemán
    
    Args:
        text: Texto a traducir
        source_lang: Código de idioma fuente ('auto' para detección automática)
    
    Returns:
        Tupla (texto_traducido, fue_traducido, idioma_original)
    """
    if not text or not isinstance(text, str) or len(text.strip()) < 3:
        return text, False, 'unknown'
    
    # Limpiar HTML tags para mejor detección de idioma
    text_clean = re.sub(r'<[^>]+>', '', text).strip()
    
    # Verificar cache primero
    cache_key = hashlib.md5(text_clean.encode('utf-8')).hexdigest()
    if cache_key in translation_cache:
        cached = translation_cache[cache_key]
        return cached['translated_text'], cached['was_translated'], cached['source_lang']
    
    try:
        # Intentar traducir usando Google Translator
        # deep-translator detecta automáticamente si es necesario traducir
        translator = GoogleTranslator(source='auto', target='de')
        translated_text = translator.translate(text_clean)
        
        # Si el texto traducido es igual al original, probablemente ya era alemán
        was_translated = translated_text != text_clean
        source_lang = 'de' if not was_translated else 'auto'
        
        # Guardar en cache
        translation_cache[cache_key] = {
            'translated_text': translated_text,
            'was_translated': was_translated,
            'source_lang': source_lang
        }
        
        return translated_text, was_translated, source_lang
        
    except (TranslationNotFound, NotValidPayload) as e:
        # Si no se puede traducir, retornar texto original
        print(f"⚠️  No se pudo traducir: {e}")
        return text, False, 'unknown'
    except Exception as e:
        # Si falla la traducción, retornar texto original
        print(f"⚠️  Error traduciendo texto: {e}")
        return text, False, 'error'

def load_reviews():
    """Cargar y procesar las reseñas desde DatasetScr.json (Airbnb) y DatasetScrBooking.json (Booking)"""
    processed_reviews = []
    apartment_stats = {}
    reviews_filtered_by_apartment = 0
    reviews_filtered_by_date = 0
    reviews_filtered_by_empty_content = 0  # Nuevo: reviews vacías de Booking
    total_reviews_found_airbnb = 0
    total_reviews_found_booking = 0
    unique_apartments = set()
    
    try:
        # Verificar y crear snapshot si el dataset cambió
        check_and_create_snapshot()
        
        # ===== CARGAR REVIEWS DE AIRBNB =====
        json_file_path_airbnb = os.path.join(JSON_FOLDER_PATH, JSON_FILE_NAME)
        
        if os.path.exists(json_file_path_airbnb):
            print(f"\n📁 Cargando reviews de Airbnb: {JSON_FILE_NAME}")
            
            with open(json_file_path_airbnb, 'r', encoding='utf-8') as file:
                reviews_data_airbnb = json.load(file)
            
            if isinstance(reviews_data_airbnb, list):
                total_reviews_found_airbnb = len(reviews_data_airbnb)
                print(f"✅ {total_reviews_found_airbnb} reviews de Airbnb encontradas")
                
                # Procesar cada review de Airbnb
                for review in reviews_data_airbnb:
                    listing_url = review.get('listingUrl', '')
                    reviewer_name = review.get('reviewerName', 'Anonym')
                    reviewer_picture = review.get('reviewerProfilePicture', '')
                    review_date_iso = review.get('reviewDate', '')
                    review_text = review.get('reviewText', '')
                    language = review.get('language', 'de')
                    review_id_num = review.get('reviewId', 0)
                    
                    # Extraer apartment_id de la URL
                    apartment_id = extract_apartment_id_from_url(listing_url)
                    if not apartment_id:
                        continue
                    
                    unique_apartments.add(apartment_id)
                    
                    # Filtrar apartamentos excluidos
                    if apartment_id in EXCLUDED_APARTMENT_IDS:
                        reviews_filtered_by_apartment += 1
                        continue
                    
                    # Convertir fecha ISO a formato legible
                    date_display = convert_iso_to_display(review_date_iso)
                    
                    # Filtrar reviews antiguas
                    if not is_review_recent_iso(review_date_iso, max_days=MAX_REVIEW_AGE_DAYS):
                        reviews_filtered_by_date += 1
                        continue
                    
                    # Obtener nombre del apartamento
                    apartment_name = get_apartment_name_from_url(listing_url)
                    
                    # Inicializar estadísticas del apartamento
                    if apartment_id not in apartment_stats:
                        apartment_stats[apartment_id] = {'count': 0, 'name': apartment_name, 'source': 'Airbnb'}
                    
                    # Generar ID único
                    review_id = f"airbnb_{review_id_num}_{apartment_id}"
                    
                    # Procesar rating (Airbnb usa escala de 5)
                    rating = review.get('rating', 0)
                    if not isinstance(rating, int):
                        rating = int(rating) if rating else 0
                    
                    processed_review = {
                        'id': review_id,
                        'text': review_text,
                        'rating': rating,
                        'max_rating': 5,  # Escala máxima de Airbnb
                        'platform_code': 'AB',  # Siglas para Airbnb
                        'date': date_display,
                        'reviewer_name': reviewer_name,
                        'reviewer_picture': reviewer_picture,
                        'reviewer_location': '',
                        'host_name': 'Urlaubsmagie',
                        'created_at': review_date_iso,
                        'language': language,
                        'apartment_id': apartment_id,
                        'apartment_name': apartment_name,
                        'apartment_url': listing_url,
                        'source': 'Airbnb',
                        'stay_info': None  # Airbnb no tiene información de estadías
                    }
                    
                    processed_reviews.append(processed_review)
                    apartment_stats[apartment_id]['count'] += 1
        else:
            print(f"\n⚠️  Archivo Airbnb no encontrado: {json_file_path_airbnb}")
        
        # ===== CARGAR REVIEWS DE BOOKING =====
        json_file_path_booking = os.path.join(JSON_FOLDER_PATH, BOOKING_JSON_FILE_NAME)
        
        if os.path.exists(json_file_path_booking):
            print(f"\n📁 Cargando reviews de Booking: {BOOKING_JSON_FILE_NAME}")
            
            with open(json_file_path_booking, 'r', encoding='utf-8') as file:
                reviews_data_booking = json.load(file)
            
            if isinstance(reviews_data_booking, list):
                total_reviews_found_booking = len(reviews_data_booking)
                print(f"✅ {total_reviews_found_booking} reviews de Booking encontradas")
                
                # Procesar cada review de Booking
                for review in reviews_data_booking:
                    booking_url = review.get('startUrl', '')
                    reviewer_name = review.get('userName', 'Anonym')
                    reviewer_picture = review.get('userAvatar', '')
                    review_date_iso = review.get('reviewDate', '')
                    rating_booking = review.get('rating', 0)
                    
                    # Validar que haya rating válido
                    if not rating_booking or (isinstance(rating_booking, (int, float)) and rating_booking == 0):
                        continue  # Saltar reviews sin rating
                    
                    # Construir texto de review de Booking
                    review_title = review.get('reviewTitle')
                    liked_text = review.get('likedText')
                    disliked_text = review.get('dislikedText')
                    room_info = review.get('roomInfo', '')
                    traveler_type = review.get('travelerType', '')
                    
                    # Combinar textos de review con manejo de null y traducción automática
                    review_parts = []
                    
                    # Traducir review_title si existe y no es alemán
                    if review_title:
                        title_translated, title_was_translated, title_lang = translate_to_german(review_title)
                        review_parts.append(f"<b>{title_translated}</b>")
                        if title_was_translated:
                            print(f"   🌐 Título traducido de {title_lang} a DE")
                    
                    # Traducir liked_text si existe y no es alemán
                    if liked_text:
                        liked_translated, liked_was_translated, liked_lang = translate_to_german(liked_text)
                        review_parts.append(f"👍 {liked_translated}")
                        if liked_was_translated:
                            print(f"   🌐 Texto positivo traducido de {liked_lang} a DE")
                    
                    # Traducir disliked_text si existe y no es alemán
                    if disliked_text:
                        disliked_translated, disliked_was_translated, disliked_lang = translate_to_german(disliked_text)
                        review_parts.append(f"👎 {disliked_translated}")
                        if disliked_was_translated:
                            print(f"   🌐 Texto negativo traducido de {disliked_lang} a DE")
                    
                    # Si no hay texto de review, usar información de la estadía
                    if not review_parts:
                        # Construir descripción basada en la estadía (EN ALEMÁN)
                        stay_parts = []
                        
                        # Traducir tipo de viajero al alemán
                        traveler_type_de = translate_traveler_type(traveler_type)
                        if traveler_type_de:
                            stay_parts.append(f"<i>{traveler_type_de}</i>")
                        
                        # Procesar room_info (puede tener "1 rooms, 2 guests" por ejemplo)
                        if room_info:
                            room_info_de = translate_room_info(room_info)
                            stay_parts.append(f"<b>{room_info_de}</b>")
                        
                        # Usar rating como resumen si no hay otro texto
                        if stay_parts:
                            review_parts.append(' - '.join(stay_parts))
                        else:
                            # Si tampoco hay información de estadía, crear mensaje neutral basado en rating
                            review_parts.append(f"Bewertung: <b>{rating_booking}/10</b>")
                    
                    review_text = '<br/>'.join(review_parts) if review_parts else f"Bewertung: <b>{rating_booking}/10</b>"
                    
                    # Validación final: evitar reviews completamente vacías
                    if not review_text or (len(review_text) < 5 and not review_title and not liked_text and not disliked_text):
                        reviews_filtered_by_empty_content += 1
                        continue  # Saltar si el texto es muy corto y no hay componentes de review
                    
                    language = review.get('reviewLanguage', 'de')
                    review_id_booking = review.get('id', '')
                    
                    # Obtener código del apartamento desde URL de Booking
                    apartment_code = get_apartment_code_from_booking_url(booking_url)
                    if not apartment_code:
                        continue
                    
                    # Usar el código como apartment_id para Booking
                    apartment_id = f"booking_{apartment_code}"
                    unique_apartments.add(apartment_id)
                    
                    # Convertir fecha ISO a formato legible
                    date_display = convert_iso_to_display(review_date_iso)
                    
                    # Filtrar reviews antiguas
                    if not is_review_recent_iso(review_date_iso, max_days=MAX_REVIEW_AGE_DAYS):
                        reviews_filtered_by_date += 1
                        continue
                    
                    # Nombre del apartamento es el código
                    apartment_name = apartment_code
                    
                    # Inicializar estadísticas del apartamento
                    if apartment_id not in apartment_stats:
                        apartment_stats[apartment_id] = {'count': 0, 'name': apartment_name, 'source': 'Booking'}
                    
                    # Generar ID único
                    review_id = f"booking_{review_id_booking}_{apartment_code}"
                    
                    # Procesar rating (Booking usa escala de 10, mantener original)
                    if isinstance(rating_booking, (int, float)):
                        rating = int(rating_booking)  # Mantener escala de 10
                    else:
                        rating = 0
                    
                    # Información de estadía para Booking
                    stay_info = {
                        'check_in': review.get('checkInDate', ''),
                        'check_out': review.get('checkOutDate', ''),
                        'number_of_nights': review.get('numberOfNights', 0),
                        'room_info': review.get('roomInfo', ''),
                        'traveler_type': review.get('travelerType', '')
                    }
                    
                    processed_review = {
                        'id': review_id,
                        'text': review_text,
                        'rating': rating,
                        'max_rating': 10,  # Escala máxima de Booking
                        'platform_code': 'BK',  # Siglas para Booking
                        'date': date_display,
                        'reviewer_name': reviewer_name if reviewer_name else 'Anonym',
                        'reviewer_picture': reviewer_picture if reviewer_picture else '',
                        'reviewer_location': review.get('userLocation', ''),
                        'host_name': 'Urlaubsmagie',
                        'created_at': review_date_iso,
                        'language': language,
                        'apartment_id': apartment_id,
                        'apartment_name': apartment_name,
                        'apartment_url': booking_url,
                        'source': 'Booking',
                        'stay_info': stay_info  # Información de estadía solo para Booking
                    }
                    
                    processed_reviews.append(processed_review)
                    apartment_stats[apartment_id]['count'] += 1
        else:
            print(f"\n⚠️  Archivo Booking no encontrado: {json_file_path_booking}")
        
        # Ordenar de forma aleatoria
        random.shuffle(processed_reviews)
        
        # Resumen final
        total_reviews = len(processed_reviews)
        total_apartments = len(unique_apartments)
        total_reviews_found = total_reviews_found_airbnb + total_reviews_found_booking
        
        print(f"\n📊 Resumen de carga:")
        print(f"   🏠 Total apartamentos únicos: {total_apartments}")
        print(f"   📄 Total comentarios encontrados:")
        print(f"      - Airbnb: {total_reviews_found_airbnb}")
        print(f"      - Booking: {total_reviews_found_booking}")
        print(f"      - Total: {total_reviews_found}")
        print(f"   🚭 Apartamentos excluidos: {reviews_filtered_by_apartment} comentarios")
        print(f"   📅 Filtrados por fecha (>{MAX_REVIEW_AGE_DAYS} días): {reviews_filtered_by_date} comentarios")
        print(f"   ⚠️  Filtrados por contenido vacío (Booking): {reviews_filtered_by_empty_content} comentarios")
        print(f"   ⭐ Comentarios finales (recientes, ≤{MAX_REVIEW_AGE_DAYS} días): {total_reviews}")
        print(f"\n🏠 Apartamentos con comentarios recientes:")
        for apt_id, info in apartment_stats.items():
            source_icon = "🅰️" if info['source'] == 'Airbnb' else "🅱️"
            print(f"   {source_icon} {info['name']}: {info['count']} comentarios")
        print()
        
        return processed_reviews
        
    except json.JSONDecodeError as e:
        print(f"❌ Error al leer JSON: {e}")
        return []
    except Exception as e:
        print(f"❌ Error crítico al cargar reviews: {e}")
        import traceback
        traceback.print_exc()
        return []

def get_apartment_info():
    """Información del apartamento basada en el ID"""
    config = load_apartment_config()
    general_info = config.get('general_info', {})
    apartments = config.get('apartments', {})
    
    # Crear lista de códigos de apartamentos
    apartment_codes = [apt['code'] for apt in apartments.values()]
    
    return {
        'id': '1086254381830942280',
        'name': f'Apartments {", ".join(apartment_codes)}',
        'title': general_info.get('title', 'Ferienwohnungen - Sächsische Schweiz'),
        'location': general_info.get('location', 'Sebnitz, Sächsische Schweiz'),
        'description': f'Gemütliche Ferienwohnungen mit verschiedenen Ausstattungen: {", ".join(apartment_codes)}',
        'host': general_info.get('host', 'Urlaubsmagie')
    }

def get_statistics(reviews):
    """Calcular estadísticas de las reseñas"""
    if not reviews:
        return {
            'total_reviews': 0,
            'average_rating': 0,
            'rating_distribution': {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
            'five_star_percentage': 0
        }
    
    total_reviews = len(reviews)
    # Filtrar ratings válidos (no None, no 0, y que sean números)
    ratings = []
    for r in reviews:
        rating = r.get('rating')
        if rating is not None and isinstance(rating, (int, float)) and rating > 0:
            ratings.append(int(rating))
    
    avg_rating = sum(ratings) / len(ratings) if ratings else 0
    
    # Contar distribución de estrellas
    rating_distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for rating in ratings:
        if rating in rating_distribution:
            rating_distribution[rating] += 1
    
    return {
        'total_reviews': total_reviews,
        'average_rating': round(avg_rating, 1),
        'rating_distribution': rating_distribution,
        'five_star_percentage': round((rating_distribution[5] / len(ratings)) * 100) if ratings else 0
    }

@app.route('/')
def index():
    """Página principal - Presentación automática de reseñas (Slideshow)"""
    reviews = load_reviews()
    apartment_info = get_apartment_info()
    stats = get_statistics(reviews)
    
    return render_template('slideshow.html', 
                         reviews=reviews,
                         apartment_info=apartment_info,
                         stats=stats,
                         total_reviews=len(reviews))

@app.route('/reviews')
def reviews_view():
    """Vista de reseñas con filtros y búsqueda"""
    reviews = load_reviews()
    stats = get_statistics(reviews)
    
    return render_template('index.html',
                         reviews=reviews,
                         stats=stats,
                         total_reviews=len(reviews))

@app.route('/slideshow')
def slideshow():
    """Ruta alternativa para slideshow"""
    return index()

@app.route('/api/reviews')
def api_reviews():
    """API endpoint para obtener todas las reseñas"""
    reviews = load_reviews()
    return jsonify(reviews)

@app.route('/api/stats')
def api_stats():
    """API endpoint para obtener estadísticas"""
    reviews = load_reviews()
    stats = get_statistics(reviews)
    return jsonify(stats)

@app.route('/analytics')
def analytics():
    """Página de análisis con gráficos temporales usando snapshots automáticos"""
    try:
        # Cargar metadata de snapshots automáticos
        metadata = load_snapshots_metadata()
        snapshot_list = metadata.get('snapshots', [])
        
        if not snapshot_list:
            return render_template('analytics.html', snapshots=[], has_data=False)
        
        # Procesar cada snapshot para generar estadísticas por apartamento
        processed_snapshots = []
        all_apartments = set()
        
        for snapshot_info in snapshot_list:
            snapshot_file = os.path.join(SNAPSHOTS_DIR, snapshot_info['filename'])
            
            if not os.path.exists(snapshot_file):
                continue
            
            # Leer archivo de snapshot
            with open(snapshot_file, 'r', encoding='utf-8') as f:
                reviews_data = json.load(f)
            
            # Calcular estadísticas por apartamento para este snapshot
            apartment_stats = {}
            
            for review in reviews_data:
                listing_url = review.get('listingUrl', '')
                rating = review.get('rating', 0)
                
                apartment_id = extract_apartment_id_from_url(listing_url)
                if not apartment_id or apartment_id in EXCLUDED_APARTMENT_IDS:
                    continue
                
                all_apartments.add(apartment_id)
                
                if apartment_id not in apartment_stats:
                    apartment_name = get_apartment_name_from_url(listing_url)
                    apartment_stats[apartment_id] = {
                        'apartment_id': apartment_id,
                        'apartment_name': apartment_name,
                        'total_reviews': 0,
                        'total_stars': 0,
                        'ratings': []
                    }
                
                if rating > 0:
                    apartment_stats[apartment_id]['total_reviews'] += 1
                    apartment_stats[apartment_id]['total_stars'] += rating
                    apartment_stats[apartment_id]['ratings'].append(rating)
            
            # Calcular promedios y porcentajes
            apartments_list = []
            for apt_id, stats in apartment_stats.items():
                if stats['total_reviews'] > 0:
                    avg_rating = stats['total_stars'] / stats['total_reviews']
                    five_stars = sum(1 for r in stats['ratings'] if r == 5)
                    five_star_pct = (five_stars / stats['total_reviews']) * 100 if stats['total_reviews'] > 0 else 0
                    
                    apartments_list.append({
                        'apartment_id': apt_id,
                        'apartment_name': stats['apartment_name'],
                        'total_reviews': stats['total_reviews'],
                        'average_rating': round(avg_rating, 2),
                        'five_star_percentage': round(five_star_pct, 1)
                    })
            
            # Agregar snapshot procesado
            processed_snapshots.append({
                'date': snapshot_info['created_at'][:10],  # Solo fecha (YYYY-MM-DD)
                'snapshot_id': snapshot_info['id'],
                'total_reviews': snapshot_info['total_reviews'],
                'apartments': apartments_list
            })
        
        # Preparar datos para cada apartamento (series temporales)
        apartments_data = {}
        for apt_id in all_apartments:
            apartments_data[apt_id] = {
                'name': '',
                'dates': [],
                'ratings': [],
                'reviews': [],
                'five_star_percentages': []
            }
        
        # Llenar datos por fecha
        for snapshot in processed_snapshots:
            date = snapshot['date']
            for apt in snapshot['apartments']:
                apt_id = apt['apartment_id']
                if apt_id in apartments_data:
                    apartments_data[apt_id]['name'] = apt['apartment_name']
                    apartments_data[apt_id]['dates'].append(date)
                    apartments_data[apt_id]['ratings'].append(apt['average_rating'])
                    apartments_data[apt_id]['reviews'].append(apt['total_reviews'])
                    apartments_data[apt_id]['five_star_percentages'].append(apt['five_star_percentage'])
        
        return render_template('analytics.html', 
                             snapshots=processed_snapshots,
                             apartments_data=apartments_data,
                             has_data=True)
    
    except Exception as e:
        print(f"❌ Error en analytics: {e}")
        import traceback
        traceback.print_exc()
        return render_template('analytics.html', snapshots=[], has_data=False)

@app.route('/rankings')
def rankings():
    """Página de rankings de apartamentos por estrellas (usa todas las reviews, sin filtro de fecha)"""
    try:
        # Leer todas las reviews sin filtro de fecha
        json_file_path = os.path.join(JSON_FOLDER_PATH, JSON_FILE_NAME)
        
        if not os.path.exists(json_file_path):
            return render_template('rankings.html', rankings=[], total_apartments=0, global_stats={})
        
        with open(json_file_path, 'r', encoding='utf-8') as file:
            all_reviews = json.load(file)
        
        # Calcular estadísticas por apartamento
        apartment_rankings = {}
        all_ratings = []  # Para estadísticas globales
        
        for review in all_reviews:
            listing_url = review.get('listingUrl', '')
            rating = review.get('rating', 0)
            
            # Extraer apartment_id
            apartment_id = extract_apartment_id_from_url(listing_url)
            if not apartment_id or apartment_id in EXCLUDED_APARTMENT_IDS:
                continue
            
            # Obtener nombre del apartamento
            apartment_name = get_apartment_name_from_url(listing_url)
            
            if apartment_id not in apartment_rankings:
                apartment_rankings[apartment_id] = {
                    'id': apartment_id,
                    'name': apartment_name,
                    'url': listing_url,
                    'total_reviews': 0,
                    'total_stars': 0,
                    'ratings': []
                }
            
            if rating > 0:
                apartment_rankings[apartment_id]['total_reviews'] += 1
                apartment_rankings[apartment_id]['total_stars'] += rating
                apartment_rankings[apartment_id]['ratings'].append(rating)
                all_ratings.append(rating)
        
        # Calcular promedio y distribución para cada apartamento
        rankings_list = []
        for apt_id, data in apartment_rankings.items():
            if data['total_reviews'] > 0:
                avg_rating = data['total_stars'] / data['total_reviews']
                
                # Distribución de estrellas
                rating_dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
                for r in data['ratings']:
                    if r in rating_dist:
                        rating_dist[r] += 1
                
                rankings_list.append({
                    'id': data['id'],
                    'name': data['name'],
                    'url': data['url'],
                    'average_rating': round(avg_rating, 2),
                    'total_reviews': data['total_reviews'],
                    'total_stars': data['total_stars'],
                    'rating_distribution': rating_dist,
                    'five_star_count': rating_dist[5],
                    'five_star_percentage': round((rating_dist[5] / data['total_reviews']) * 100) if data['total_reviews'] > 0 else 0
                })
        
        # Ordenar por promedio de estrellas (descendente)
        rankings_list.sort(key=lambda x: x['average_rating'], reverse=True)
        
        # Agrupar apartamentos por prefijo (completo)
        grouped_apartments = {}
        for apt in rankings_list:
            # Extraer prefijo completo (todas las letras antes del primer número)
            name = apt['name'] if apt['name'] else 'X'
            
            # Extraer prefijo: todas las letras consecutivas del inicio (sin números)
            prefix_match = re.match(r'^([A-Za-z]+)', name)
            if prefix_match:
                prefix = prefix_match.group(1).upper()  # Normalizar a mayúsculas
            else:
                prefix = 'OTHER'
            
            # Reglas especiales de agrupación
            if prefix == 'FAMZI':
                prefix = 'UO'  # FAMZI va con UO
            elif prefix == 'FO':
                prefix = 'HW'  # FO va con HW
            
            if prefix not in grouped_apartments:
                grouped_apartments[prefix] = {
                    'prefix': prefix,
                    'apartments': [],
                    'total_reviews': 0,
                    'total_stars': 0,
                    'count': 0
                }
            
            grouped_apartments[prefix]['apartments'].append(apt)
            grouped_apartments[prefix]['total_reviews'] += apt['total_reviews']
            grouped_apartments[prefix]['total_stars'] += apt['total_stars']
            grouped_apartments[prefix]['count'] += 1
        
        # Calcular promedio por grupo
        groups_list = []
        for prefix, group_data in grouped_apartments.items():
            avg_rating = group_data['total_stars'] / group_data['total_reviews'] if group_data['total_reviews'] > 0 else 0
            groups_list.append({
                'prefix': prefix,
                'apartments': group_data['apartments'],
                'average_rating': round(avg_rating, 2),
                'total_reviews': group_data['total_reviews'],
                'total_stars': group_data['total_stars'],
                'count': group_data['count']
            })
        
        # Ordenar grupos por promedio de estrellas
        groups_list.sort(key=lambda x: x['average_rating'], reverse=True)
        
        # Calcular estadísticas globales y destacados
        global_stats = {}
        if all_ratings and rankings_list:
            # Buscar apartamentos con más de cada tipo de estrella
            most_5_stars = max(rankings_list, key=lambda x: x['rating_distribution'][5])
            most_4_stars = max(rankings_list, key=lambda x: x['rating_distribution'][4])
            most_3_stars = max(rankings_list, key=lambda x: x['rating_distribution'][3])
            
            global_stats = {
                'total_reviews': len(all_ratings),
                'average_rating': round(sum(all_ratings) / len(all_ratings), 2),
                'five_star_total': sum(1 for r in all_ratings if r == 5),
                'four_star_total': sum(1 for r in all_ratings if r == 4),
                'three_star_total': sum(1 for r in all_ratings if r == 3),
                'rating_distribution': {
                    1: sum(1 for r in all_ratings if r == 1),
                    2: sum(1 for r in all_ratings if r == 2),
                    3: sum(1 for r in all_ratings if r == 3),
                    4: sum(1 for r in all_ratings if r == 4),
                    5: sum(1 for r in all_ratings if r == 5)
                },
                # Destacados (solo por tipo de estrellas)
                'most_5_stars': most_5_stars,
                'most_4_stars': most_4_stars,
                'most_3_stars': most_3_stars
            }
        
        return render_template('rankings.html',
                             rankings=rankings_list,
                             groups=groups_list,
                             total_apartments=len(rankings_list),
                             global_stats=global_stats)
    
    except Exception as e:
        print(f"❌ Error en rankings: {e}")
        import traceback
        traceback.print_exc()
        return render_template('rankings.html', rankings=[], total_apartments=0, global_stats={})

@app.route('/apartment-issues')
def apartment_issues():
    """Página de lista de problemas de apartamentos"""
    return render_template('apartment_issues.html')

@app.route('/api/apartment-issues')
def api_apartment_issues():
    """API endpoint para obtener problemas de apartamentos desde GeneralReviews.json"""
    try:
        general_reviews_path = os.path.join(JSON_FOLDER_PATH, GENERAL_REVIEWS_FILE_NAME)
        
        if not os.path.exists(general_reviews_path):
            return jsonify({
                'error': 'GeneralReviews.json no encontrado',
                'wohnungen': []
            }), 404
        
        with open(general_reviews_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Load history reviews from HRFinal.json
        hrfinal_path = os.path.join(os.path.dirname(__file__), 'HRFinal.json')
        history_wohnungen = []
        if os.path.exists(hrfinal_path):
            with open(hrfinal_path, 'r', encoding='utf-8') as f:
                hist_data = json.load(f)
            if isinstance(hist_data, list) and len(hist_data) > 0:
                history_wohnungen = hist_data[0].get('message', {}).get('content', {}).get('wohnungen', [])
        
        # Extract recents from general data
        recents_wohnungen = []
        if isinstance(data, list) and len(data) > 0:
            recents_wohnungen = data[0].get('message', {}).get('content', {}).get('wohnungen', [])
        
        # Merge history and recents for general view
        merged = {}
        for apt in history_wohnungen:
            merged[apt.get('wohnung')] = {
                'wohnung': apt.get('wohnung'),
                'probleme': apt.get('probleme', []).copy()
            }
        for apt in recents_wohnungen:
            key = apt.get('wohnung')
            if key in merged:
                # Merge problems, avoid duplicates based on description
                existing = merged[key]['probleme']
                for prob in apt.get('probleme', []):
                    if not any(p.get('beschreibung') == prob.get('beschreibung') for p in existing):
                        existing.append(prob)
            else:
                merged[key] = {
                    'wohnung': apt.get('wohnung'),
                    'probleme': apt.get('probleme', []).copy()
                }
        general_wohnungen = list(merged.values())
        
        return jsonify({
            'history': history_wohnungen,
            'recents': recents_wohnungen,
            'general': general_wohnungen
        })
    except Exception as e:
        print(f"❌ Error al cargar problemas de apartamentos: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': str(e),
            'wohnungen': []
        }), 500

@app.route('/api/apartment-reviews/<apartment_code>')
def api_apartment_reviews(apartment_code):
    """API endpoint para obtener reviews detalladas de un apartamento específico"""
    try:
        data_folder = os.path.join(os.path.dirname(__file__), 'data', 'DataProblemListing')
        
        # Map special apartment codes to their file names
        code_mapping = {
            'FZ': 'FAMZI',
            # Add more mappings here if needed
        }
        
        # Use mapped code if it exists, otherwise use original
        file_code = code_mapping.get(apartment_code, apartment_code)
        
        # Try both Airbnb and Booking files
        reviews = []
        
        # Load Airbnb reviews
        airbnb_file = os.path.join(data_folder, f'Airbnb{file_code}.json')
        if os.path.exists(airbnb_file):
            with open(airbnb_file, 'r', encoding='utf-8') as f:
                airbnb_data = json.load(f)
                for review in airbnb_data:
                    reviews.append({
                        'id': str(review.get('reviewId', '')),
                        'name': review.get('reviewerName', ''),
                        'date': review.get('reviewDate', ''),
                        'text': review.get('reviewText', ''),
                        'rating': review.get('rating', 0),
                        'source': 'Airbnb'
                    })
        
        # Load Booking reviews
        booking_file = os.path.join(data_folder, f'Booking{file_code}.json')
        if os.path.exists(booking_file):
            with open(booking_file, 'r', encoding='utf-8') as f:
                booking_data = json.load(f)
                for review in booking_data:
                    # Combine liked and disliked text
                    liked = review.get('likedText', '') or ''
                    disliked = review.get('dislikedText', '') or ''
                    full_text = ''
                    if liked:
                        full_text += f"👍 {liked}"
                    if disliked:
                        if full_text:
                            full_text += " | "
                        full_text += f"👎 {disliked}"
                    
                    reviews.append({
                        'id': '',  # Booking doesn't have review IDs
                        'name': review.get('userName', ''),
                        'date': review.get('reviewDate', ''),
                        'text': full_text or review.get('reviewTitle', ''),
                        'rating': review.get('rating', 0),
                        'source': 'Booking'
                    })
        
        return jsonify({
            'apartment': apartment_code,
            'reviews': reviews
        })
        
    except Exception as e:
        print(f"❌ Error al cargar reviews del apartamento {apartment_code}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': str(e),
            'reviews': []
        }), 500

@app.route('/api/current-reviews')
def api_current_reviews():
    """API endpoint para obtener reviews actuales desde DatasetScr y DatasetScrBooking"""
    try:
        dataset_folder = r'C:\Users\admin\n8n-docker\files'
        
        reviews = []
        
        # Load Airbnb reviews from DatasetScr.json
        airbnb_file = os.path.join(dataset_folder, 'DatasetScr.json')
        if os.path.exists(airbnb_file):
            with open(airbnb_file, 'r', encoding='utf-8') as f:
                airbnb_data = json.load(f)
                for review in airbnb_data:
                    reviews.append({
                        'id': str(review.get('reviewId', '')),
                        'name': review.get('reviewerName', ''),
                        'date': review.get('reviewDate', ''),
                        'text': review.get('reviewText', ''),
                        'rating': review.get('rating', 0),
                        'source': 'Airbnb'
                    })
        
        # Load Booking reviews from DatasetScrBooking.json
        booking_file = os.path.join(dataset_folder, 'DatasetScrBooking.json')
        if os.path.exists(booking_file):
            with open(booking_file, 'r', encoding='utf-8') as f:
                booking_data = json.load(f)
                for review in booking_data:
                    # Combine liked and disliked text
                    liked = review.get('likedText', '') or ''
                    disliked = review.get('dislikedText', '') or ''
                    full_text = ''
                    if liked:
                        full_text += f"👍 {liked}"
                    if disliked:
                        if full_text:
                            full_text += " | "
                        full_text += f"👎 {disliked}"
                    
                    reviews.append({
                        'id': review.get('id', ''),
                        'name': review.get('userName', ''),
                        'date': review.get('reviewDate', ''),
                        'text': full_text or review.get('reviewTitle', ''),
                        'rating': review.get('rating', 0),
                        'source': 'Booking'
                    })
        
        return jsonify({
            'reviews': reviews,
            'total': len(reviews)
        })
        
    except Exception as e:
        print(f"❌ Error al cargar reviews actuales: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': str(e),
            'reviews': []
        }), 500

@app.route('/api/backup-dates')
def api_backup_dates():
    """API endpoint para listar fechas de backup disponibles"""
    try:
        backup_folder = os.path.join(os.path.dirname(__file__), 'data', 'BackupIssues')
        
        if not os.path.exists(backup_folder):
            return jsonify({'dates': []})
        
        # Find all GeneralReviews backup files
        files = os.listdir(backup_folder)
        backup_dates = set()
        
        for filename in files:
            # Extract date from filename (e.g., GeneralReviews021225.json -> 021225)
            if filename.startswith('GeneralReviews') and filename.endswith('.json'):
                date_part = filename.replace('GeneralReviews', '').replace('.json', '')
                if len(date_part) == 6 and date_part.isdigit():
                    backup_dates.add(date_part)
        
        # Sort dates (most recent first)
        sorted_dates = sorted(list(backup_dates), reverse=True)
        
        # Convert to readable format
        date_list = []
        for date_str in sorted_dates:
            try:
                from datetime import datetime
                day = date_str[0:2]
                month = date_str[2:4]
                year = '20' + date_str[4:6]
                date_obj = datetime.strptime(f"{day}{month}{year}", "%d%m%Y")
                date_list.append({
                    'date_key': date_str,
                    'date_formatted': date_obj.strftime('%d.%m.%Y'),
                    'date_iso': date_obj.strftime('%Y-%m-%d')
                })
            except:
                continue
        
        return jsonify({'dates': date_list})
        
    except Exception as e:
        print(f"❌ Error al listar fechas de backup: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'dates': []}), 500

@app.route('/api/backup-data/<date_key>')
def api_backup_data(date_key):
    """API endpoint para obtener datos de backup de una fecha específica"""
    try:
        backup_folder = os.path.join(os.path.dirname(__file__), 'data', 'BackupIssues')
        
        # Load GeneralReviews backup for this date
        general_file = os.path.join(backup_folder, f'GeneralReviews{date_key}.json')
        
        if not os.path.exists(general_file):
            return jsonify({'error': 'Backup no encontrado', 'wohnungen': []}), 404
        
        with open(general_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Extract wohnungen from backup
        backup_wohnungen = []
        if isinstance(data, list) and len(data) > 0:
            backup_wohnungen = data[0].get('message', {}).get('content', {}).get('wohnungen', [])
        
        return jsonify({
            'date_key': date_key,
            'wohnungen': backup_wohnungen
        })
        
    except Exception as e:
        print(f"❌ Error al cargar backup {date_key}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': str(e),
            'wohnungen': []
        }), 500

@app.route('/api/backup-reviews/<date_key>')
def api_backup_reviews(date_key):
    """API endpoint para obtener reviews de backup de una fecha específica"""
    try:
        backup_folder = os.path.join(os.path.dirname(__file__), 'data', 'BackupIssues')
        
        reviews = []
        
        # Load Airbnb reviews from DatasetScr backup
        airbnb_file = os.path.join(backup_folder, f'DatasetScr{date_key}.json')
        if os.path.exists(airbnb_file):
            with open(airbnb_file, 'r', encoding='utf-8') as f:
                airbnb_data = json.load(f)
                for review in airbnb_data:
                    reviews.append({
                        'id': str(review.get('reviewId', '')),
                        'name': review.get('reviewerName', ''),
                        'date': review.get('reviewDate', ''),
                        'text': review.get('reviewText', ''),
                        'rating': review.get('rating', 0),
                        'source': 'Airbnb'
                    })
        
        # Load Booking reviews from DatasetScrBooking backup
        booking_file = os.path.join(backup_folder, f'DatasetScrBooking{date_key}.json')
        if os.path.exists(booking_file):
            with open(booking_file, 'r', encoding='utf-8') as f:
                booking_data = json.load(f)
                for review in booking_data:
                    # Combine liked and disliked text
                    liked = review.get('likedText', '') or ''
                    disliked = review.get('dislikedText', '') or ''
                    full_text = ''
                    if liked:
                        full_text += f"👍 {liked}"
                    if disliked:
                        if full_text:
                            full_text += " | "
                        full_text += f"👎 {disliked}"
                    
                    reviews.append({
                        'id': review.get('id', ''),
                        'name': review.get('userName', ''),
                        'date': review.get('reviewDate', ''),
                        'text': full_text or review.get('reviewTitle', ''),
                        'rating': review.get('rating', 0),
                        'source': 'Booking'
                    })
        
        return jsonify({
            'date_key': date_key,
            'reviews': reviews,
            'total': len(reviews)
        })
        
    except Exception as e:
        print(f"❌ Error al cargar reviews de backup {date_key}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': str(e),
            'reviews': []
        }), 500

@app.route('/api/snapshots')
def api_list_snapshots():
    """API endpoint para listar todos los snapshots disponibles"""
    try:
        metadata = load_snapshots_metadata()
        return jsonify(metadata)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/create-snapshot', methods=['POST'])
def api_create_snapshot():
    """API endpoint para crear un snapshot manual"""
    try:
        json_file_path = os.path.join(JSON_FOLDER_PATH, JSON_FILE_NAME)
        
        if not os.path.exists(json_file_path):
            return jsonify({'error': 'Dataset no encontrado'}), 404
        
        snapshot_info = create_snapshot(json_file_path)
        
        if snapshot_info:
            # Actualizar hash
            current_hash = calculate_file_hash(json_file_path)
            save_hash(current_hash)
            
            return jsonify({
                'success': True,
                'snapshot': snapshot_info,
                'message': 'Snapshot creado exitosamente'
            })
        else:
            return jsonify({'error': 'No se pudo crear el snapshot'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analytics-weekly')
def api_analytics_weekly():
    """API endpoint para analytics semanal usando BackupIssues"""
    try:
        backup_folder = os.path.join(os.path.dirname(__file__), 'data', 'BackupIssues')
        
        if not os.path.exists(backup_folder):
            return jsonify({'error': 'BackupIssues folder not found', 'backups': []}), 404
        
        # Buscar todas las fechas de backup (desde DatasetScr)
        files = os.listdir(backup_folder)
        backup_dates = set()
        
        for filename in files:
            if filename.startswith('DatasetScr') and filename.endswith('.json') and not filename.startswith('DatasetScrBooking'):
                # Extraer fecha: DatasetScr021225.json -> 021225
                date_part = filename.replace('DatasetScr', '').replace('.json', '')
                if len(date_part) == 6 and date_part.isdigit():
                    backup_dates.add(date_part)
        
        if not backup_dates:
            return jsonify({'error': 'No backups available', 'backups': []}), 404
        
        # Ordenar fechas (más antiguo primero para timeline)
        sorted_dates = sorted(list(backup_dates))
        
        # Procesar cada backup
        processed_backups = []
        all_apartments = {}
        
        for date_key in sorted_dates:
            # Convertir fecha DDMMYY a formato legible
            try:
                from datetime import datetime
                day = date_key[0:2]
                month = date_key[2:4]
                year = '20' + date_key[4:6]
                date_obj = datetime.strptime(f"{day}{month}{year}", "%d%m%Y")
                date_formatted = date_obj.strftime('%Y-%m-%d')
            except:
                continue
            
            # Leer archivos de este backup
            airbnb_file = os.path.join(backup_folder, f'DatasetScr{date_key}.json')
            booking_file = os.path.join(backup_folder, f'DatasetScrBooking{date_key}.json')
            
            apartment_stats = {}
            
            # Procesar Airbnb
            if os.path.exists(airbnb_file):
                with open(airbnb_file, 'r', encoding='utf-8') as f:
                    airbnb_reviews = json.load(f)
                
                for review in airbnb_reviews:
                    listing_url = review.get('listingUrl', '')
                    apartment_id = extract_apartment_id_from_url(listing_url)
                    
                    if not apartment_id or apartment_id in EXCLUDED_APARTMENT_IDS:
                        continue
                    
                    apt_code = get_apartment_name_from_url(listing_url)
                    rating = review.get('rating', 0)
                    
                    if apt_code not in apartment_stats:
                        apartment_stats[apt_code] = {'airbnb_ratings': [], 'booking_ratings': []}
                    
                    if rating > 0:
                        apartment_stats[apt_code]['airbnb_ratings'].append(rating)
            
            # Procesar Booking
            if os.path.exists(booking_file):
                with open(booking_file, 'r', encoding='utf-8') as f:
                    booking_reviews = json.load(f)
                
                for review in booking_reviews:
                    booking_url = review.get('startUrl', '')
                    apt_code = get_apartment_code_from_booking_url(booking_url)
                    
                    if not apt_code:
                        continue
                    
                    rating = review.get('rating', 0)
                    
                    if apt_code not in apartment_stats:
                        apartment_stats[apt_code] = {'airbnb_ratings': [], 'booking_ratings': []}
                    
                    if rating > 0:
                        apartment_stats[apt_code]['booking_ratings'].append(rating)
            
            # Calcular promedios combinados (normalizar Booking a escala 5)
            apartments_list = []
            for apt_code, stats in apartment_stats.items():
                airbnb_ratings = stats['airbnb_ratings']
                booking_ratings = stats['booking_ratings']
                
                # Normalizar Booking de 10 a 5
                all_ratings_normalized = airbnb_ratings + [r / 2 for r in booking_ratings]
                
                if all_ratings_normalized:
                    avg_rating = sum(all_ratings_normalized) / len(all_ratings_normalized)
                    apartments_list.append({
                        'code': apt_code,
                        'average_rating': round(avg_rating, 2),
                        'total_reviews': len(all_ratings_normalized)
                    })
                    
                    # Registrar apartamento
                    if apt_code not in all_apartments:
                        all_apartments[apt_code] = {'dates': [], 'ratings': []}
                    
                    all_apartments[apt_code]['dates'].append(date_formatted)
                    all_apartments[apt_code]['ratings'].append(round(avg_rating, 2))
            
            processed_backups.append({
                'date': date_formatted,
                'date_key': date_key,
                'apartments': apartments_list
            })
        
        # Preparar timeline
        timeline = []
        for apt_code, data in all_apartments.items():
            timeline.append({
                'code': apt_code,
                'dates': data['dates'],
                'ratings': data['ratings']
            })
        
        # Calcular tendencias
        trends = []
        for apt_code, data in all_apartments.items():
            if len(data['ratings']) >= 2:
                first_rating = data['ratings'][0]
                last_rating = data['ratings'][-1]
                change = last_rating - first_rating
                change_pct = (change / first_rating) * 100 if first_rating > 0 else 0
                
                trends.append({
                    'code': apt_code,
                    'first_rating': round(first_rating, 2),
                    'last_rating': round(last_rating, 2),
                    'change': round(change, 2),
                    'change_percentage': round(change_pct, 1),
                    'trend': 'up' if change > 0 else ('down' if change < 0 else 'stable')
                })
        
        # Ordenar trends por cambio (descendente)
        trends.sort(key=lambda x: x['change'], reverse=True)
        
        return jsonify({
            'timeline': timeline,
            'trends': trends,
            'backup_count': len(processed_backups),
            'date_range': {
                'start': processed_backups[0]['date'] if processed_backups else None,
                'end': processed_backups[-1]['date'] if processed_backups else None
            }
        })
        
    except Exception as e:
        print(f"❌ Error en api_analytics_weekly: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/analytics-general')
def api_analytics_general():
    """API endpoint para analytics usando datos históricos de DataProblemListing"""
    try:
        data_folder = os.path.join(os.path.dirname(__file__), 'data', 'DataProblemListing')
        
        if not os.path.exists(data_folder):
            return jsonify({'error': 'DataProblemListing folder not found'}), 404
        
        # Diccionario para almacenar stats por apartamento
        apartments = {}
        
        # Leer todos los archivos JSON
        for filename in os.listdir(data_folder):
            if not filename.endswith('.json'):
                continue
            
            # Determinar fuente (Airbnb o Booking) y código de apartamento
            if filename.startswith('Airbnb'):
                source = 'Airbnb'
                apt_code = filename.replace('Airbnb', '').replace('.json', '')
            elif filename.startswith('Booking'):
                source = 'Booking'
                apt_code = filename.replace('Booking', '').replace('.json', '')
            else:
                continue
            
            # Leer archivo
            file_path = os.path.join(data_folder, filename)
            with open(file_path, 'r', encoding='utf-8') as f:
                reviews = json.load(f)
            
            # Inicializar apartamento si no existe
            if apt_code not in apartments:
                apartments[apt_code] = {
                    'code': apt_code,
                    'airbnb': {'reviews': [], 'ratings': [], 'dates': []},
                    'booking': {'reviews': [], 'ratings': [], 'dates': []}
                }
            
            # Procesar reviews
            for review in reviews:
                if source == 'Airbnb':
                    rating = review.get('rating', 0)
                    date = review.get('reviewDate', '')
                    if rating > 0:
                        apartments[apt_code]['airbnb']['reviews'].append(review)
                        apartments[apt_code]['airbnb']['ratings'].append(rating)
                        apartments[apt_code]['airbnb']['dates'].append(date)
                else:  # Booking
                    rating = review.get('rating', 0)
                    date = review.get('reviewDate', '')
                    if rating > 0:
                        apartments[apt_code]['booking']['reviews'].append(review)
                        apartments[apt_code]['booking']['ratings'].append(rating)
                        apartments[apt_code]['booking']['dates'].append(date)
        
        # Calcular estadísticas por apartamento
        result = []
        for apt_code, data in apartments.items():
            airbnb_ratings = data['airbnb']['ratings']
            booking_ratings = data['booking']['ratings']
            
            apt_stats = {
                'code': apt_code,
                'airbnb': {
                    'total_reviews': len(airbnb_ratings),
                    'average_rating': round(sum(airbnb_ratings) / len(airbnb_ratings), 2) if airbnb_ratings else 0,
                    'five_star_count': sum(1 for r in airbnb_ratings if r == 5),
                    'five_star_percentage': round((sum(1 for r in airbnb_ratings if r == 5) / len(airbnb_ratings)) * 100, 1) if airbnb_ratings else 0
                },
                'booking': {
                    'total_reviews': len(booking_ratings),
                    'average_rating': round(sum(booking_ratings) / len(booking_ratings), 2) if booking_ratings else 0,
                    'ten_rating_count': sum(1 for r in booking_ratings if r == 10),
                    'ten_rating_percentage': round((sum(1 for r in booking_ratings if r == 10) / len(booking_ratings)) * 100, 1) if booking_ratings else 0
                },
                'combined': {
                    'total_reviews': len(airbnb_ratings) + len(booking_ratings)
                }
            }
            
            # Calcular rating combinado (normalizar Booking de 10 a 5)
            all_ratings_normalized = airbnb_ratings + [r / 2 for r in booking_ratings]
            if all_ratings_normalized:
                apt_stats['combined']['average_rating'] = round(sum(all_ratings_normalized) / len(all_ratings_normalized), 2)
            else:
                apt_stats['combined']['average_rating'] = 0
            
            result.append(apt_stats)
        
        # Ordenar por código de apartamento
        result.sort(key=lambda x: x['code'])
        
        return jsonify({
            'apartments': result,
            'total_apartments': len(result)
        })
        
    except Exception as e:
        print(f"❌ Error en api_analytics_general: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=80)
