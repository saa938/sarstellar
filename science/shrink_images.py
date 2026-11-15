"""Re-encode stage images for the web: max 1100 px on the long side, WebP quality 72.

    python science/shrink_images.py web/public/stages
"""
import sys
from pathlib import Path

from PIL import Image

MAX_SIDE, QUALITY = 1100, 72

for p in sorted(Path(sys.argv[1]).glob("*/img/*.webp")):
    im = Image.open(p)
    im.load()
    w, h = im.size
    s = min(1.0, MAX_SIDE / max(w, h))
    if s < 1.0:
        im = im.resize((round(w * s), round(h * s)), Image.LANCZOS)
    im.save(p, "WEBP", quality=QUALITY, method=6)
print("done")
