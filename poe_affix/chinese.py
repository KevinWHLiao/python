"""Fetch the current PoEDB Chinese localization PIN codes."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import unescape

from . import DATA_DIR
from .net import fetch

CHINESE_PAGE = "https://poedb.tw/tw/chinese"
CACHE_FILE = DATA_DIR / "chinese_pin.json"

_BLOCK = re.compile(
    r"(tw|cn)\s*PIN</h5>\s*<div class=\"card-body\">.*?<h4[^>]*>\s*(\d{3,8})\s*</h4>"
    r".*?Server Version:\s*([0-9.]+).*?Patch Version:\s*([0-9.]+)",
    re.IGNORECASE | re.DOTALL,
)
_TEXT_BLOCK = re.compile(
    r"(tw|cn)\s+PIN\s+(\d{3,8})\s+Server Version:\s*([0-9.]+)\s+Patch Version:\s*([0-9.]+)",
    re.IGNORECASE,
)
_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class PinInfo:
    locale: str
    pin: str
    server_version: str
    patch_version: str


@dataclass
class ChinesePins:
    tw: PinInfo | None
    cn: PinInfo | None
    fetched_at: str
    source: str
    from_cache: bool = False

    def as_cache(self) -> dict:
        payload = asdict(self)
        payload.pop("from_cache", None)
        return payload


def _plain_text(html: str) -> str:
    text = unescape(_TAGS.sub(" ", html))
    return _SPACE.sub(" ", text).strip()


def _pin_from_match(match: re.Match[str]) -> PinInfo:
    locale, pin, server, patch = match.groups()
    return PinInfo(locale.lower(), pin, server, patch)


def parse_pins(html: str) -> tuple[PinInfo | None, PinInfo | None]:
    found: dict[str, PinInfo] = {}
    for match in _BLOCK.finditer(html):
        info = _pin_from_match(match)
        found[info.locale] = info
    if "tw" not in found or "cn" not in found:
        for match in _TEXT_BLOCK.finditer(_plain_text(html)):
            info = _pin_from_match(match)
            found.setdefault(info.locale, info)
    return found.get("tw"), found.get("cn")


def _load_cache() -> ChinesePins | None:
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    tw = data.get("tw")
    cn = data.get("cn")
    return ChinesePins(
        tw=PinInfo(**tw) if tw else None,
        cn=PinInfo(**cn) if cn else None,
        fetched_at=str(data.get("fetched_at") or ""),
        source=str(data.get("source") or CHINESE_PAGE),
        from_cache=True,
    )


def _save_cache(pins: ChinesePins) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(pins.as_cache(), ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_pins(*, force: bool = False) -> ChinesePins:
    cached = _load_cache()
    try:
        _ = force
        html = fetch(CHINESE_PAGE)
        tw, cn = parse_pins(html)
        if not tw and not cn:
            raise RuntimeError("頁面上找不到 PIN 碼。")
        pins = ChinesePins(
            tw=tw,
            cn=cn,
            fetched_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            source=CHINESE_PAGE,
        )
        _save_cache(pins)
        return pins
    except Exception as error:
        if cached and (cached.tw or cached.cn):
            return cached
        raise RuntimeError(f"無法讀取中文化 PIN：{error}") from error
