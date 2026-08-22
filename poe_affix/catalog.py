"""Parse PoEDB ModsView payloads and build a searchable affix catalog."""

from __future__ import annotations

import html as html_lib
import json
import re
from collections import defaultdict
from typing import Any, Iterable

GEN_NAMES = {"1": "前綴", "2": "後綴", "3": "固定", "5": "汙染"}
CORRUPT_SOURCE_KEYS = {"corrupted", "graft_corrupted", "corruption_upgrade"}

SOURCE_TITLES = {
    "normal": "基底",
    "shaper": "塑界者",
    "elder": "異界尊師",
    "crusader": "聖戰軍王",
    "redeemer": "救贖者",
    "hunter": "狩獵者",
    "warlord": "總督軍",
    "searing": "灼烙總督",
    "eater": "吞噬天地",
    "delve": "掘獄聯盟",
    "incursion": "時空穿越",
    "veiled": "隱匿",
    "master": "工藝台",
    "essence": "精髓",
    "perfect_essence": "完美精髓",
    "bestiary": "獸獵",
    "synthesis": "尋夢追憶",
    "synthesis_corrupted": "尋夢追憶已汙染",
    "corrupted": "已汙染",
    "enchant": "附魔",
    "infamous": "萬惡",
    "sentinel": "重組裝置",
    "desecrated": "褻瀆",
    "haunted": "糾纏",
    "scourgeup": "災魘有利",
    "scourgedown": "災魘有害",
    "warbands": "Warbands",
}

# Order shown in the GUI source filter.
SOURCE_ORDER = [
    "normal",
    "shaper",
    "elder",
    "crusader",
    "redeemer",
    "hunter",
    "warlord",
    "searing",
    "eater",
    "essence",
    "master",
    "veiled",
    "delve",
    "incursion",
    "bestiary",
    "synthesis",
    "corrupted",
    "infamous",
    "enchant",
]

_NUMBER_RE = re.compile(
    r"\(?\d+(?:\.\d+)?(?:\s*[—–\-]\s*\d+(?:\.\d+)?)?\)?%?"
)
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    text = text.replace('<span class="ndash">—</span>', "—")
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = _TAG_RE.sub("", text)
    text = html_lib.unescape(text)
    return _SPACE_RE.sub(" ", text).strip()


def generalize(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return "#%" if match.group(0).endswith("%") else "#"

    label = _NUMBER_RE.sub(repl, text)
    label = re.sub(r"\(\s*#\s*\)", "#", label)
    return _SPACE_RE.sub(" ", label).strip()


def extract_mods_view(page_html: str) -> dict[str, Any] | None:
    marker = "new ModsView("
    start = page_html.find(marker)
    if start < 0:
        return None
    start += len(marker)
    if start >= len(page_html) or page_html[start] != "{":
        return None
    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(page_html[start:], start):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(page_html[start : index + 1])
    return None


def iter_mod_entries(value: Any) -> Iterable[dict[str, Any]]:
    if value is None:
        return
    if isinstance(value, list):
        for item in value:
            yield from iter_mod_entries(item)
        return
    if isinstance(value, dict):
        if any(key in value for key in ("Level", "str", "Name", "ModGenerationTypeID")):
            yield value
            return
        for nested in value.values():
            yield from iter_mod_entries(nested)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _family_key(entry: dict[str, Any]) -> str:
    family = entry.get("ModFamilyList") or []
    if isinstance(family, str):
        return family
    return "|".join(str(part) for part in family if part)


def parse_slot(slot_name: str, slug: str, payload: dict[str, Any]) -> dict[str, Any]:
    config = payload.get("config") or {}
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)

    for source_key, raw in payload.items():
        if source_key in {"baseitem", "config", "gen", "opt"}:
            continue
        for entry in iter_mod_entries(raw):
            text = strip_html(str(entry.get("str") or ""))
            if not text:
                continue
            gen_id = str(entry.get("ModGenerationTypeID") or "")
            is_corrupt = source_key in CORRUPT_SOURCE_KEYS or gen_id == "5"
            affix = "汙染" if is_corrupt else GEN_NAMES.get(gen_id)
            if not affix:
                continue
            source_title = SOURCE_TITLES.get(source_key)
            if not source_title:
                raw_title = ""
                cfg = config.get(source_key)
                if isinstance(cfg, dict):
                    raw_title = strip_html(str(cfg.get("title") or ""))
                source_title = raw_title or source_key
            if is_corrupt:
                source_title = "已汙染"
            grouped[(source_key, affix, _family_key(entry))].append(
                {
                    "name": strip_html(str(entry.get("Name") or "")),
                    "level": _as_int(entry.get("Level")),
                    "text": text,
                    "weight": _as_int(entry.get("DropChance"), 0),
                    "explicit_tier": _as_int(entry.get("Tier"), 0) or None,
                    "source": source_title,
                    "source_key": source_key,
                    "affix": affix,
                    "family": _family_key(entry),
                    "is_corrupt": is_corrupt,
                }
            )

    groups: list[dict[str, Any]] = []
    for (_source_key, affix, family), rows in grouped.items():
        unique_rows: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for row in rows:
            stamp = (row["level"], row["name"], row["text"])
            if stamp in seen:
                continue
            seen.add(stamp)
            unique_rows.append(row)
        unique_rows.sort(key=lambda item: (-item["level"], item["name"]))
        tiers = [
            {
                "tier": index,
                "level": row["level"],
                "name": row["name"],
                "text": row["text"],
                "weight": row["weight"],
            }
            for index, row in enumerate(unique_rows, start=1)
        ]
        label_source = next((item["text"] for item in tiers), "")
        groups.append(
            {
                "family": family,
                "affix": affix,
                "source": unique_rows[0]["source"] if unique_rows else "",
                "source_key": unique_rows[0]["source_key"] if unique_rows else "",
                "label": generalize(label_source) or family or label_source,
                "is_corrupt": bool(unique_rows[0].get("is_corrupt")) if unique_rows else False,
                "tier_count": len(tiers),
                "min_level": min((item["level"] for item in tiers), default=0),
                "max_level": max((item["level"] for item in tiers), default=0),
                "tiers": tiers,
            }
        )

    groups.sort(key=lambda item: (item["affix"], item["source"], item["label"]))
    return {
        "name": slot_name,
        "slug": slug,
        "url": f"https://poedb.tw/tw/{slug}#ModifiersCalc",
        "groups": groups,
    }


