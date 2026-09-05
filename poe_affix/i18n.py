"""Traditional Chinese item names for economy lookup.

Sources:
- PoeCharm zh-rTW item maps
- POE Ninja 中文化 extension index (yuh926323/poe-ninja-translator, from poedb.tw)
- poedb.tw item pages for leftovers
- poe2db.tw item pages for PoE2 (`names_zh_poe2.json`, see i18n_sync.py)
"""

from __future__ import annotations

import json
import re
from functools import lru_cache

from . import resolve_named_data

PREFIXES = (
    ("Replica ", "贗品．"),
    ("Foulborn ", "穢生．"),
    ("Tainted ", "汙染"),
)

# poe.ninja map overview names are often aggregated, not base-type keys.
_MAP_TIER_RE = re.compile(r"^(?:(.*) )?Map \(Tier (\d+)\)$")
_VAAL_TEMPLE_RE = re.compile(r"^(.*) Vaal Temple Map$")
_TEMPLE_ROOM_TIER_RE = re.compile(r"^(.*) \(Tier (\d+)\)$")
# poe.ninja tags PoE2 gems / flux with a level, e.g. "Uncut Skill Gem (Level 12)".
LEVEL_SUFFIX_RE = re.compile(r"^(.*?)\s*\(Level (\d+)\)$")

MAP_NAME_PARTS: dict[str, str] = {
    "Al-Hezmin": "奧赫茲明",
    "Baran": "巴倫",
    "Drox": "圖拉克斯",
    "Veritania": "維羅提尼亞",
    "The Purifier": "淨化者",
    "The Eradicator": "根除者",
    "The Enslaver": "奴役者",
    "The Constrictor": "束縛者",
    "Nightmare": "夢魘",
    "Shaper Guardian": "塑界者守護者",
}

