"""Build the PoE2 league-start catalog from Maxroll's build tier list.

Primary source is the League Starter Build Tier List (actual builds with
guide links). Each guide page is then scraped for introduction / pros / cons
and the Maxroll planner URL. Ascendancy names are resolved to 繁中 via
poe2db.tw.
"""

from __future__ import annotations

import html as html_lib
import json
import re
import time
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlparse

from . import DATA_DIR, POE2DB_BASE
from .net import fetch

MAXROLL_BASE = "https://maxroll.gg"
MAXROLL_HUB_URL = f"{MAXROLL_BASE}/poe2/tierlists"
MAXROLL_BUILD_TIERLIST_URL = f"{MAXROLL_BASE}/poe2/tierlists/league-starter-build-tier-list"
MAXROLL_ASC_TIERLIST_URL = f"{MAXROLL_BASE}/poe2/tierlists/league-starter-ascendancy-tier-list"
STARTERS_FILE_POE2 = "league_starters_poe2.json"

ProgressCb = Callable[[int, int, str], None]

_SMALL_WORDS = {"of", "the", "and", "a", "an"}
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_SCRIPT_RE = re.compile(r"<script[\s\S]*?</script>", re.IGNORECASE)

TIER_HINT = {
    "S": "最強開荒選擇，容錯高、成長曲線平穩",
    "A": "很好的開荒選擇，稍微吃裝備或操作",
    "B": "可以開荒，但需要更多資源或熟練度",
    "C": "偏弱的開荒選擇，建議有經驗再玩",
    "D": "不建議開荒，通常要等裝備成型",
}

TIER_DIFFICULTY = {
    "S": "easy",
    "A": "easy",
    "B": "medium",
    "C": "hard",
    "D": "hard",
}


def _text(fragment: str | None) -> str:
    if not fragment:
        return ""
    cleaned = _SCRIPT_RE.sub(" ", fragment)
    return _SPACE_RE.sub(" ", html_lib.unescape(_TAG_RE.sub(" ", cleaned))).strip()


def _slug_to_title(slug: str) -> str:
    words = [part for part in slug.split("-") if part]
    if not words:
        return ""
    return " ".join(
        word.capitalize() if index == 0 or word not in _SMALL_WORDS else word
        for index, word in enumerate(words)
    )


def _slug_to_page(slug: str) -> str:
    return _slug_to_title(slug).replace(" ", "_")


def _name_from_guide_url(href: str) -> str:
    path = urlparse(href).path.rstrip("/")
    slug = path.rsplit("/", 1)[-1]
    for suffix in ("-build-guide", "-build", "-guide"):
        if slug.endswith(suffix):
            slug = slug[: -len(suffix)]
            break
    return _slug_to_title(slug)


def parse_build_tierlist(html: str) -> list[dict]:
    """Return builds [{tier, name, ascendancy_slug, guide_url}] in page order."""
    start = html.find("_Tierlist__tier_")
    if start < 0:
        raise RuntimeError("Maxroll Build tier list 格式改變了，找不到 tier 區塊。")
    blocks = re.split(r'class="_Tierlist__tier_[^"]*"', html[max(0, start - 4000) :])
    entries: list[dict] = []
    seen: set[str] = set()
    for block in blocks[1:]:
        tier_match = re.search(r'_Tierlist__tierName_[^"]*"[^>]*>([\s\S]*?)</', block)
        tier = _text(tier_match.group(1) if tier_match else "").upper()
        if not tier:
            continue
        for chunk in re.split(r'class="_Tierlist__tierItemContainer_[^"]*"', block)[1:]:
            href = ""
            href_match = re.search(r'href="([^"]+)"', chunk)
            if href_match:
                href = html_lib.unescape(href_match.group(1))
            if not href or "/build-guides/" not in href:
                continue
            guide_url = (MAXROLL_BASE + href) if href.startswith("/") else href
            if guide_url in seen:
                continue
            seen.add(guide_url)

            name_match = re.search(r'_Tierlist__tierItemText_[^"]*"[^>]*>([\s\S]*?)</span>', chunk)
            name = _text(name_match.group(1) if name_match else "")
            if not name:
                name = _name_from_guide_url(href)

            asc_slug = ""
            icon_match = re.search(r'src="([^"]*ascendancy/[^"]+)"', chunk)
            if icon_match:
                icon = icon_match.group(1)
                slug_match = re.search(r"/ascendancy/([a-z0-9\-]+)\.", icon)
                if slug_match:
                    asc_slug = slug_match.group(1)

            entries.append(
                {
                    "tier": tier,
                    "name": name,
                    "ascendancy_slug": asc_slug,
                    "ascendancy": _slug_to_title(asc_slug) if asc_slug else "",
                    "guide_url": guide_url,
                }
            )
    if not entries:
        raise RuntimeError("Maxroll Build tier list 沒有解析到任何 Build。")
    return entries