def collect_index_links(index_html: str) -> list[tuple[str, str]]:
    """Return unique (display_name, slug) pairs for ModifiersCalc pages."""
    pattern = re.compile(
        r'href="(?:https://poedb\.tw)?(?:/tw/)?([^"#\s]+)#ModifiersCalc"[^>]*>(.*?)</a>',
        re.I | re.S,
    )
    seen: set[str] = set()
    links: list[tuple[str, str]] = []
    for match in pattern.finditer(index_html):
        slug = html_lib.unescape(match.group(1)).strip()
        name = strip_html(match.group(2))
        if not slug or not name or slug in seen:
            continue
        seen.add(slug)
        links.append((name, slug))
    return links


FALLBACK_SLOTS: list[tuple[str, str]] = [
    ("爪", "Claws"),
    ("匕首", "Daggers"),
    ("法杖", "Wands"),
    ("單手劍", "One_Hand_Swords"),
    ("單手斧", "One_Hand_Axes"),
    ("單手錘", "One_Hand_Maces"),
    ("權杖", "Sceptres"),
    ("符紋匕首", "Rune_Daggers"),
    ("細劍", "Thrusting_One_Hand_Swords"),
    ("弓", "Bows"),
    ("長杖", "Staves"),
    ("雙手劍", "Two_Hand_Swords"),
    ("雙手斧", "Two_Hand_Axes"),
    ("雙手錘", "Two_Hand_Maces"),
    ("征戰長杖", "Warstaves"),
    ("項鍊", "Amulets"),
    ("戒指", "Rings"),
    ("腰帶", "Belts"),
    ("飾品", "Trinkets"),
    ("手套(力)", "Gloves_str"),
    ("手套(敏)", "Gloves_dex"),
    ("手套(智)", "Gloves_int"),
    ("手套(力敏)", "Gloves_str_dex"),
    ("手套(力智)", "Gloves_str_int"),
    ("手套(敏智)", "Gloves_dex_int"),
    ("鞋子(力)", "Boots_str"),
    ("鞋子(敏)", "Boots_dex"),
    ("鞋子(智)", "Boots_int"),
    ("鞋子(力敏)", "Boots_str_dex"),
    ("鞋子(力智)", "Boots_str_int"),
    ("鞋子(敏智)", "Boots_dex_int"),
    ("胸甲(力)", "Body_Armours_str"),
    ("胸甲(敏)", "Body_Armours_dex"),
    ("胸甲(智)", "Body_Armours_int"),
    ("胸甲(力敏)", "Body_Armours_str_dex"),
    ("胸甲(力智)", "Body_Armours_str_int"),
    ("胸甲(敏智)", "Body_Armours_dex_int"),
    ("胸甲(力敏智)", "Body_Armours_str_dex_int"),
    ("頭部(力)", "Helmets_str"),
    ("頭部(敏)", "Helmets_dex"),
    ("頭部(智)", "Helmets_int"),
    ("頭部(力敏)", "Helmets_str_dex"),
    ("頭部(力智)", "Helmets_str_int"),
    ("頭部(敏智)", "Helmets_dex_int"),
    ("箭袋", "Quivers"),
    ("盾(力)", "Shields_str"),
    ("盾(敏)", "Shields_dex"),
    ("盾(智)", "Shields_int"),
    ("盾(力敏)", "Shields_str_dex"),
    ("盾(力智)", "Shields_str_int"),
    ("盾(敏智)", "Shields_dex_int"),
    ("赤紅珠寶", "Crimson_Jewel"),
    ("翠綠珠寶", "Viridian_Jewel"),
    ("鈷藍珠寶", "Cobalt_Jewel"),
    ("三相珠寶", "Prismatic_Jewel"),
    ("生命藥劑", "Life_Flasks"),
    ("魔力藥劑", "Mana_Flasks"),
    ("功能藥劑", "Utility_Flasks"),
]