# Names missing from the PoeCharm dump (newer currency, catalysts, etc.).
EXTRA_NAMES: dict[str, str] = {
    "Accelerating Catalyst": "加速催化劑",
    "Abrasive Catalyst": "研磨的催化劑",
    "Ancient Orb": "古變石",
    "Armourer's Scrap": "護甲片",
    "Awakener's Orb": "覺醒者寶珠",
    "Blacksmith's Whetstone": "磨刀石",
    "Crusader's Exalted Orb": "聖戰軍王崇高石",
    "Crystallised Rancour": "結晶怨恨",
    "Dead Man's Sulphur": "亡者硫酸",
    "Elder's Exalted Orb": "尊師崇高石",
    "Eldritch Chaos Orb": "異能混沌石",
    "Eldritch Exalted Orb": "異能崇高石",
    "Eldritch Orb of Annulment": "異能無效石",
    "Exceptional Eldritch Ember": "卓越異能餘燼",
    "Exceptional Eldritch Ichor": "卓越異能膿血",
    "Fertile Catalyst": "富饒的催化劑",
    "Flesh of Xesht": "謝什特之肉",
    "Fracturing Orb": "破裂石",
    "Fracturing Shard": "破裂石碎片",
    "Glassblower's Bauble": "玻璃彈珠",
    "Grand Eldritch Ember": "宏偉異能餘燼",
    "Grand Eldritch Ichor": "宏偉異能膿血",
    "Greater Eldritch Ember": "較大異能餘燼",
    "Greater Eldritch Ichor": "較大異能膿血",
    "Hinekora's Lock": "悉妮蔻拉之鎖",
    "Hunter's Exalted Orb": "狩獵者崇高石",
    "Imbued Catalyst": "充能的催化劑",
    "Intrinsic Catalyst": "本質的催化劑",
    "Lesser Eldritch Ember": "較小異能餘燼",
    "Lesser Eldritch Ichor": "較小異能膿血",
    "Maven's Chisel of Avarice": "釋界者的貪婪鑿子",
    "Maven's Chisel of Divination": "釋界者的命運鑿子",
    "Maven's Chisel of Procurement": "釋界者的獲取鑿子",
    "Maven's Chisel of Proliferation": "釋界者的增殖鑿子",
    "Maven's Chisel of Scarabs": "釋界者的聖甲蟲鑿子",
    "Mirror of Kalandra": "卡蘭德的魔鏡",
    "Mirror Shard": "卡蘭德的魔鏡碎片",
    "Noxious Catalyst": "毒性催化劑",
    "Orb of Annulment": "無效石",
    "Orb of Augmentation": "增幅石",
    "Orb of Binding": "束縛石",
    "Orb of Conflict": "衝突寶珠",
    "Orb of Dominance": "支配寶珠",
    "Orb of Intention": "意圖寶珠",
    "Orb of Remembrance": "追憶寶珠",
    "Orb of Transmutation": "蛻變石",
    "Orb of Unmaking": "還原石",
    "Orb of Unravelling": "解析寶珠",
    "Portal Scroll": "傳送卷軸",
    "Primal Crystallised Lifeforce": "原始結晶生靈之力",
    "Prismatic Catalyst": "多稜的催化劑",
    "Redeemer's Exalted Orb": "救贖者崇高石",
    "Reflecting Mist": "倒映迷霧",
    "Rogue's Marker": "盜賊標記",
    "Sacred Crystallised Lifeforce": "神聖結晶生靈之力",
    "Sacred Orb": "神聖寶珠",
    "Scroll of Wisdom": "知識卷軸",
    "Shaper's Exalted Orb": "塑者崇高石",
    "Stacked Deck": "未知的命運",
    "Tailoring Orb": "裁縫石",
    "Tainted Armourer's Scrap": "汙染的護甲片",
    "Tainted Blacksmith's Whetstone": "汙染的磨刀石",
    "Tainted Catalyst": "汙染催化劑",
    "Tainted Chaos Orb": "汙染混沌石",
    "Tainted Chromatic Orb": "汙染幻色石",
    "Tainted Divine Teardrop": "汙染神聖淚滴",
    "Tainted Exalted Orb": "汙染崇高石",
    "Tainted Jeweller's Orb": "汙染工匠石",
    "Tainted Mythic Orb": "汙染神話石",
    "Tainted Orb of Fusing": "汙染鏈結石",
    "Tempering Catalyst": "冶鍊的催化劑",
    "Tempering Orb": "淬鍊石",
    "Turbulent Catalyst": "洶湧的催化劑",
    "Unstable Catalyst": "易變催化劑",
    "Veiled Chaos Orb": "隱匿混沌石",
    "Veiled Exalted Orb": "隱匿崇高石",
    "Vivid Crystallised Lifeforce": "鮮明結晶生靈之力",
    "Volatile Vaal Orb": "不穩定瓦爾寶珠",
    "Warlord's Exalted Orb": "總督軍崇高石",
    "Wild Crystallised Lifeforce": "野性結晶生靈之力",
    # Keepers / Allflame — Wombgifts (胎贈)
    "Ancient Wombgift": "古老之胎贈",
    "Lavish Wombgift": "奢華之胎贈",
    "Mysterious Wombgift": "神秘之胎贈",
    "Provisioning Wombgift": "供應之胎贈",
    # Settlers — Runegrafts (符文之結)
    "Runegraft of Bellows": "轟鳴符文之結",
    "Runegraft of Blasphemy": "瀆神符文之結",
    "Runegraft of Connection": "聯繫符文之結",
    "Runegraft of Consecration": "奉獻符文之結",
    "Runegraft of Fury": "憤怒符文之結",
    "Runegraft of Gemcraft": "寶石工藝符文之結",
    "Runegraft of Loyalty": "忠誠符文之結",
    "Runegraft of Quaffing": "狂飲符文之結",
    "Runegraft of Rallying": "召集符文之結",
    "Runegraft of Refraction": "折射符文之結",
    "Runegraft of Restitching": "重新縫合符文之結",
    "Runegraft of Resurgence": "復甦符文之結",
    "Runegraft of Rotblood": "腐血符文之結",
    "Runegraft of Stability": "穩定符文之結",
    "Runegraft of Suffering": "折磨符文之結",
    "Runegraft of Time": "時間符文之結",
    "Runegraft of Treachery": "背信符文之結",
    "Runegraft of the Agile": "迅敏符文之結",
    "Runegraft of the Angler": "長竿符文之結",
    "Runegraft of the Bound": "緊密符文之結",
    "Runegraft of the Combatant": "戰鬥者符文之結",
    "Runegraft of the Fortress": "堡壘符文之結",
    "Runegraft of the Gauche": "笨拙符文之結",
    "Runegraft of the Imbued": "灌注符文之結",
    "Runegraft of the Jeweller": "工匠符文之結",
    "Runegraft of the Novamark": "星印符文之結",
    "Runegraft of the River": "河川符文之結",
    "Runegraft of the Sinistral": "左旋符文之結",
    "Runegraft of the Soulwick": "魂芯符文之結",
    "Runegraft of the Spellbound": "魔縛符文之結",
    "Runegraft of the Warp": "扭曲符文之結",
    "Runegraft of the Witchmark": "巫印符文之結",
    # Aggregated map labels from poe.ninja
    "Nightmare Map": "夢魘地圖",
    "Shaper Guardian Map": "塑界者守護者地圖",
    # Allflame Embers (不滅之火餘燼)
    "Allflame Ember of Flesh": "不滅之火血肉餘燼",
    "Allflame Ember of Kulemak": "不滅之火骷髏馬克餘燼",
    "Allflame Ember of Propagation": "不滅之火傳播餘燼",
    "Allflame Ember of Resplendence": "不滅之火輝煌餘燼",
    "Allflame Ember of Toads": "不滅之火蟾蜍餘燼",
    "Allflame Ember of the Ethereal": "不滅之火虛靈餘燼",
    "Allflame Ember of the Gilded": "不滅之火鍍金餘燼",
    "Allflame Ember of the Wildwood": "不滅之火荒林餘燼",
    # Curse of the Allflame — Ducats (達克特)
    "Brinehook's Ducat": "布琳霍克的達克特",
    "Katakohi's Ducat": "卡塔科希的達克特",
    "Kishara's Ducat": "奇夏拉的達克特",
    "Merrick's Ducat": "莫里克的達克特",
    "Rotmother's Ducat": "腐母的達克特",
    "The Changeling's Ducat": "變形靈的達克特",
    "Tzamoto's Ducat": "薩摩特的達克特",
    "Ukatoa's Ducat": "烏卡托瓦的達克特",
    "Cyaxan's Ducat": "塞亞珊的達克特",
    "Telesia's Ducat": "特雷西亞的達克特",
    "The Genteel's Ducat": "文雅者的達克特",
    # Legion — Enshrouding Crystals (壟罩晶石)
    "Imperial Enshrouding Crystal": "永恆壟罩晶石",
    "Karui Enshrouding Crystal": "卡魯壟罩晶石",
    "Vaal Enshrouding Crystal": "瓦爾壟罩晶石",
    "Maraketh Enshrouding Crystal": "馬拉克斯壟罩晶石",
    "Templar Enshrouding Crystal": "聖宗壟罩晶石",
    # Atlas — Astrolabes (星盤)
    "Deceptive Astrolabe": "幻象星盤",
    "Fruiting Astrolabe": "碩果星盤",
    "Grasping Astrolabe": "執掌星盤",
    "Lightless Astrolabe": "無光星盤",
    "Chaotic Astrolabe": "混沌星盤",
    "Timeless Astrolabe": "永恆星盤",
    "Fungal Astrolabe": "菌群星盤",
    "Nameless Astrolabe": "無名星盤",
    "Runic Astrolabe": "符文星盤",
    "Templar Astrolabe": "聖堂星盤",
    "Enshrouded Astrolabe": "壟罩星盤",
    # Incursion — Temple of Atzoatl rooms (阿茲瓦特神殿)
    # Room names that collide with maps use Alva/poedb room titles, not map titles.
    "Anomaly Research Lab": "異常研究所",
    "Antechamber": "神殿前院",
    "Apex of Ascension": "祭祀之巔",
    "Apex of Atzoatl": "阿茲瓦特之巔",
    "Arena of Valour": "傳說對決",
    "Armourer's Workshop": "裝甲磨坊",
    "Armoury": "軍械庫",
    "Atlas of Worlds": "異界輿圖",
    "Automaton Lab": "自運研究所",
    "Banquet Hall": "神殿宴會場",
    "Barracks": "軍隊憩所",
    "Breach Containment Chamber": "裂痕異域室",
    "Catalyst of Corruption": "腐敗孳生室",
    "Cellar": "神殿地窖",
    "Chamber of Iron": "鋼鍛之室",
    "Chasm": "神殿裂口",
    "Cloister": "神殿廟",
    "Conduit of Lightning": "雷霆導管",
    "Corruption Chamber": "腐敗之室",
    "Court of Sealed Death": "封亡院庭",
    "Crucible of Flame": "烈焰熔爐",
    "Cultivar Chamber": "培育秘室",
    "Defense Research Lab": "禦防研究所",
    "Demolition Lab": "拆除庫",
    "Department of Thaumaturgy": "魔法部",
    "Doryani's Institute": "多里亞尼之院",
    "Engineering Department": "工程部",
    "Explosives Room": "彈藥庫",
    "Factory": "瓦爾工廠",
    "Flame Workshop": "獄炎磨坊",
    "Gemcutter's Workshop": "刻石磨坊",
    "Glittering Halls": "閃耀聖殿",
    "Guardhouse": "衛兵房",
    "Hall of Champions": "冠軍聖殿",
    "Hall of Heroes": "英雄之殿",
    "Hall of Legends": "神話之殿",
    "Hall of Locks": "千鎖殿堂",
    "Hall of Lords": "權貴殿堂",
    "Hall of Mettle": "勇氣之殿",
    "Hall of Offerings": "獻祭殿堂",
    "Hall of War": "戰爭聖殿",
    "Halls": "神殿殿堂",
    "Hatchery": "孵化室",
    "House of the Others": "異者居所",
    "Hurricane Engine": "颶風引擎室",
    "Hybridisation Chamber": "異種之域",
    "Jeweller's Workshop": "寶匠磨坊",
    "Jewellery Forge": "珠寶冶煉室",
    "Lightning Workshop": "風雷磨坊",
    "Locus of Corruption": "腐敗之地",
    "Museum of Artefacts": "文物展館",
    "Office of Cartography": "製圖研製室",
    "Omnitect Forge": "全能冶煉室",
    "Omnitect Reactor Plant": "全能反應廠",
    "Passageways": "神殿通道",
    "Pits": "神殿舊窖",
    "Poison Garden": "監獄花園",
    "Pools of Restoration": "治癒之泉",
    "Royal Meeting Room": "王室宴客室",
    "Sacrificial Chamber": "獻祭之室",
    "Sadist's Den": "虐狂之巢",
    "Sanctum of Immortality": "不朽聖殿",
    "Sanctum of Unity": "統領聖殿",
    "Sanctum of Vitality": "活力聖殿",
    "Shrine of Empowerment": "恩賜神殿",
    "Shrine of Unmaking": "毀滅神殿",
    "Sparring Room": "格鬥場",
    "Storage Room": "儲物室",
    "Storm of Corruption": "腐敗風暴",
    "Strongbox Chamber": "寶箱之殿",
    "Surveyor's Study": "研究書房",
    "Tempest Generator": "暴雷發電室",
    "Temple Defense Workshop": "神殿禦防室",
    "Temple Nexus": "死神靈殿",
    "Throne of Atziri": "阿茲里宴殿",
    "Tombs": "神殿陵寢",
    "Torment Cells": "磨難牢房",
    "Torture Cages": "拷刑大牢",
    "Toxic Grove": "劇毒果園",
    "Trap Workshop": "陷阱磨坊",
    "Treasury": "祕寶庫",
    "Tunnels": "神殿地道",
    "Vault": "藏寶庫",
    "Warehouses": "倉庫間",
    "Wealth of the Vaal": "瓦爾聚寶庫",
    "Workshop": "工作坊",
}

