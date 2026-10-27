"""Рисует иконки приложения (асфальт + янтарная «капля»)."""
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "web" / "icons"
BG, FG = (15, 27, 45), (255, 200, 61)


def icon(size, pad_ratio):
    scale = 4
    s = size * scale
    im = Image.new("RGB", (s, s), BG)
    d = ImageDraw.Draw(im)
    cx, cy = s / 2, s * 0.56
    r = s * (0.30 - pad_ratio)
    top = cy - r * 2.1
    d.polygon([(cx, top), (cx - r * 0.95, cy - r * 0.45), (cx + r * 0.95, cy - r * 0.45)], fill=FG)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=FG)
    # стрелка-метка внутри капли
    k = r * 0.5
    d.polygon([(cx, cy - k), (cx + k * 0.8, cy + k * 0.7), (cx, cy + k * 0.25), (cx - k * 0.8, cy + k * 0.7)], fill=BG)
    return im.resize((size, size), Image.LANCZOS)


OUT.mkdir(parents=True, exist_ok=True)
icon(192, 0).save(OUT / "icon-192.png")
icon(512, 0).save(OUT / "icon-512.png")
icon(512, 0.06).save(OUT / "icon-maskable-512.png")
icon(180, 0).save(OUT / "apple-touch-icon.png")
print("ok")
