"""The manifest and head tags reference exact icon paths + sizes; guard that the
generated icons exist with the right dimensions (regenerate via
python -m ChatBotAI.scripts.generate_pwa_icons)."""
import os
from PIL import Image

IMG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'static', 'img', 'pwa')

EXPECTED = {
    'icon-192.png': (192, 192),
    'icon-512.png': (512, 512),
    'icon-maskable-192.png': (192, 192),
    'icon-maskable-512.png': (512, 512),
    'apple-touch-icon.png': (180, 180),
}


def test_pwa_icons_exist_with_correct_dimensions():
    for name, size in EXPECTED.items():
        path = os.path.join(IMG, name)
        assert os.path.exists(path), f"missing {name} — run generate_pwa_icons"
        assert Image.open(path).size == size, f"{name} wrong size"


def test_apple_icon_is_opaque():
    # iOS home-screen icons must not have an alpha channel.
    im = Image.open(os.path.join(IMG, 'apple-touch-icon.png'))
    assert im.mode == 'RGB'
