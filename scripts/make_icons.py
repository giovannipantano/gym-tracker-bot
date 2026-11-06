"""
Genera le icone dell'app (PNG) in src/web/icons/.

Serve solo quando vuoi cambiare l'aspetto dell'icona (richiede Pillow: pip install pillow).
Le icone generate sono già nel repository: il server non ne ha bisogno.
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "src" / "web" / "icons"
BACKGROUND = (11, 11, 15)      # quasi nero, come l'app
BOLT = (10, 132, 255)          # blu iOS (#0A84FF)
# Il fulmine disegnato su una griglia 24x24 (stesso tracciato dell'icona nell'interfaccia)
BOLT_POINTS = [(3.75, 13.5), (14.25, 2.25), (12, 10.5), (20.25, 10.5), (9.75, 21.75), (12, 13.5)]


def draw_icon(size: int) -> Image.Image:
    scale = 4  # si disegna più grande e poi si riduce: bordi più morbidi
    big = size * scale
    img = Image.new("RGB", (big, big), BACKGROUND)  # opaca e a pieno campo: iOS arrotonda da sé
    # Il fulmine occupa ~56% del lato: resta nella "zona sicura" delle icone maskable di Android
    box = big * 0.56
    x0 = y0 = (big - box) / 2
    min_x, max_x = 3.75, 20.25
    min_y, max_y = 2.25, 21.75
    k = box / max(max_x - min_x, max_y - min_y)
    cx, cy = (min_x + max_x) / 2, (min_y + max_y) / 2
    pts = [((px - cx) * k + big / 2, (py - cy) * k + big / 2) for px, py in BOLT_POINTS]
    ImageDraw.Draw(img).polygon(pts, fill=BOLT)
    return img.resize((size, size), Image.LANCZOS)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size in (("icon-512.png", 512), ("icon-192.png", 192), ("apple-touch-icon.png", 180), ("favicon-32.png", 32)):
        draw_icon(size).save(OUT / name, optimize=True)
        print("creata", OUT / name)


if __name__ == "__main__":
    main()
