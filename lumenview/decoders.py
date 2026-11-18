"""Format dispatch for Lumen View.

Pillow is the workhorse; HEIF/JXL/PSD/RAW/SVG go through dedicated decoders.
Every loader returns :class:`Loaded` with one or more already-detached QImages,
so decoding can happen on a worker thread and the file handle can be closed.
"""

from __future__ import annotations

import gzip
import io
import os
from dataclasses import dataclass, field

from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QImage, QImageReader, QPainter
from PySide6.QtSvg import QSvgRenderer

RAW_EXTS = {
    "3fr", "ari", "arw", "bay", "cr2", "cr3", "crw", "dcr", "dng", "erf",
    "fff", "iiq", "k25", "kdc", "mdc", "mef", "mos", "mrw", "nef", "nrw",
    "orf", "pef", "raf", "raw", "rw2", "rwl", "sr2", "srf", "srw", "x3f",
}
SVG_EXTS = {"svg", "svgz"}
PSD_EXTS = {"psd", "psb"}
PIL_EXTS = {
    "jpg", "jpeg", "jpe", "jfif", "png", "apng", "gif", "bmp", "dib", "tif",
    "tiff", "webp", "ico", "cur", "avif", "heic", "heif", "jxl", "jp2", "j2k",
    "jpx", "pcx", "tga", "ppm", "pgm", "pbm", "pnm", "dds", "sgi", "xbm",
}
SUPPORTED_EXTS = PIL_EXTS | RAW_EXTS | SVG_EXTS | PSD_EXTS

# Pillow format id -> human label
_LABELS = {
    "JPEG": "JPEG", "PNG": "PNG", "GIF": "GIF", "BMP": "BMP", "TIFF": "TIFF",
    "WEBP": "WebP", "ICO": "ICO", "AVIF": "AVIF", "HEIF": "HEIC", "MPO": "JPEG (MPO)",
    "JPEG2000": "JPEG 2000", "DDS": "DDS", "TGA": "TGA", "PCX": "PCX",
    "PPM": "PPM", "SGI": "SGI", "XBM": "XBM",
}


@dataclass
class Frame:
    image: QImage
    duration: int = 0


@dataclass
class Loaded:
    path: str
    frames: list[Frame]
    fmt: str
    width: int
    height: int
    mode: str = ""
    file_size: int = 0
    exif: dict = field(default_factory=dict)
    pages: int = 1

    @property
    def animated(self) -> bool:
        return len(self.frames) > 1 and any(f.duration for f in self.frames)

    @property
    def first(self) -> QImage:
        return self.frames[0].image


class DecodeError(Exception):
    """A user-presentable decoding failure."""


# --------------------------------------------------------------------------- #
# plugin bootstrap
# --------------------------------------------------------------------------- #
def _register_plugins() -> None:
    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
    except Exception:
        pass
    try:
        import pillow_jxl  # noqa: F401  (registers itself on import)
    except Exception:
        pass


_register_plugins()


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _pil_to_qimage(im: Image.Image) -> QImage:
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        buf = im.tobytes("raw", "RGBA")
        qimg = QImage(buf, im.width, im.height, im.width * 4, QImage.Format.Format_RGBA8888)
    else:
        im = im.convert("RGB")
        buf = im.tobytes("raw", "RGB")
        qimg = QImage(buf, im.width, im.height, im.width * 3, QImage.Format.Format_RGB888)
    return qimg.copy()


