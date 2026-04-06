#!/usr/bin/env python3
"""
Script para generar HRFinal.json desde los archivos en PLD/
Fusiona apartamentos de Airbnb (AB) y Booking (BK) en un solo JSON consolidado
"""

import json
import os
import glob
import re
from collections import defaultdict

PLD_DIR = r"C:\Users\admin\Server\FlaskApp\PLD"
OUTPUT_FILE = r"C:\Users\admin\Server\FlaskApp\HRFinal.json"

def extract_apartment_code(filename):
    """
    Extraer código del apartamento desde el nombre del archivo.
    Ejemplos:
    - ABB2.json → B2
    - BKH1.json → H1
    - ABFAMZI.json → FAMZI
    """
    base = os.path.splitext(filename)[0]
    
    # Remover prefijo AB o BK
    if base.startswith("AB"):
        return base[2:]  # Quitar "AB"
    elif base.startswith("BK"):
        return base[2:]  # Quitar "BK"
    
    return base

def parse_pld_json(file_path):
    """
    Parsear archivos JSON de PLD que tienen estructura:
    [{
        "content": {
            "parts": [{"text": "{JSON_ESCAPADO}"}],
            "role": "model"
        },
        "finishReason": "STOP",
        "index": 0
    }]
    
    Retorna: (codigo_apartamento, lista_problemas, fuente)
    """
    filename = os.path.basename(file_path)
    apartment_code = extract_apartment_code(filename)
    source = "Airbnb" if filename.startswith("AB") else "Booking"
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Extraer el texto JSON escapado
        if isinstance(data, list) and len(data) > 0:
            parts = data[0].get('content', {}).get('parts', [])
            if parts and len(parts) > 0:
                text_content = parts[0].get('text', '{}')
                
                # Parsear el JSON interno
                try:
                    inner_data = json.loads(text_content)
                    probleme = inner_data.get('probleme', [])
                    
                    # Validar que cada problema tenga los campos necesarios
                    valid_probleme = []
                    for p in probleme:
                        if 'beschreibung' in p and 'erwähnungen' in p:
                            # Normalizar el campo de trazabilidad
                            # Puede ser "ID", "ids", o "Name"
                            trace_field = None
                            if 'ID' in p:
                                trace_field = 'ids'
                                p['ids'] = p.pop('ID')
                            elif 'ids' in p:
                                trace_field = 'ids'
                            elif 'Name' in p:
                                trace_field = 'names'
                                p['names'] = p.pop('Name')
                            
                            valid_probleme.append(p)
                    
                    return apartment_code, valid_probleme, source
                    
                except json.JSONDecodeError as e:
                    print(f"⚠️  Error parseando JSON interno en {filename}: {e}")
                    return apartment_code, [], source
        
        print(f"⚠️  Estructura inesperada en {filename}")
        return apartment_code, [], source
        
    except Exception as e:
        print(f"❌ Error leyendo {filename}: {e}")
        return apartment_code, [], source

def merge_apartments(apartments_data):
    """
    Fusionar problemas de Airbnb y Booking para el mismo apartamento.
    
    Input: {
        'B2': {
            'Airbnb': [lista_problemas],
            'Booking': [lista_problemas]
        }
    }
    
    Output: Lista de wohnungen con problemas fusionados
    """
    wohnungen = []
    
    for apt_code in sorted(apartments_data.keys()):
        sources = apartments_data[apt_code]
        all_problems = []
        
        # Agregar problemas de ambas fuentes
        for source, problems in sources.items():
            for p in problems:
                # Agregar metadata de fuente
                problem_with_source = p.copy()
                problem_with_source['quelle'] = source  # "quelle" = fuente en alemán
                all_problems.append(problem_with_source)
        
        if all_problems:
            wohnungen.append({
                'wohnung': apt_code,
                'probleme': all_problems
            })
    
    return wohnungen

def generate_hrfinal():
    """
    Generar HRFinal.json desde todos los archivos en PLD/
    """
    print("🔍 Escaneando archivos en PLD...")
    
    files = glob.glob(os.path.join(PLD_DIR, "*.json"))
    print(f"📄 Encontrados {len(files)} archivos JSON")
    
    # Estructura: {codigo_apartamento: {'Airbnb': [...], 'Booking': [...]}}
    apartments_data = defaultdict(lambda: defaultdict(list))
    
    total_problems = 0
    
    for file_path in files:
        filename = os.path.basename(file_path)
        apt_code, problems, source = parse_pld_json(file_path)
        
        if problems:
            apartments_data[apt_code][source].extend(problems)
            total_problems += len(problems)
            print(f"✅ {filename}: {len(problems)} problemas ({source})")
        else:
            print(f"⚠️  {filename}: Sin problemas válidos")
    
    print(f"\n📊 Resumen:")
    print(f"   🏠 Apartamentos únicos: {len(apartments_data)}")
    print(f"   🔧 Total problemas: {total_problems}")
    
    # Fusionar apartamentos
    print(f"\n🔄 Fusionando datos de Airbnb y Booking...")
    wohnungen = merge_apartments(apartments_data)
    
    # Estadísticas de fusión
    airbnb_only = sum(1 for apt in apartments_data.values() if 'Airbnb' in apt and 'Booking' not in apt)
    booking_only = sum(1 for apt in apartments_data.values() if 'Booking' in apt and 'Airbnb' not in apt)
    both = sum(1 for apt in apartments_data.values() if 'Airbnb' in apt and 'Booking' in apt)
    
    print(f"   🅰️  Solo Airbnb: {airbnb_only}")
    print(f"   🅱️  Solo Booking: {booking_only}")
    print(f"   🔀 Ambas plataformas: {both}")
    
    # Crear estructura final compatible con el estándar
    final_structure = [{
        "index": 0,
        "message": {
            "role": "assistant",
            "content": {
                "wohnungen": wohnungen
            }
        },
        "refusal": None,
        "annotations": []
    }]
    
    # Guardar archivo
    print(f"\n💾 Guardando {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_structure, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ ¡Completado exitosamente!")
    print(f"   📁 Archivo: {OUTPUT_FILE}")
    print(f"   🏠 Apartamentos: {len(wohnungen)}")
    print(f"   🔧 Total problemas: {total_problems}")
    
    # Mostrar muestra de apartamentos procesados
    print(f"\n🏠 Apartamentos procesados:")
    for wohnung in wohnungen[:10]:  # Mostrar primeros 10
        apt_code = wohnung['wohnung']
        num_problems = len(wohnung['probleme'])
        sources = set(p.get('quelle', 'Unknown') for p in wohnung['probleme'])
        sources_str = " + ".join(sorted(sources))
        print(f"   {apt_code}: {num_problems} problemas ({sources_str})")
    
    if len(wohnungen) > 10:
        print(f"   ... y {len(wohnungen) - 10} más")
    
    return True

if __name__ == "__main__":
    print("=" * 70)
    print("🏗️  GENERADOR DE HRFinal.json")
    print("=" * 70)
    print()
    
    try:
        success = generate_hrfinal()
        if success:
            print("\n" + "=" * 70)
            print("🎉 PROCESO COMPLETADO")
            print("=" * 70)
    except Exception as e:
        print(f"\n❌ Error crítico: {e}")
        import traceback
        traceback.print_exc()
