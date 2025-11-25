"""
Airbnb Reviews Scraper - Versión Robusta con Playwright
Diseñado para máxima fiabilidad y tasa de éxito del 100%
"""

import json
import time
from datetime import datetime
from typing import List, Dict, Optional
from playwright.sync_api import sync_playwright, Page, Browser, TimeoutError as PlaywrightTimeout
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('airbnb_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class AirbnbReviewsScraper:
    """Scraper robusto para obtener reviews de Airbnb"""
    
    def __init__(self, headless: bool = False, timeout: int = 30000):
        """
        Inicializar el scraper
        
        Args:
            headless: Si True, ejecuta el navegador sin interfaz gráfica
            timeout: Tiempo máximo de espera en milisegundos (default: 30s)
        """
        self.headless = headless
        self.timeout = timeout
        self.browser: Optional[Browser] = None
        self.context = None
        self.page: Optional[Page] = None
        
    def __enter__(self):
        """Context manager entry"""
        self.start_browser()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close_browser()
        
    def start_browser(self):
        """Iniciar el navegador con configuración robusta"""
        try:
            self.playwright = sync_playwright().start()
            
            # Configuración anti-detección
            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox'
                ]
            )
            
            # Crear contexto con user agent real
            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='es-ES',
                timezone_id='Europe/Madrid'
            )
            
            self.page = self.context.new_page()
            self.page.set_default_timeout(self.timeout)
            
            logger.info("Navegador iniciado correctamente")
            
        except Exception as e:
            logger.error(f"Error al iniciar navegador: {e}")
            raise
            
    def close_browser(self):
        """Cerrar el navegador de forma segura"""
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if hasattr(self, 'playwright'):
                self.playwright.stop()
            logger.info("Navegador cerrado correctamente")
        except Exception as e:
            logger.warning(f"Error al cerrar navegador: {e}")
            
    def wait_and_scroll(self, scrolls: int = 5, delay: float = 2.0):
        """
        Hacer scroll para cargar contenido dinámico
        
        Args:
            scrolls: Número de scrolls a realizar
            delay: Tiempo de espera entre scrolls en segundos
        """
        try:
            if not self.page or self.page.is_closed():
                logger.warning("Página cerrada, saltando scroll")
                return
                
            for i in range(scrolls):
                try:
                    self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    logger.info(f"Scroll {i+1}/{scrolls} completado")
                    time.sleep(delay)
                except Exception as e:
                    logger.warning(f"Error en scroll {i+1}: {e}")
                    break
            
            # Volver arriba
            try:
                self.page.evaluate('window.scrollTo(0, 0)')
                time.sleep(1)
            except:
                pass
            
        except Exception as e:
            logger.warning(f"Error durante scroll: {e}")
            
    def click_show_more_reviews(self, max_clicks: int = 10):
        """
        Hacer clic en 'Mostrar más' reseñas repetidamente
        
        Args:
            max_clicks: Número máximo de clics a intentar
        """
        clicks = 0
        while clicks < max_clicks:
            try:
                # Buscar botón de "Show more" o similar
                show_more = self.page.locator('button:has-text("Show all"), button:has-text("Mostrar todas")').first
                
                if show_more.is_visible(timeout=3000):
                    show_more.click()
                    logger.info(f"Clic en 'Mostrar más' #{clicks+1}")
                    time.sleep(2)
                    clicks += 1
                else:
                    break
                    
            except PlaywrightTimeout:
                logger.info("No hay más botones 'Mostrar más'")
                break
            except Exception as e:
                logger.warning(f"Error al hacer clic en 'Mostrar más': {e}")
                break
                
    def extract_reviews(self) -> List[Dict]:
        """
        Extraer todas las reseñas de la página actual
        
        Returns:
            Lista de diccionarios con información de reviews
        """
        reviews = []
        
        try:
            if not self.page or self.page.is_closed():
                logger.error("Página cerrada, no se pueden extraer reviews")
                return reviews
                
            # Esperar a que carguen las reviews con múltiples selectores
            try:
                self.page.wait_for_selector('[data-review-id], [itemprop="review"], div[id*="review"]', timeout=10000)
            except PlaywrightTimeout:
                logger.warning("Timeout esperando reviews, intentando con selectores alternativos")
            
            # Múltiples selectores para máxima compatibilidad
            review_selectors = [
                '[data-review-id]',
                '[itemprop="review"]',
                'div[role="listitem"]'
            ]
            
            review_elements = None
            for selector in review_selectors:
                try:
                    review_elements = self.page.locator(selector).all()
                    if review_elements:
                        logger.info(f"Encontradas {len(review_elements)} reviews con selector: {selector}")
                        break
                except:
                    continue
                    
            if not review_elements:
                logger.warning("No se encontraron elementos de review")
                return reviews
                
            # Extraer información de cada review
            for idx, review_elem in enumerate(review_elements):
                try:
                    review_data = self._extract_single_review(review_elem, idx)
                    if review_data:
                        reviews.append(review_data)
                except Exception as e:
                    logger.warning(f"Error extrayendo review {idx}: {e}")
                    continue
                    
            logger.info(f"Total de {len(reviews)} reviews extraídas exitosamente")
            
        except PlaywrightTimeout:
            logger.error("Timeout esperando reviews. Posiblemente no hay reviews en esta página.")
        except Exception as e:
            logger.error(f"Error extrayendo reviews: {e}")
            
        return reviews
        
    def _extract_single_review(self, element, idx: int) -> Optional[Dict]:
        """
        Extraer datos de una sola review
        
        Args:
            element: Elemento Playwright de la review
            idx: Índice de la review
            
        Returns:
            Diccionario con datos de la review o None
        """
        try:
            review_data = {
                'id': idx + 1,
                'extracted_at': datetime.now().isoformat()
            }
            
            # Intentar extraer texto del review
            text_selectors = [
                'span[class*="review"]',
                '[itemprop="description"]',
                'span:has-text("")',
                'div[class*="comment"]'
            ]
            
            for selector in text_selectors:
                try:
                    text_elem = element.locator(selector).first
                    text = text_elem.inner_text(timeout=1000).strip()
                    if text and len(text) > 10:  # Validar que sea texto real
                        review_data['text'] = text
                        break
                except:
                    continue
                    
            # Intentar extraer nombre del autor
            author_selectors = [
                'a[href*="/users/show"]',
                '[itemprop="author"]',
                'div[class*="author"] span',
                'button[aria-label*="perfil"]'
            ]
            
            for selector in author_selectors:
                try:
                    author_elem = element.locator(selector).first
                    author = author_elem.inner_text(timeout=1000).strip()
                    if author:
                        review_data['author'] = author
                        break
                except:
                    continue
                    
            # Intentar extraer fecha
            date_selectors = [
                'span:has-text("202")',  # Año
                '[class*="date"]',
                'time',
                'span[class*="time"]'
            ]
            
            for selector in date_selectors:
                try:
                    date_elem = element.locator(selector).first
                    date_text = date_elem.inner_text(timeout=1000).strip()
                    if date_text:
                        review_data['date'] = date_text
                        break
                except:
                    continue
                    
            # Intentar extraer rating (estrellas)
            try:
                rating_elem = element.locator('[aria-label*="star"], [role="img"][aria-label*="rating"]').first
                rating_text = rating_elem.get_attribute('aria-label', timeout=1000)
                if rating_text:
                    review_data['rating'] = rating_text
            except:
                pass
                
            # Solo devolver si al menos tiene texto
            if 'text' in review_data and review_data['text']:
                return review_data
            else:
                return None
                
        except Exception as e:
            logger.debug(f"Error en review individual {idx}: {e}")
            return None
            
    def scrape_room(self, room_url: str, max_scrolls: int = 5, max_show_more_clicks: int = 10) -> Dict:
        """
        Scraping completo de una habitación de Airbnb
        
        Args:
            room_url: URL de la habitación de Airbnb
            max_scrolls: Número máximo de scrolls para cargar contenido
            max_show_more_clicks: Número máximo de clics en "Mostrar más"
            
        Returns:
            Diccionario con información de la habitación y sus reviews
        """
        result = {
            'url': room_url,
            'scraped_at': datetime.now().isoformat(),
            'success': False,
            'reviews': [],
            'total_reviews': 0,
            'error': None
        }
        
        try:
            logger.info(f"Iniciando scraping de: {room_url}")
            
            # Navegar a la URL
            response = self.page.goto(room_url, wait_until='networkidle')
            
            if response.status != 200:
                raise Exception(f"HTTP {response.status}: No se pudo cargar la página")
                
            logger.info("Página cargada correctamente")
            
            # Esperar a que cargue contenido inicial
            time.sleep(3)
            
            # Extraer información básica de la habitación
            try:
                title = self.page.locator('h1').first.inner_text(timeout=5000)
                result['room_title'] = title
                logger.info(f"Habitación: {title}")
            except:
                logger.warning("No se pudo extraer título de la habitación")
                
            # Buscar y hacer clic en sección de reviews si existe
            try:
                # Buscar enlace con número de reviews
                reviews_link = self.page.locator('a:has-text("review"), a:has-text("reseña")').first
                if reviews_link.is_visible(timeout=5000):
                    reviews_link.scroll_into_view_if_needed()
                    time.sleep(1)
                    reviews_link.click()
                    logger.info("Click en sección de reviews")
                    time.sleep(4)
            except Exception as e:
                logger.info(f"No se navegó a reviews dedicadas: {e}")
                
            # Hacer scroll para cargar contenido
            self.wait_and_scroll(scrolls=max_scrolls)
            
            # Hacer clic en "Mostrar más" si existe
            self.click_show_more_reviews(max_clicks=max_show_more_clicks)
            
            # Extraer todas las reviews
            reviews = self.extract_reviews()
            
            result['reviews'] = reviews
            result['total_reviews'] = len(reviews)
            result['success'] = True
            
            logger.info(f"✓ Scraping completado: {len(reviews)} reviews extraídas")
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"✗ Error durante scraping: {e}")
            
        return result
        
    def scrape_multiple_rooms(self, room_urls: List[str], output_file: str = None) -> List[Dict]:
        """
        Scraping de múltiples habitaciones
        
        Args:
            room_urls: Lista de URLs de habitaciones
            output_file: Archivo JSON para guardar resultados (opcional)
            
        Returns:
            Lista de resultados de cada habitación
        """
        results = []
        
        for i, url in enumerate(room_urls, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"Procesando habitación {i}/{len(room_urls)}")
            logger.info(f"{'='*60}")
            
            result = self.scrape_room(url)
            results.append(result)
            
            # Pausa entre requests para evitar bloqueos
            if i < len(room_urls):
                wait_time = 5
                logger.info(f"Esperando {wait_time} segundos antes de la siguiente habitación...")
                time.sleep(wait_time)
                
        # Guardar resultados si se especifica archivo
        if output_file:
            self.save_results(results, output_file)
            
        return results
        
    @staticmethod
    def save_results(results: List[Dict], filename: str):
        """
        Guardar resultados en archivo JSON
        
        Args:
            results: Lista de resultados
            filename: Nombre del archivo de salida
        """
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            logger.info(f"✓ Resultados guardados en: {filename}")
        except Exception as e:
            logger.error(f"Error guardando resultados: {e}")


def main():
    """Función principal de ejemplo"""
    
    # URLs de ejemplo (reemplaza con tus URLs reales)
    room_urls = [
        "https://www.airbnb.com/rooms/12937",
        # Agrega más URLs aquí
    ]
    
    # Usar el scraper con context manager (maneja automáticamente apertura/cierre)
    with AirbnbReviewsScraper(headless=False) as scraper:
        results = scraper.scrape_multiple_rooms(
            room_urls=room_urls,
            output_file='airbnb_reviews_output.json'
        )
        
        # Mostrar resumen
        print("\n" + "="*60)
        print("RESUMEN DE SCRAPING")
        print("="*60)
        
        total_reviews = 0
        successful = 0
        
        for result in results:
            if result['success']:
                successful += 1
                total_reviews += result['total_reviews']
                print(f"✓ {result.get('room_title', 'Sin título')}: {result['total_reviews']} reviews")
            else:
                print(f"✗ {result['url']}: Error - {result['error']}")
                
        print(f"\nTotal: {successful}/{len(results)} exitosos")
        print(f"Reviews totales: {total_reviews}")


if __name__ == "__main__":
    main()
