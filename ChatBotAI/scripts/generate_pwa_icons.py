"""Generate PWA icons from static/img/umi-logo.png (1080x1080 RGBA).

Run once (idempotent): python -m ChatBotAI.scripts.generate_pwa_icons
Writes into static/img/pwa/. Maskable + apple icons sit on the brand burgundy so
Android adaptive masks and iOS (which does not mask) both look right.
"""
import os
from PIL import Image

BRAND = (0x7B, 0x23, 0x32, 255)  # #7B2332
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, 'static', 'img', 'umi-logo.png')
OUT = os.path.join(HERE, 'static', 'img', 'pwa')


def _resized_logo(size):
    logo = Image.open(SRC).convert('RGBA')
    return logo.resize((size, size), Image.LANCZOS)


def _any_icon(size):
    # Transparent logo scaled to the full square (purpose "any").
    return _resized_logo(size)


def _padded_on_brand(size, logo_fraction, flatten):
    # Logo centered on a burgundy square with padding (maskable safe zone / apple).
    canvas = Image.new('RGBA', (size, size), BRAND)
    inner = max(1, int(size * logo_fraction))
    logo = _resized_logo(inner)
    off = (size - inner) // 2
    canvas.paste(logo, (off, off), logo)
    if flatten:
        return canvas.convert('RGB')  # iOS icons must not be transparent
    return canvas


def main():
    os.makedirs(OUT, exist_ok=True)
    _any_icon(192).save(os.path.join(OUT, 'icon-192.png'))
    _any_icon(512).save(os.path.join(OUT, 'icon-512.png'))
    # Maskable: logo at ~62% so it survives Android's circular/rounded crop.
    _padded_on_brand(192, 0.62, flatten=False).save(os.path.join(OUT, 'icon-maskable-192.png'))
    _padded_on_brand(512, 0.62, flatten=False).save(os.path.join(OUT, 'icon-maskable-512.png'))
    # Apple touch icon: 180x180, opaque, logo at ~80%.
    _padded_on_brand(180, 0.80, flatten=True).save(os.path.join(OUT, 'apple-touch-icon.png'))
    print("PWA icons written to", OUT)


if __name__ == '__main__':
    main()
