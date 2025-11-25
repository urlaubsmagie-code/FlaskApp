"""
Script para crear snapshots semanales de estadísticas de apartamentos.
Ejecutar este script una vez por semana para mantener el historial.
"""

import json
import os
from datetime import datetime
from app import extract_apartment_id_from_url, get_apartment_name_from_url, EXCLUDED_APARTMENT_IDS

# Configuración
JSON_FOLDER_PATH = r"C:\Users\admin\n8n-docker\files"
DATASET_FILE = "DatasetScr.json"
SNAPSHOTS_FILE = r"C:\Users\admin\Server\FlaskApp\data\snapshots.json"

def create_snapshot():
    """Crear un snapshot de las estadísticas actuales"""
    
    print("\n📸 Creando snapshot de estadísticas...")
    
    # Crear directorio de datos si no existe
    os.makedirs(os.path.dirname(SNAPSHOTS_FILE), exist_ok=True)
    
    # Leer DatasetScr.json
    dataset_path = os.path.join(JSON_FOLDER_PATH, DATASET_FILE)
    
    if not os.path.exists(dataset_path):
        print(f"❌ Error: No se encontró {dataset_path}")
        return
    
    with open(dataset_path, 'r', encoding='utf-8') as f:
        all_reviews = json.load(f)
    
    # Calcular estadísticas por apartamento
    apartment_stats = {}
    
    for review in all_reviews:
        listing_url = review.get('listingUrl', '')
        rating = review.get('rating', 0)
        
        apartment_id = extract_apartment_id_from_url(listing_url)
        if not apartment_id or apartment_id in EXCLUDED_APARTMENT_IDS:
            continue
        
        if apartment_id not in apartment_stats:
            apartment_name = get_apartment_name_from_url(listing_url)
            apartment_stats[apartment_id] = {
                'id': apartment_id,
                'name': apartment_name,
                'total_reviews': 0,
                'total_stars': 0,
                'ratings': []
            }
        
        if rating > 0:
            apartment_stats[apartment_id]['total_reviews'] += 1
            apartment_stats[apartment_id]['total_stars'] += rating
            apartment_stats[apartment_id]['ratings'].append(rating)
    
    # Calcular promedios y distribuciones
    snapshot_data = []
    
    for apt_id, data in apartment_stats.items():
        if data['total_reviews'] > 0:
            avg_rating = data['total_stars'] / data['total_reviews']
            
            # Distribución de estrellas
            rating_dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            for r in data['ratings']:
                if r in rating_dist:
                    rating_dist[r] += 1
            
            snapshot_data.append({
                'apartment_id': apt_id,
                'apartment_name': data['name'],
                'average_rating': round(avg_rating, 2),
                'total_reviews': data['total_reviews'],
                'total_stars': data['total_stars'],
                'rating_distribution': rating_dist,
                'five_star_count': rating_dist[5],
                'five_star_percentage': round((rating_dist[5] / data['total_reviews']) * 100, 1)
            })
    
    # Ordenar por rating promedio
    snapshot_data.sort(key=lambda x: x['average_rating'], reverse=True)
    
    # Cargar snapshots existentes
    snapshots = []
    if os.path.exists(SNAPSHOTS_FILE):
        try:
            with open(SNAPSHOTS_FILE, 'r', encoding='utf-8') as f:
                snapshots = json.load(f)
        except:
            snapshots = []
    
    # Agregar nuevo snapshot
    new_snapshot = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'week': datetime.now().strftime('%Y-W%U'),  # Año-Semana
        'timestamp': datetime.now().isoformat(),
        'apartments': snapshot_data
    }
    
    snapshots.append(new_snapshot)
    
    # Guardar snapshots
    with open(SNAPSHOTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(snapshots, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Snapshot creado exitosamente!")
    print(f"   📅 Fecha: {new_snapshot['date']}")
    print(f"   📊 Semana: {new_snapshot['week']}")
    print(f"   🏠 Apartamentos: {len(snapshot_data)}")
    print(f"   💾 Guardado en: {SNAPSHOTS_FILE}")
    print(f"   📈 Total de snapshots: {len(snapshots)}")

if __name__ == '__main__':
    create_snapshot()
