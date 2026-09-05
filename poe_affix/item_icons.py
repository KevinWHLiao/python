"""Download and cache item icons from web.poecdn.com / poe.ninja."""

from __future__ import annotations

import hashlib
import io
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import DATA_DIR

POECDN = "https://web.poecdn.com"
USER_AGENT = "PoELookupTool/1.0 (Windows desktop; personal local app)"
_ICON_DIR = DATA_DIR / "item_icons"
_cache_lock = threading.Lock()
_memory_png: dict[str, bytes] = {}
_failed: set[str] = set()


def absolute_icon_url(raw: str | None) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if text.startswith("http://") or text.startswith("https://"):
        return text
    if text.startswith("/"):
        return POECDN + text
    return f"{POECDN}/{text}"


def _cache_key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


def _cache_path(url: str) -> Path:
    _ICON_DIR.mkdir(parents=True, exist_ok=True)
    return _ICON_DIR / f"{_cache_key(url)}.png"


def fetch_icon_png(url: str, *, size: int = 48, force: bool = False) -> bytes | None:
    """Return PNG bytes for an icon URL, with disk + memory cache."""
    url = absolute_icon_url(url)
    if not url:
        return None
    key = _cache_key(url)
    with _cache_lock:
        if not force and key in _failed:
            return None
        cached = _memory_png.get(key)
        if cached and not force:
            return cached
    path = _cache_path(url)
    if path.exists() and not force:
        data = path.read_bytes()
        with _cache_lock:
            _memory_png[key] = data
        return data
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "image/avif,image/webp,image/*,*/*"},
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

        image = Image.open(io.BytesIO(raw)).convert("RGBA")
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.paste(image, ((size - image.size[0]) // 2, (size - image.size[1]) // 2), image)
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


def preload_icon_pngs(urls: list[str], *, size: int = 48, max_workers: int = 8) -> dict[str, bytes]:
    """Fetch many icons; returns absolute-url → png bytes."""
    unique: list[str] = []
    seen: set[str] = set()
    for raw in urls:
        url = absolute_icon_url(raw)
        if not url or url in seen:
            continue
        seen.add(url)
        unique.append(url)
    if not unique:
        return {}
    result: dict[str, bytes] = {}

    def one(url: str) -> tuple[str, bytes | None]:
        return url, fetch_icon_png(url, size=size)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(one, url) for url in unique]
        for future in as_completed(futures):
            try:
                url, png = future.result()
            except Exception:
                continue
            if png:
                result[url] = png
    return result
