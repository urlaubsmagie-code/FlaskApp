import pandas as pd

df = pd.read_excel(r'C:\Users\admin\Server\FlaskApp\positive_reviews_FINAL.xlsx', sheet_name='Reviews Positivas')

print('Columnas:', list(df.columns))
print('\nPrimeras 3 filas con contactos:')
sample = df[df['Nombre_Completo'].notna()].head(3)
print(sample[['Name', 'Nombre_Completo', 'Email', 'Telefon', 'Direccion']].to_string())

print('\n\nEstadísticas de relleno:')
print(f'Total reviews: {len(df)}')
print(f'Nombre_Completo: {df["Nombre_Completo"].notna().sum()} ({df["Nombre_Completo"].notna().sum()/len(df)*100:.1f}%)')
print(f'Email: {df["Email"].notna().sum()} ({df["Email"].notna().sum()/len(df)*100:.1f}%)')
print(f'Telefon: {df["Telefon"].notna().sum()} ({df["Telefon"].notna().sum()/len(df)*100:.1f}%)')
print(f'Direccion: {df["Direccion"].notna().sum()} ({df["Direccion"].notna().sum()/len(df)*100:.1f}%)')
