/**
 * ==========================================
 * Gästebewertungen Slideshow - HW3B JavaScript
 * ==========================================
 */

class SlideshowController {
    constructor() {
        // Configuración principal - PUEDES EDITAR ESTOS VALORES
        this.slideDuration = 30000; // 30 segundos por diapositiva (30000ms = 30s)
        this.loadingDuration = 2000; // 2 segundos de pantalla de carga (2000ms = 2s)
        
        // Variables internas
        this.slides = document.querySelectorAll('.slide');
        this.currentSlide = 0;
        this.slideInterval = null;
        this.progressInterval = null;
        
        this.init();
    }
    
    /**
     * Inicializar el slideshow
     */
    init() {
        // Iniciar slideshow inmediatamente (sin pantalla de carga)
        document.getElementById('loadingScreen').style.display = 'none';
        document.getElementById('slideshowContainer').style.display = 'block';
        this.startSlideshow();
        
        // Recalcular tamaños cuando cambia el tamaño de ventana
        window.addEventListener('resize', () => {
            if (this.slides[this.currentSlide]) {
                this.adjustTextSize(this.slides[this.currentSlide]);
            }
        });
    }
    
    /**
     * Iniciar el slideshow automático
     */
    startSlideshow() {
        this.showSlide(0);
        this.slideInterval = setInterval(() => {
            this.nextSlide();
        }, this.slideDuration);
    }
    
    /**
     * Mostrar una diapositiva específica
     * @param {number} index - Índice de la diapositiva a mostrar
     */
    showSlide(index) {
        // Ocultar todas las diapositivas
        this.slides.forEach(slide => {
            slide.classList.remove('active');
        });
        
        // Mostrar la diapositiva actual
        if (this.slides[index]) {
            this.slides[index].classList.add('active');
            this.currentSlide = index;
            this.updateSlideCounter();
            this.adjustTextSize(this.slides[index]);
            this.startProgressBar();
        }
    }
    
    /**
     * Ir a la siguiente diapositiva
     */
    nextSlide() {
        let nextIndex = (this.currentSlide + 1) % this.slides.length;
        this.showSlide(nextIndex);
    }
    
    /**
     * Actualizar el contador de diapositivas
     */
    updateSlideCounter() {
        const currentSlideElements = document.querySelectorAll('#current-slide');
        currentSlideElements.forEach(element => {
            element.textContent = this.currentSlide + 1;
        });
    }
    
    /**
     * Ajustar el tamaño del texto según la longitud y el tamaño de pantalla
     * @param {Element} slide - Elemento de la diapositiva actual
     */
    adjustTextSize(slide) {
        const reviewText = slide.querySelector('.review-text');
        const textLength = reviewText.textContent.length;
        const screenWidth = window.innerWidth;
        
        // Definir tamaños base según el tamaño de pantalla
        let baseSizes;
        if (screenWidth <= 768) {
            // Móvil/tablet
            baseSizes = { large: '0.9rem', medium: '1rem', normal: '1.05rem', small: '1.1rem' };
        } else if (screenWidth <= 1399) {
            // Laptop
            baseSizes = { large: '1.1rem', medium: '1.2rem', normal: '1.25rem', small: '1.3rem' };
        } else {
            // TV/monitor grande
            baseSizes = { large: '1.3rem', medium: '1.4rem', normal: '1.45rem', small: '1.5rem' };
        }
        
        // Ajustar tamaño basado en longitud del texto
        // PUEDES MODIFICAR ESTOS VALORES PARA CAMBIAR LOS UMBRALES
        if (textLength > 800) {
            reviewText.style.fontSize = baseSizes.large;
            reviewText.style.lineHeight = '1.3';
        } else if (textLength > 300) {
            reviewText.style.fontSize = baseSizes.medium;
            reviewText.style.lineHeight = '1.35';
        } else if (textLength > 300) {
            reviewText.style.fontSize = baseSizes.normal;
            reviewText.style.lineHeight = '1.4';
        } else {
            reviewText.style.fontSize = baseSizes.small;
            reviewText.style.lineHeight = '1.4';
        }
    }
    