# Extra nicknames that are not the official client name.
NICKNAMES: dict[str, tuple[str, ...]] = {
    "Headhunter": ("富豪的頭顱", "頭顱"),
    "Mageblood": ("法師之血",),
    "Watcher's Eye": ("守望者之眼",),
    "Chromatic Orb": ("色變石", "色彩石", "幻色石"),
    "Jeweller's Orb": ("孔石",),
    "Orb of Fusing": ("連結石", "六連"),
    "Chaos Orb": ("混沌",),
    "Divine Orb": ("神聖",),
    "Exalted Orb": ("崇高",),
    # Informal spellings for newer league currencies.
    "Brinehook's Ducat": ("杜卡特",),
    "Katakohi's Ducat": ("杜卡特",),
    "Kishara's Ducat": ("杜卡特",),
    "Merrick's Ducat": ("杜卡特",),
    "Rotmother's Ducat": ("杜卡特",),
    "The Changeling's Ducat": ("杜卡特",),
    "Tzamoto's Ducat": ("杜卡特",),
    "Ukatoa's Ducat": ("杜卡特",),
    "Cyaxan's Ducat": ("杜卡特",),
    "Telesia's Ducat": ("杜卡特",),
    "The Genteel's Ducat": ("杜卡特",),
    "Imperial Enshrouding Crystal": ("壟罩結晶", "籠罩結晶"),
    "Karui Enshrouding Crystal": ("壟罩結晶", "籠罩結晶"),
    "Vaal Enshrouding Crystal": ("壟罩結晶", "籠罩結晶"),
    "Maraketh Enshrouding Crystal": ("壟罩結晶", "籠罩結晶"),
    "Templar Enshrouding Crystal": ("壟罩結晶", "籠罩結晶"),
}


