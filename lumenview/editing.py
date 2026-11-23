"""Non-destructive image operations and atomic, animation-aware export."""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps
from PySide6.QtGui import QImage

from .decoders import Loaded, _pil_to_qimage

MAX_EXPORT_BYTES = 384 * 1024 * 1024


@dataclass(frozen=True)
class EditState:
    brightness: int = 0
    contrast: int = 0
    saturation: int = 0
    rotation: int = 0
    flipped: bool = False
    ratio: str = "original"
    crop_box: tuple[float, float, float, float] | None = None
    start_ms: int = 0
    end_ms: int | None = None
    speed: float = 1.0


def to_pil(image: QImage) -> Image.Image:
    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    return Image.frombytes("RGBA", (rgba.width(), rgba.height()), bytes(rgba.constBits()),
                           "raw", "RGBA", rgba.bytesPerLine())


def transform(image: Image.Image, state: EditState) -> Image.Image:
    image = image.convert("RGBA")
    if state.rotation:
        image = image.rotate(-state.rotation, expand=True)
    if state.flipped:
        image = ImageOps.mirror(image)
    ratios = {"square": 1.0, "wide": 16 / 9, "portrait": 4 / 5}
    ratio = ratios.get(state.ratio)
    if state.crop_box is not None:
        w, h = image.size
        x0, y0, x1, y1 = state.crop_box
        left = max(0, min(w - 1, round(x0 * w)))
        top = max(0, min(h - 1, round(y0 * h)))
        right = max(left + 1, min(w, round(x1 * w)))
        bottom = max(top + 1, min(h, round(y1 * h)))
        image = image.crop((left, top, right, bottom))
    elif ratio:
        w, h = image.size
        cw, ch = min(w, max(1, round(h * ratio))), min(h, max(1, round(w / ratio)))
        x, y = (w - cw) // 2, (h - ch) // 2
        image = image.crop((x, y, x + cw, y + ch))
    alpha = image.getchannel("A")
    rgb = image.convert("RGB")
    for enhancer, value in ((ImageEnhance.Brightness, state.brightness),
                            (ImageEnhance.Contrast, state.contrast),
                            (ImageEnhance.Color, state.saturation)):
        if value:
            rgb = enhancer(rgb).enhance(max(0, 1 + value / 100))
    rgb.putalpha(alpha)
    return rgb


def preview(loaded: Loaded, state: EditState, index: int = 0) -> QImage:
    image = to_pil(loaded.frames[index].image)
    image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
    return _pil_to_qimage(transform(image, state))


def duration_ms(loaded: Loaded) -> int:
    return sum(max(20, frame.duration or 100) for frame in loaded.frames)


def selected_frames(loaded: Loaded, state: EditState) -> list[tuple[int, int]]:
    total = duration_ms(loaded)
    end = min(total, state.end_ms if state.end_ms is not None else total)
    start = max(0, state.start_ms)
    if start >= end or state.speed <= 0:
        raise ValueError("片段起点必须早于终点，播放速度必须大于零")
    selected = []
    offset = 0
    for index, frame in enumerate(loaded.frames):
        duration = max(20, frame.duration or 100)
        overlap = min(offset + duration, end) - max(offset, start)
        if overlap > 0:
            selected.append((index, max(20, round(overlap / state.speed))))
        offset += duration
    return selected


def export_image(loaded: Loaded, state: EditState, destination: str, fmt: str,
                 quality: int = 90, frame_index: int = 0, background: str = "white",
                 frame_states: list[EditState] | None = None) -> None:
    """Keep the original untouched; never leave a partially written destination."""
    target = Path(destination).resolve()
    original = Path(loaded.path).resolve()
    if target == original or (target.exists() and original.exists() and os.path.samefile(target, original)):
        raise ValueError("请保存为副本，不能覆盖原图")
    if fmt not in {"JPEG", "PNG", "WebP", "GIF", "动画 WebP"}:
        raise ValueError("不支持的输出格式")
    animated = loaded.animated and fmt in {"GIF", "动画 WebP"}
    chosen = selected_frames(loaded, state) if animated else [(frame_index, 100)]
    if any(index < 0 or index >= len(loaded.frames) for index, _ in chosen):
        raise ValueError("导出帧超出范围")
    estimate = sum(loaded.frames[i].image.width() * loaded.frames[i].image.height() * 4
                   for i, _ in chosen)
    if estimate > MAX_EXPORT_BYTES:
        raise ValueError("动画导出超过内存预算，请缩短片段后重试")
    images = [transform(to_pil(loaded.frames[i].image), frame_states[i] if frame_states else state)
              for i, _ in chosen]
    if animated and images:
        # GIF/WebP require a common canvas even when inserted frames have other sizes.
        width = max(image.width for image in images)
        height = max(image.height for image in images)
        normalized = []
        for image in images:
            canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            canvas.alpha_composite(image, ((width - image.width) // 2, (height - image.height) // 2))
            normalized.append(canvas)
        images = normalized
    options: dict = {}
    output_format = {"WebP": "WEBP", "动画 WebP": "WEBP"}.get(fmt, fmt)
    if output_format in {"JPEG", "WEBP"}:
        options["quality"] = max(10, min(100, quality))
    if output_format == "JPEG":
        base = Image.new("RGB", images[0].size, background)
        base.paste(images[0], mask=images[0].getchannel("A"))
        images = [base]
    if output_format == "GIF":
        converted = []
        for image in images:
            palette = image.convert("RGB").quantize(colors=255)
            palette.putpalette((palette.getpalette() + [0] * 768)[:768])
            palette.paste(255, mask=image.getchannel("A").point(lambda a: 255 if a < 128 else 0))
            palette.info["transparency"] = 255
            converted.append(palette)
        images = converted
        options.update(transparency=255, disposal=2, optimize=False)
    if animated:
        options.update(save_all=True, append_images=images[1:],
                       duration=[d for _, d in chosen], loop=loaded.loop)
    handle = tempfile.NamedTemporaryFile(prefix=".lumen-", suffix=".tmp", dir=target.parent, delete=False)
    temporary = handle.name
    handle.close()
    try:
        images[0].save(temporary, format=output_format, **options)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class History:
    def __init__(self) -> None:
        self.state = EditState()
        self.undo_stack: list[EditState] = []
        self.redo_stack: list[EditState] = []

    def set(self, **changes) -> None:
        new = replace(self.state, **changes)
        if new != self.state:
            self.undo_stack.append(self.state)
            self.undo_stack = self.undo_stack[-50:]
            self.redo_stack.clear()
            self.state = new

    def undo(self) -> None:
        if self.undo_stack:
            self.redo_stack.append(self.state)
            self.state = self.undo_stack.pop()

    def redo(self) -> None:
        if self.redo_stack:
            self.undo_stack.append(self.state)
            self.state = self.redo_stack.pop()