    /**
     * Iniciar la barra de progreso para la diapositiva actual
     */
    startProgressBar() {
        // Resetear barra de progreso
        const progressBars = document.querySelectorAll('.progress-bar');
        progressBars.forEach(bar => {
            bar.style.width = '0%';
        });
        
        // Iniciar barra de progreso para la diapositiva actual
        const currentProgressBar = document.getElementById(`progressBar${this.currentSlide + 1}`);
        if (currentProgressBar) {
            let progress = 0;
            const increment = 100 / (this.slideDuration / 100);
            
            clearInterval(this.progressInterval);
            this.progressInterval = setInterval(() => {
                progress += increment;
                if (progress >= 100) {
                    progress = 100;
                    clearInterval(this.progressInterval);
                }
                currentProgressBar.style.width = progress + '%';
            }, 100);
        }
    }
    
    /**
     * Obtener información actual del slideshow
     * @returns {Object} Información del estado actual
     */
    getCurrentInfo() {
        return {
            currentSlide: this.currentSlide + 1,
            totalSlides: this.slides.length,
            slideDuration: this.slideDuration,
            isRunning: this.slideInterval !== null
        };
    }
}

// ==========================================
// CONFIGURACIÓN PERSONALIZABLE
// ==========================================

/**
 * Configuración que puedes modificar fácilmente
 */
const SLIDESHOW_CONFIG = {
    // Duración de cada diapositiva en milisegundos (30000 = 30 segundos)
    slideDuration: 30000,
    
    // Duración de la pantalla de carga en milisegundos (2000 = 2 segundos)
    loadingDuration: 2000,
    
    // Umbrales de longitud de texto para ajuste automático
    textThresholds: {
        long: 200,      // Más de 800 caracteres = texto muy pequeño
        medium: 400,    // Más de 500 caracteres = texto pequeño
        normal: 450     // Más de 300 caracteres = texto normal
    }
};

// ==========================================
// INICIALIZACIÓN
// ==========================================

// Variable global para acceder al slideshow desde la consola del navegador
let slideshow;

// Inicializar slideshow cuando la página esté cargada
document.addEventListener('DOMContentLoaded', () => {
    slideshow = new SlideshowController();
    
    // Información adicional en consola del navegador
    console.log('🏠 Gästebewertungen Slideshow gestartet');
    console.log('📊 Gesamtbewertungen: ' + document.querySelectorAll('.slide').length);
    console.log('🏡 Apartment: HW3B');
    console.log('🔄 Automatischer Wechsel alle 30 Sekunden');
    console.log('');
    console.log('💡 Debugging-Befehle:');
    console.log('   slideshow.getCurrentInfo() - Aktuelle Slideshow-Info');
    console.log('   slideshow.nextSlide() - Nächste Folie');
    console.log('   slideshow.showSlide(index) - Bestimmte Folie anzeigen');
});

// ==========================================
// FUNCIONES DE UTILIDAD PARA DEBUGGING
// ==========================================

/**
 * Funciones útiles que puedes usar en la consola del navegador
 * para debugging y personalización en tiempo real
 */

// Pausar el slideshow
function pauseSlideshow() {
    if (slideshow && slideshow.slideInterval) {
        clearInterval(slideshow.slideInterval);
        clearInterval(slideshow.progressInterval);
        slideshow.slideInterval = null;
        console.log('⏸️ Slideshow pausiert');
    }
}

// Reanudar el slideshow
function resumeSlideshow() {
    if (slideshow && !slideshow.slideInterval) {
        slideshow.startSlideshow();
        console.log('▶️ Slideshow fortgesetzt');
    }
}

// Cambiar velocidad del slideshow
function changeSpeed(seconds) {
    if (slideshow) {
        slideshow.slideDuration = seconds * 1000;
        console.log(`⚡ Geschwindigkeit geändert zu ${seconds} Sekunden pro Folie`);
        
        // Reiniciar si está funcionando
        if (slideshow.slideInterval) {
            pauseSlideshow();
            resumeSlideshow();
        }
    }
}

// Ir a una diapositiva específica
function goToSlide(slideNumber) {
    if (slideshow) {
        const index = slideNumber - 1; // Convertir a índice base-0
        if (index >= 0 && index < slideshow.slides.length) {
            slideshow.showSlide(index);
            console.log(`🎯 Zu Folie ${slideNumber} gewechselt`);
        } else {
            console.log('❌ Ungültige Foliennummer');
        }
    }
}