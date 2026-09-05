"""poe.ninja ascendancy / class portraits for the builds ranking UI."""

from __future__ import annotations

import re
import threading
import urllib.error
import urllib.request
from pathlib import Path

from . import DATA_DIR

ICON_CDN = "https://assets.poe.ninja"
USER_AGENT = "PoELookupTool/1.0 (Windows desktop; personal local app)"
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_cache_lock = threading.Lock()
_memory_png: dict[tuple[str, str], bytes] = {}
_failed: set[tuple[str, str]] = set()


def class_icon_slug(name: str) -> str:
    slug = _SLUG_RE.sub("-", (name or "").strip().lower()).strip("-")
    return slug


def class_icon_url(game: str, name: str) -> str:
    realm = "poe2" if game == "poe2" else "poe1"
    slug = class_icon_slug(name)
    if not slug:
        return ""
    return f"{ICON_CDN}/{realm}/classes/{slug}.webp"


def _icon_dir(game: str) -> Path:
    realm = "poe2" if game == "poe2" else "poe1"
    path = DATA_DIR / "class_icons" / realm
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_path(game: str, name: str) -> Path:
    return _icon_dir(game) / f"{class_icon_slug(name)}.png"


def fetch_class_icon_png(game: str, name: str, force: bool = False) -> bytes | None:
    """Download (or load cached) class portrait as PNG bytes."""
    key = ("poe2" if game == "poe2" else "poe1", class_icon_slug(name))
    if not key[1]:
        return None
    with _cache_lock:
        if not force and key in _failed:
            return None
        cached = _memory_png.get(key)
        if cached and not force:
            return cached
    path = _cache_path(game, name)
    if path.exists() and not force:
        data = path.read_bytes()
        with _cache_lock:
            _memory_png[key] = data
        return data
    url = class_icon_url(game, name)
    if not url:
        return None
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "image/webp,image/*,*/*"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        with _cache_lock:
            _failed.add(key)
        return None
    try:
        from PIL import Image
        import io

        image = Image.open(io.BytesIO(raw)).convert("RGBA")
        # Tree rows look better with a compact square crop.
        side = max(image.size)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(image, ((side - image.size[0]) // 2, (side - image.size[1]) // 2), image)
        canvas = canvas.resize((64, 64), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        canvas.save(buf, format="PNG")
        png = buf.getvalue()
    except Exception:
        with _cache_lock:
            _failed.add(key)
        return None
    try:
        path.write_bytes(png)
    except OSError:
        pass
    with _cache_lock:
        _memory_png[key] = png
        _failed.discard(key)
    return png


def preload_class_icons(game: str, names: list[str]) -> dict[str, bytes]:
    """Fetch many class icons; returns english-name → png bytes for successes."""
    result: dict[str, bytes] = {}
    seen: set[str] = set()
    for name in names:
        if not name or name in seen:
            continue
        seen.add(name)
        png = fetch_class_icon_png(game, name)
        if png:
            result[name] = png
    return result
