#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script de prueba para verificar la funcionalidad de traducción automática
"""

from deep_translator import GoogleTranslator

# Textos de ejemplo en diferentes idiomas (típicos de Booking)
test_texts = [
    ("Great location and very clean!", "en"),
    ("Très bon emplacement", "fr"),
    ("Excelente ubicación", "es"),
    ("Ottima posizione", "it"),
    ("Zeer schone kamer", "nl"),
    ("Отличное расположение", "ru"),
    ("Muito limpo e confortável", "pt"),
    ("Già in tedesco", "de"),  # Este ya está en alemán
]

print("=" * 70)
print("TEST DE TRADUCCIÓN AUTOMÁTICA")
print("=" * 70)
print()

for text, expected_lang in test_texts:
    try:
        translator = GoogleTranslator(source='auto', target='de')
        translated = translator.translate(text)
        
        was_translated = translated != text
        status = "✅ TRADUCIDO" if was_translated else "⏭️  SIN CAMBIO"
        
        print(f"{status}")
        print(f"  Original ({expected_lang}): {text}")
        print(f"  Alemán: {translated}")
        print()
        
    except Exception as e:
        print(f"❌ ERROR con '{text}': {e}")
        print()

print("=" * 70)
print("TEST COMPLETADO")
print("=" * 70)
