import pandas as pd

# Leer archivo de ejemplo
df = pd.read_excel('C:/Users/admin/Documents/wg/B120222025.xlsx')

print('=== ANÁLISIS DE DATOS DE CONTACTO ===')
print()
print('📊 Total de reservas en B1:', len(df))
print()
print('🔍 Columnas con información de contacto:')
print()

# 1. Nombres
print('1. NOMBRE (Gast):')
gast_filled = df['Gast'].notna().sum()
print(f'   - Registros con nombre: {gast_filled}/{len(df)} ({gast_filled/len(df)*100:.1f}%)')
print('   - Ejemplos:')
for name in df[df['Gast'].notna()]['Gast'].head(5):
    print(f'     • {name}')
print()

# 2. Email
print('2. EMAIL (E-Mail):')
email_filled = df['E-Mail'].notna().sum()
print(f'   - Registros con email: {email_filled}/{len(df)} ({email_filled/len(df)*100:.1f}%)')
if email_filled > 0:
    print('   - Ejemplos:')
    for email in df[df['E-Mail'].notna()]['E-Mail'].head(3):
        print(f'     • {email}')
print()

# 3. Teléfono
print('3. TELÉFONO (Telefon):')
phone_filled = df['Telefon'].notna().sum()
print(f'   - Registros con teléfono: {phone_filled}/{len(df)} ({phone_filled/len(df)*100:.1f}%)')
if phone_filled > 0:
    print('   - Ejemplos:')
    for phone in df[df['Telefon'].notna()]['Telefon'].head(3):
        print(f'     • {phone}')
print()

# 4. Dirección
print('4. DIRECCIÓN (Adresse):')
addr_filled = df['Adresse'].notna().sum()
print(f'   - Registros con dirección: {addr_filled}/{len(df)} ({addr_filled/len(df)*100:.1f}%)')
if addr_filled > 0:
    print('   - Ejemplos:')
    for addr in df[df['Adresse'].notna()]['Adresse'].head(2):
        print(f'     • {addr}')
print()

# 5. Distribución por portal
print('5. DISTRIBUCIÓN POR PORTAL:')
print()
for portal, count in df['Portal'].value_counts().items():
    percentage = (count / len(df)) * 100
    print(f'   {portal:20} {count:3} reservas ({percentage:5.1f}%)')
print()

# Análisis de datos útiles
print('=' * 60)
print('💡 DATOS ÚTILES DISPONIBLES:')
print('=' * 60)
print()
print(f'✅ NOMBRE: Disponible en {gast_filled} reservas ({gast_filled/len(df)*100:.1f}%)')
print(f'{"✅" if email_filled > 0 else "❌"} EMAIL: Disponible en {email_filled} reservas ({email_filled/len(df)*100:.1f}%)')
print(f'{"✅" if phone_filled > 0 else "❌"} TELÉFONO: Disponible en {phone_filled} reservas ({phone_filled/len(df)*100:.1f}%)')
print(f'{"✅" if addr_filled > 0 else "❌"} DIRECCIÓN: Disponible en {addr_filled} reservas ({addr_filled/len(df)*100:.1f}%)')
print()

# Conclusiones
print('=' * 60)
print('📝 CONCLUSIÓN:')
print('=' * 60)
print()
if email_filled > 0 or phone_filled > 0:
    print('✓ SÍ hay datos de contacto útiles en los archivos')
    print()
    if email_filled > 0:
        print(f'  - {email_filled} emails disponibles')
    if phone_filled > 0:
        print(f'  - {phone_filled} teléfonos disponibles')
    print()
    print('  Estos datos podrían usarse para:')
    print('  • Cruzar con reviews para identificar huéspedes específicos')
    print('  • Contactar huéspedes que dejaron reviews positivas')
    print('  • Crear campañas de marketing dirigido')
    print('  • Análisis de clientes recurrentes')
else:
    print('✗ NO hay datos de contacto (email/teléfono) en este archivo')
    print('  Solo está disponible el nombre del huésped')
