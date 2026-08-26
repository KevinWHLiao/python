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


# Longer / more specific family tokens first.
_FAMILY_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("LifeLeech", "偷取"),
    ("ManaLeech", "偷取"),
    ("EnergyShield", "能量護盾"),
    ("MaximumLife", "生命"),
    ("IncreasedLife", "生命"),
    ("PercentLife", "生命"),
    ("HybridLife", "生命"),
    ("JewelLife", "生命"),
    ("LifeRegen", "生命"),
    ("LifeOnHit", "生命"),
    ("LifeOnKill", "生命"),
    ("FlaskLife", "生命"),
    ("MaximumMana", "魔力"),
    ("IncreasedMana", "魔力"),
    ("ManaRegen", "魔力"),
    ("FlaskMana", "魔力"),
    ("FireResistance", "抗性"),
    ("ColdResistance", "抗性"),
    ("LightningResistance", "抗性"),
    ("ChaosResistance", "抗性"),
    ("AllResistance", "抗性"),
    ("AllResistances", "抗性"),
    ("AttackSpeed", "速度"),
    ("CastSpeed", "速度"),
    ("MovementSpeed", "速度"),
    ("ProjectileSpeed", "速度"),
    ("Attack", "攻擊"),
    ("Accuracy", "攻擊"),
    ("Critical", "暴擊"),
    ("Crits", "暴擊"),
    ("Crit", "暴擊"),
    ("AddedFire", "火焰"),
    ("FireDamage", "火焰"),
    ("AddedCold", "冰冷"),
    ("ColdDamage", "冰冷"),
    ("AddedLightning", "閃電"),
    ("LightningDamage", "閃電"),
    ("AddedChaos", "混沌"),
    ("ChaosDamage", "混沌"),
    ("PhysicalDamage", "物理"),
    ("AddedPhysical", "物理"),
    ("Armour", "護甲"),
    ("Armor", "護甲"),
    ("Evasion", "閃避"),
    ("Block", "格擋"),
    ("Spell", "法術"),
    ("Minion", "召喚物"),
    ("Totem", "圖騰"),
    ("Trap", "陷阱"),
    ("Mine", "地雷"),
    ("Curse", "詛咒"),
    ("Flask", "藥劑"),
    ("Gem", "寶石"),
    ("Socketed", "寶石"),
    ("Attribute", "能力"),
    ("Strength", "能力"),
    ("Dexterity", "能力"),
    ("Intelligence", "能力"),
    ("Ailment", "異常狀態"),
    ("Bleed", "異常狀態"),
    ("Poison", "異常狀態"),
    ("Ignite", "異常狀態"),
    ("Freeze", "異常狀態"),
    ("Chill", "異常狀態"),
    ("Shock", "異常狀態"),
    ("Projectile", "投射物"),
    ("Arrow", "投射物"),
    ("Area", "範圍"),
    ("Duration", "持續"),
    ("Charge", "球"),
    ("Leech", "偷取"),
    ("Life", "生命"),
    ("Mana", "魔力"),
    ("Fire", "火焰"),
    ("Cold", "冰冷"),
    ("Lightning", "閃電"),
    ("Chaos", "混沌"),
    ("Physical", "物理"),
    ("Elemental", "元素"),
    ("Speed", "速度"),
    ("Damage", "傷害"),
)

_LABEL_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("最大生命", "生命"),
    ("生命偷取", "偷取"),
    ("生命恢復", "生命"),
    ("生命回復", "生命"),
    ("最大魔力", "魔力"),
    ("魔力恢復", "魔力"),
    ("魔力回復", "魔力"),
    ("能量護盾", "能量護盾"),
    ("火焰抗性", "抗性"),
    ("冰冷抗性", "抗性"),
    ("閃電抗性", "抗性"),
    ("混沌抗性", "抗性"),
    ("全部元素抗性", "抗性"),
    ("所有元素抗性", "抗性"),
    ("物理傷害", "物理"),
    ("火焰傷害", "火焰"),
    ("冰冷傷害", "冰冷"),
    ("閃電傷害", "閃電"),
    ("混沌傷害", "混沌"),
    ("元素傷害", "元素"),
    ("攻擊速度", "速度"),
    ("攻擊", "攻擊"),
    ("施放速度", "速度"),
    ("移動速度", "速度"),
    ("暴擊", "暴擊"),
    ("命中", "攻擊"),
    ("護甲", "護甲"),
    ("閃避", "閃避"),
    ("格擋", "格擋"),
    ("力量", "能力"),
    ("敏捷", "能力"),
    ("智慧", "能力"),
    ("藥劑", "藥劑"),
    ("寶石", "寶石"),
    ("召喚物", "召喚物"),
    ("圖騰", "圖騰"),
    ("詛咒", "詛咒"),
)


