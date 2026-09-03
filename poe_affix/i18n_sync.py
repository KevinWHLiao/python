"""Build the PoE2 item name table (English → 繁中) from poe2db.tw.

poe.ninja publishes PoE2 prices with English names only, and the bundled
``names_zh.json`` covers PoE1. Every PoE2 currency / rune / essence / idol has
a poe2db page whose title is the 繁中 name, so the table can be filled by
walking the names poe.ninja actually returns.
"""

from __future__ import annotations

import html as html_lib
import json
import re
import time
import urllib.parse
from typing import Callable

from . import DATA_DIR, POE2DB_BASE, resolve_named_data
from .economy import category_labels, fetch_leagues, fetch_prices
from .i18n import LEVEL_SUFFIX_RE, translate_name
from .net import fetch

NAMES_FILE_POE2 = "names_zh_poe2.json"
ProgressCb = Callable[[int, int, str], None]

_TITLE_RE = re.compile(r"<title>([^<]+)</title>", re.I)
_HAS_ZH_RE = re.compile(r"[\u4e00-\u9fff]")
_HAS_LATIN_RE = re.compile(r"[A-Za-z]")
_SUBTITLE_RE = re.compile(r"^(.*?):\s*(.+)$")


def _page_candidates(name: str) -> list[str]:
    base = name.replace(" ", "_")
    return list(dict.fromkeys([base, urllib.parse.quote(base, safe="_")]))


def is_item_title(zh: str) -> bool:
    """poe2db falls back to stat pages / raw slugs; those are not item names."""
    return bool(zh) and bool(_HAS_ZH_RE.search(zh)) and not _HAS_LATIN_RE.search(zh)


def _title_zh(page: str) -> str:
    title = _TITLE_RE.search(page)
    if not title:
        return ""
    zh = html_lib.unescape(title.group(1)).split(" - ")[0].strip()
    # poe2db occasionally doubles the possessive 的 (e.g. 瓜特利斯的的耐久…).
    zh = re.sub("的的+", "的", zh)
    return zh if is_item_title(zh) else ""


def _lookup_exact(name: str) -> str:
    for candidate in _page_candidates(name):
        try:
            page = fetch(f"{POE2DB_BASE}/{candidate}", timeout=20)
        except RuntimeError:
            continue
        zh = _title_zh(page)
        if zh:
            return zh
    return ""


def lookup_zh(name: str) -> str:
    """Return the 繁中 name from the item's poe2db page, or "" if unknown."""
    zh = _lookup_exact(name)
    if zh:
        return zh
    # "Zarokh's Reliquary Key: Against the Darkness" only has a base page.
    subtitle = _SUBTITLE_RE.match(name)
    if subtitle:
        base_zh = _lookup_exact(subtitle.group(1).strip())
        if base_zh:
            return f"{base_zh}（{subtitle.group(2).strip()}）"
    return ""


def collect_names(progress: ProgressCb | None = None) -> list[str]:
    """Every item name poe.ninja returns for PoE2, across the listed leagues."""
    names: list[str] = []
    seen: set[str] = set()
    leagues = fetch_leagues(game="poe2")
    labels = category_labels("poe2")
    total = len(leagues) * len(labels)
    done = 0
    for league in leagues:
        for label in labels:
            done += 1
            if progress:
                progress(done, total, f"讀取 {league.name} / {label}")
            try:
                rows = fetch_prices(league, label, game="poe2")
            except RuntimeError:
                continue
            for row in rows:
                if row.name and row.name not in seen:
                    seen.add(row.name)
                    names.append(row.name)
    return names


def load_existing() -> dict[str, str]:
    path = resolve_named_data(NAMES_FILE_POE2)
    if not path:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    # Drop values an older run scraped off a stat page instead of an item page.
    cleaned: dict[str, str] = {}
    for key, value in data.items():
        if not key or not value:
            continue
        text = re.sub("的的+", "的", str(value))
        if is_item_title(text.split("（")[0]):
            cleaned[str(key)] = text
    return cleaned


def sync_poe2_names(progress: ProgressCb | None = None, delay: float = 0.2) -> dict[str, str]:
    def report(done: int, total: int, message: str) -> None:
        if progress:
            progress(done, total, message)

    names = collect_names(progress=progress)
    mapping = load_existing()
    # Bases only: "(Level 12)" style suffixes are re-attached at display time.
    wanted: list[str] = []
    for name in names:
        match = LEVEL_SUFFIX_RE.match(name)
        base = match.group(1) if match else name
        if base in mapping or translate_name(base, game="poe2"):
            continue
        if base not in wanted:
            wanted.append(base)

    total = len(wanted)
    report(0, total, f"共 {len(names)} 個物品名稱，需要查 {total} 個")
    unresolved: list[str] = []
    for index, base in enumerate(wanted, start=1):
        zh = lookup_zh(base)
        if zh:
            mapping[base] = zh
        else:
            unresolved.append(base)
        report(index, total, f"{base} → {zh or '查不到'}")
        if delay:
            time.sleep(delay)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ordered = {key: mapping[key] for key in sorted(mapping)}
    (DATA_DIR / NAMES_FILE_POE2).write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if unresolved:
        report(total, total, f"完成，但 {len(unresolved)} 個查不到：{'、'.join(unresolved[:8])}")
    else:
        report(total, total, f"完成，共 {len(ordered)} 筆中文名")
    return ordered


if __name__ == "__main__":
    def _cli(done: int, total: int, message: str) -> None:
        print(f"[{done}/{total}] {message}")

    result = sync_poe2_names(progress=_cli)
    print(f"寫入 {DATA_DIR / NAMES_FILE_POE2}：{len(result)} 筆")
