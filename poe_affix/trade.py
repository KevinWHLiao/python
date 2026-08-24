"""Official Path of Exile trade site helper (search + listing peek)."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .i18n import NICKNAMES, name_map, translate_name
from .net import USER_AGENT

TRADE_BASE = "https://www.pathofexile.com"
TRADE_PAGE = f"{TRADE_BASE}/trade/search"
CACHE_TTL = 10 * 60
ITEMS_CACHE_TTL = 6 * 60 * 60
SEARCH_CACHE_TTL = 45
FETCH_BATCH = 10
SUGGEST_LIMIT = 40
# Stay under trade-search-request-limit (≈5 / 12s) when not logged in.
MIN_SEARCH_GAP = 1.4
MIN_FETCH_GAP = 0.4
MIN_DATA_GAP = 0.25

_league_cache: tuple[float, list["TradeLeague"]] | None = None
_items_cache: tuple[float, list["TradeItem"]] | None = None
_search_cache: dict[tuple, tuple[float, "TradeSearchResult"]] = {}
_rate_lock = threading.Lock()
_cooldown_until = 0.0
_last_search_at = 0.0
_last_fetch_at = 0.0
_last_data_at = 0.0

CATEGORY_ZH: dict[str, str] = {
    "Accessories": "飾品",
    "Armour": "護甲",
    "Cards": "命運卡",
    "Currency": "通貨",
    "Flasks": "藥劑",
    "Gems": "寶石",
    "Jewels": "珠寶",
    "Maps": "地圖",
    "Weapons": "武器",
    "Leaguestones": "聯盟石",
    "Itemised Monsters": "野獸",
    "Heist Equipment": "劫盜裝備",
    "Heist Mission": "劫盜任務",
    "Expedition Logbooks": "探險日誌",
    "Sanctum": "聖域",
    "Tincture": "酊劑",
    "Itemised Corpse": "屍體",
    "Idol": "神像",
    "Graft": "嫁接",
    "Wombgift": "子宮贈禮",
    "Enshrouded Item": "籠罩物品",
    "Chart": "海圖",
}

# Official trade site seller availability dropdown → API status.option
# Default on the website is "available" (instant buyout + in person).
STATUS_OPTIONS: list[tuple[str, str]] = [
    ("available", "即刻購買以及面對面交易"),
    ("securable", "即刻購買"),
    ("onlineleague", "面對面交易（聯盟在線）"),
    ("online", "面對面交易（在線）"),
    ("any", "任何"),
]
STATUS_LABELS = [label for _key, label in STATUS_OPTIONS]
_STATUS_BY_LABEL = {label: key for key, label in STATUS_OPTIONS}
DEFAULT_STATUS = "available"
DEFAULT_STATUS_LABEL = next(label for key, label in STATUS_OPTIONS if key == DEFAULT_STATUS)

# type_filters.category options used by the official trade site.
ITEM_CATEGORIES: list[tuple[str, str]] = [
    ("", "不限"),
    ("weapon", "武器"),
    ("weapon.one", "單手武器"),
    ("weapon.onemelee", "單手近戰"),
    ("weapon.twomelee", "雙手近戰"),
    ("weapon.bow", "弓"),
    ("weapon.claw", "爪"),
    ("weapon.dagger", "匕首"),
    ("weapon.rune", "符文匕首"),
    ("weapon.wand", "法杖"),
    ("weapon.sceptre", "權杖"),
    ("weapon.staff", "長杖"),
    ("weapon.warstaff", "征戰長杖"),
    ("armour", "護甲"),
    ("armour.chest", "胸甲"),
    ("armour.helmet", "頭部"),
    ("armour.gloves", "手套"),
    ("armour.boots", "鞋子"),
    ("armour.shield", "盾"),
    ("armour.quiver", "箭袋"),
    ("accessory", "飾品"),
    ("accessory.amulet", "項鍊"),
    ("accessory.ring", "戒指"),
    ("accessory.belt", "腰帶"),
    ("jewel", "珠寶"),
    ("jewel.abyss", "深淵珠寶"),
    ("jewel.cluster", "星團珠寶"),
    ("flask", "藥劑"),
    ("gem", "寶石"),
    ("gem.activegem", "技能寶石"),
    ("gem.supportgem", "輔助寶石"),
    ("card", "命運卡"),
    ("map", "地圖"),
    ("map.unique", "傳奇地圖"),
    ("currency", "通貨"),
]

RARITY_OPTIONS: list[tuple[str, str]] = [
    ("", "不限"),
    ("normal", "普通"),
    ("magic", "魔法"),
    ("rare", "稀有"),
    ("unique", "傳奇"),
    ("uniquefoil", "傳奇（貼箔）"),
    ("nonunique", "非傳奇"),
]

CORRUPT_OPTIONS: list[tuple[str, str]] = [
    ("", "不限"),
    ("true", "是"),
    ("false", "否"),
]

PRICE_CURRENCIES: list[tuple[str, str]] = [
    ("chaos", "混沌石"),
    ("divine", "神聖石"),
    ("exalted", "崇高石"),
    ("mirror", "卡蘭德的魔鏡"),
]

CATEGORY_LABELS = [label for _key, label in ITEM_CATEGORIES]
RARITY_LABELS = [label for _key, label in RARITY_OPTIONS]
CORRUPT_LABELS = [label for _key, label in CORRUPT_OPTIONS]
PRICE_CURRENCY_LABELS = [label for _key, label in PRICE_CURRENCIES]
_CATEGORY_BY_LABEL = {label: key for key, label in ITEM_CATEGORIES}
_RARITY_BY_LABEL = {label: key for key, label in RARITY_OPTIONS}
_CORRUPT_BY_LABEL = {label: key for key, label in CORRUPT_OPTIONS}
_PRICE_BY_LABEL = {label: key for key, label in PRICE_CURRENCIES}

_stats_cache: tuple[float, list["TradeStat"]] | None = None


@dataclass
class TradeLeague:
    id: str
    text: str

    @property
    def name(self) -> str:
        return self.text or self.id


@dataclass
class TradeListing:
    id: str
    name: str
    name_zh: str
    type_line: str
    price_amount: float | None
    price_currency: str
    price_text: str
    account: str
    character: str
    whisper: str
    indexed: str
    ilvl: int | None
    corrupted: bool
    mirrors: bool
    method: str
    method_zh: str
    fee: int | None


@dataclass
class TradeSearchResult:
    search_id: str
    total: int
    url: str
    query_en: str
    listings: list[TradeListing]
    from_cache: bool = False


class TradeRateLimitError(RuntimeError):
    """Official trade API 429 / local cooldown."""

    def __init__(self, retry_after: float, message: str | None = None) -> None:
        self.retry_after = max(1, int(retry_after + 0.999))
        super().__init__(message or f"官方賣場請求過快，請約 {self.retry_after} 秒後再試")


def cooldown_remaining() -> float:
    with _rate_lock:
        return max(0.0, _cooldown_until - time.monotonic())


def _set_cooldown(seconds: float) -> None:
    global _cooldown_until
    until = time.monotonic() + max(0.0, float(seconds))
    with _rate_lock:
        if until > _cooldown_until:
            _cooldown_until = until


def _wait_for_slot(kind: str) -> None:
    """Block until local cooldown / spacing allows another request."""
    global _last_search_at, _last_fetch_at, _last_data_at
    while True:
        with _rate_lock:
            now = time.monotonic()
            wait = max(0.0, _cooldown_until - now)
            if kind == "search":
                wait = max(wait, _last_search_at + MIN_SEARCH_GAP - now)
            elif kind == "fetch":
                wait = max(wait, _last_fetch_at + MIN_FETCH_GAP - now)
            else:
                wait = max(wait, _last_data_at + MIN_DATA_GAP - now)
        if wait <= 0:
            return
        # Long cooldowns (60–300s) should fail fast so the UI can show a timer.
        if wait > 20:
            raise TradeRateLimitError(wait)
        time.sleep(min(wait, 1.0))


def _mark_request(kind: str) -> None:
    global _last_search_at, _last_fetch_at, _last_data_at
    now = time.monotonic()
    with _rate_lock:
        if kind == "search":
            _last_search_at = now
        elif kind == "fetch":
            _last_fetch_at = now
        else:
            _last_data_at = now


@dataclass
class TradeItem:
    """One catalogue entry from /api/trade/data/items (official suggest source)."""

    category_id: str
    category_en: str
    category_zh: str
    name: str
    type_line: str
    text: str
    disc: str
    unique: bool

    @property
    def english(self) -> str:
        if self.text:
            return self.text
        if self.name and self.type_line:
            return f"{self.name} {self.type_line}"
        return self.name or self.type_line

    @property
    def chinese(self) -> str:
        if self.name and self.type_line:
            zh_name = translate_name(self.name)
            zh_type = translate_name(self.type_line)
            if zh_name and zh_type:
                return f"{zh_name} {zh_type}"
            return zh_name or zh_type or ""
        return translate_name(self.name or self.type_line or self.text) or ""

    @property
    def display(self) -> str:
        en = self.english
        zh = self.chinese
        if zh and en and zh.casefold() != en.casefold():
            return f"{zh} ({en})"
        return en or zh

    @property
    def search_text(self) -> str:
        """Value written into the search box after picking a suggestion."""
        return self.name or self.type_line or self.text

    @property
    def exact_name(self) -> str | None:
        return self.name or None

    @property
    def exact_type(self) -> str | None:
        return self.type_line or None


@dataclass
class SuggestRow:
    """Popup row: category header or selectable item."""

    kind: str  # "header" | "item"
    text: str
    item: TradeItem | None = None
    stat: "TradeStat | None" = None


@dataclass
class TradeStat:
    """One mod entry from /api/trade/data/stats."""

    id: str
    text: str
    type: str
    group_id: str
    group_label: str

    @property
    def display(self) -> str:
        return f"[{self.group_label}] {self.text}"


@dataclass
class StatFilter:
    stat_id: str
    text: str
    min_value: float | None = None
    max_value: float | None = None

    def cache_key(self) -> tuple:
        return (self.stat_id, self.min_value, self.max_value)


@dataclass
class SearchFilters:
    category: str = ""
    rarity: str = ""
    ilvl_min: int | None = None
    ilvl_max: int | None = None
    corrupted: str = ""
    price_currency: str = "chaos"
    price_min: float | None = None
    price_max: float | None = None
    stats: tuple[StatFilter, ...] = ()

    def cache_key(self) -> tuple:
        return (
            self.category,
            self.rarity,
            self.ilvl_min,
            self.ilvl_max,
            self.corrupted,
            self.price_currency,
            self.price_min,
            self.price_max,
            tuple(stat.cache_key() for stat in self.stats),
        )

    def is_empty(self) -> bool:
        return self.cache_key() == SearchFilters().cache_key()


def trade_search_url(league: str, search_id: str | None = None) -> str:
    league_enc = urllib.parse.quote(league, safe="")
    if search_id:
        return f"{TRADE_PAGE}/{league_enc}/{search_id}"
    return f"{TRADE_PAGE}/{league_enc}"


def resolve_status(raw: str | None) -> str:
    """Map UI label or API key to a valid trade status.option."""
    text = (raw or "").strip()
    if not text:
        return DEFAULT_STATUS
    if text in _STATUS_BY_LABEL:
        return _STATUS_BY_LABEL[text]
    keys = {key for key, _label in STATUS_OPTIONS}
    if text in keys:
        return text
    lowered = text.casefold()
    for key, label in STATUS_OPTIONS:
        if label.casefold() == lowered or key.casefold() == lowered:
            return key
    return DEFAULT_STATUS


def status_label(option: str) -> str:
    for key, label in STATUS_OPTIONS:
        if key == option:
            return label
    return DEFAULT_STATUS_LABEL


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def find_name_candidates(raw: str, *, limit: int = 12) -> list[str]:
    """Ranked English item names from the local zh map / nicknames."""
    query = (raw or "").strip()
    if not query:
        return []
    mapping = name_map()
    lowered = query.casefold()

    if query in mapping:
        return [query]
    for english, chinese in mapping.items():
        if chinese == query:
            return [english]
    for english, nicks in NICKNAMES.items():
        if english.casefold() == lowered or query in nicks:
            return [english]

    scored: list[tuple[int, str]] = []
    for english, chinese in mapping.items():
        score = 0
        en_l = english.casefold()
        if en_l == lowered:
            score = 100
        elif en_l.startswith(lowered):
            score = 80
        elif lowered in en_l:
            score = 60
        if chinese:
            if chinese == query:
                score = max(score, 100)
            elif chinese.startswith(query):
                score = max(score, 85)
            elif query in chinese:
                score = max(score, 70)
        for nick in NICKNAMES.get(english, ()):
            if query == nick:
                score = max(score, 95)
            elif query in nick or nick in query:
                score = max(score, 75)
        if score:
            scored.append((score, english))

    scored.sort(key=lambda row: (-row[0], len(row[1]), row[1]))
    out: list[str] = []
    seen: set[str] = set()
    for _score, english in scored:
        if english in seen:
            continue
        seen.add(english)
        out.append(english)
        if len(out) >= limit:
            break
    return out


def resolve_english_query(raw: str) -> str:
    """Best single English name for display, or the original keyword."""
    query = (raw or "").strip()
    if not query:
        return ""
    hits = find_name_candidates(query, limit=2)
    if len(hits) == 1:
        return hits[0]
    return query


def resolve_search_term(raw: str) -> tuple[str, str]:
    """Return (api_term, display_label) for official trade `term` search.

    Official `name` / `type` require exact catalogue strings and reject keywords
    like ``hope``. The site search box uses ``term`` instead.
    """
    query = (raw or "").strip()
    if not query:
        raise RuntimeError("請輸入物品關鍵字（英文或中文）")

    hits = find_name_candidates(query, limit=8)
    if len(hits) == 1:
        return hits[0], hits[0]

    if _contains_cjk(query):
        if not hits:
            raise RuntimeError("找不到對應的英文物品名，請改試英文關鍵字或更完整的中文名")
        preview = "、".join(f"{translate_name(name) or name}（{name}）" for name in hits[:5])
        raise RuntimeError(f"關鍵字對到多個物品，請輸入更完整名稱：{preview}")

    # Latin / keyword search — pass through to trade `term`.
    return query, query


def _request(
    url: str,
    *,
    data: bytes | None = None,
    timeout: int = 30,
    kind: str = "data",
) -> dict | list:
    _wait_for_slot(kind)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    last_error: Exception | None = None
    for attempt in range(2):
        _wait_for_slot(kind)
        try:
            _mark_request(kind)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", "replace") if error.fp else ""
            if error.code == 429:
                retry = int(error.headers.get("Retry-After") or 60)
                _set_cooldown(retry)
                # Only auto-retry short cool-downs; long bans must surface to the UI.
                if retry <= 8 and attempt == 0:
                    time.sleep(retry + 0.3)
                    continue
                raise TradeRateLimitError(retry) from error
            if error.code in {403, 503}:
                raise RuntimeError("官方賣場暫時拒絕連線（可能被 Cloudflare 擋下），請稍後再試或改開網頁") from error
            detail = body[:200].strip() if body else error.reason
            raise RuntimeError(f"官方賣場 HTTP {error.code}: {detail}") from error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error
            time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"無法連線官方賣場: {last_error}")


def fetch_leagues(force: bool = False) -> list[TradeLeague]:
    global _league_cache
    now = time.monotonic()
    if not force and _league_cache and now - _league_cache[0] < CACHE_TTL:
        return list(_league_cache[1])
    payload = _request(f"{TRADE_BASE}/api/trade/data/leagues", kind="data")
    rows = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError("官方賣場聯盟清單格式異常")
    leagues: list[TradeLeague] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        league_id = str(row.get("id") or "").strip()
        if not league_id or league_id in seen:
            continue
        seen.add(league_id)
        leagues.append(TradeLeague(id=league_id, text=str(row.get("text") or league_id)))
    if not leagues:
        raise RuntimeError("官方賣場沒有可用聯盟")
    _league_cache = (now, leagues)
    return list(leagues)


def fetch_items(force: bool = False) -> list[TradeItem]:
    """Official trade item catalogue used by the website autocomplete."""
    global _items_cache
    now = time.monotonic()
    if not force and _items_cache and now - _items_cache[0] < ITEMS_CACHE_TTL:
        return list(_items_cache[1])
    payload = _request(f"{TRADE_BASE}/api/trade/data/items", kind="data")
    rows = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError("官方賣場物品清單格式異常")
    items: list[TradeItem] = []
    for group in rows:
        if not isinstance(group, dict):
            continue
        category_id = str(group.get("id") or "")
        category_en = str(group.get("label") or category_id)
        category_zh = CATEGORY_ZH.get(category_en, category_en)
        for entry in group.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            flags = entry.get("flags") or {}
            items.append(
                TradeItem(
                    category_id=category_id,
                    category_en=category_en,
                    category_zh=category_zh,
                    name=str(entry.get("name") or "").strip(),
                    type_line=str(entry.get("type") or "").strip(),
                    text=str(entry.get("text") or "").strip(),
                    disc=str(entry.get("disc") or "").strip(),
                    unique=bool(flags.get("unique")),
                )
            )
    if not items:
        raise RuntimeError("官方賣場物品清單是空的")
    _items_cache = (now, items)
    return list(items)


def _score_item(query: str, item: TradeItem) -> int:
    lowered = query.casefold()
    haystacks = [
        item.name,
        item.type_line,
        item.text,
        item.english,
        item.chinese,
        item.search_text,
    ]
    for nick in NICKNAMES.get(item.name, ()):
        haystacks.append(nick)
    score = 0
    for hay in haystacks:
        if not hay:
            continue
        hay_l = hay.casefold()
        if hay_l == lowered:
            score = max(score, 100)
        elif hay_l.startswith(lowered):
            score = max(score, 90)
        elif lowered in hay_l:
            score = max(score, 70)
        elif query in hay:  # Chinese substring (casefold no-op)
            score = max(score, 75)
    # Prefer shorter / unique named matches slightly.
    if score and item.unique:
        score += 2
    if score and item.name and item.name.casefold() == lowered:
        score += 5
    return score


def suggest_items(raw: str, *, limit: int = SUGGEST_LIMIT) -> list[SuggestRow]:
    """Build official-style grouped suggestions for a typed keyword."""
    query = (raw or "").strip()
    if len(query) < 1:
        return []
    try:
        catalog = fetch_items()
    except RuntimeError:
        return []

    ranked: list[tuple[int, TradeItem]] = []
    for item in catalog:
        score = _score_item(query, item)
        if score:
            ranked.append((score, item))
    ranked.sort(key=lambda row: (-row[0], row[1].category_en, len(row[1].english), row[1].english))

    # Keep category order by first appearance in ranked list; cap total items.
    by_cat: dict[str, list[TradeItem]] = {}
    order: list[str] = []
    taken = 0
    for _score, item in ranked:
        if taken >= limit:
            break
        key = item.category_en
        if key not in by_cat:
            by_cat[key] = []
            order.append(key)
        if len(by_cat[key]) >= 12:
            continue
        by_cat[key].append(item)
        taken += 1

    rows: list[SuggestRow] = []
    for key in order:
        sample = by_cat[key][0]
        rows.append(SuggestRow(kind="header", text=sample.category_zh))
        for item in by_cat[key]:
            rows.append(SuggestRow(kind="item", text=item.display, item=item))
    return rows


def fetch_stats(force: bool = False) -> list[TradeStat]:
    """Official trade mod catalogue used by the website filter autocomplete."""
    global _stats_cache
    now = time.monotonic()
    if not force and _stats_cache and now - _stats_cache[0] < ITEMS_CACHE_TTL:
        return list(_stats_cache[1])
    payload = _request(f"{TRADE_BASE}/api/trade/data/stats", kind="data")
    rows = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError("官方賣場詞綴清單格式異常")
    stats: list[TradeStat] = []
    for group in rows:
        if not isinstance(group, dict):
            continue
        group_id = str(group.get("id") or "")
        group_label = str(group.get("label") or group_id)
        for entry in group.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            stat_id = str(entry.get("id") or "").strip()
            text = str(entry.get("text") or "").strip()
            if not stat_id or not text:
                continue
            stats.append(
                TradeStat(
                    id=stat_id,
                    text=text,
                    type=str(entry.get("type") or group_id),
                    group_id=group_id,
                    group_label=group_label,
                )
            )
    if not stats:
        raise RuntimeError("官方賣場詞綴清單是空的")
    _stats_cache = (now, stats)
    return list(stats)


def _score_stat(query: str, stat: TradeStat) -> int:
    lowered = query.casefold()
    text_l = stat.text.casefold()
    score = 0
    if text_l == lowered:
        score = 100
    elif text_l.startswith(lowered):
        score = 90
    elif lowered in text_l:
        score = 70
    if lowered in stat.group_label.casefold():
        score = max(score, 40)
    if score and stat.type == "pseudo":
        score += 3
    elif score and stat.type == "explicit":
        score += 2
    return score


def suggest_stats(raw: str, *, limit: int = 30) -> list[SuggestRow]:
    """Grouped mod suggestions for the filter panel."""
    query = (raw or "").strip()
    if len(query) < 2:
        return []
    try:
        catalog = fetch_stats()
    except RuntimeError:
        return []
    ranked: list[tuple[int, TradeStat]] = []
    for stat in catalog:
        score = _score_stat(query, stat)
        if score:
            ranked.append((score, stat))
    ranked.sort(key=lambda row: (-row[0], row[1].group_label, len(row[1].text), row[1].text))

    by_group: dict[str, list[TradeStat]] = {}
    order: list[str] = []
    taken = 0
    for _score, stat in ranked:
        if taken >= limit:
            break
        key = stat.group_label
        if key not in by_group:
            by_group[key] = []
            order.append(key)
        if len(by_group[key]) >= 10:
            continue
        by_group[key].append(stat)
        taken += 1

    rows: list[SuggestRow] = []
    for key in order:
        rows.append(SuggestRow(kind="header", text=key))
        for stat in by_group[key]:
            rows.append(SuggestRow(kind="item", text=stat.text, stat=stat))
    return rows


def resolve_category(raw: str | None) -> str:
    text = (raw or "").strip()
    if not text or text == "不限":
        return ""
    if text in _CATEGORY_BY_LABEL:
        return _CATEGORY_BY_LABEL[text]
    if text in {key for key, _label in ITEM_CATEGORIES}:
        return text
    return ""


def resolve_rarity(raw: str | None) -> str:
    text = (raw or "").strip()
    if not text or text == "不限":
        return ""
    if text in _RARITY_BY_LABEL:
        return _RARITY_BY_LABEL[text]
    if text in {key for key, _label in RARITY_OPTIONS}:
        return text
    return ""


def resolve_corrupt(raw: str | None) -> str:
    text = (raw or "").strip()
    if not text or text == "不限":
        return ""
    if text in _CORRUPT_BY_LABEL:
        return _CORRUPT_BY_LABEL[text]
    if text in {"true", "false"}:
        return text
    return ""


def resolve_price_currency(raw: str | None) -> str:
    text = (raw or "").strip()
    if text in _PRICE_BY_LABEL:
        return _PRICE_BY_LABEL[text]
    if text in {key for key, _label in PRICE_CURRENCIES}:
        return text
    return "chaos"


def optional_number(raw: str | None) -> float | None:
    text = (raw or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def optional_int(raw: str | None) -> int | None:
    value = optional_number(raw)
    if value is None:
        return None
    return int(value)


def build_trade_filters(filters: SearchFilters | None) -> dict:
    """Convert SearchFilters into official query.filters + stats filters list."""
    if filters is None:
        return {"filters": {}, "stat_filters": []}

    type_filters: dict = {}
    if filters.category:
        type_filters["category"] = {"option": filters.category}
    if filters.rarity:
        type_filters["rarity"] = {"option": filters.rarity}

    misc_filters: dict = {}
    if filters.ilvl_min is not None or filters.ilvl_max is not None:
        ilvl: dict = {}
        if filters.ilvl_min is not None:
            ilvl["min"] = filters.ilvl_min
        if filters.ilvl_max is not None:
            ilvl["max"] = filters.ilvl_max
        misc_filters["ilvl"] = ilvl
    if filters.corrupted:
        misc_filters["corrupted"] = {"option": filters.corrupted}

    trade_filters: dict = {}
    if filters.price_min is not None or filters.price_max is not None:
        price: dict = {"option": filters.price_currency or "chaos"}
        if filters.price_min is not None:
            price["min"] = filters.price_min
        if filters.price_max is not None:
            price["max"] = filters.price_max
        trade_filters["price"] = price

    payload: dict = {}
    if type_filters:
        payload["type_filters"] = {"filters": type_filters}
    if misc_filters:
        payload["misc_filters"] = {"filters": misc_filters}
    if trade_filters:
        payload["trade_filters"] = {"filters": trade_filters}

    stat_filters = []
    for stat in filters.stats:
        if not stat.stat_id:
            continue
        entry: dict = {"id": stat.stat_id, "disabled": False}
        value: dict = {}
        if stat.min_value is not None:
            value["min"] = stat.min_value
        if stat.max_value is not None:
            value["max"] = stat.max_value
        if value:
            entry["value"] = value
        stat_filters.append(entry)
    return {"filters": payload, "stat_filters": stat_filters}


def _format_price(amount: float | None, currency: str) -> str:
    if amount is None:
        return "—"
    if amount >= 100:
        text = f"{amount:,.0f}"
    elif amount >= 10:
        text = f"{amount:,.1f}".rstrip("0").rstrip(".")
    else:
        text = f"{amount:.2f}".rstrip("0").rstrip(".")
    return f"{text} {currency}".strip() if currency else text


def _method_zh(method: str, fee: int | None) -> str:
    """Classify listing trade mode.

    Official fetch payloads still use ``method: "psapi"`` for both instant
    buyout and in-person trades. Instant buyout listings include a gold ``fee``.
    """
    if fee is not None and fee >= 0:
        return "即刻購買"
    key = (method or "").strip().casefold()
    if key in {"secure", "securable", "instant"} or "secure" in key or "instant" in key:
        return "即刻購買"
    return "面對面"


def _parse_listing(entry: dict) -> TradeListing:
    listing = entry.get("listing") or {}
    item = entry.get("item") or {}
    price = listing.get("price") or {}
    account = listing.get("account") or {}
    amount = price.get("amount")
    try:
        amount_f = float(amount) if amount is not None else None
    except (TypeError, ValueError):
        amount_f = None
    currency = str(price.get("currency") or "").strip()
    name = str(item.get("name") or "").strip()
    type_line = str(item.get("typeLine") or "").strip()
    display = name or type_line or "(未知物品)"
    ilvl_raw = item.get("ilvl")
    try:
        ilvl = int(ilvl_raw) if ilvl_raw is not None else None
    except (TypeError, ValueError):
        ilvl = None
    fee_raw = listing.get("fee")
    try:
        fee = int(fee_raw) if fee_raw is not None else None
    except (TypeError, ValueError):
        fee = None
    method = str(listing.get("method") or "").strip()
    return TradeListing(
        id=str(entry.get("id") or ""),
        name=display,
        name_zh=translate_name(name) or translate_name(type_line) or "",
        type_line=type_line,
        price_amount=amount_f,
        price_currency=currency,
        price_text=_format_price(amount_f, currency),
        account=str(account.get("name") or ""),
        character=str((listing.get("char") or listing.get("character") or "")),
        whisper=str(listing.get("whisper") or ""),
        indexed=str(listing.get("indexed") or ""),
        ilvl=ilvl,
        corrupted=bool(item.get("corrupted")),
        mirrors=bool(item.get("duplicated")),
        method=method,
        method_zh=_method_zh(method, fee),
        fee=fee,
    )


def _post_search(league: str, payload: dict) -> dict:
    league_enc = urllib.parse.quote(league, safe="")
    body = json.dumps(payload).encode("utf-8")
    search = _request(f"{TRADE_BASE}/api/trade/search/{league_enc}", data=body, kind="search")
    if not isinstance(search, dict) or not search.get("id"):
        raise RuntimeError("搜尋失敗：沒有取得搜尋 ID")
    return search


def _fetch_listings(search_id: str, result_ids: list[str], limit: int) -> list[TradeListing]:
    listings: list[TradeListing] = []
    take = max(0, min(limit, FETCH_BATCH * 2))
    batch_ids = result_ids[:take]
    for start in range(0, len(batch_ids), FETCH_BATCH):
        chunk = batch_ids[start : start + FETCH_BATCH]
        if not chunk:
            break
        fetch_url = (
            f"{TRADE_BASE}/api/trade/fetch/{','.join(chunk)}"
            f"?query={urllib.parse.quote(search_id, safe='')}"
        )
        payload = _request(fetch_url, kind="fetch")
        rows = payload.get("result") if isinstance(payload, dict) else None
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    listings.append(_parse_listing(row))
    return listings


def search_items(
    league: str,
    query: str,
    *,
    status: str | None = None,
    online_only: bool | None = None,
    limit: int = 20,
    exact_name: str | None = None,
    exact_type: str | None = None,
    filters: SearchFilters | None = None,
) -> TradeSearchResult:
    """POST trade search then fetch the first listings.

    Free typing uses ``term`` (keyword). Picking a suggestion can pass exact
    ``name`` / ``type`` like the official autocomplete selection.
    ``filters`` adds type / misc / trade / mod constraints.
    """
    league = (league or "").strip()
    if not league:
        raise RuntimeError("請選擇聯盟")

    if status:
        status_option = resolve_status(status)
    elif online_only is False:
        status_option = "any"
    elif online_only is True:
        status_option = "online"
    else:
        status_option = DEFAULT_STATUS

    search_filters = filters or SearchFilters()
    query_text = (query or "").strip()
    if not query_text and not exact_name and not exact_type and search_filters.is_empty():
        raise RuntimeError("請輸入物品關鍵字，或至少設定一項過濾條件")

    cache_key = (
        league,
        status_option,
        query_text.casefold(),
        exact_name or "",
        exact_type or "",
        search_filters.cache_key(),
        int(limit),
    )
    now = time.monotonic()
    cached = _search_cache.get(cache_key)
    if cached and now - cached[0] < SEARCH_CACHE_TTL:
        result = cached[1]
        return TradeSearchResult(
            search_id=result.search_id,
            total=result.total,
            url=result.url,
            query_en=result.query_en,
            listings=list(result.listings),
            from_cache=True,
        )

    remaining = cooldown_remaining()
    if remaining > 0:
        raise TradeRateLimitError(remaining)

    built = build_trade_filters(search_filters)
    query_body: dict = {
        "status": {"option": status_option},
        "stats": [{"type": "and", "filters": built["stat_filters"]}],
    }
    if built["filters"]:
        query_body["filters"] = built["filters"]

    label = ""
    if exact_name or exact_type:
        if exact_name:
            query_body["name"] = exact_name
            label = exact_name
        if exact_type:
            query_body["type"] = exact_type
            if not label:
                label = exact_type
            elif exact_name:
                label = f"{exact_name} {exact_type}".strip()
    elif query_text:
        term, label = resolve_search_term(query_text)
        query_body["term"] = term
    else:
        label = "過濾搜尋"
        if search_filters.stats:
            label = search_filters.stats[0].text or label

    search = _post_search(
        league,
        {"query": query_body, "sort": {"price": "asc"}},
    )
    result_ids = [str(x) for x in (search.get("result") or []) if x]
    total = int(search.get("total") or len(result_ids))
    search_id = str(search["id"])
    result = TradeSearchResult(
        search_id=search_id,
        total=total,
        url=trade_search_url(league, search_id),
        query_en=label,
        listings=_fetch_listings(search_id, result_ids, limit),
        from_cache=False,
    )
    _search_cache[cache_key] = (time.monotonic(), result)
    if len(_search_cache) > 40:
        oldest = sorted(_search_cache.items(), key=lambda item: item[1][0])[:15]
        for key, _value in oldest:
            _search_cache.pop(key, None)
    return result
