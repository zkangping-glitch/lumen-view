"""Mini wheel installer used because pip's temp-file handling is blocked by the sandbox.

Downloads cp312/abi3 win_amd64 wheels from PyPI, resolves Requires-Dist
recursively (using pip's vendored packaging), and unzips them into .pylibs.
Never uses temp files that need delete-on-close semantics.
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import urllib.request
import zipfile

from pip._vendor.packaging.markers import Marker
from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.specifiers import SpecifierSet
from pip._vendor.packaging.version import InvalidVersion, Version

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WHEEL_DIR = os.path.join(ROOT, ".wheels")
LIB_DIR = os.path.join(ROOT, ".pylibs")

ENV = {
    "python_version": "3.12",
    "python_full_version": "3.12.14",
    "sys_platform": "win32",
    "platform_system": "Windows",
    "platform_machine": "AMD64",
    "os_name": "nt",
    "implementation_name": "cpython",
    "implementation_version": "3.12.14",
    "extra": "",
}

WHEEL_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9_.]+)-(?P<ver>[^-]+)(?:-(?P<build>\d[^-]*))?"
    r"-(?P<py>cp\d+|py\d+|pp\d+)(?:-(?P<abi>[^-]+))?-(?P<plat>[^-]+)\.whl$"
)


def http_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "LumenView-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def compatible(fname: str) -> bool:
    m = WHEEL_RE.match(fname)
    if not m:
        return False
    plat, py, abi = m.group("plat"), m.group("py"), m.group("abi") or ""
    if plat == "any":
        return py in ("py3", "py2.py3", "py2")
    if plat != "win_amd64":
        return False
    if py.startswith("py"):
        return True
    if py == "cp312":
        return True
    if abi == "abi3" and py in ("cp310", "cp311", "cp312"):
        return True
    return False


def pick_candidate(pkg: str, spec: SpecifierSet):
    """Return (version, url, filename) for the newest satisfying release with a usable wheel."""
    data = http_json(f"https://pypi.org/pypi/{pkg}/json")
    best = None
    for ver_str, files in data["releases"].items():
        try:
            ver = Version(ver_str)
        except InvalidVersion:
            continue
        if ver.is_prerelease:
            continue
        if spec and not spec.contains(ver):
            continue
        for f in files:
            if f.get("yanked"):
                continue
            if not compatible(f["filename"]):
                continue
            if best is None or ver > best[0]:
                best = (ver, f["url"], f["filename"])
            break
    return best


def already_installed(pkg: str) -> bool:
    if not os.path.isdir(LIB_DIR):
        return False
    norm = pkg.lower().replace("-", "_")
    for entry in os.listdir(LIB_DIR):
        if entry.lower().startswith(norm + "-") and entry.lower().endswith(".dist-info"):
            return True
        if entry.lower() == norm:
            return True
    return False


def download(url: str, dest: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "LumenView-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as fh:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)


def extract(wheel: str, target: str) -> None:
    import shutil

    with zipfile.ZipFile(wheel) as zf:
        zf.extractall(target)
        names = zf.namelist()

    # wheels that carry DLLs in `<pkg>.data/platlib` expect pip to flatten them
    for entry in list(names):
        parts = entry.split("/")
        if len(parts) >= 3 and parts[0].endswith(".data") and parts[1] in ("platlib", "purelib"):
            src = os.path.join(target, *parts)
            dst = os.path.join(target, *parts[2:])
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.exists(dst) and os.path.isdir(dst) and os.path.isdir(src):
                for sub in os.listdir(src):
                    shutil.move(os.path.join(src, sub), os.path.join(dst, sub))
            else:
                shutil.move(src, dst)
    for entry in os.listdir(target):
        if entry.endswith(".data"):
            shutil.rmtree(os.path.join(target, entry), ignore_errors=True)


def metadata_text(target: str, pkg: str) -> str:
    norm = pkg.lower().replace("-", "_")
    for entry in os.listdir(target):
        low = entry.lower()
        if low.startswith(norm) and low.endswith(".dist-info"):
            meta = os.path.join(target, entry, "METADATA")
            if os.path.exists(meta):
                with open(meta, encoding="utf-8", errors="replace") as fh:
                    return fh.read()
    return ""


def install(pkg: str, spec: str = "", seen: set[str] | None = None, depth: int = 0) -> None:
    seen = seen if seen is not None else set()
    key = pkg.lower().replace("-", "_")
    if key in seen:
        return
    seen.add(key)
    if already_installed(pkg):
        print(f"[skip] {pkg} already present")
        return

    if depth > 6:
        print(f"[warn] dependency depth exceeded at {pkg}")
        return

    cand = pick_candidate(pkg, SpecifierSet(spec) if spec else SpecifierSet())
    if cand is None:
        print(f"[FAIL] no compatible wheel for {pkg}{spec}")
        return
    ver, url, fname = cand
    os.makedirs(WHEEL_DIR, exist_ok=True)
    wheel_path = os.path.join(WHEEL_DIR, fname)
    if not os.path.exists(wheel_path):
        print(f"[get ] {fname}  ({ver})")
        download(url, wheel_path + ".part")
        os.replace(wheel_path + ".part", wheel_path)
    else:
        print(f"[cache] {fname}")

    os.makedirs(LIB_DIR, exist_ok=True)
    extract(wheel_path, LIB_DIR)

    meta = metadata_text(LIB_DIR, pkg)
    for line in meta.splitlines():
        if not line.startswith("Requires-Dist:"):
            continue
        raw = line.split(":", 1)[1].strip()
        try:
            req = Requirement(raw)
        except Exception:
            continue
        if req.marker is not None:
            try:
                if not req.marker.evaluate(ENV):
                    continue
            except Exception:
                continue
        if req.name.lower().replace("-", "_") in ("pyside6_addons", "pyqt5", "pyqt6"):
            continue
        install(req.name, str(req.specifier), seen, depth + 1)


def main() -> int:
    targets = sys.argv[1:] or [
        "PySide6-Essentials",
        "pillow-heif",
        "pillow-jxl-plugin",
        "psd-tools",
        "rawpy",
    ]
    for pkg in targets:
        install(pkg)
    print("done; libs in", LIB_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


