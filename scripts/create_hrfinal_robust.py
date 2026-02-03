#!/usr/bin/env python3
"""
Script robusto para generar HRFinal.json desde archivos PLD/
Maneja errores de JSON truncados y extrae toda la información disponible
"""

import json
import os
import glob
from collections import defaultdict

PLD_DIR = r"C:\Users\admin\Server\FlaskApp\PLD"
OUTPUT_FILE = r"C:\Users\admin\Server\FlaskApp\HRFinal.json"

def extract_apartment_code(filename):
    """Extraer código del apartamento del nombre de archivo (sin AB/BK)"""
    base = os.path.splitext(filename)[0]
    if base.startswith("AB"):
        return base[2:]
    elif base.startswith("BK"):
        return base[2:]
    return base

def parse_pld_file(file_path):
    """
    Parsear archivo PLD extrayendo información incluso si está truncado
    Retorna: (codigo_apartamento, lista_problemas, fuente)
    """
    filename = os.path.basename(file_path)
    apt_code = extract_apartment_code(filename)
    source = "Airbnb" if filename.startswith("AB") else "Booking"
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parsear el JSON externo
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            print(f"⚠️  Error en JSON externo de {filename}: {e}")
            return apt_code, [], source
        
        # Extraer el texto interno
        if not isinstance(data, list) or len(data) == 0:
            print(f"⚠️  {filename}: Estructura de array vacía")
            return apt_code, [], source
        
        parts = data[0].get('content', {}).get('parts', [])
        if not parts or len(parts) == 0:
            print(f"⚠️  {filename}: Sin parts")
            return apt_code, [], source
        
        text_content = parts[0].get('text', '{}')
        
        # Intentar parsear el JSON interno
        try:
            inner_data = json.loads(text_content)
            probleme = inner_data.get('probleme', [])
        except json.JSONDecodeError:
            # Si falla, intentar extraer manualmente los problemas válidos
            print(f"⚠️  {filename}: JSON interno truncado, extrayendo datos parciales...")
            probleme = extract_partial_problems(text_content)
        
        # Procesar y normalizar problemas
        valid_probleme = []
        for p in probleme:
            if not isinstance(p, dict):
                continue
            
            if 'beschreibung' not in p or 'erwähnungen' not in p:
                continue
            
            # Normalizar campos de trazabilidad
            problem = {
                'beschreibung': p['beschreibung'],
                'erwähnungen': p['erwähnungen']
            }
            
            # Normalizar ID/ids/Name/names/namen
            if 'ID' in p:
                problem['ids'] = p['ID'] if isinstance(p['ID'], list) else [p['ID']]
            elif 'ids' in p:
                problem['ids'] = p['ids'] if isinstance(p['ids'], list) else [p['ids']]
            elif 'IDs' in p:
                problem['ids'] = p['IDs'] if isinstance(p['IDs'], list) else [p['IDs']]
            
            if 'Name' in p:
                problem['names'] = p['Name'] if isinstance(p['Name'], list) else [p['Name']]
            elif 'Namen' in p:
                problem['names'] = p['Namen'] if isinstance(p['Namen'], list) else [p['Namen']]
            elif 'names' in p:
                problem['names'] = p['names'] if isinstance(p['names'], list) else [p['names']]
            elif 'namen' in p:
                problem['names'] = p['namen'] if isinstance(p['namen'], list) else [p['namen']]
            
            valid_probleme.append(problem)
        
        return apt_code, valid_probleme, source
        
    except Exception as e:
        print(f"❌ Error crítico en {filename}: {e}")
        return apt_code, [], source

def extract_partial_problems(text_content):
    """
    Extraer problemas de JSON parcialmente válido/truncado
    Busca patrones de objetos problema incluso si el JSON está incompleto
    """
    import re
    
    probleme = []
    
    # Patrón para encontrar objetos problema
    # Busca desde { hasta el siguiente } considerando anidamiento
    pattern = r'\{\s*"beschreibung":\s*"([^"]+)",\s*"erwähnungen":\s*(\d+)(?:,\s*"(?:ID|ids|IDs|Name|Namen|names)":\s*(\[[^\]]+\]))?[^}]*\}'
    
    matches = re.finditer(pattern, text_content, re.DOTALL)
    
    for match in matches:
        beschreibung = match.group(1)
        erwähnungen = int(match.group(2))
        trace_data = match.group(3)
        
        problem = {
            'beschreibung': beschreibung,
            'erwähnungen': erwähnungen
        }
        
        if trace_data:
            try:
                trace_list = json.loads(trace_data)
                # Determinar si son IDs o nombres
                if trace_list and isinstance(trace_list[0], str):
                    if trace_list[0].isdigit() or len(trace_list[0]) > 15:
                        problem['ids'] = trace_list
                    else:
                        problem['names'] = trace_list
            except:
                pass
        
        probleme.append(problem)
    
    return probleme

