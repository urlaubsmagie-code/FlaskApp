import pandas as pd
from pathlib import Path
from datetime import datetime
import shutil

def normalize_name(name):
    """Normaliza nombres para mejor comparación"""
    if pd.isna(name) or not name:
        return ""
    # Convertir a minúsculas y quitar espacios extras
    return str(name).lower().strip()

def get_month_year(date_str):
    """Extrae mes y año de una fecha"""
    if pd.isna(date_str) or not date_str:
        return None, None
    try:
        # Intentar parsear la fecha
        if isinstance(date_str, str):
            # Formato YYYY-MM-DD
            if '-' in date_str:
                parts = date_str.split('-')
                return int(parts[1]), int(parts[0])  # mes, año
            # Formato DD.MM.YY o DD.MM.YYYY
            elif '.' in date_str:
                parts = date_str.split('.')
                if len(parts) >= 2:
                    month = int(parts[1])
                    year = int(parts[2]) if len(parts[2]) == 4 else int('20' + parts[2])
                    return month, year
        elif isinstance(date_str, datetime):
            return date_str.month, date_str.year
    except:
        pass
    return None, None

def find_contact_info(name, apartment, review_date, wg_dir):
    """
    Busca información de contacto en los archivos Excel de apartamentos
    """
    # Normalizar búsqueda
    search_name = normalize_name(name)
    if not search_name:
        return None, None, None, None
    
    # Obtener mes y año del review
    review_month, review_year = get_month_year(review_date)
    if not review_month or not review_year:
        return None, None, None, None
    
    # Buscar archivo del apartamento
    apartment_file = wg_dir / f"{apartment}20222025.xlsx"
    
    if not apartment_file.exists():
        return None, None, None, None
    
    try:
        # Leer archivo del apartamento
        df_apartment = pd.read_excel(apartment_file)
        
        # Buscar coincidencias
        for idx, row in df_apartment.iterrows():
            guest_name = normalize_name(row.get('Gast', ''))
            
            # Verificar si el nombre coincide
            if search_name in guest_name or guest_name in search_name:
                # Verificar fecha (Anreise o Abreise)
                anreise_month, anreise_year = get_month_year(row.get('Anreise'))
                abreise_month, abreise_year = get_month_year(row.get('Abreise'))
                
                # Si el mes/año coincide con check-in o check-out
                if ((anreise_month == review_month and anreise_year == review_year) or
                    (abreise_month == review_month and abreise_year == review_year)):
                    
                    email = row.get('E-Mail')
                    telefon = row.get('Telefon')
                    nombre_completo = row.get('Gast')
                    direccion = row.get('Adresse')
                    
                    # Retornar si encontramos algo
                    if pd.notna(email) or pd.notna(telefon):
                        return (
                            email if pd.notna(email) else None,
                            telefon if pd.notna(telefon) else None,
                            nombre_completo if pd.notna(nombre_completo) else None,
                            direccion if pd.notna(direccion) else None
                        )
        
    except Exception as e:
        print(f"  ⚠️  Error buscando en {apartment_file.name}: {e}")
    
    return None, None, None, None

def enrich_reviews():
    print("=" * 80)
    print("ENRIQUECIMIENTO DE REVIEWS CON DATOS DE CONTACTO")
    print("=" * 80)
    print()
    
    # Rutas
    original_file = Path(r'C:\Users\admin\Server\FlaskApp\positive_reviews_simple.xlsx')
    backup_file = Path(r'C:\Users\admin\Server\FlaskApp\positive_reviews_simple_BACKUP.xlsx')
    enriched_file = Path(r'C:\Users\admin\Server\FlaskApp\positive_reviews_enriched.xlsx')
    wg_dir = Path(r'C:\Users\admin\Documents\wg')
    
    # 1. Crear backup
    print("📋 Paso 1: Creando backup del archivo original...")
    shutil.copy(original_file, backup_file)
    print(f"   ✓ Backup creado: {backup_file.name}")
    print()
    
    # 2. Leer Excel de reviews
    print("📖 Paso 2: Leyendo archivo de reviews...")
    df_reviews = pd.read_excel(original_file)
    print(f"   ✓ {len(df_reviews)} reviews cargadas")
    print()
    
    # 3. Agregar nuevas columnas
    df_reviews['Email'] = None
    df_reviews['Telefon'] = None
    df_reviews['Nombre_Completo'] = None
    df_reviews['Direccion'] = None
    
    # 4. Buscar coincidencias
    print("🔍 Paso 3: Buscando coincidencias y agregando datos de contacto...")
    print()
    
    matches_found = 0
    emails_found = 0
    phones_found = 0
    full_names_found = 0
    addresses_found = 0
    
    for idx, row in df_reviews.iterrows():
        name = row['Name']
        apartment = row['Wohnung']
        date = row['Datum']
        
        # Mostrar progreso cada 50 registros
        if (idx + 1) % 50 == 0:
            print(f"   Procesando {idx + 1}/{len(df_reviews)}...")
        
        # Buscar información de contacto
        email, telefon, nombre_completo, direccion = find_contact_info(name, apartment, date, wg_dir)
        
        if email or telefon:
            matches_found += 1
            if email:
                df_reviews.at[idx, 'Email'] = email
                emails_found += 1
            if telefon:
                df_reviews.at[idx, 'Telefon'] = telefon
                phones_found += 1
            if nombre_completo:
                df_reviews.at[idx, 'Nombre_Completo'] = nombre_completo
                full_names_found += 1
            if direccion:
                df_reviews.at[idx, 'Direccion'] = direccion
                addresses_found += 1
            
            print(f"   ✓ Match #{matches_found}: {name} ({apartment}) -> Email: {'✓' if email else '✗'} | Tel: {'✓' if telefon else '✗'} | Dir: {'✓' if direccion else '✗'}")
    
    print()
    print("=" * 80)
    print()
    
    # 5. Guardar archivo enriquecido
    print("💾 Paso 4: Guardando archivo enriquecido...")
    df_reviews.to_excel(enriched_file, index=False, engine='openpyxl')
    print(f"   ✓ Archivo guardado: {enriched_file.name}")
    print()
    
    # 6. Resumen final
    print("=" * 80)
    print("📊 RESUMEN FINAL")
    print("=" * 80)
    print()
    print(f"Total de reviews:              {len(df_reviews)}")
    print(f"Coincidencias encontradas:     {matches_found} ({matches_found/len(df_reviews)*100:.1f}%)")
    print(f"Emails agregados:              {emails_found}")
    print(f"Teléfonos agregados:           {phones_found}")
    print(f"Nombres completos agregados:   {full_names_found}")
    print(f"Direcciones agregadas:         {addresses_found}")
    print()
    print("📁 ARCHIVOS GENERADOS:")
    print()
    print(f"  1. {backup_file.name}")
    print(f"     → Backup del archivo original")
    print()
    print(f"  2. {enriched_file.name}")
    print(f"     → Archivo con datos de contacto agregados")
    print()
    print("=" * 80)

if __name__ == '__main__':
    enrich_reviews()