_CAMEL_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")
_SHORT_FAMILY_PARTS = {
    "life",
    "mana",
    "fire",
    "cold",
    "lightning",
    "chaos",
    "physical",
    "speed",
    "damage",
    "attack",
    "arrow",
    "projectile",
    "shock",
    "chill",
    "bleed",
    "spell",
    "gem",
    "area",
    "mine",
    "trap",
    "curse",
    "flask",
    "block",
    "leech",
    "crit",
}

# Exact ModFamilyList keys → official-style tags (legacy helper / offline fallback).
_FAMILY_TAG_OVERRIDES: dict[str, tuple[str, ...]] = {
    "AdditionalArrows": ("攻擊",),
    "ProjectileSpeed": ("速度",),
    "AdditionalProjectiles": ("投射物",),
    "Pierce": ("投射物",),
    "ProjectileDamagePerEnemyPierced": ("投射物", "傷害"),
    "IncreaseProjectileAttackDamagePerAccuracy": ("投射物", "攻擊", "傷害"),
    "DisplaySocketedSkillsFork": ("投射物", "寶石"),
    "SingleProjAOE": ("投射物", "攻擊", "範圍"),
    "SupportedByProjectileSpeed": ("寶石", "速度"),
    "SupportedByMultipleProjectiles": ("寶石", "投射物"),
}

# Match PoEDB crafting-badge order when filling heuristic tags.
_TAG_ORDER = (
    "生命",
    "魔力",
    "防禦",
    "能量護盾",
    "護甲",
    "閃避",
    "傷害",
    "元素",
    "火焰",
    "冰冷",
    "閃電",
    "混沌",
    "物理",
    "攻擊",
    "法術",
    "速度",
    "暴擊",
    "異常狀態",
    "抗性",
    "偷取",
    "能力",
    "寶石",
    "召喚物",
    "詛咒",
    "藥劑",
    "範圍",
    "投射物",
    "持續",
    "球",
    "圖騰",
    "陷阱",
    "地雷",
    "格擋",
    "其他",
)


def extract_mod_tags(entry: dict[str, Any]) -> list[str]:
    """Read official PoEDB crafting badges from ModsView ``mod_no`` only.

    Empty ``mod_no`` means PoEDB shows no crafting tag for that mod. Do not
    invent badges from ``fossil_no`` / family heuristics — those are not the
    same as the on-page crafting badges.
    """
    tags: list[str] = []
    seen: set[str] = set()
    for raw in entry.get("mod_no") or []:
        text = strip_html(str(raw))
        if text and text not in seen:
            seen.add(text)
            tags.append(text)
    return tags


def _family_parts(family: str) -> set[str]:
    return {part.casefold() for part in _CAMEL_RE.findall(family or "")}


def _family_token_hits(family: str, token: str) -> bool:
    lowered = (family or "").casefold()
    needle = token.casefold()
    if needle in _SHORT_FAMILY_PARTS:
        return needle in _family_parts(family)
    return needle in lowered


def _sorted_tags(tags: list[str]) -> list[str]:
    rank = {name: index for index, name in enumerate(_TAG_ORDER)}
    unique: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if tag and tag not in seen:
            seen.add(tag)
            unique.append(tag)
    unique.sort(key=lambda name: (rank.get(name, len(_TAG_ORDER)), name))
    return unique


