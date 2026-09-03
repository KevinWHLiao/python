"""Build the PoE2 league-start catalog from Maxroll's ascendancy tier list.

Maxroll renders the tier list server-side, so the table can be read straight
from the HTML. Ascendancy names are then resolved to 繁中 via poe2db.tw, the
same wiki the affix lookup already uses.
"""

from __future__ import annotations

import html as html_lib
import json
import re
import time
from datetime import datetime, timezone
from typing import Callable

from . import DATA_DIR, POE2DB_BASE
from .net import fetch

MAXROLL_TIERLIST_URL = "https://maxroll.gg/poe2/tierlists/league-starter-ascendancy-tier-list"
MAXROLL_BASE = "https://maxroll.gg"
STARTERS_FILE_POE2 = "league_starters_poe2.json"

ProgressCb = Callable[[int, int, str], None]

# Words poe2db keeps lowercase in page titles (Smith_of_Kitava, Acolyte_of_Chayula).
_SMALL_WORDS = {"of", "the", "and", "a", "an"}
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")

TIER_HINT = {
    "S": "最強開荒選擇，容錯高、成長曲線平穩",
    "A": "很好的開荒選擇，稍微吃裝備或操作",
    "B": "可以開荒，但需要更多資源或熟練度",
    "C": "偏弱的開荒選擇，建議有經驗再玩",
    "D": "不建議開荒，通常要等裝備成型",
}


def _text(fragment: str | None) -> str:
    if not fragment:
        return ""
    return _SPACE_RE.sub(" ", html_lib.unescape(_TAG_RE.sub(" ", fragment))).strip()


def _slug_to_page(slug: str) -> str:
    words = [part for part in slug.split("-") if part]
    if not words:
        return ""
    return "_".join(
        word.capitalize() if index == 0 or word not in _SMALL_WORDS else word
        for index, word in enumerate(words)
    )


def parse_tierlist(html: str) -> list[dict]:
    """Return [{tier, name, class_slug, ascendancy_slug, guide_url}] in page order."""
    start = html.find("_Tierlist__tier_")
    if start < 0:
        raise RuntimeError("Maxroll 頁面格式改變了，找不到 tier list 區塊。")
    blocks = re.split(r'class="_Tierlist__tier_[^"]*"', html[max(0, start - 4000):])
    entries: list[dict] = []
    for block in blocks[1:]:
        tier_match = re.search(r'_Tierlist__tierName_[^"]*"[^>]*>([\s\S]*?)</', block)
        tier = _text(tier_match.group(1) if tier_match else "").upper()
        if not tier:
            continue
        for chunk in re.split(r'class="_Tierlist__tierItemContainer_[^"]*"', block)[1:]:
            name_match = re.search(r'_Tierlist__tierItemText_[^"]*"[^>]*>([\s\S]*?)</div>', chunk)
            name = _text(name_match.group(1) if name_match else "")
            if not name:
                continue
            href = ""
            href_match = re.search(r'href="([^"]+)"', chunk)
            if href_match:
                href = html_lib.unescape(href_match.group(1))
            class_slug = ""
            asc_slug = ""
            class_match = re.search(r"filter\[classes\]\[value\]=([a-z0-9\-]+)", href)
            if class_match:
                class_slug = class_match.group(1)
            asc_match = re.search(r"filter\[classes\]\[filters\]\[0\]\[value\]=([a-z0-9\-]+)", href)
            if asc_match:
                asc_slug = asc_match.group(1)
            entries.append(
                {
                    "tier": tier,
                    "name": name,
                    "class_slug": class_slug,
                    "ascendancy_slug": asc_slug or name.lower().replace(" ", "-"),
                    "guide_url": (MAXROLL_BASE + href) if href.startswith("/") else href,
                }
            )
    if not entries:
        raise RuntimeError("Maxroll 頁面沒有解析到任何昇華，格式可能改版了。")
    return entries


def parse_page_meta(html: str) -> dict:
    """Patch label, author and last-updated date from the article header."""
    plain = _text(re.sub(r"<script[\s\S]*?</script>", " ", html))
    meta: dict[str, str] = {}
    patch = re.search(r"League Starter Ascendancy Tier List for Path of Exile 2 ([^|]+?)\s*\|", plain)
    if patch:
        meta["patch"] = patch.group(1).strip()
    author = re.search(r"by ([A-Za-z0-9_\-]+) ", plain)
    if author:
        meta["author"] = author.group(1)
    updated = re.search(r"Last Updated:\s*([A-Za-z]+ \d{1,2}, \d{4})", plain)
    if updated:
        meta["updated"] = updated.group(1)
    intro = re.search(r"(This Ascendancy Tier List[^.]*\.(?:[^.]*\.){0,2})", plain)
    if intro:
        meta["intro"] = intro.group(1).strip()
    return meta