def _numpy_to_qimage(arr) -> QImage:
    import numpy as np

    arr = np.ascontiguousarray(arr)
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)
    if arr.shape[2] == 4:
        arr = np.ascontiguousarray(arr[:, :, :3])
    h, w, _ = arr.shape
    return QImage(arr.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


def _exif_summary(im: Image.Image) -> dict:
    out: dict = {}
    try:
        exif = im.getexif()
    except Exception:
        return out
    if not exif:
        return out

    def clean(v) -> str:
        if isinstance(v, bytes):
            v = v.decode("utf-8", "replace")
        return str(v).replace("\x00", "").strip()

    make = clean(exif.get(271, "") or "")
    model = clean(exif.get(272, "") or "")
    if make and model.lower().startswith(make.lower()):
        model = model[len(make):].strip()
    if model:
        out["相机"] = f"{make} {model}".strip()
    elif make:
        out["相机"] = make
    when = clean(exif.get(36867, "") or exif.get(306, "") or "")
    if when:
        out["拍摄时间"] = when.replace(":", "-", 2)
    return out


def _size_label(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"


def format_size(n: int) -> str:
    return _size_label(n)


# --------------------------------------------------------------------------- #
# individual decoders
# --------------------------------------------------------------------------- #
def _load_svg(path: str) -> Loaded:
    with open(path, "rb") as fh:
        data = fh.read()
    if path.lower().endswith(".svgz") or data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    renderer = QSvgRenderer(QByteArray(data))
    if not renderer.isValid():
        raise DecodeError("SVG 解析失败（文件损坏或包含不支持的语法）")

    size = renderer.defaultSize()
    vb = renderer.viewBoxF()
    dw, dh = size.width(), size.height()
    if dw <= 0 or dh <= 0:
        dw, dh = (vb.width(), vb.height()) if vb.isValid() else (1024, 1024)
    if dw <= 0 or dh <= 0:
        dw, dh = 1024, 1024

    # render vectors big enough to stay crisp when zoomed in
    target = 2048.0
    scale = max(1.0, min(target, 4096.0) / max(dw, dh))
    w, h = int(round(dw * scale)), int(round(dh * scale))
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter)
    painter.end()

    loaded = Loaded(
        path=path, frames=[Frame(img)], fmt="SVG", width=w, height=h,
        mode="vector", file_size=os.path.getsize(path),
    )
    loaded.exif["画布"] = f"{int(round(dw))} × {int(round(dh))} (矢量)"
    return loaded


def _load_psd(path: str) -> Loaded:
    try:
        from psd_tools import PSDImage
    except ImportError as exc:  # pragma: no cover
        raise DecodeError("缺少 psd-tools，无法打开 PSD") from exc

    try:
        psd = PSDImage.open(path)
    except Exception as exc:
        raise DecodeError(f"PSD 解析失败：{exc}") from exc

    im = None
    try:
        im = psd.topil()
    except Exception:
        im = None
    if im is None:
        try:
            im = psd.composite()
        except Exception as exc:
            raise DecodeError(f"PSD 合成图像失败：{exc}") from exc
    if im is None:
        raise DecodeError("这个 PSD 没有可显示的合成图像（可能全部图层被隐藏）")

    qimg = _pil_to_qimage(im)
    loaded = Loaded(
        path=path, frames=[Frame(qimg)], fmt="PSD", width=qimg.width(),
        height=qimg.height(), mode=im.mode, file_size=os.path.getsize(path),
    )
    try:
        loaded.exif["图层"] = str(len(psd))
    except Exception:
        pass
    return loaded


def _load_raw(path: str) -> Loaded:
    try:
        import rawpy
    except ImportError as exc:  # pragma: no cover
        raise DecodeError("缺少 rawpy，无法打开相机 RAW") from exc

    try:
        with rawpy.imread(path) as raw:
            rgb = raw.postprocess(use_camera_wb=True, output_bps=8)
    except Exception as exc:
        raise DecodeError(f"RAW 解码失败：{exc}") from exc

    qimg = _numpy_to_qimage(rgb)
    ext = os.path.splitext(path)[1].lstrip(".").upper()
    loaded = Loaded(
        path=path, frames=[Frame(qimg)], fmt=f"RAW ({ext})", width=qimg.width(),
        height=qimg.height(), mode="RGB", file_size=os.path.getsize(path),
    )
    return loaded


def _load_pillow(path: str) -> Loaded:
    try:
        im = Image.open(path)
    except UnidentifiedImageError:
        raise DecodeError("无法识别这个文件：可能已损坏，或者它其实不是图片") from None
    except Exception as exc:
        raise DecodeError(f"读取图片时出错：{exc}") from exc

    fmt_id = (im.format or os.path.splitext(path)[1].lstrip(".")).upper()
    fmt = _LABELS.get(fmt_id, fmt_id or "未知")
    n_frames = getattr(im, "n_frames", 1)
    animated = (
        n_frames > 1
        and getattr(im, "is_animated", False)
        and fmt_id not in ("HEIF", "HEIC")
    )

    frames: list[Frame] = []
    exif: dict = {}
    if animated:
        for index, frame in enumerate(ImageSequence.Iterator(im)):
            duration = int(frame.info.get("duration", 0) or im.info.get("duration", 0) or 0)
            frames.append(Frame(_pil_to_qimage(frame), max(duration, 20) if duration else 100))
            if index >= 600:  # keep memory sane for absurd GIFs
                break
        exif = _exif_summary(im)
        width, height = im.size
        mode = im.mode
    else:
        if n_frames > 1:
            im.seek(0)
        im.load()
        try:
            transposed = ImageOps.exif_transpose(im)
            if transposed is not None:
                im = transposed
        except Exception:
            pass
        frames = [Frame(_pil_to_qimage(im))]
        exif = _exif_summary(im)
        width, height = im.size
        mode = im.mode

    loaded = Loaded(
        path=path, frames=frames, fmt=fmt, width=width, height=height,
        mode=mode, file_size=os.path.getsize(path), exif=exif, pages=max(n_frames, 1),
    )
    if n_frames > 1 and not animated:
        loaded.exif["页数"] = f"{n_frames} 页（显示第 1 页）"
    return loaded


def _load_qt(path: str) -> Loaded:
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    img = reader.read()
    if img.isNull():
        raise DecodeError(f"无法解码该图片：{reader.errorString()}")
    ext = os.path.splitext(path)[1].lstrip(".").upper()
    return Loaded(
        path=path, frames=[Frame(img)], fmt=ext, width=img.width(),
        height=img.height(), mode="RGB", file_size=os.path.getsize(path),
    )


# --------------------------------------------------------------------------- #
# public entry points
# --------------------------------------------------------------------------- #
def extension(path: str) -> str:
    return os.path.splitext(path)[1].lstrip(".").lower()


def is_supported(path: str) -> bool:
    return extension(path) in SUPPORTED_EXTS


def load_image(path: str) -> Loaded:
    ext = extension(path)
    if not os.path.isfile(path):
        raise DecodeError("文件不存在")
    if ext in SVG_EXTS:
        return _load_svg(path)
    if ext in PSD_EXTS:
        return _load_psd(path)
    if ext in RAW_EXTS:
        return _load_raw(path)
    if ext in PIL_EXTS:
        try:
            return _load_pillow(path)
        except DecodeError as exc:
            # some Pillow builds lack a codec while Qt still has one (or vice versa)
            try:
                return _load_qt(path)
            except DecodeError:
                raise exc from None
    # unknown extension: try both before giving up
    try:
        return _load_pillow(path)
    except DecodeError:
        return _load_qt(path)


def load_thumbnail(path: str, size: int = 160) -> QImage:
    """Fast-ish thumbnail; uses embedded previews when a format offers one."""
    ext = extension(path)
    try:
        if ext in PSD_EXTS:
            from psd_tools import PSDImage

            psd = PSDImage.open(path)
            thumb = psd.thumbnail()
            if thumb is not None:
                return _scaled(_pil_to_qimage(thumb), size)
        if ext in RAW_EXTS:
            import rawpy

            with rawpy.imread(path) as raw:
                try:
                    thumb = raw.extract_thumb()
                    if thumb.format == rawpy.ThumbFormat.JPEG:
                        with Image.open(io.BytesIO(thumb.data)) as im:
                            return _scaled(_pil_to_qimage(im), size)
                    if thumb.format == rawpy.ThumbFormat.BITMAP:
                        return _scaled(_numpy_to_qimage(thumb.data), size)
                except Exception:
                    pass
        if ext in ("jpg", "jpeg", "jpe", "jfif"):
            with Image.open(path) as im:
                im.draft("RGB", (size * 2, size * 2))
                return _scaled(_pil_to_qimage(im), size)
        if ext in PIL_EXTS:
            with Image.open(path) as im:
                im.seek(0)
                im.load()
                return _scaled(_pil_to_qimage(im), size)
        return _scaled(load_image(path).first, size)
    except Exception:
        raise


def _scaled(img: QImage, size: int) -> QImage:
    if img.width() <= size and img.height() <= size:
        return img
    return img.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                      Qt.TransformationMode.SmoothTransformation)

