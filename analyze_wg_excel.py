import pandas as pd
from pathlib import Path
from datetime import datetime

def analyze_wg_files():
    wg_dir = Path(r'C:\Users\admin\Documents\wg')
    
    excel_files = list(wg_dir.glob('*.xlsx'))
    
    print("=" * 80)
    print("ANÁLISIS DE ARCHIVOS EXCEL DE APARTAMENTOS")
    print("=" * 80)
    print()
    print(f"📁 Total de archivos encontrados: {len(excel_files)}")
    print()
    
    # Diccionario para almacenar información
    apartments_data = {}
    total_bookings = 0
    total_nights = 0
    portals_summary = {}
    
    for file in sorted(excel_files):
        apartment_code = file.stem.replace('20222025', '')  # Extraer código (B1, F3, etc.)
        
        try:
            df = pd.read_excel(file)
            
            # Estadísticas básicas
            num_bookings = len(df)
            total_bookings += num_bookings
            
            # Portales
            if 'Portal' in df.columns:
                portals = df['Portal'].value_counts().to_dict()
                for portal, count in portals.items():
                    if pd.notna(portal):
                        portals_summary[portal] = portals_summary.get(portal, 0) + count
            
            # Noches totales
            if 'Anzahl Nächte' in df.columns:
                nights = df['Anzahl Nächte'].sum()
                if pd.notna(nights):
                    total_nights += int(nights)
            
            apartments_data[apartment_code] = {
                'bookings': num_bookings,
                'file_size': file.stat().st_size,
                'columns': len(df.columns)
            }
            
        except Exception as e:
            print(f"❌ Error en {file.name}: {e}")
    
    # Mostrar resumen por apartamento
    print("📊 RESERVAS POR APARTAMENTO:")
    print()
    for code in sorted(apartments_data.keys()):
        data = apartments_data[code]
        print(f"  {code:10} {data['bookings']:4} reservas")
    
    print()
    print("=" * 80)
    print()
    
    # Resumen general
    print("🎯 RESUMEN GENERAL (2022-2025)")
    print()
    print(f"Total de apartamentos:     {len(apartments_data)}")
    print(f"Total de reservas:         {total_bookings}")
    print(f"Total de noches:           {total_nights:,}")
    print(f"Promedio reservas/apto:    {total_bookings / len(apartments_data):.1f}")
    
    print()
    print("=" * 80)
    print()
    
    # Portales
    print("🌐 DISTRIBUCIÓN POR PORTAL:")
    print()
    for portal, count in sorted(portals_summary.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total_bookings) * 100
        print(f"  {portal:20} {count:5} reservas ({percentage:5.1f}%)")
    
    print()
    print("=" * 80)
    print()
    
    # Información de columnas
    print("📋 COLUMNAS EN LOS ARCHIVOS:")
    print()
    sample_file = excel_files[0]
    df_sample = pd.read_excel(sample_file)
    for i, col in enumerate(df_sample.columns, 1):
        print(f"  {i:2}. {col}")
    
    print()
    print("=" * 80)
    
    return apartments_data

if __name__ == '__main__':
    analyze_wg_files()