@lru_cache(maxsize=1)
def name_map() -> dict[str, str]:
    mapping = dict(EXTRA_NAMES)
    path = resolve_named_data("names_zh.json")
    if path:
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, value in data.items():
            if key and value and str(key) not in mapping:
                mapping[str(key)] = str(value)
    mapping.update(EXTRA_NAMES)
    return mapping


# PoE2 items that poe2db.tw does not yet have a 繁中 page for (league-specific,
# or the slug leads to a stats page instead of an item page).  Update when
# poe2db catches up, then run ``py -3 -m poe_affix.i18n_sync`` to move them
# into the auto-generated ``names_zh_poe2.json``.
EXTRA_NAMES_POE2: dict[str, str] = {
    "Perfect Jeweller's Orb": "完美寶匠石",
    "Aldur's Legacy": "阿德爾的遺贈",
    "Betrayal of Aldur": "阿德爾的背叛",
    "Breath of Aldur": "阿德爾的吐息",
    "Ire of Aldur": "阿德爾的憤怒",
    "Passion of Aldur": "阿德爾的熱情",
    "Aldur's Saga": "阿德爾的傳說",
    "Thaumaturgic Flux": "魔能熔劑",
    "Azmeri Reliquary Key": "愛茲麥里的寶庫鑰匙",
    "Ancient Rune of Control": "遠古控制符文",
    "Citaqualotl's Thesis": "希特克拉多的論點",
}


