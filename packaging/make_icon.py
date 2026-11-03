"""Draws the app icon and writes packaging/icon.icns. Run by packaging/build.sh when missing."""
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

S = 1024
SCALE = 4  # draw large, shrink for smooth edges


def rounded(draw, box, radius, fill):
    draw.rounded_rectangle([v * SCALE for v in box], radius * SCALE, fill=fill)


size = S * SCALE
gradient = Image.new("RGB", (1, 256))
for y in range(256):
    t = y / 255
    gradient.putpixel((0, y), (round(85 - 31 * t), round(130 - 57 * t), round(139 - 51 * t)))
gradient = gradient.resize((size, size))

mask = Image.new("L", (size, size), 0)
rounded(ImageDraw.Draw(mask), (100, 100, 924, 924), 186, 255)  # Apple's icon grid
icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
icon.paste(gradient, (0, 0), mask)

# Three rising bars with a coin-like dot: money growing.
draw = ImageDraw.Draw(icon)
white = (201, 228, 202, 255)
for x, top in ((262, 560), (452, 440), (642, 320)):
    rounded(draw, (x, top, x + 120, 740), 40, white)
icon = icon.resize((S, S), Image.LANCZOS)

here = Path(__file__).parent
with tempfile.TemporaryDirectory() as tmp:
    iconset = Path(tmp) / "icon.iconset"
    iconset.mkdir()
    for px in (16, 32, 64, 128, 256, 512, 1024):
        small = icon.resize((px, px), Image.LANCZOS)
        if px < 1024:
            small.save(iconset / f"icon_{px}x{px}.png")
        if px > 16:
            small.save(iconset / f"icon_{px // 2}x{px // 2}@2x.png")
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(here / "icon.icns")], check=True)
icon.save(here / "icon.png")
