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
CACHE_TTL = 15 * 60
MAX_WORKERS = 3
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
    ("Runegraft", "符文嫁接", "runegrafts"),
    ("AllflameEmber", "萬火餘燼", "allflame-embers"),
    ("DjinnCoin", "巨靈幣", "djinn-coins"),
    ("Ducat", "杜卡特", "ducats"),
    ("EnshroudingCrystal", "籠罩結晶", "enshrouding-crystals"),
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
    ("Wombgift", "子宮贈禮", "wombgifts"),
    ("IncursionTemple", "神殿", "incursion-temples"),
    ("ScryingOrb", "占卜球", "scrying-orbs"),
]

CATEGORIES = EXCHANGE_TYPES + ITEM_TYPES
CATEGORY_LABELS = [label for _key, label, _slug in CATEGORIES]
_EXCHANGE_BY_KEY = {key: (label, slug) for key, label, slug in EXCHANGE_TYPES}
_ITEM_BY_KEY = {key: (label, slug) for key, label, slug in ITEM_TYPES}
_LABEL_TO_SPEC = {label: (key, kind, slug) for kind, group in (("exchange", EXCHANGE_TYPES), ("item", ITEM_TYPES)) for key, label, slug in group}

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
    chaos: float
    divine: float
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
_league_cache: tuple[float, list[League]] | None = None
_overview_cache: dict[tuple[str, str, str], tuple[float, list[PriceRow]]] = {}


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


def fetch_leagues(force: bool = False) -> list[League]:
    global _league_cache
    with _cache_lock:
        if not force and _league_cache and _fresh(_league_cache[0]):
            return list(_league_cache[1])
    data = _request(f"{NINJA_BASE}/poe1/api/economy/leagues")
    if not isinstance(data, list) or not data:
        raise RuntimeError("poe.ninja 沒有回傳聯盟列表。")
    leagues = [League(id=str(item.get("id") or ""), name=str(item.get("name") or item.get("id") or "")) for item in data]
    leagues = [league for league in leagues if league.id]
    with _cache_lock:
        _league_cache = (time.time(), leagues)
    return list(leagues)


def clear_cache(league_id: str | None = None) -> None:
    global _league_cache
    with _cache_lock:
        if league_id is None:
            _league_cache = None
            _overview_cache.clear()
            return
        for key in [cached for cached in _overview_cache if cached[0] == league_id]:
            _overview_cache.pop(key, None)


def _item_url(league: League, slug: str, details_id: str) -> str:
    if details_id:
        return f"{NINJA_BASE}/poe1/economy/{league.slug}/{slug}/{details_id}"
    return f"{NINJA_BASE}/poe1/economy/{league.slug}/{slug}"


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


def _parse_exchange(league: League, api_type: str, payload: dict) -> list[PriceRow]:
    label, slug = _EXCHANGE_BY_KEY[api_type]
    items = {item.get("id"): item for item in payload.get("items") or [] if isinstance(item, dict)}
    core = payload.get("core") or {}
    rates = core.get("rates") or {}
    divine_per_chaos = _to_float(rates.get("divine"), 0.0)
    rows: list[PriceRow] = []
    for line in payload.get("lines") or []:
        if not isinstance(line, dict):
            continue
        item_id = line.get("id")
        meta = items.get(item_id) or {}
        name = str(meta.get("name") or item_id or "")
        if not name:
            continue
        chaos = _to_float(line.get("primaryValue"))
        divine = chaos * divine_per_chaos if divine_per_chaos else 0.0
        details_id = str(meta.get("detailsId") or item_id or "")
        name_zh = translate_name(name)
        rows.append(
            PriceRow(
                name=name,
                name_zh=name_zh,
                category=label,
                chaos=chaos,
                divine=divine,
                change=_spark_change(line.get("sparkline")),
                extra="",
                listings=None,
                details_id=details_id,
                ninja_url=_item_url(league, slug, details_id),
                search_blob=_search_blob(details_id.replace("-", " "), *search_terms(name, name_zh)),
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


def _parse_items(league: League, api_type: str, payload: dict) -> list[PriceRow]:
    label, slug = _ITEM_BY_KEY[api_type]
    rows: list[PriceRow] = []
    for line in payload.get("lines") or []:
        if not isinstance(line, dict):
            continue
        name = str(line.get("name") or "")
        if not name:
            continue
        details_id = str(line.get("detailsId") or "")
        extra = _item_extra(line)
        name_zh = translate_name(name)
        base_zh = translate_name(str(line.get("baseType") or ""))
        rows.append(
            PriceRow(
                name=name,
                name_zh=name_zh,
                category=label,
                chaos=_to_float(line.get("chaosValue")),
                divine=_to_float(line.get("divineValue")),
                change=_spark_change(line.get("sparkLine")),
                extra=extra,
                listings=int(line["listingCount"]) if line.get("listingCount") not in (None, "") else None,
                details_id=details_id,
                ninja_url=_item_url(league, slug, details_id),
                search_blob=_search_blob(
                    line.get("baseType"),
                    base_zh,
                    extra,
                    details_id.replace("-", " "),
                    *search_terms(name, name_zh),
                ),
            )
        )
    return rows


def _cached_rows(league_id: str, kind: str, api_type: str) -> list[PriceRow] | None:
    with _cache_lock:
        hit = _overview_cache.get((league_id, kind, api_type))
        if hit and _fresh(hit[0]):
            return list(hit[1])
    return None


def _store_rows(league_id: str, kind: str, api_type: str, rows: list[PriceRow]) -> None:
    with _cache_lock:
        _overview_cache[(league_id, kind, api_type)] = (time.time(), rows)


def fetch_overview(league: League, kind: str, api_type: str, force: bool = False) -> list[PriceRow]:
    if not force:
        cached = _cached_rows(league.id, kind, api_type)
        if cached is not None:
            return cached
    encoded = urllib.parse.urlencode({"league": league.id, "type": api_type})
    if kind == "exchange":
        url = f"{NINJA_BASE}/poe1/api/economy/exchange/current/overview?{encoded}"
        payload = _request(url)
        rows = _parse_exchange(league, api_type, payload if isinstance(payload, dict) else {})
    else:
        url = f"{NINJA_BASE}/poe1/api/economy/stash/current/item/overview?{encoded}"
        payload = _request(url)
        rows = _parse_items(league, api_type, payload if isinstance(payload, dict) else {})
    _store_rows(league.id, kind, api_type, rows)
    return list(rows)


def _specs_for_label(label: str) -> list[tuple[str, str, str]]:
    if label == ALL:
        return [(key, "exchange", slug) for key, _name, slug in EXCHANGE_TYPES] + [
            (key, "item", slug) for key, _name, slug in ITEM_TYPES
        ]
    spec = _LABEL_TO_SPEC.get(label)
    if not spec:
        return []
    key, kind, slug = spec
    return [(key, kind, slug)]


def fetch_prices(
    league: League,
    category_label: str,
    force: bool = False,
    progress=None,
) -> list[PriceRow]:
    specs = _specs_for_label(category_label)
    if not specs:
        return []
    missing: list[tuple[str, str, str]] = []
    rows: list[PriceRow] = []
    for api_type, kind, _slug in specs:
        if force:
            missing.append((api_type, kind, _slug))
            continue
        cached = _cached_rows(league.id, kind, api_type)
        if cached is None:
            missing.append((api_type, kind, _slug))
        else:
            rows.extend(cached)

    total = len(missing)
    if progress and total:
        progress(0, total, "下載價格…")

    if missing:
        done = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(fetch_overview, league, kind, api_type, force): (api_type, kind)
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
