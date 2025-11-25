#!/usr/bin/env python3
"""
Script para comparar IDs de apartamentos entre el JSON de enlaces y el archivo TXT
"""

import json
import re
import os

# Rutas de archivos
JSON_FILE_PATH = r"C:\Users\admin\Downloads\dataset_Airbnb-Listings-Url_2025-10-21_12-07-09-132.json"
TXT_FILE_PATH = r"C:\Users\admin\Desktop\ID.txt"

def extract_ids_from_json():
    """Extraer IDs de apartamentos desde el archivo JSON de enlaces"""
    ids = set()
    
    try:
        with open(JSON_FILE_PATH, 'r', encoding='utf-8') as file:
            data = json.load(file)
            
        # El JSON contiene una lista con un objeto que tiene "urls"
        if isinstance(data, list) and len(data) > 0:
            urls = data[0].get('urls', [])
            
            for url in urls:
                # Extraer ID de la URL: https://www.airbnb.de/rooms/ID
                match = re.search(r'/rooms/(\d+)', url)
                if match:
                    apartment_id = match.group(1)
                    ids.add(apartment_id)
                    
        print(f"✅ IDs extraídas del JSON: {len(ids)}")
        
    except FileNotFoundError:
        print(f"❌ No se encontró el archivo JSON: {JSON_FILE_PATH}")
        return set()
    except Exception as e:
        print(f"❌ Error leyendo JSON: {e}")
        return set()
    
    return ids

def extract_ids_from_txt():
    """Extraer IDs de apartamentos desde el archivo TXT"""
    ids = set()
    
    try:
        with open(TXT_FILE_PATH, 'r', encoding='utf-8') as file:
            for line_num, line in enumerate(file, 1):
                line = line.strip()
                if not line:  # Saltar líneas vacías
                    continue
                    
                # Buscar patrón: ID (CÓDIGO)
                match = re.match(r'(\d+)\s*\(([^)]+)\)', line)
                if match:
                    apartment_id = match.group(1)
                    ids.add(apartment_id)
                    
        print(f"✅ IDs extraídas del TXT: {len(ids)}")
        
    except FileNotFoundError:
        print(f"❌ No se encontró el archivo TXT: {TXT_FILE_PATH}")
        return set()
    except Exception as e:
        print(f"❌ Error leyendo TXT: {e}")
        return set()
    
    return ids

def compare_ids(json_ids, txt_ids):
    """Comparar las IDs y mostrar diferencias"""
    
    # IDs que están en JSON pero NO en TXT (faltan en TXT)
    missing_in_txt = json_ids - txt_ids
    
    # IDs que están en TXT pero NO en JSON (sobran en TXT o JSON incompleto)
    missing_in_json = txt_ids - json_ids
    
    # IDs que están en ambos
    common_ids = json_ids & txt_ids
    
    return {
        'missing_in_txt': missing_in_txt,
        'missing_in_json': missing_in_json,
        'common_ids': common_ids
    }

def main():
    print("🔍 Comparando IDs de apartamentos...")
    print(f"📄 JSON: {os.path.basename(JSON_FILE_PATH)}")
    print(f"📄 TXT:  {os.path.basename(TXT_FILE_PATH)}")
    print("-" * 70)
    
    # Extraer IDs
    json_ids = extract_ids_from_json()
    txt_ids = extract_ids_from_txt()
    
    if not json_ids or not txt_ids:
        print("❌ No se pudieron cargar las IDs de uno o ambos archivos")
        return
    
    # Comparar
    comparison = compare_ids(json_ids, txt_ids)
    
    print(f"\n📊 Resumen de comparación:")
    print(f"   🔗 Total IDs en JSON: {len(json_ids)}")
    print(f"   📝 Total IDs en TXT:  {len(txt_ids)}")
    print(f"   ✅ IDs comunes:       {len(comparison['common_ids'])}")
    print(f"   ❌ Faltan en TXT:     {len(comparison['missing_in_txt'])}")
    print(f"   ⚠️  Faltan en JSON:   {len(comparison['missing_in_json'])}")
    
    # Mostrar IDs que faltan en TXT
    if comparison['missing_in_txt']:
        print(f"\n❌ IDs que están en JSON pero FALTAN en TXT ({len(comparison['missing_in_txt'])}):")
        for apartment_id in sorted(comparison['missing_in_txt']):
            print(f"   🔗 {apartment_id}")
        
        print(f"\n💡 Para agregar al TXT, usa este formato:")
        for apartment_id in sorted(comparison['missing_in_txt']):
            print(f"   {apartment_id} (CÓDIGO_AQUÍ)")
    else:
        print(f"\n✅ Todas las IDs del JSON están en el TXT")
    
    # Mostrar IDs que faltan en JSON
    if comparison['missing_in_json']:
        print(f"\n⚠️  IDs que están en TXT pero FALTAN en JSON ({len(comparison['missing_in_json'])}):")
        print("    (Esto puede significar que el JSON no está completo)")
        for apartment_id in sorted(comparison['missing_in_json']):
            print(f"   📝 {apartment_id}")
    
    # Mostrar algunas IDs comunes como verificación
    if comparison['common_ids']:
        print(f"\n✅ Algunas IDs comunes (verificación):")
        common_sample = sorted(list(comparison['common_ids']))[:5]
        for apartment_id in common_sample:
            print(f"   ✓ {apartment_id}")
        if len(comparison['common_ids']) > 5:
            print(f"   ... y {len(comparison['common_ids']) - 5} más")

if __name__ == "__main__":
    main()