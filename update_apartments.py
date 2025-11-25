#!/usr/bin/env python3
"""
Script para actualizar apartment_config.json desde el archivo ID.txt
Ejecutar este script cada vez que se agreguen nuevos apartamentos al archivo TXT
"""

import json
import os
import re

# Rutas de archivos
TXT_FILE_PATH = r"C:\Users\admin\Desktop\ID.txt"
CONFIG_FILE_PATH = "apartment_config.json"

def parse_txt_file():
    """Leer y parsear el archivo TXT con los IDs de apartamentos"""
    apartments = {}
    
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
                    apartment_code = match.group(2)
                    
                    apartments[apartment_id] = {
                        "code": apartment_code,
                        "name": f"{apartment_code} - Ferienwohnung",
                        "description": f"Apartamento {apartment_code} en Sebnitz"
                    }
                    print(f"✅ Línea {line_num}: {apartment_id} → {apartment_code}")
                else:
                    print(f"⚠️  Línea {line_num}: Formato no reconocido - '{line}'")
    
    except FileNotFoundError:
        print(f"❌ No se encontró el archivo: {TXT_FILE_PATH}")
        return {}
    except Exception as e:
        print(f"❌ Error leyendo el archivo TXT: {e}")
        return {}
    
    return apartments

def create_apartment_config(apartments):
    """Crear la configuración completa de apartamentos"""
    config = {
        "apartments": apartments,
        "default_apartment": {
            "code": "UNK",
            "name": "Unbekanntes Apartment",
            "description": "Apartamento no identificado"
        },
        "general_info": {
            "location": "Sebnitz, Sächsische Schweiz",
            "host": "Anna-Lena",
            "title": "Ferienwohnungen - Sächsische Schweiz"
        }
    }
    return config

def save_config(config):
    """Guardar la configuración en el archivo JSON"""
    try:
        with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as file:
            json.dump(config, file, indent=4, ensure_ascii=False)
        print(f"✅ Configuración guardada en: {CONFIG_FILE_PATH}")
        return True
    except Exception as e:
        print(f"❌ Error guardando configuración: {e}")
        return False

def main():
    print("🏠 Actualizando configuración de apartamentos...")
    print(f"📄 Leyendo: {TXT_FILE_PATH}")
    print(f"💾 Actualizando: {CONFIG_FILE_PATH}")
    print("-" * 50)
    
    # Parsear archivo TXT
    apartments = parse_txt_file()
    
    if not apartments:
        print("❌ No se encontraron apartamentos válidos")
        return
    
    print(f"\n📊 Resumen:")
    print(f"   🏡 Apartamentos encontrados: {len(apartments)}")
    print(f"   📝 Códigos únicos: {len(set(apt['code'] for apt in apartments.values()))}")
    
    # Mostrar lista de apartamentos
    print(f"\n🏠 Lista de apartamentos:")
    for apt_id, info in sorted(apartments.items()):
        print(f"   {info['code']}: ID {apt_id}")
    
    # Crear configuración
    config = create_apartment_config(apartments)
    
    # Guardar configuración
    if save_config(config):
        print(f"\n🎉 ¡Actualización completada exitosamente!")
        print(f"   📁 Archivo actualizado: {CONFIG_FILE_PATH}")
        print(f"   🏡 Total apartamentos: {len(apartments)}")
        print(f"\n💡 Tip: Ahora la aplicación Flask reconocerá automáticamente")
        print(f"     todos estos apartamentos cuando agregues nuevos archivos JSON.")
    else:
        print(f"\n❌ Error en la actualización")

if __name__ == "__main__":
    main()