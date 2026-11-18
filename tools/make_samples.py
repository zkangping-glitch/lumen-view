"""Generate a sample image in every format Lumen View claims to support."""

from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image, ImageDraw

try:  # optional codecs so the generator covers them too
    import pillow_heif

    pillow_heif.register_heif_opener()
except Exception:
    pass
try:
    import pillow_jxl  # noqa: F401
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "samples")


def base(w: int = 900, h: int = 600) -> Image.Image:
    y, x = np.mgrid[0:h, 0:w]
    r = (x / w * 255).astype(np.uint8)
    g = (y / h * 255).astype(np.uint8)
    b = (120 + 100 * np.sin((x + y) / 140.0)).astype(np.uint8)
    arr = np.stack([r, g, b], axis=-1)
    im = Image.fromarray(arr, "RGB")
    draw = ImageDraw.Draw(im)
    draw.ellipse((w * 0.62, h * 0.16, w * 0.86, h * 0.40), fill=(255, 240, 200))
    draw.polygon(
        [(0, h), (w * 0.32, h * 0.45), (w * 0.55, h * 0.78), (w * 0.72, h * 0.58), (w, h)],
        fill=(24, 32, 48),
    )
    draw.rounded_rectangle((24, 24, 260, 88), radius=16, fill=(10, 14, 22))
    draw.text((44, 42), "Lumen View", fill=(230, 236, 255))
    return im


def write(name: str, fn) -> None:
    path = os.path.join(OUT, name)
    try:
        fn(path)
        print(f"  ok   {name}")
    except Exception as exc:
        print(f"  skip {name}: {exc}")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    im = base()

    write("sample.jpg", lambda p: im.save(p, quality=92))
    write("sample.png", lambda p: im.convert("RGBA").save(p))

    def make_gif(p: str) -> None:
        frames = []
        for i in range(6):
            frame = base(320, 220).rotate(i * 20, expand=False)
            frames.append(frame.convert("P", palette=Image.Palette.ADAPTIVE))
        frames[0].save(p, save_all=True, append_images=frames[1:], duration=120, loop=0)

    write("sample.gif", make_gif)

    def make_webp(p: str) -> None:
        frames = [base(400, 300).rotate(i * 15) for i in range(4)]
        frames[0].save(p, save_all=True, append_images=frames[1:], duration=150, loop=0)

    write("sample.webp", make_webp)

    def make_tiff(p: str) -> None:
        im.save(p, save_all=True, append_images=[base(450, 300).rotate(8)])

    write("sample.tiff", make_tiff)

    write("sample.bmp", lambda p: im.save(p))
    write("sample.ico", lambda p: im.save(p, sizes=[(256, 256), (64, 64), (32, 32)]))
    write("sample.ppm", lambda p: im.save(p))
    write("sample.tga", lambda p: im.save(p))
    write("sample.pcx", lambda p: im.save(p))
    write("sample.dds", lambda p: im.save(p))
    write("sample.avif", lambda p: im.save(p, quality=70))
    write("sample.jxl", lambda p: im.save(p, quality=88))
    write("sample.heic", lambda p: im.save(p, quality=80))

    def make_psd(p: str) -> None:
        from psd_tools import PSDImage

        PSDImage.frompil(im.convert("RGBA")).save(p)

    write("sample.psd", make_psd)

    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="800" height="500" viewBox="0 0 800 500">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#7c9cff"/>
      <stop offset="1" stop-color="#2a3350"/>
    </linearGradient>
  </defs>
  <rect width="800" height="500" fill="#0b0c0f"/>
  <rect x="40" y="40" width="720" height="420" rx="28" fill="url(#g)" opacity="0.9"/>
  <circle cx="610" cy="160" r="70" fill="#ffe9b0" opacity="0.95"/>
  <path d="M40 460 L260 240 L360 360 L520 210 L760 460 Z" fill="#12151c" opacity="0.92"/>
  <text x="90" y="130" font-family="Segoe UI" font-size="46" fill="#ffffff">Lumen View SVG</text>
</svg>"""

    def make_svg(p: str) -> None:
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(svg)

    write("sample.svg", make_svg)
    print(f"samples in {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