def fetch_zh_names(name_en: str, slug: str) -> tuple[str, str]:
    """Look up (ascendancy_zh, class_zh) on poe2db; fall back to the English name."""
    candidates = [name_en.replace(" ", "_"), _slug_to_page(slug)]
    for candidate in dict.fromkeys(part for part in candidates if part):
        try:
            page = fetch(f"{POE2DB_BASE}/{candidate}")
        except RuntimeError:
            continue
        title = re.search(r"<title>([^<]+)</title>", page)
        asc_zh = ""
        if title:
            asc_zh = _text(title.group(1)).split(" - ")[0].strip()
        class_zh = ""
        class_match = re.search(r"角色\s*[:：]\s*(?:<[^>]*>\s*)*([\u4e00-\u9fff]{1,8})", page)
        if class_match:
            class_zh = class_match.group(1)
        if asc_zh and re.search(r"[\u4e00-\u9fff]", asc_zh):
            return asc_zh, class_zh
    return name_en, ""


def build_catalog(progress: ProgressCb | None = None, delay: float = 0.25) -> dict:
    def report(done: int, total: int, message: str) -> None:
        if progress:
            progress(done, total, message)

    report(0, 1, "下載 Maxroll 開荒 tier list…")
    html = fetch(MAXROLL_TIERLIST_URL)
    entries = parse_tierlist(html)
    meta = parse_page_meta(html)

    builds: list[dict] = []
    classes: list[str] = []
    total = len(entries)
    rank_in_tier: dict[str, int] = {}
    for index, entry in enumerate(entries, start=1):
        report(index, total, f"對應繁中名稱 {index}/{total}：{entry['name']}")
        asc_zh, class_zh = fetch_zh_names(entry["name"], entry["ascendancy_slug"])
        style = class_zh or (entry["class_slug"] or "").replace("-", " ").title() or "其他"
        if style not in classes:
            classes.append(style)
        tier = entry["tier"]
        position = rank_in_tier.get(tier, 0)
        rank_in_tier[tier] = position + 1
        summary_bits = [f"Maxroll 開荒評級 {tier} 級。"]
        if TIER_HINT.get(tier):
            summary_bits.append(TIER_HINT[tier] + "。")
        summary_bits.append(f"同梯隊內 Maxroll 由上而下排序；點「開啟 Guide」可看 {entry['name']} 的 Maxroll 攻略清單。")
        builds.append(
            {
                "id": f"poe2-{entry['ascendancy_slug']}",
                "name": entry["name"],
                "name_zh": f"{asc_zh}（{entry['name']}）" if asc_zh != entry["name"] else entry["name"],
                "ascendancy": entry["name"],
                "ascendancy_zh": asc_zh,
                "skill": "",
                "skill_zh": "",
                "styles": [style],
                "damage": [],
                "playstyles": [],
                "budget": "league_start",
                "difficulty": "medium",
                "goals": [],
                "modes": ["trade", "ssf"],
                "tier": tier,
                # Keep Maxroll's line-by-line order inside a tier without crossing tiers.
                "score_bias": round(-0.1 * position, 2),
                "summary": " ".join(summary_bits),
                "guide_url": entry["guide_url"] or MAXROLL_TIERLIST_URL,
                "pob_url": "",
                "tags": [tier, style, entry["name"]],
            }
        )
        if delay:
            time.sleep(delay)

    notes_bits = ["資料來源：Maxroll 開荒昇華 tier list"]
    if meta.get("patch"):
        notes_bits.append(meta["patch"])
    if meta.get("author"):
        notes_bits.append(f"作者 {meta['author']}")
    if meta.get("updated"):
        notes_bits.append(f"Maxroll 更新 {meta['updated']}")

    catalog = {
        "game": "poe2",
        "league": meta.get("patch") or "Path of Exile 2",
        "league_zh": f"流亡黯道 2 · {meta.get('patch') or '開荒昇華'}",
        "updated": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d"),
        "source": MAXROLL_TIERLIST_URL,
        "notes": "　·　".join(notes_bits),
        "intro": meta.get("intro", ""),
        "styles": classes,
        "damage_types": [],
        "playstyles": [],
        "goals": [],
        "budgets": [{"id": "league_start", "label": "開荒零成本"}],
        "difficulties": [{"id": "medium", "label": "中等"}],
        "builds": builds,
    }
    report(total, total, f"完成，共 {len(builds)} 個昇華")
    return catalog


def sync_league_starters_poe2(progress: ProgressCb | None = None, delay: float = 0.25) -> dict:
    catalog = build_catalog(progress=progress, delay=delay)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / STARTERS_FILE_POE2).write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return catalog


if __name__ == "__main__":
    def _cli(done: int, total: int, message: str) -> None:
        print(f"[{done}/{total}] {message}")

    result = sync_league_starters_poe2(progress=_cli)
    print(f"寫入 {DATA_DIR / STARTERS_FILE_POE2}：{len(result['builds'])} 個昇華")