def affix_categories(family: str, label: str = "") -> list[str]:
    """Heuristic tags used when a catalog row has no official PoEDB badges."""
    family_text = family or ""
    if "|" not in family_text:
        override = _FAMILY_TAG_OVERRIDES.get(family_text)
        if override:
            return _sorted_tags(list(override))

    found: list[str] = []
    seen: set[str] = set()
    for token, category in _FAMILY_CATEGORIES:
        if category in seen:
            continue
        if _family_token_hits(family_text, token):
            found.append(category)
            seen.add(category)
    label_text = label or ""
    for token, category in _LABEL_CATEGORIES:
        if category not in seen and token in label_text:
            found.append(category)
            seen.add(category)
    if any(name in seen for name in ("能量護盾", "護甲", "閃避")):
        if "防禦" not in seen:
            found.insert(0, "防禦")
            seen.add("防禦")
    if "傷害" in seen and any(name in seen for name in ("火焰", "冰冷", "閃電")) and "元素" not in seen:
        found.append("元素")
        seen.add("元素")
    return _sorted_tags(found) or ["其他"]


def affix_category(family: str, label: str = "") -> str:
    """Map a PoEDB mod family / label to the first Traditional Chinese group tag."""
    return affix_categories(family, label)[0]


def format_tag_text(tags: list[str]) -> str:
    parts = [tag for tag in tags if tag]
    return "  ".join(parts) if parts else "—"


def format_tag_text_marked(tags: list[str]) -> str:
    """Treeview-friendly multi-tag text with colored emoji markers."""
    from .theme import tag_marker

    parts: list[str] = []
    for tag in tags:
        if not tag:
            continue
        parts.append(f"{tag_marker(tag)}{tag}")
    return "  ".join(parts) if parts else "—"


def group_categories(group: dict[str, Any]) -> list[str]:
    """Return official PoEDB crafting tags only; empty when PoEDB has no badge."""
    tag_source = group.get("tag_source")
    cached = group.get("categories")
    if tag_source == "none":
        return []
    if isinstance(cached, list):
        return [str(tag) for tag in cached if tag]
    if tag_source == "poedb":
        return []
    # Legacy rows without tag_source: do not invent labels from family names.
    return []


def group_category(group: dict[str, Any]) -> str:
    tags = group_categories(group)
    return tags[0] if tags else ""


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


def _build_group(
    affix: str,
    family: str,
    label: str,
    unique_rows: list[dict[str, Any]],
    *,
    prefer_poedb_tags: bool = True,
) -> dict[str, Any]:
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
    poedb_tags: list[str] = []
    seen_tags: set[str] = set()
    for row in unique_rows:
        for tag in row.get("tags") or []:
            if tag not in seen_tags:
                seen_tags.add(tag)
                poedb_tags.append(tag)
    if poedb_tags:
        tags = poedb_tags
        tag_source = "poedb"
    elif prefer_poedb_tags:
        # Match historical parse_slot behavior: no inventing badges without PoEDB mod_no.
        tags = []
        tag_source = "none"
    else:
        heuristic = affix_categories(family, label)
        tags = [] if heuristic == ["其他"] else heuristic
        tag_source = "heuristic" if tags else "none"
    return {
        "family": family,
        "category": tags[0] if tags else "",
        "categories": tags,
        "tag_source": tag_source,
        "affix": affix,
        "source": unique_rows[0]["source"] if unique_rows else "",
        "source_key": unique_rows[0]["source_key"] if unique_rows else "",
        "label": label,
        "is_corrupt": bool(unique_rows[0].get("is_corrupt")) if unique_rows else False,
        "tier_count": len(tiers),
        "min_level": min((item["level"] for item in tiers), default=0),
        "max_level": max((item["level"] for item in tiers), default=0),
        "tiers": tiers,
    }


