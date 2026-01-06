import json
import csv
from pathlib import Path

def export_to_csv():
    # Leer el archivo JSON generado
    json_file = Path(r'C:\Users\admin\Server\FlaskApp\positive_reviews_report.json')
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Preparar archivo CSV
    csv_file = Path(r'C:\Users\admin\Server\FlaskApp\positive_reviews_report.csv')
    
    with open(csv_file, 'w', newline='', encoding='utf-8-sig') as f:
        fieldnames = [
            'Plattform',
            'Wohnung',
            'Name',
            'Datum',
            'Kommentar',
            'Gefundenes Muster',
            'Originalsprache'
        ]
        
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        # Escribir reviews de Airbnb
        for review in data['reviews']['airbnb']:
            fecha = review['reviewDate'][:10] if review['reviewDate'] else ''
            comentario = review.get('translated_text', review['full_text']).replace('<br/>', ' ').strip()
            patrones = ', '.join([p.replace('\\s+', ' ').replace('?', '') for p in review['matched_patterns']])
            idioma_original = review.get('original_language', review.get('language', 'unknown'))
            
            writer.writerow({
                'Plattform': 'Airbnb',
                'Wohnung': review.get('apartmentCode', 'UNKNOWN'),
                'Name': review['reviewerName'],
                'Datum': fecha,
                'Kommentar': comentario,
                'Gefundenes Muster': patrones,
                'Originalsprache': idioma_original
            })
        
        # Escribir reviews de Booking
        for review in data['reviews']['booking']:
            fecha = review['reviewDate'][:10] if review['reviewDate'] else ''
            
            # Usar texto traducido si existe
            if review.get('translated_text'):
                comentario = review['translated_text']
            else:
                comentario = ''
                if review['likedText']:
                    comentario += f"👍 {review['likedText']} "
                if review['dislikedText']:
                    comentario += f"👎 {review['dislikedText']}"
                comentario = comentario.strip()
            
            idioma_original = review.get('original_language', review.get('reviewLanguage', 'unknown'))
            patrones = ', '.join([p.replace('\\s+', ' ').replace('?', '') for p in review['matched_patterns']])
            
            writer.writerow({
                'Plattform': 'Booking.com',
                'Wohnung': review.get('apartmentCode', 'UNKNOWN'),
                'Name': review['userName'],
                'Datum': fecha,
                'Kommentar': comentario,
                'Gefundenes Muster': patrones,
                'Originalsprache': idioma_original
            })
    
    print(f"✓ Archivo CSV generado exitosamente: {csv_file}")
    print(f"Total de reviews exportadas: {data['total_positive_reviews']}")
    print(f"  - Airbnb: {data['airbnb_count']}")
    print(f"  - Booking: {data['booking_count']}")

if __name__ == '__main__':
    export_to_csv()