def parse_page_meta(html: str) -> dict:
    """Patch label and last-updated date from the article header."""
    plain = _text(_SCRIPT_RE.sub(" ", html))
    meta: dict[str, str] = {}
    patch = re.search(r"(?:The )?([A-Za-z][A-Za-z0-9 ']+?)\s+(0\.\d+\.\d+[a-zA-Z0-9.]*)", plain)
    # Prefer the seasonal component line, e.g. "The Forbidden Rites 0.5.5".
    seasonal = re.search(r"The ([A-Za-z][A-Za-z0-9 ']+)\s+(0\.\d+\.\d+[a-zA-Z0-9.]*)", plain)
    created = re.search(r"Created for\s+(0\.\d+\.\d+[a-zA-Z0-9.]*)", plain)
    if seasonal:
        meta["league"] = seasonal.group(1).strip()
        meta["patch"] = seasonal.group(2).strip()
    elif created:
        meta["patch"] = created.group(1).strip()
    elif patch:
        meta["league"] = patch.group(1).strip()
        meta["patch"] = patch.group(2).strip()
    updated = re.search(r"Last Updated:\s*([A-Za-z]+ \d{1,2}, \d{4})", plain)
    if updated:
        meta["updated"] = updated.group(1)
    intro = re.search(
        r"(This League Starter Build Tier List[^.]*\.(?:[^.]*\.){0,2})",
        plain,
    )
    if intro:
        meta["intro"] = intro.group(1).strip()
    return meta


def fetch_guide_details(url: str) -> dict:
    """Pull introduction, pros, cons and planner URL from a Maxroll build guide."""
    page = fetch(url, timeout=30)

    def list_items(kind: str) -> list[str]:
        block = re.search(
            rf'_StrAndWeak__blockTitle_[^"]*"[^>]*>{re.escape(kind)}</span>'
            rf'[\s\S]*?<ul class="_StrAndWeak__blockList_[^"]*">([\s\S]*?)</ul>',
            page,
        )
        if not block:
            return []
        values: list[str] = []
        for item in re.findall(r'_StrAndWeak__blockListItem_[^"]*"[^>]*>([\s\S]*?)</li>', block.group(1)):
            text = _text(re.sub(r"<svg[\s\S]*?</svg>", " ", item))
            if text:
                values.append(text)
            if len(values) >= 6:
                break
        return values

    summary = ""
    intro = re.search(
        r'id="introduction-header"[\s\S]*?class="maxroll-rich-text-editor">([\s\S]*?)</div></div>',
        page,
        re.IGNORECASE,
    )
    if intro:
        paragraphs = re.findall(r"<p[^>]*>([\s\S]*?)</p>", intro.group(1), re.IGNORECASE)
        summary = " ".join(_text(part) for part in paragraphs[:2] if _text(part)).strip()
        if len(summary) > 420:
            summary = summary[:417].rstrip() + "…"

    planner = ""
    planner_match = re.search(r"https://maxroll\.gg/poe2/planner/[A-Za-z0-9_\-]+", page)
    if planner_match:
        planner = planner_match.group(0)

    return {
        "summary": summary,
        "pros": list_items("Pros"),
        "cons": list_items("Cons"),
        "planner_url": planner,
    }


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
    return name_en or slug.replace("-", " ").title(), ""


def _skill_from_name(build_name: str, ascendancy: str) -> str:
    """Strip ascendancy words from the Maxroll build title to leave the skill focus."""
    if not build_name:
        return ""
    drop = {part.lower() for part in re.split(r"[\s\-]+", ascendancy) if part}
    drop.update({"build", "guide", "league", "starter"})
    kept = [word for word in build_name.split() if word.lower() not in drop]
    return " ".join(kept).strip()