def parse_slot(slot_name: str, slug: str, payload: dict[str, Any]) -> dict[str, Any]:
    config = payload.get("config") or {}
    # Include generalized mod text so PoEDB families that share one ModFamilyList
    # (e.g. GlobalDamageTypeGemLevel) stay split by damage type like on poedb.tw.
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)

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
            family = _family_key(entry)
            pattern = generalize(text) or text
            grouped[(source_key, affix, family, pattern)].append(
                {
                    "name": strip_html(str(entry.get("Name") or "")),
                    "level": _as_int(entry.get("Level")),
                    "text": text,
                    "weight": _as_int(entry.get("DropChance"), 0),
                    "explicit_tier": _as_int(entry.get("Tier"), 0) or None,
                    "source": source_title,
                    "source_key": source_key,
                    "affix": affix,
                    "family": family,
                    "tags": extract_mod_tags(entry),
                    "is_corrupt": is_corrupt,
                }
            )

    groups: list[dict[str, Any]] = []
    for (_source_key, affix, family, pattern), rows in grouped.items():
        unique_rows: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for row in rows:
            stamp = (row["level"], row["name"], row["text"])
            if stamp in seen:
                continue
            seen.add(stamp)
            unique_rows.append(row)
        unique_rows.sort(key=lambda item: (-item["level"], item["name"]))
        label_source = next((item["text"] for item in unique_rows), "")
        label = pattern or generalize(label_source) or family or label_source
        groups.append(_build_group(affix, family, label, unique_rows))

    groups.sort(key=lambda item: (item["affix"], item["source"], item["label"]))
    return {
        "name": slot_name,
        "slug": slug,
        "url": f"https://poedb.tw/tw/{slug}#ModifiersCalc",
        "groups": groups,
    }


def _refine_split_tags(label: str, family: str, original_tags: list[str]) -> list[str]:
    """Pick tags for a group split out of a previously merged family."""
    heuristic = affix_categories(family, label)
    if heuristic == ["其他"]:
        heuristic = []
    if not original_tags:
        return heuristic
    kept = [tag for tag in original_tags if tag in label or tag in heuristic]
    # Elemental badge: fire/cold/lightning gem mods show 元素 on poedb.tw.
    if (
        "元素" in original_tags
        and "元素" not in kept
        and any(token in label for token in ("火焰", "火燄", "冰冷", "閃電"))
    ):
        kept.append("元素")
    return kept or heuristic or list(original_tags)


def rematerialize_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    """Re-split already-synced groups by generalized mod text (no network)."""
    slots_out: list[dict[str, Any]] = []
    for slot in catalog.get("slots") or []:
        if not isinstance(slot, dict):
            continue
        rebuilt: list[dict[str, Any]] = []
        for group in slot.get("groups") or []:
            if not isinstance(group, dict):
                continue
            tiers = group.get("tiers") or []
            buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for tier in tiers:
                if not isinstance(tier, dict):
                    continue
                text = str(tier.get("text") or "")
                if not text:
                    continue
                buckets[generalize(text) or text].append(tier)
            if len(buckets) <= 1:
                rebuilt.append(group)
                continue
            family = str(group.get("family") or "")
            affix = str(group.get("affix") or "")
            original_tags = [str(tag) for tag in (group.get("categories") or []) if tag]
            for pattern, bucket in buckets.items():
                bucket.sort(key=lambda item: (-_as_int(item.get("level")), str(item.get("name") or "")))
                rows = [
                    {
                        "level": _as_int(item.get("level")),
                        "name": str(item.get("name") or ""),
                        "text": str(item.get("text") or ""),
                        "weight": _as_int(item.get("weight")),
                        "source": str(group.get("source") or ""),
                        "source_key": str(group.get("source_key") or ""),
                        "is_corrupt": bool(group.get("is_corrupt")),
                        "tags": [],
                    }
                    for item in bucket
                ]
                built = _build_group(affix, family, pattern, rows, prefer_poedb_tags=False)
                built["categories"] = _refine_split_tags(pattern, family, original_tags)
                built["category"] = built["categories"][0] if built["categories"] else ""
                built["tag_source"] = "poedb" if built["categories"] and original_tags else built["tag_source"]
                rebuilt.append(built)
        rebuilt.sort(key=lambda item: (item.get("affix") or "", item.get("source") or "", item.get("label") or ""))
        slot_out = dict(slot)
        slot_out["groups"] = rebuilt
        slots_out.append(slot_out)
    result = dict(catalog)
    result["slots"] = slots_out
    result["group_count"] = sum(len(slot.get("groups") or []) for slot in slots_out)
    return result


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