@lru_cache(maxsize=1)
def name_map_poe2() -> dict[str, str]:
    """PoE2-only names harvested from poe2db (see i18n_sync.py)."""
    path = resolve_named_data("names_zh_poe2.json")
    if not path:
        return dict(EXTRA_NAMES_POE2)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(EXTRA_NAMES_POE2)
    if not isinstance(data, dict):
        return dict(EXTRA_NAMES_POE2)
    merged = dict(EXTRA_NAMES_POE2)
    # File entries take priority over the hardcoded fallbacks.
    merged.update({str(key): str(value) for key, value in data.items() if key and value})
    return merged


def _translate_temple_room(english: str, mapping: dict[str, str]) -> str:
    """Translate Atzoatl room names, including poe.ninja ``(Tier N)`` suffixes."""
    tier_match = _TEMPLE_ROOM_TIER_RE.match(english)
    if tier_match:
        base, tier = tier_match.group(1), tier_match.group(2)
        base_zh = mapping.get(base) or ""
        if base_zh:
            return f"{base_zh}（階級 {tier}）"
        return ""
    return ""


def _translate_map_label(english: str, mapping: dict[str, str]) -> str:
    """Handle poe.ninja aggregated map names that are not plain base types."""
    tier_match = _MAP_TIER_RE.match(english)
    if tier_match:
        prefix, tier = tier_match.group(1) or "", tier_match.group(2)
        if not prefix:
            return f"地圖（階級 {tier}）"
        prefix_zh = mapping.get(prefix) or MAP_NAME_PARTS.get(prefix) or ""
        if prefix_zh:
            return f"{prefix_zh}地圖（階級 {tier}）"
        return ""

    temple_match = _VAAL_TEMPLE_RE.match(english)
    if temple_match:
        prefix = temple_match.group(1)
        prefix_zh = mapping.get(prefix) or MAP_NAME_PARTS.get(prefix) or ""
        temple_zh = mapping.get("Vaal Temple Map") or "瓦爾密殿"
        if prefix_zh:
            return f"{prefix_zh}{temple_zh}"
        return ""

    if english.endswith(" Map"):
        # Full keys like ``Beach Map`` are already resolved by name_map().
        # Only synthesize from MAP_NAME_PARTS / non-room prefixes here.
        prefix = english[: -len(" Map")]
        part = MAP_NAME_PARTS.get(prefix) or ""
        if part:
            return f"{part}地圖"
        # Prefer the dedicated Map entry; do not reuse temple-room short names.
        map_entry = mapping.get(english)
        if map_entry:
            return map_entry
    return ""


