"""Build the runtime PNG and multi-resolution Windows icon."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageOps


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "LumenView-source.png"
RUNTIME_PNG = ROOT / "lumenview" / "assets" / "LumenView.png"
WINDOWS_ICO = ROOT / "LumenView.ico"


def main() -> int:
    source = Image.open(SOURCE).convert("RGB")

    # Trim the generated canvas around the mark while retaining its soft shadow.
    difference = ImageChops.difference(source, Image.new("RGB", source.size, "white"))
    bounds = difference.convert("L").point(lambda value: 255 if value > 10 else 0).getbbox()
    if bounds is None:
        raise RuntimeError(f"No icon artwork found in {SOURCE}")
    left, top, right, bottom = bounds
    padding = max(24, int(max(right - left, bottom - top) * 0.035))
    bounds = (
        max(0, left - padding),
        max(0, top - padding),
        min(source.width, right + padding),
        min(source.height, bottom + padding),
    )
    artwork = ImageOps.fit(source.crop(bounds), (1024, 1024), Image.Resampling.LANCZOS)

    # Transparent corners keep the circular mark clean on both light and dark taskbars.
    alpha = Image.new("L", artwork.size, 0)
    from PIL import ImageDraw

    ImageDraw.Draw(alpha).ellipse((12, 12, 1012, 1012), fill=255)
    alpha = alpha.filter(ImageFilter.GaussianBlur(3.0))
    artwork = artwork.convert("RGBA")
    artwork.putalpha(alpha)

    RUNTIME_PNG.parent.mkdir(parents=True, exist_ok=True)
    artwork.save(RUNTIME_PNG, optimize=True)
    artwork.save(
        WINDOWS_ICO,
        sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48),
               (64, 64), (128, 128), (256, 256)],
    )
    print(f"wrote {RUNTIME_PNG}")
    print(f"wrote {WINDOWS_ICO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


