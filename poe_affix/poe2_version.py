"""Fetch the current Path of Exile 2 patch version from poe2db.tw."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import unescape

from . import DATA_DIR, POE2DB_BASE
from .net import fetch

HOME_URL = f"{POE2DB_BASE}"
CACHE_FILE = DATA_DIR / "poe2_version.json"

_VERSION_HREF = re.compile(
    r'href="(?:https?://poe2db\.tw)?(?:/tw)?/(Version_(\d+\.\d+\.\d+[a-zA-Z0-9.]*))"[^>]*>([^<]*)',
    re.IGNORECASE,
)
_TITLE_RE = re.compile(r"<title>([^<]+)</title>", re.IGNORECASE)
_H1_RE = re.compile(r"<h1[^>]*>([\s\S]*?)</h1>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class Poe2Version:
    version: str
    title_zh: str
    url: str
    fetched_at: str
    source: str
    from_cache: bool = False

    def as_cache(self) -> dict:
        payload = asdict(self)
        payload.pop("from_cache", None)
        return payload

    @property
    def display(self) -> str:
        if self.title_zh and self.title_zh != self.version:
            return f"{self.version}（{self.title_zh}）"
        return self.version


def _plain(fragment: str) -> str:
    return _SPACE_RE.sub(" ", unescape(_TAG_RE.sub(" ", fragment))).strip()


def _version_key(version: str) -> tuple:
    """Sort key so 0.5.5 > 0.5.4b > 0.5.4."""
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)([a-zA-Z]*)$", version)
    if not match:
        return (0, 0, 0, "")
    major, minor, patch, suffix = match.groups()
    return (int(major), int(minor), int(patch), suffix or "")


def parse_latest_version(html: str) -> tuple[str, str]:
    """Return (version, page_slug) for the newest published patch on the home page."""
    candidates: list[tuple[str, str, str]] = []
    for match in _VERSION_HREF.finditer(html):
        slug, version, label = match.groups()
        label = _plain(label)
        # Skip pure countdown teasers for unreleased major versions (e.g. 1.0.0).
        if "開始倒數" in label and "更新" not in label:
            continue
        candidates.append((version, slug, label))
    if not candidates:
        raise RuntimeError("poe2db 首頁找不到版本連結。")

    # Prefer pages marked as patch notes / update announcements.
    announced = [item for item in candidates if "更新" in item[2] or "公告" in item[2]]
    pool = announced or candidates
    version, slug, _label = max(pool, key=lambda item: _version_key(item[0]))
    return version, slug


def parse_version_title(html: str, version: str) -> str:
    """Chinese short title from the version page, e.g. 禁忌儀式活動聯盟."""
    h1 = _H1_RE.search(html)
    if h1:
        text = _plain(h1.group(1))
        text = re.sub(rf"^版本\s*{re.escape(version)}\s*", "", text).strip(" ·-—")
        if text:
            return text
    title = _TITLE_RE.search(html)
    if title:
        text = _plain(title.group(1)).split(" - ")[0].strip()
        text = re.sub(rf"^Version[_\s]*{re.escape(version)}\s*", "", text, flags=re.I).strip()
        if text and text != version:
            return text
    return ""


def _load_cache() -> Poe2Version | None:
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not data.get("version"):
        return None
    return Poe2Version(
        version=str(data["version"]),
        title_zh=str(data.get("title_zh") or ""),
        url=str(data.get("url") or ""),
        fetched_at=str(data.get("fetched_at") or ""),
        source=str(data.get("source") or HOME_URL),
        from_cache=True,
    )


def _save_cache(info: Poe2Version) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(info.as_cache(), ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_poe2_version(*, force: bool = False) -> Poe2Version:
    cached = _load_cache()
    try:
        _ = force
        home = fetch(HOME_URL)
        version, slug = parse_latest_version(home)
        url = f"{POE2DB_BASE}/{slug}"
        title_zh = ""
        try:
            page = fetch(url)
            title_zh = parse_version_title(page, version)
        except RuntimeError:
            title_zh = ""
        info = Poe2Version(
            version=version,
            title_zh=title_zh,
            url=url,
            fetched_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            source=HOME_URL,
        )
        _save_cache(info)
        return info
    except Exception as error:
        if cached:
            return cached
        raise RuntimeError(f"無法讀取 PoE2 版本：{error}") from error