def translate_name(english: str, game: str = "poe1") -> str:
    if not english:
        return ""
    if game == "poe2":
        hit = name_map_poe2().get(english)
        if hit:
            return hit
    mapping = name_map()
    hit = mapping.get(english)
    if hit:
        return hit
    for prefix_en, prefix_zh in PREFIXES:
        if english.startswith(prefix_en):
            rest = translate_name(english[len(prefix_en) :], game)
            if rest:
                return prefix_zh + rest
    if english.startswith("Deafening Essence of "):
        stat = english.removeprefix("Deafening Essence of ")
        if stat in {"Horror", "Delirium", "Hysteria", "Insanity"}:
            return translate_name(f"Essence of {stat}", game)
    level_match = LEVEL_SUFFIX_RE.match(english)
    if level_match:
        base_zh = translate_name(level_match.group(1), game)
        if base_zh:
            return f"{base_zh}（等級 {level_match.group(2)}）"
    map_zh = _translate_map_label(english, mapping)
    if map_zh:
        return map_zh
    temple_zh = _translate_temple_room(english, mapping)
    if temple_zh:
        return temple_zh
    return ""


def search_terms(english: str, chinese: str) -> tuple[str, ...]:
    terms = [english, chinese, *NICKNAMES.get(english, ())]
    return tuple(term for term in terms if term)
