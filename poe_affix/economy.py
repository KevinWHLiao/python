"""poe.ninja economy price lookup (documented public API only)."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from .i18n import search_terms, translate_name

NINJA_BASE = "https://poe.ninja"
ECONOMY_PAGE = f"{NINJA_BASE}/poe1/economy/"
ECONOMY_PAGE_POE2 = f"{NINJA_BASE}/poe2/economy/"
CACHE_TTL = 15 * 60
MAX_WORKERS = 3
GAINER_WORKERS = 6
MIN_GAIN_PERCENT = 30
USER_AGENT = "PoELookupTool/1.0 (Windows desktop; personal local app)"

ALL = "全部"

# Exchange overview categories (currency-like trading).
EXCHANGE_TYPES: list[tuple[str, str, str]] = [
    ("Currency", "通貨", "currency"),
    ("Fragment", "碎片", "fragments"),
    ("DivinationCard", "命運卡", "divination-cards"),
    ("Oil", "聖油", "oils"),
    ("Essence", "精華", "essences"),
    ("Scarab", "聖甲蟲", "scarabs"),
    ("Fossil", "化石", "fossils"),
    ("Resonator", "共振器", "resonators"),
    ("DeliriumOrb", "譫妄玉", "delirium-orbs"),
    ("Omen", "預兆", "omens"),
    ("Tattoo", "紋身", "tattoos"),
    ("Artifact", "探險文物", "artifacts"),
    ("Runegraft", "符文之結", "runegrafts"),
    ("AllflameEmber", "不滅之火餘燼", "allflame-embers"),
    ("DjinnCoin", "巨靈幣", "djinn-coins"),
    ("Ducat", "達克特", "ducats"),
    ("EnshroudingCrystal", "壟罩晶石", "enshrouding-crystals"),
    ("Astrolabe", "星盤", "astrolabes"),
]

# Stash item overview categories.
ITEM_TYPES: list[tuple[str, str, str]] = [
    ("UniqueWeapon", "傳奇武器", "unique-weapons"),
    ("UniqueArmour", "傳奇護甲", "unique-armours"),
    ("UniqueAccessory", "傳奇飾品", "unique-accessories"),
    ("UniqueFlask", "傳奇藥劑", "unique-flasks"),
    ("UniqueJewel", "傳奇珠寶", "unique-jewels"),
    ("ForbiddenJewel", "禁忌珠寶", "forbidden-jewels"),
    ("ClusterJewel", "星團珠寶", "cluster-jewels"),
    ("UniqueTincture", "傳奇酊劑", "unique-tinctures"),
    ("UniqueRelic", "傳奇聖物", "unique-relics"),
    ("ShrineBelt", "神殿腰帶", "shrine-belts"),
    ("SkillGem", "技能寶石", "skill-gems"),
    ("ImbuedGem", "灌注寶石", "imbued-gems"),
    ("Map", "地圖", "maps"),
    ("UniqueMap", "傳奇地圖", "unique-maps"),
    ("BlightedMap", "凋落地圖", "blighted-maps"),
    ("BlightRavagedMap", "凋落蔓延地圖", "blight-ravaged-maps"),
    ("ValdoMap", "瓦爾多地圖", "valdo-maps"),
    ("Invitation", "邀請函", "invitations"),
    ("Memory", "記憶", "memories"),
    ("BaseType", "基底", "base-types"),
    ("Flask", "藥劑", "flasks"),
    ("Beast", "野獸", "beasts"),
    ("Incubator", "培育器", "incubators"),
    ("Vial", "瓶子", "vials"),
    ("Corpse", "屍體", "corpses"),
    ("Wombgift", "胎贈", "wombgifts"),
    ("IncursionTemple", "阿茲瓦特神殿", "incursion-temples"),
    ("ScryingOrb", "占卜寶珠", "scrying-orbs"),
]

# PoE2 exchange overview categories.
EXCHANGE_TYPES_POE2: list[tuple[str, str, str]] = [
    ("Currency", "通貨", "currency"),
    ("Fragments", "碎片", "fragments"),
    ("Essences", "精華", "essences"),
    ("Runes", "符文", "runes"),
    ("SoulCores", "魂核", "soul-cores"),
    ("Idols", "神像", "idols"),
    ("UncutGems", "未切割寶石", "uncut-gems"),
    ("Expedition", "探險文物", "expedition"),
    ("Abyss", "深淵之骨", "abyss"),
    ("LineageSupportGems", "族裔寶石", "lineage-support-gems"),
]

# PoE2 stash item overview categories (public stash tab prices).
ITEM_TYPES_POE2: list[tuple[str, str, str]] = [
    ("UniqueWeapons", "傳奇武器", "unique-weapons"),
    ("UniqueArmours", "傳奇護甲", "unique-armours"),
    ("UniqueAccessories", "傳奇飾品", "unique-accessories"),
    ("UniqueFlasks", "傳奇藥劑", "unique-flasks"),
    ("UniqueCharms", "傳奇護符", "unique-charms"),
    ("UniqueJewels", "傳奇珠寶", "unique-jewels"),
    ("UniqueSanctumRelics", "傳奇聖物", "unique-relics"),
    ("UniqueTablets", "傳奇石板", "unique-tablets"),
    ("PrecursorTablets", "先驅石板", "precursor-tablets"),
]

CATEGORIES = EXCHANGE_TYPES + ITEM_TYPES
CATEGORY_LABELS = [label for _key, label, _slug in CATEGORIES]
CATEGORIES_POE2 = EXCHANGE_TYPES_POE2 + ITEM_TYPES_POE2
CATEGORY_LABELS_POE2 = [label for _key, label, _slug in CATEGORIES_POE2]
# Extra search tokens so informal / older spellings still match price rows.
CATEGORY_SEARCH_ALIASES: dict[str, tuple[str, ...]] = {
    "Ducat": ("達克特", "杜卡特"),
    "EnshroudingCrystal": ("壟罩晶石", "壟罩結晶", "籠罩晶石", "籠罩結晶"),
    "Astrolabe": ("星盤",),
    "IncursionTemple": ("阿茲瓦特神殿", "阿茲瓦神殿", "神殿"),
    "ScryingOrb": ("占卜寶珠", "占卜球"),
    "Fragments": ("碎片",),
    "Essences": ("精華", "精髓"),
    "Runes": ("符文",),
    "SoulCores": ("魂核", "魂魄核心", "核心"),
    "Idols": ("神像", "偶像"),
    "UncutGems": ("未切割寶石", "未切割", "寶石"),
    "Expedition": ("探險文物", "探險"),
    "Abyss": ("深淵之骨", "深淵骨"),
    "LineageSupportGems": ("族裔寶石", "族裔"),
    "UniqueWeapons": ("傳奇武器", "武器"),
    "UniqueArmours": ("傳奇護甲", "護甲"),
    "UniqueAccessories": ("傳奇飾品", "飾品"),
    "UniqueFlasks": ("傳奇藥劑",),
    "UniqueCharms": ("傳奇護符", "護符"),
    "UniqueJewels": ("傳奇珠寶", "珠寶"),
    "UniqueSanctumRelics": ("傳奇聖物", "聖物"),
    "UniqueTablets": ("傳奇石板", "石板"),
    "PrecursorTablets": ("先驅石板", "先驅"),
}
GAME_LABELS = {"poe1": "PoE1", "poe2": "PoE2"}
CURRENCY_NAMES_ZH = {"chaos": "混沌石", "divine": "神聖石", "exalted": "崇高石"}
GAMES: dict[str, dict] = {
    "poe1": {
        "id": "poe1",
        "realm": "poe1",
        "label": "PoE1",
        "exchange": EXCHANGE_TYPES,
        "item": ITEM_TYPES,
        "page": ECONOMY_PAGE,
        # poe.ninja serves per-item PoE1 pages; the PoE2 economy is one SPA route.
        "deep_links": True,
        # poe.ninja quotes PoE1 in chaos and PoE2 in divine.
        "primary": "chaos",
        "secondary": "divine",
    },
    "poe2": {
        "id": "poe2",
        "realm": "poe2",
        "label": "PoE2",
        "exchange": EXCHANGE_TYPES_POE2,
        "item": ITEM_TYPES_POE2,
        "page": ECONOMY_PAGE_POE2,
        "deep_links": False,
        "primary": "divine",
        "secondary": "chaos",
    },
}


def game_spec(game: str) -> dict:
    return GAMES.get(game) or GAMES["poe1"]


def currency_labels(game: str) -> tuple[str, str]:
    """Chinese names for the (primary, secondary) price currencies of a game."""
    spec = game_spec(game)
    primary = spec["primary"]
    secondary = spec["secondary"]
    return CURRENCY_NAMES_ZH.get(primary, primary), CURRENCY_NAMES_ZH.get(secondary, secondary)


def _lookups(game: str) -> dict:
    spec = game_spec(game)
    cached = spec.get("_lookups")
    if cached:
        return cached
    exchange = spec["exchange"]
    items = spec["item"]
    label_to_spec = {
        label: (key, kind, slug)
        for kind, group in (("exchange", exchange), ("item", items))
        for key, label, slug in group
    }
    # Allow selecting / filtering by informal category spellings.
    for api_key, aliases in CATEGORY_SEARCH_ALIASES.items():
        found = next(((key, "exchange", slug) for key, _label, slug in exchange if key == api_key), None)
        if found is None:
            found = next(((key, "item", slug) for key, _label, slug in items if key == api_key), None)
        if not found:
            continue
        for alias in aliases:
            label_to_spec.setdefault(alias, found)
    cached = {
        "exchange_by_key": {key: (label, slug) for key, label, slug in exchange},
        "item_by_key": {key: (label, slug) for key, label, slug in items},
        "label_to_spec": label_to_spec,
    }
    spec["_lookups"] = cached
    return cached


def category_labels(game: str) -> list[str]:
    spec = game_spec(game)
    return [label for _key, label, _slug in list(spec["exchange"]) + list(spec["item"])]


def economy_page(game: str) -> str:
    return game_spec(game)["page"]


@dataclass
class League:
    id: str
    name: str

    @property
    def slug(self) -> str:
        return self.id.lower().replace(" ", "-")


@dataclass
class PriceRow:
    name: str
    name_zh: str
    category: str
    primary: float
    secondary: float
    change: float | None
    extra: str
    listings: int | None
    details_id: str
    ninja_url: str
    search_blob: str = field(repr=False, default="")

    @property
    def display_zh(self) -> str:
        return self.name_zh or "—"


_cache_lock = threading.Lock()
_league_cache: dict[str, tuple[float, list[League]]] = {}
_overview_cache: dict[tuple[str, str, str, str], tuple[float, list[PriceRow]]] = {}


def _request(url: str, timeout: int = 30) -> dict | list:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read().decode("utf-8", "replace")
            return json.loads(payload)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return {}
            last_error = error
            time.sleep(1.0 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error
            time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"無法讀取 poe.ninja：{last_error}")


def _fresh(stamp: float) -> bool:
    return (time.time() - stamp) < CACHE_TTL


def fetch_leagues(force: bool = False, game: str = "poe1") -> list[League]:
    realm = game_spec(game)["realm"]
    with _cache_lock:
        hit = _league_cache.get(realm)
        if not force and hit and _fresh(hit[0]):
            return list(hit[1])
    data = _request(f"{NINJA_BASE}/{realm}/api/economy/leagues")
    if not isinstance(data, list) or not data:
        raise RuntimeError("poe.ninja 沒有回傳聯盟列表。")
    leagues = [League(id=str(item.get("id") or ""), name=str(item.get("name") or item.get("id") or "")) for item in data]
    leagues = [league for league in leagues if league.id]
    with _cache_lock:
        _league_cache[realm] = (time.time(), leagues)
    return list(leagues)


def clear_cache(league_id: str | None = None, game: str | None = None) -> None:
    with _cache_lock:
        if league_id is None and game is None:
            _league_cache.clear()
            _overview_cache.clear()
            return
        realm = game_spec(game)["realm"] if game else None
        if realm and league_id is None:
            _league_cache.pop(realm, None)
        for key in [
            cached
            for cached in _overview_cache
            if (league_id is None or cached[1] == league_id) and (realm is None or cached[0] == realm)
        ]:
            _overview_cache.pop(key, None)


def _item_url(game: str, league: League, slug: str, details_id: str) -> str:
    spec = game_spec(game)
    if not spec["deep_links"]:
        return spec["page"]
    realm = spec["realm"]
    if details_id:
        return f"{NINJA_BASE}/{realm}/economy/{league.slug}/{slug}/{details_id}"
    return f"{NINJA_BASE}/{realm}/economy/{league.slug}/{slug}"


def _search_blob(*parts: object) -> str:
    chunks = [str(part).strip().lower() for part in parts if part not in (None, "")]
    return " ".join(chunks)


def _spark_change(spark) -> float | None:
    if not isinstance(spark, dict):
        return None
    value = spark.get("totalChange")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_exchange(game: str, league: League, api_type: str, payload: dict) -> list[PriceRow]:
    label, slug = _lookups(game)["exchange_by_key"][api_type]
    items = {item.get("id"): item for item in payload.get("items") or [] if isinstance(item, dict)}
    core = payload.get("core") or {}
    rates = core.get("rates") or {}
    secondary_id = str(core.get("secondary") or game_spec(game)["secondary"])
    secondary_per_primary = _to_float(rates.get(secondary_id), 0.0)
    rows: list[PriceRow] = []
    for line in payload.get("lines") or []:
        if not isinstance(line, dict):
            continue
        item_id = line.get("id")
        meta = items.get(item_id) or {}
        name = str(meta.get("name") or item_id or "")
        if not name:
            continue
        primary = _to_float(line.get("primaryValue"))
        secondary = primary * secondary_per_primary if secondary_per_primary else 0.0
        details_id = str(meta.get("detailsId") or item_id or "")
        name_zh = translate_name(name, game)
        aliases = CATEGORY_SEARCH_ALIASES.get(api_type, ())
        rows.append(
            PriceRow(
                name=name,
                name_zh=name_zh,
                category=label,
                primary=primary,
                secondary=secondary,
                change=_spark_change(line.get("sparkline")),
                extra="",
                listings=None,
                details_id=details_id,
                ninja_url=_item_url(game, league, slug, details_id),
                search_blob=_search_blob(
                    details_id.replace("-", " "),
                    label,
                    *aliases,
                    *search_terms(name, name_zh),
                ),
            )
        )
    return rows


def _item_extra(line: dict) -> str:
    bits: list[str] = []
    variant = line.get("variant")
    if variant:
        bits.append(str(variant))
    links = line.get("links")
    if links:
        bits.append(f"{links}L")
    if not variant:
        gem_level = line.get("gemLevel")
        gem_quality = line.get("gemQuality")
        if gem_level not in (None, 0) or gem_quality not in (None, 0):
            level_text = f"Lv{gem_level}" if gem_level not in (None, 0) else ""
            quality_text = f"{gem_quality}%" if gem_quality not in (None, 0) else ""
            bits.append(" ".join(part for part in (level_text, quality_text) if part))
    if line.get("corrupted"):
        bits.append("汙染")
    map_tier = line.get("mapTier")
    if map_tier not in (None, 0):
        bits.append(f"T{map_tier}")
    return " · ".join(bits)


def _parse_items(game: str, league: League, api_type: str, payload: dict) -> list[PriceRow]:
    label, slug = _lookups(game)["item_by_key"][api_type]
    aliases = CATEGORY_SEARCH_ALIASES.get(api_type, ())

    # PoE1 stash items carry chaosValue / divineValue directly on each line.
    # PoE2 stash items use primaryValue (divine) + core.rates for the secondary.
    core = payload.get("core") or {}
    rates = core.get("rates") or {}
    use_primary = game != "poe1"  # PoE2 stash API
    secondary_id = str(core.get("secondary") or game_spec(game)["secondary"])
    secondary_per_primary = _to_float(rates.get(secondary_id), 0.0) if use_primary else 0.0

    rows: list[PriceRow] = []
    for line in payload.get("lines") or []:
        if not isinstance(line, dict):
            continue
        name = str(line.get("name") or "")
        if not name:
            continue
        details_id = str(line.get("detailsId") or "")
        extra = _item_extra(line)
        # Scrying orbs are keyed by bare map names on poe.ninja (e.g. "Beach").
        if api_type == "ScryingOrb":
            name_zh = translate_name(f"{name} Map", game) or translate_name(name, game)
        else:
            name_zh = translate_name(name, game)
        base_zh = translate_name(str(line.get("baseType") or ""), game)
        if use_primary:
            primary = _to_float(line.get("primaryValue"))
            secondary = primary * secondary_per_primary if secondary_per_primary else 0.0
        else:
            primary = _to_float(line.get("chaosValue"))
            secondary = _to_float(line.get("divineValue"))
        rows.append(
            PriceRow(
                name=name,
                name_zh=name_zh,
                category=label,
                primary=primary,
                secondary=secondary,
                change=_spark_change(line.get("sparkLine")),
                extra=extra,
                listings=int(line["listingCount"]) if line.get("listingCount") not in (None, "") else None,
                details_id=details_id,
                ninja_url=_item_url(game, league, slug, details_id),
                search_blob=_search_blob(
                    line.get("baseType"),
                    base_zh,
                    extra,
                    details_id.replace("-", " "),
                    label,
                    *aliases,
                    *search_terms(name, name_zh),
                ),
            )
        )
    return rows


def _cached_rows(realm: str, league_id: str, kind: str, api_type: str) -> list[PriceRow] | None:
    with _cache_lock:
        hit = _overview_cache.get((realm, league_id, kind, api_type))
        if hit and _fresh(hit[0]):
            return list(hit[1])
    return None


def _store_rows(realm: str, league_id: str, kind: str, api_type: str, rows: list[PriceRow]) -> None:
    with _cache_lock:
        _overview_cache[(realm, league_id, kind, api_type)] = (time.time(), rows)


def fetch_overview(
    league: League,
    kind: str,
    api_type: str,
    force: bool = False,
    game: str = "poe1",
) -> list[PriceRow]:
    realm = game_spec(game)["realm"]
    if not force:
        cached = _cached_rows(realm, league.id, kind, api_type)
        if cached is not None:
            return cached
    encoded = urllib.parse.urlencode({"league": league.id, "type": api_type})
    if kind == "exchange":
        url = f"{NINJA_BASE}/{realm}/api/economy/exchange/current/overview?{encoded}"
        payload = _request(url)
        rows = _parse_exchange(game, league, api_type, payload if isinstance(payload, dict) else {})
    else:
        url = f"{NINJA_BASE}/{realm}/api/economy/stash/current/item/overview?{encoded}"
        payload = _request(url)
        rows = _parse_items(game, league, api_type, payload if isinstance(payload, dict) else {})
    _store_rows(realm, league.id, kind, api_type, rows)
    return list(rows)


def _specs_for_label(game: str, label: str) -> list[tuple[str, str, str]]:
    spec_game = game_spec(game)
    if label == ALL:
        return [(key, "exchange", slug) for key, _name, slug in spec_game["exchange"]] + [
            (key, "item", slug) for key, _name, slug in spec_game["item"]
        ]
    spec = _lookups(game)["label_to_spec"].get(label)
    if not spec:
        return []
    key, kind, slug = spec
    return [(key, kind, slug)]


def fetch_prices(
    league: League,
    category_label: str,
    force: bool = False,
    progress=None,
    max_workers: int | None = None,
    game: str = "poe1",
) -> list[PriceRow]:
    realm = game_spec(game)["realm"]
    specs = _specs_for_label(game, category_label)
    if not specs:
        return []
    missing: list[tuple[str, str, str]] = []
    rows: list[PriceRow] = []
    for api_type, kind, _slug in specs:
        if force:
            missing.append((api_type, kind, _slug))
            continue
        cached = _cached_rows(realm, league.id, kind, api_type)
        if cached is None:
            missing.append((api_type, kind, _slug))
        else:
            rows.extend(cached)

    total = len(missing)
    if progress and total:
        progress(0, total, "下載價格…")

    if missing:
        done = 0
        with ThreadPoolExecutor(max_workers=max_workers or MAX_WORKERS) as pool:
            futures = {
                pool.submit(fetch_overview, league, kind, api_type, force, game): (api_type, kind)
                for api_type, kind, _slug in missing
            }
            for future in as_completed(futures):
                api_type, kind = futures[future]
                done += 1
                try:
                    rows.extend(future.result())
                except RuntimeError:
                    # Skip categories the current league does not publish.
                    pass
                if progress:
                    progress(done, total, f"下載價格 {done}/{total}")
    if progress:
        progress(total, total, "價格資料已就緒")
    return rows


def matches(row: PriceRow, query: str) -> bool:
    text = query.strip().lower()
    if not text:
        return True
    return all(token in row.search_blob for token in text.split())