def merge_apartments(apartments_data):
    """
    Fusionar datos de Airbnb y Booking para el mismo apartamento
    """
    wohnungen = []
    
    for apt_code in sorted(apartments_data.keys()):
        sources = apartments_data[apt_code]
        all_problems = []
        
        # Combinar problemas de ambas fuentes
        for source, problems in sorted(sources.items()):
            for p in problems:
                problem_copy = p.copy()
                all_problems.append(problem_copy)
        
        if all_problems:
            wohnungen.append({
                'wohnung': apt_code,
                'probleme': all_problems
            })
    
    return wohnungen

def generate_hrfinal():
    """Generar HRFinal.json desde todos los archivos PLD"""
    
    print("=" * 70)
    print("🏗️  GENERANDO HRFinal.json")
    print("=" * 70)
    print()
    
    files = sorted(glob.glob(os.path.join(PLD_DIR, "*.json")))
    print(f"📄 Archivos encontrados: {len(files)}\n")
    
    apartments_data = defaultdict(lambda: defaultdict(list))
    total_problems = 0
    files_with_errors = []
    
    for file_path in files:
        filename = os.path.basename(file_path)
        apt_code, problems, source = parse_pld_file(file_path)
        
        if problems:
            apartments_data[apt_code][source].extend(problems)
            total_problems += len(problems)
            print(f"✅ {filename:20s} → {apt_code:10s} | {len(problems):3d} problemas | {source}")
        else:
            files_with_errors.append(filename)
            print(f"⚠️  {filename:20s} → {apt_code:10s} | Sin datos válidos")
    
    print(f"\n{'=' * 70}")
    print("📊 RESUMEN")
    print(f"{'=' * 70}")
    print(f"🏠 Apartamentos únicos: {len(apartments_data)}")
    print(f"🔧 Total problemas: {total_problems}")
    print(f"✅ Archivos procesados correctamente: {len(files) - len(files_with_errors)}")
    print(f"⚠️  Archivos con errores: {len(files_with_errors)}")
    
    if files_with_errors:
        print(f"\n⚠️  Archivos que no pudieron procesarse:")
        for f in files_with_errors:
            print(f"   - {f}")
    
    # Fusionar apartamentos
    print(f"\n🔄 Fusionando apartamentos AB + BK...")
    wohnungen = merge_apartments(apartments_data)
    
    # Estadísticas
    airbnb_only = sum(1 for apt in apartments_data.values() if 'Airbnb' in apt and 'Booking' not in apt)
    booking_only = sum(1 for apt in apartments_data.values() if 'Booking' in apt and 'Airbnb' not in apt)
    both = sum(1 for apt in apartments_data.values() if 'Airbnb' in apt and 'Booking' in apt)
    
    print(f"   🅰️  Solo Airbnb: {airbnb_only}")
    print(f"   🅱️  Solo Booking: {booking_only}")
    print(f"   🔀 Ambas plataformas: {both}")
    
    # Crear estructura final
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
    
    # Guardar
    print(f"\n💾 Guardando {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_structure, f, ensure_ascii=False, indent=2)
    
    file_size = os.path.getsize(OUTPUT_FILE) / 1024
    
    print(f"\n{'=' * 70}")
    print("✅ COMPLETADO EXITOSAMENTE")
    print(f"{'=' * 70}")
    print(f"📁 Archivo: {OUTPUT_FILE}")
    print(f"📦 Tamaño: {file_size:.2f} KB")
    print(f"🏠 Apartamentos: {len(wohnungen)}")
    print(f"🔧 Problemas totales: {total_problems}")
    print()
    
    # Muestra de apartamentos
    print("🏠 Muestra de apartamentos procesados:")
    print(f"{'=' * 70}")
    for w in wohnungen[:15]:
        apt = w['wohnung']
        n_prob = len(w['probleme'])
        # Contar problemas con IDs (Airbnb) y Names (Booking)
        with_ids = sum(1 for p in w['probleme'] if 'ids' in p)
        with_names = sum(1 for p in w['probleme'] if 'names' in p)
        sources_info = []
        if with_ids > 0:
            sources_info.append(f"AB:{with_ids}")
        if with_names > 0:
            sources_info.append(f"BK:{with_names}")
        sources_str = " + ".join(sources_info) if sources_info else "sin trazabilidad"
        print(f"  {apt:10s} | {n_prob:3d} problemas | {sources_str}")
    
    if len(wohnungen) > 15:
        print(f"\n  ... y {len(wohnungen) - 15} apartamentos más")
    
    print(f"\n{'=' * 70}\n")

if __name__ == "__main__":
    generate_hrfinal()