def build_catalog(progress: ProgressCb | None = None, delay: float = 0.2) -> dict:
    def report(done: int, total: int, message: str) -> None:
        if progress:
            progress(done, total, message)

    report(0, 1, "下載 Maxroll 開荒 Build tier list…")
    html = fetch(MAXROLL_BUILD_TIERLIST_URL)
    entries = parse_build_tierlist(html)
    meta = parse_page_meta(html)

    builds: list[dict] = []
    classes: list[str] = []
    zh_cache: dict[str, tuple[str, str]] = {}
    total = len(entries)
    rank_in_tier: dict[str, int] = {}

    for index, entry in enumerate(entries, start=1):
        asc_en = entry["ascendancy"] or entry["ascendancy_slug"].replace("-", " ").title()
        report(index, total, f"讀取攻略 {index}/{total}：{entry['name']}")
        details: dict = {"summary": "", "pros": [], "cons": [], "planner_url": ""}
        try:
            details = fetch_guide_details(entry["guide_url"])
        except RuntimeError:
            details = {"summary": "", "pros": [], "cons": [], "planner_url": ""}

        cache_key = entry["ascendancy_slug"] or asc_en
        if cache_key in zh_cache:
            asc_zh, class_zh = zh_cache[cache_key]
        else:
            asc_zh, class_zh = fetch_zh_names(asc_en, entry["ascendancy_slug"])
            zh_cache[cache_key] = (asc_zh, class_zh)

        style = class_zh or "其他"
        if style not in classes:
            classes.append(style)

        skill = _skill_from_name(entry["name"], asc_en)
        tier = entry["tier"]
        position = rank_in_tier.get(tier, 0)
        rank_in_tier[tier] = position + 1

        summary_bits = [f"Maxroll 開荒 Build 評級 {tier} 級。"]
        if TIER_HINT.get(tier):
            summary_bits.append(TIER_HINT[tier] + "。")
        if details.get("summary"):
            summary_bits.append(details["summary"])
        else:
            summary_bits.append(f"點「開啟 Guide」可看 {entry['name']} 的完整 Maxroll 攻略與配點。")

        guide_slug = urlparse(entry["guide_url"]).path.rstrip("/").rsplit("/", 1)[-1]
        builds.append(
            {
                "id": f"poe2-{guide_slug}",
                "name": entry["name"],
                "name_zh": f"{entry['name']}（{asc_zh}）" if asc_zh and asc_zh != entry["name"] else entry["name"],
                "ascendancy": asc_en,
                "ascendancy_zh": asc_zh,
                "skill": skill,
                "skill_zh": skill,
                "styles": [style],
                "damage": [],
                "playstyles": [],
                "budget": "league_start",
                "difficulty": TIER_DIFFICULTY.get(tier, "medium"),
                "goals": ["開荒推圖"],
                "modes": ["trade", "ssf"],
                "tier": tier,
                "score_bias": round(-0.1 * position, 2),
                "pros": details.get("pros") or [],
                "cons": details.get("cons") or [],
                "summary": " ".join(summary_bits),
                "leveling": (
                    "開荒建議：依 Maxroll Guide 的 Campaign / Leveling 章節推進；"
                    "成型前先求穩定清圖與容錯，再補傷害。"
                ),
                "guide_url": entry["guide_url"],
                "pob_url": details.get("planner_url") or "",
                "tags": [tier, style, asc_en, skill, entry["name"], "Maxroll Build"],
            }
        )
        if delay:
            time.sleep(delay)

    patch = meta.get("patch") or ""
    league = meta.get("league") or ""
    league_label = f"{league} {patch}".strip() or "Path of Exile 2"
    notes_bits = [
        "資料來源：Maxroll 開荒 Build tier list",
        f"總表 {MAXROLL_HUB_URL}",
    ]
    if league_label:
        notes_bits.append(league_label)
    if meta.get("updated"):
        notes_bits.append(f"Maxroll 更新 {meta['updated']}")

    catalog = {
        "game": "poe2",
        "league": league_label,
        "league_zh": f"流亡黯道 2 · {league_label}",
        "updated": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d"),
        "source": MAXROLL_BUILD_TIERLIST_URL,
        "notes": "　·　".join(notes_bits),
        "intro": meta.get("intro", ""),
        "styles": classes,
        "damage_types": [],
        "playstyles": [],
        "goals": ["開荒推圖"],
        "budgets": [{"id": "league_start", "label": "開荒零成本"}],
        "difficulties": [
            {"id": "easy", "label": "簡單"},
            {"id": "medium", "label": "中等"},
            {"id": "hard", "label": "進階"},
        ],
        "builds": builds,
        "related": {
            "ascendancy_tierlist": MAXROLL_ASC_TIERLIST_URL,
            "hub": MAXROLL_HUB_URL,
        },
    }
    report(total, total, f"完成，共 {len(builds)} 套開荒 Build")
    return catalog


def sync_league_starters_poe2(progress: ProgressCb | None = None, delay: float = 0.2) -> dict:
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
    print(f"寫入 {DATA_DIR / STARTERS_FILE_POE2}：{len(result['builds'])} 套 Build")
