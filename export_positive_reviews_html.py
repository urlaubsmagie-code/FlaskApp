import json
from pathlib import Path
from datetime import datetime

def export_to_html():
    # Leer el archivo JSON generado
    json_file = Path(r'C:\Users\admin\Server\FlaskApp\positive_reviews_report.json')
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Generar HTML
    html_content = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reporte de Reviews Positivas</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            color: #333;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        
        .header p {{
            font-size: 1.1em;
            opacity: 0.9;
        }}
        
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            padding: 30px;
            background: #f8f9fa;
            border-bottom: 2px solid #e9ecef;
        }}
        
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            text-align: center;
        }}
        
        .stat-number {{
            font-size: 2.5em;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 5px;
        }}
        
        .stat-label {{
            color: #666;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .filters {{
            padding: 20px 30px;
            background: #f8f9fa;
            border-bottom: 2px solid #e9ecef;
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            align-items: center;
        }}
        
        .filter-btn {{
            padding: 10px 20px;
            border: 2px solid #667eea;
            background: white;
            color: #667eea;
            border-radius: 25px;
            cursor: pointer;
            font-weight: bold;
            transition: all 0.3s;
        }}
        
        .filter-btn:hover, .filter-btn.active {{
            background: #667eea;
            color: white;
        }}
        
        .reviews-container {{
            padding: 30px;
        }}
        
        .review-card {{
            background: white;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            padding: 25px;
            margin-bottom: 20px;
            transition: all 0.3s;
        }}
        
        .review-card:hover {{
            box-shadow: 0 5px 20px rgba(0,0,0,0.1);
            border-color: #667eea;
        }}
        
        .review-header {{
            display: flex;
            justify-content: space-between;
            align-items: start;
            margin-bottom: 15px;
            flex-wrap: wrap;
            gap: 10px;
        }}
        
        .review-user {{
            display: flex;
            align-items: center;
            gap: 15px;
        }}
        
        .user-avatar {{
            width: 50px;
            height: 50px;
            border-radius: 50%;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 1.5em;
            font-weight: bold;
        }}
        
        .user-info h3 {{
            font-size: 1.2em;
            margin-bottom: 3px;
        }}
        
        .user-info p {{
            color: #666;
            font-size: 0.9em;
        }}
        
        .review-meta {{
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
        }}
        
        .badge {{
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: bold;
        }}
        
        .badge-airbnb {{
            background: #FF5A5F;
            color: white;
        }}
        
        .badge-booking {{
            background: #003580;
            color: white;
        }}
        
        .badge-rating {{
            background: #ffd700;
            color: #333;
        }}
        
        .badge-pattern {{
            background: #e9ecef;
            color: #667eea;
            border: 2px solid #667eea;
        }}
        
        .review-text {{
            line-height: 1.8;
            color: #444;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
            margin-top: 15px;
        }}
        
        .review-footer {{
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #e9ecef;
            font-size: 0.9em;
            color: #666;
        }}
        
        .search-box {{
            flex: 1;
            min-width: 250px;
        }}
        
        .search-box input {{
            width: 100%;
            padding: 10px 20px;
            border: 2px solid #e9ecef;
            border-radius: 25px;
            font-size: 1em;
            transition: all 0.3s;
        }}
        
        .search-box input:focus {{
            outline: none;
            border-color: #667eea;
        }}
        
        .no-results {{
            text-align: center;
            padding: 50px;
            color: #666;
            font-size: 1.2em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Reporte de Reviews Positivas</h1>
            <p>Reviews que mencionan "wieder kommen", "gerne wieder" y variaciones similares</p>
            <p style="font-size: 0.9em; margin-top: 10px;">Generado: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-number">{data['total_positive_reviews']}</div>
                <div class="stat-label">Total Reviews</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{data['airbnb_count']}</div>
                <div class="stat-label">Airbnb</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{data['booking_count']}</div>
                <div class="stat-label">Booking.com</div>
            </div>
        </div>
        
        <div class="filters">
            <div class="search-box">
                <input type="text" id="searchInput" placeholder="🔍 Buscar por nombre, texto, patrón...">
            </div>
            <button class="filter-btn active" onclick="filterReviews('all')">Todos</button>
            <button class="filter-btn" onclick="filterReviews('airbnb')">Airbnb</button>
            <button class="filter-btn" onclick="filterReviews('booking')">Booking</button>
        </div>
        
        <div class="reviews-container" id="reviewsContainer">
"""
    
    # Agregar reviews de Airbnb
    for review in data['reviews']['airbnb']:
        patterns_badges = ''.join([f'<span class="badge badge-pattern">{pattern.replace("\\\\s+", " ").replace("?", "")}</span> ' 
                                   for pattern in review['matched_patterns']])
        
        initial = review['reviewerName'][0].upper() if review['reviewerName'] else '?'
        review_text = review['full_text'].replace('<br/>', '<br>')
        
        html_content += f"""
            <div class="review-card" data-source="airbnb">
                <div class="review-header">
                    <div class="review-user">
                        <div class="user-avatar">{initial}</div>
                        <div class="user-info">
                            <h3>{review['reviewerName']}</h3>
                            <p>{review['reviewDate'][:10]}</p>
                        </div>
                    </div>
                    <div class="review-meta">
                        <span class="badge badge-airbnb">Airbnb</span>
                        <span class="badge badge-rating">⭐ {review['rating']}/5</span>
                        {patterns_badges}
                    </div>
                </div>
                <div class="review-text">{review_text}</div>
                <div class="review-footer">
                    <strong>Idioma:</strong> {review['language']} | 
                    <strong>ID:</strong> {review['reviewId']}
                </div>
            </div>
"""
    
    # Agregar reviews de Booking
    for review in data['reviews']['booking']:
        patterns_badges = ''.join([f'<span class="badge badge-pattern">{pattern.replace("\\\\s+", " ").replace("?", "")}</span> ' 
                                   for pattern in review['matched_patterns']])
        
        initial = review['userName'][0].upper() if review['userName'] else '?'
        liked_text = review['likedText'] if review['likedText'] else ''
        disliked_text = review['dislikedText'] if review['dislikedText'] else ''
        
        review_text = ''
        if liked_text:
            review_text += f"<strong>👍 Lo que gustó:</strong><br>{liked_text}<br><br>"
        if disliked_text:
            review_text += f"<strong>👎 Lo que no gustó:</strong><br>{disliked_text}"
        
        html_content += f"""
            <div class="review-card" data-source="booking">
                <div class="review-header">
                    <div class="review-user">
                        <div class="user-avatar">{initial}</div>
                        <div class="user-info">
                            <h3>{review['userName']}</h3>
                            <p>{review['reviewDate'][:10]}</p>
                        </div>
                    </div>
                    <div class="review-meta">
                        <span class="badge badge-booking">Booking.com</span>
                        <span class="badge badge-rating">⭐ {review['rating']}/10</span>
                        {patterns_badges}
                    </div>
                </div>
                <div class="review-text">{review_text}</div>
                <div class="review-footer">
                    <strong>Idioma:</strong> {review['language']} | 
                    <strong>Tipo:</strong> {review['travelerType']} | 
                    <strong>Check-in:</strong> {review['checkInDate']} - {review['checkOutDate']}
                </div>
            </div>
"""
    
    html_content += """
        </div>
    </div>
    
    <script>
        // Funcionalidad de búsqueda
        document.getElementById('searchInput').addEventListener('input', function(e) {
            const searchTerm = e.target.value.toLowerCase();
            const cards = document.querySelectorAll('.review-card');
            
            cards.forEach(card => {
                const text = card.textContent.toLowerCase();
                if (text.includes(searchTerm)) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
        });
        
        // Funcionalidad de filtros
        function filterReviews(source) {
            const cards = document.querySelectorAll('.review-card');
            const buttons = document.querySelectorAll('.filter-btn');
            
            // Actualizar botones activos
            buttons.forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            
            // Filtrar cards
            cards.forEach(card => {
                if (source === 'all') {
                    card.style.display = 'block';
                } else {
                    if (card.getAttribute('data-source') === source) {
                        card.style.display = 'block';
                    } else {
                        card.style.display = 'none';
                    }
                }
            });
        }
    </script>
</body>
</html>
"""
    
    # Guardar archivo HTML
    html_file = Path(r'C:\Users\admin\Server\FlaskApp\positive_reviews_report.html')
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✓ Archivo HTML generado exitosamente: {html_file}")
    print(f"\nTotal de reviews exportadas: {data['total_positive_reviews']}")
    print(f"  - Airbnb: {data['airbnb_count']}")
    print(f"  - Booking: {data['booking_count']}")
    print(f"\n💡 Abre el archivo HTML en tu navegador para ver el reporte interactivo")

if __name__ == '__main__':
    export_to_html()
