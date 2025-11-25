from flask import Flask, render_template, jsonify
import json
import os
import random
import re
from datetime import datetime, timedelta
import locale
import hashlib
import shutil

app = Flask(__name__)

# Configuración
JSON_FOLDER_PATH = r"C:\Users\admin\n8n-docker\files"
APARTMENT_CONFIG_FILE = "apartment_config.json"
ID_MAPPING_FILE = r"C:\Users\admin\Desktop\ID.txt"
IDB_MAPPING_FILE = r"C:\Users\admin\Desktop\IDB.txt"

# Nombre de los archivos JSON
JSON_FILE_NAME = "DatasetScr.json"  # Airbnb reviews
BOOKING_JSON_FILE_NAME = "DatasetScrBooking.json"  # Booking reviews

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


def load_reviews():
    """Cargar y procesar las reseñas desde DatasetScr.json (Airbnb) y DatasetScrBooking.json (Booking)"""
    processed_reviews = []
    apartment_stats = {}
    reviews_filtered_by_apartment = 0
    reviews_filtered_by_date = 0
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
                    
                    # Construir texto de review de Booking
                    review_title = review.get('reviewTitle', '')
                    liked_text = review.get('likedText', '')
                    disliked_text = review.get('dislikedText', '')
                    
                    # Combinar textos de review
                    review_parts = []
                    if review_title:
                        review_parts.append(f"<b>{review_title}</b>")
                    if liked_text:
                        review_parts.append(f"👍 {liked_text}")
                    if disliked_text:
                        review_parts.append(f"👎 {disliked_text}")
                    
                    review_text = '<br/>'.join(review_parts) if review_parts else ''
                    
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
                    rating_booking = review.get('rating', 0)
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
        print(f"   🚫 Apartamentos excluidos: {reviews_filtered_by_apartment} comentarios")
        print(f"   📅 Filtrados por fecha (>{MAX_REVIEW_AGE_DAYS} días): {reviews_filtered_by_date} comentarios")
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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
