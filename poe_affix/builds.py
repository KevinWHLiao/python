"""poe.ninja build ranking lookup."""

from __future__ import annotations

import html as html_lib
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from .i18n import translate_name

NINJA_BASE = "https://poe.ninja"
CACHE_TTL = 30 * 60
COMBO_CLASSES = 10
COMBO_SKILLS_PER_CLASS = 2
COMBO_LIMIT = 16
COMBO_WORKERS = 2
CLASS_STAT_LIMIT = 0  # lazy: fill on row select
SKILL_STAT_LIMIT = 0
COMBO_STAT_PREFETCH = 3  # only top combos get DPS/items at load
COMBO_TREND_PREFETCH = 0  # combo day trends: on-demand only
ITEM_DETAIL_LIMIT = 12
REQUEST_MIN_INTERVAL = 0.45  # seconds between poe.ninja calls
REQUEST_MAX_CONCURRENT = 2
_PRIVATE_LEAGUE_RE = re.compile(r"\(PL\d+\)", re.I)
_RETRY_AFTER_RE = re.compile(r"(?:try again|retry)(?:\s+in)?\s+(\d+)\s*s", re.I)
DPS_ELEMENTS = (
    ("physical", "物理"),
    ("fire", "火焰"),
    ("cold", "冰冷"),
    ("lightning", "閃電"),
    ("chaos", "混沌"),
)
TREND_DAYS = ("day-6", "day-5", "day-4", "day-3", "day-2", "day-1")
TREND_DAY_LABELS = ("6日前", "5日前", "4日前", "3日前", "2日前", "昨日", "今日")
GENERIC_ITEM_PREFIXES = ("Rare ", "Magic ", "Normal ", "White ")
USER_AGENT = "PoELookupTool/1.0 (Windows desktop; personal local app)"

ALL = "全部"
LADDER_EXP = "經驗榜"
LADDER_DELVE = "挖掘榜"
LADDER_LABELS = {
    "exp": LADDER_EXP,
    "depthsolo": LADDER_DELVE,
}
GAME_LABELS = {"poe1": "PoE1", "poe2": "PoE2"}

CLASS_ZH = {
    "Scion": "貴族",
    "Ascendant": "昇華使徒",
    "Marauder": "野蠻人",
    "Juggernaut": "勇士",
    "Berserker": "狂戰士",
    "Chieftain": "酋長",
    "Ranger": "遊俠",
    "Raider": "襲擊者",
    "Deadeye": "銳眼",
    "Pathfinder": "追獵者",
    "Warden": "看守者",
    "Witch": "女巫",
    "Occultist": "秘術家",
    "Elementalist": "元素使",
    "Necromancer": "死靈師",
    "Duelist": "決鬥者",
    "Slayer": "處刑者",
    "Gladiator": "衛士",
    "Champion": "冠軍",
    "Templar": "聖堂武僧",
    "Inquisitor": "判官",
    "Hierophant": "聖宗",
    "Guardian": "守護者",
    "Shadow": "暗影刺客",
    "Assassin": "刺客",
    "Trickster": "詐欺師",
    "Saboteur": "破壞者",
    "Luminary": "輝耀使徒",
    "Reliquarian": "遺守使徒",
}

# PoE2 base / ascendancy names from poe2db.tw Ascendancy_class.
CLASS_ZH_POE2 = {
    "Warrior": "戰士",
    "Mercenary": "傭兵",
    "Ranger": "遊俠",
    "Monk": "僧侶",
    "Sorceress": "女術者",
    "Witch": "女巫",
    "Huntress": "女獵人",
    "Martial Artist": "武聖",
    "Gemling Legionnaire": "古靈軍團",
    "Spirit Walker": "魂靈行者",
    "Deadeye": "銳眼",
    "Oracle": "天啟先知",
    "Stormweaver": "風暴編織者",
    "Infernalist": "獄火師",
    "Disciple of Varashta": "瓦拉什塔門徒",
    "Blood Mage": "血法師",
    "Titan": "泰坦",
    "Abyssal Lich": "深淵妖巫",
    "Pathfinder": "追獵者",
    "Shaman": "狂徒薩滿",
    "Witchhunter": "女巫獵人",
    "Tactician": "智勇軍師",
    "Chronomancer": "時空幻術師",
    "Amazon": "亞馬遜",
    "Acolyte of Chayula": "夏烏拉侍僧",
    "Warbringer": "戰爭使者",
    "Smith of Kitava": "奇塔弗工匠",
    "Invoker": "祈靈者",
    "Lich": "巫妖",
    "Ritualist": "儀式行者",
}


def builds_page(game: str = "poe1") -> str:
    realm = "poe2" if game == "poe2" else "poe1"
    return f"{NINJA_BASE}/{realm}/builds"


def api_root(game: str = "poe1") -> str:
    realm = "poe2" if game == "poe2" else "poe1"
    return f"{NINJA_BASE}/{realm}/api"


BUILDS_PAGE = builds_page("poe1")

_ISLAND_RE = re.compile(r"<astro-island\b([^>]*)>", re.I)
_ATTR_RE = re.compile(r'([a-zA-Z0-9:-]+)="([^"]*)"')


@dataclass
class BuildLeague:
    name: str
    url: str
    snapshot_name: str
    version: str
    ladder: str
    character_count: int | None = None
    time_labels: list[str] = field(default_factory=list)
    game: str = "poe1"

    @property
    def ladder_label(self) -> str:
        return LADDER_LABELS.get(self.ladder, self.ladder)

    @property
    def page_url(self) -> str:
        return f"{builds_page(self.game)}/{self.url}"

    @property
    def game_label(self) -> str:
        return GAME_LABELS.get(self.game, self.game)


@dataclass
class SampleChar:
    name: str
    account: str
    level: int = 0
    life: int = 0
    es: int = 0
    dps: float = 0.0
    ehp: float = 0.0
    dps_text: str = ""
    ehp_text: str = ""
    ninja_url: str = ""
    weapon: str = ""
    main_skill: str = ""


@dataclass
class RankRow:
    rank: int
    name: str
    name_zh: str
    count: int
    percent: float
    kind: str
    extra: str = ""
    extra_zh: str = ""
    ninja_url: str = ""
    search_blob: str = field(repr=False, default="")
    dps: float = 0.0
    ehp: float = 0.0
    life: int = 0
    es: int = 0
    level: int = 0
    yesterday: float = 0.0
    delta: float = 0.0
    trend: list[float] = field(default_factory=list)
    items: list[str] = field(default_factory=list)
    keystones: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    supports: list[str] = field(default_factory=list)
    dps_share: dict[str, float] = field(default_factory=dict)
    second_ascendancy: list[str] = field(default_factory=list)
    bandit: list[str] = field(default_factory=list)
    pantheon: list[str] = field(default_factory=list)
    weapon_modes: list[str] = field(default_factory=list)
    anointed: list[str] = field(default_factory=list)
    samples: list[SampleChar] = field(default_factory=list)
    spirit_gems: list[str] = field(default_factory=list)
    traits: list[str] = field(default_factory=list)


@dataclass
class BuildIndex:
    leagues: list[BuildLeague]


_cache_lock = threading.Lock()
_index_cache: dict[str, tuple[float, BuildIndex]] = {}
_rank_cache: dict[
    tuple[str, str, str],
    tuple[float, tuple[int, list[RankRow], list[RankRow], list[RankRow], dict[str, int]]],
] = {}
_dict_cache: dict[str, list[str]] = {}
_history_cache: dict[tuple[str, str, str, str], tuple[float, tuple[int, dict[str, float], dict[str, float]]]] = {}


class _NinjaGate:
    """Limit concurrent / burst requests so the shared IP isn't banned from the site."""

    def __init__(self, min_interval: float, max_concurrent: int) -> None:
        self._min_interval = min_interval
        self._max_concurrent = max_concurrent
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._inflight = 0
        self._next_slot = 0.0
        self._cooldown_until = 0.0

    def acquire(self) -> None:
        with self._cond:
            while True:
                now = time.monotonic()
                wait = max(
                    0.0,
                    self._cooldown_until - now,
                    self._next_slot - now,
                )
                if wait <= 0 and self._inflight < self._max_concurrent:
                    self._inflight += 1
                    self._next_slot = now + self._min_interval
                    return
                self._cond.wait(timeout=max(wait, 0.05) if wait > 0 else 0.05)

    def release(self) -> None:
        with self._cond:
            self._inflight = max(0, self._inflight - 1)
            self._cond.notify_all()

    def cooldown(self, seconds: float) -> None:
        if seconds <= 0:
            return
        with self._cond:
            self._cooldown_until = max(self._cooldown_until, time.monotonic() + seconds)
            self._cond.notify_all()


_ninja_gate = _NinjaGate(REQUEST_MIN_INTERVAL, REQUEST_MAX_CONCURRENT)


def _retry_wait_seconds(error: urllib.error.HTTPError) -> float:
    header = error.headers.get("Retry-After") if error.headers else None
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    try:
        body = error.read().decode("utf-8", "replace")
    except Exception:
        body = ""
    match = _RETRY_AFTER_RE.search(body or "")
    if match:
        return float(match.group(1))
    return 20.0 if error.code == 429 else 2.0


def _request(url: str, timeout: int = 45, accept: str = "application/json") -> bytes:
    referer = builds_page("poe2") if "/poe2/" in url else builds_page("poe1")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Referer": referer,
        },
    )
    last_error: Exception | None = None
    for attempt in range(5):
        _ninja_gate.acquire()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return b""
            last_error = error
            if error.code in {429, 503}:
                wait = min(_retry_wait_seconds(error), 180.0)
                _ninja_gate.cooldown(wait)
                time.sleep(min(wait, 5.0) if attempt < 2 else wait)
            else:
                time.sleep(1.0 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
            time.sleep(1.0 * (attempt + 1))
        finally:
            _ninja_gate.release()
    raise RuntimeError(f"無法讀取 poe.ninja：{last_error}")


def _fresh(stamp: float) -> bool:
    return (time.time() - stamp) < CACHE_TTL


def translate_class(name: str, game: str = "poe1") -> str:
    if game == "poe2":
        hit = CLASS_ZH_POE2.get(name)
        if hit:
            return hit
    return CLASS_ZH.get(name) or translate_name(name, game=game) or name


def translate_skill(name: str, game: str = "poe1") -> str:
    return translate_name(name, game=game) or name


def format_daily_trend(row: RankRow) -> str:
    """Human-readable day-by-day share line for detail / copy."""
    if not row.trend:
        return ""
    labels = list(TREND_DAY_LABELS[-len(row.trend) :])
    return " → ".join(f"{label} {value:.1f}%" for label, value in zip(labels, row.trend))


def matches(row: RankRow, query: str) -> bool:
    text = (query or "").strip().lower()
    if not text:
        return True
    return all(token in row.search_blob for token in text.split())


def _search_blob(*parts: object) -> str:
    chunks = [str(part).strip().lower() for part in parts if part not in (None, "")]
    return " ".join(chunks)


def parse_stat(text: str) -> float:
    raw = (text or "").strip().replace(",", "").replace("%", "")
    if not raw or raw in {"—", "-"}:
        return 0.0
    multiplier = 1.0
    suffix = raw[-1].upper()
    if suffix == "B":
        multiplier = 1_000_000_000
        raw = raw[:-1]
    elif suffix == "M":
        multiplier = 1_000_000
        raw = raw[:-1]
    elif suffix == "K":
        multiplier = 1_000
        raw = raw[:-1]
    try:
        return float(raw) * multiplier
    except ValueError:
        return 0.0


def format_stat(value: float | int | None) -> str:
    if value is None:
        return "—"
    number = float(value)
    if number <= 0:
        return "—"
    if number >= 1_000_000_000:
        text = f"{number / 1_000_000_000:.1f}B"
    elif number >= 1_000_000:
        text = f"{number / 1_000_000:.1f}M"
    elif number >= 10_000:
        text = f"{number / 1_000:.0f}k"
    elif number >= 1_000:
        text = f"{number / 1_000:.1f}k"
    else:
        text = f"{number:.0f}"
    return text.replace(".0B", "B").replace(".0M", "M").replace(".0k", "k")


def sparkline(values: list[float]) -> str:
    if len(values) < 2:
        return "—"
    blocks = "▁▂▃▄▅▆▇█"
    low = min(values)
    high = max(values)
    if high <= low:
        return blocks[0] * len(values)
    return "".join(blocks[min(7, int(round((value - low) / (high - low) * 7)))] for value in values)


def _median(values: list[float] | list[int]) -> float:
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return 0.0
    numbers.sort()
    return numbers[len(numbers) // 2]


def _packed_varints(blob: bytes) -> list[int]:
    values: list[int] = []
    index = 0
    while index < len(blob):
        result = 0
        shift = 0
        while index < len(blob):
            byte = blob[index]
            index += 1
            result |= (byte & 127) << shift
            if not (byte & 128):
                break
            shift += 7
        values.append(result)
    return values


def _table_columns(result: list[tuple[int, str, object]]) -> dict[str, dict[str, object]]:
    columns: dict[str, dict[str, object]] = {}
    for field, kind, value in result:
        if field != 12 or kind != "bytes":
            continue
        inner = _decode_message(bytes(value))
        name = ""
        packed = b""
        strings: list[str] = []
        for sub_field, sub_kind, sub_value in inner:
            if sub_field == 1 and sub_kind == "bytes" and not name:
                name = _as_text(sub_value)
            elif sub_field == 6 and sub_kind == "bytes":
                packed = bytes(sub_value)
            elif sub_field == 7 and sub_kind == "bytes":
                strings.append(_as_text(sub_value))
        if name:
            columns[name] = {"packed": packed, "strings": strings}
    return columns


def _column_strings(columns: dict[str, dict[str, object]], *names: str) -> list[str]:
    for name in names:
        strings = columns.get(name, {}).get("strings")
        if isinstance(strings, list) and strings:
            return [str(item) for item in strings]
    for key, data in columns.items():
        if any(key == name or key.startswith(f"{name}-") or key.endswith(name) for name in names):
            strings = data.get("strings")
            if isinstance(strings, list) and strings:
                return [str(item) for item in strings]
    return []


def _dps_strings(columns: dict[str, dict[str, object]], skill: str = "") -> list[str]:
    if skill:
        keyed = _column_strings(columns, f"dps-{skill}.total")
        if keyed:
            return keyed
    direct = _column_strings(columns, "dps.total")
    if direct:
        return direct
    series: list[list[str]] = []
    for key, data in columns.items():
        if not (key.startswith("dps-") and key.endswith(".total")):
            continue
        strings = data.get("strings")
        if isinstance(strings, list) and strings:
            series.append([str(item) for item in strings])
    if not series:
        return []
    length = max(len(column) for column in series)
    picked: list[str] = []
    for index in range(length):
        best_text = ""
        best_value = 0.0
        for column in series:
            if index >= len(column):
                continue
            value = parse_stat(column[index])
            if value > best_value:
                best_value = value
                best_text = column[index]
        picked.append(best_text)
    return picked


def _unique_names(
    result: list[tuple[int, str, object]],
    dim_id: str,
    dict_name: str,
    limit: int = 4,
    *,
    total: int = 0,
    with_share: bool = False,
    game: str = "poe1",
) -> list[str]:
    dicts = _dictionaries(result)
    names = _dictionary_names(dicts.get(dict_name, ""), game=game)
    ordered = sorted(_dimension_counts(result, dim_id), key=lambda item: item[1], reverse=True)
    picked: list[str] = []
    for key, count in ordered:
        if key < 0 or key >= len(names):
            continue
        name = names[key]
        if any(name.startswith(prefix) for prefix in GENERIC_ITEM_PREFIXES):
            continue
        if name in {"None", "無", ""}:
            continue
        label = translate_name(name, game=game) or translate_class(name, game=game) or name
        if with_share and total > 0 and count > 0:
            label = f"{label} {count / total * 100:.1f}%"
        if label not in picked:
            picked.append(label)
        if len(picked) >= limit:
            break
    return picked


def _median_packed_share(columns: dict[str, dict[str, object]], skill: str, element: str) -> float:
    keys = []
    if skill:
        keys.append(f"dps-{skill}.{element}")
    keys.append(f"dps.{element}")
    for key in keys:
        packed = columns.get(key, {}).get("packed")
        if not packed:
            continue
        values = _packed_varints(bytes(packed))
        if values:
            return float(_median(values))
    return 0.0


def _dps_share_map(columns: dict[str, dict[str, object]], skill: str = "") -> dict[str, float]:
    shares: dict[str, float] = {}
    for key, label in DPS_ELEMENTS:
        value = _median_packed_share(columns, skill, key)
        if value > 0:
            shares[label] = value
    return shares


def _apply_table_stats(league: BuildLeague, result: list[tuple[int, str, object]], row: RankRow) -> None:
    columns = _table_columns(result)
    levels = list(columns.get("level", {}).get("packed") or b"")
    lives = _packed_varints(bytes(columns.get("life", {}).get("packed") or b""))
    shields = _packed_varints(bytes(columns.get("energyshield", {}).get("packed") or b""))
    dps_text = _dps_strings(columns, row.extra)
    ehp_text = _column_strings(columns, "ehp__str")
    names = _column_strings(columns, "name")
    accounts = _column_strings(columns, "account")
    total = _result_total(result) or row.count
    game = league.game
    row.level = int(_median(levels)) if levels else 0
    row.life = int(_median(lives)) if lives else 0
    row.es = int(_median(shields)) if shields else 0
    dps_values = [parse_stat(text) for text in dps_text]
    ehp_values = [parse_stat(text) for text in ehp_text]
    row.dps = _median(dps_values)
    row.ehp = _median(ehp_values)
    row.dps_share = _dps_share_map(columns, row.extra)
    row.items = _unique_names(
        result, "items", "item", limit=ITEM_DETAIL_LIMIT, total=total, with_share=True, game=game
    )
    row.keystones = _unique_names(
        result,
        "keypassives",
        "keypassive",
        limit=ITEM_DETAIL_LIMIT,
        total=total,
        with_share=True,
        game=game,
    )
    if not row.keystones:
        row.keystones = _unique_names(
            result, "keystones", "keystone", limit=ITEM_DETAIL_LIMIT, total=total, with_share=True, game=game
        )
    row.skills = _unique_names(result, "skills", "gem", limit=10, total=total, with_share=True, game=game)
    row.spirit_gems = _unique_names(
        result, "spiritgems", "gem", limit=8, total=total, with_share=True, game=game
    )
    row.traits = _unique_names(result, "traits", "skilltrait", limit=8, total=total, with_share=True, game=game)
    supports = [
        name
        for name in _unique_names(result, "allgems", "gem", limit=16, total=total, with_share=True, game=game)
        if name not in row.skills
    ][:10]
    if not supports and row.spirit_gems:
        supports = [name for name in row.spirit_gems if name not in row.skills][:10]
    row.supports = supports
    row.second_ascendancy = _unique_names(result, "secondascendancy", "secondascendancy", limit=5, game=game)
    row.bandit = _unique_names(result, "bandit", "bandit", limit=4, game=game)
    row.pantheon = _unique_names(result, "pantheon", "pantheon", limit=6, game=game)
    row.weapon_modes = _unique_names(
        result, "weaponmode", "weaponmode", limit=5, total=total, with_share=True, game=game
    )
    row.anointed = _unique_names(
        result, "anointed", "anointed", limit=6, total=total, with_share=True, game=game
    )
    weapons = row.weapon_modes
    main_skill = row.extra_zh or row.extra or (row.skills[0] if row.skills else "")
    samples: list[SampleChar] = []
    count = min(len(names), len(accounts), 12)
    for index in range(count):
        query = urllib.parse.urlencode({"account": accounts[index], "character": names[index]})
        samples.append(
            SampleChar(
                name=names[index],
                account=accounts[index],
                level=int(levels[index]) if index < len(levels) else 0,
                life=int(lives[index]) if index < len(lives) else 0,
                es=int(shields[index]) if index < len(shields) else 0,
                dps=dps_values[index] if index < len(dps_values) else 0.0,
                ehp=ehp_values[index] if index < len(ehp_values) else 0.0,
                dps_text=dps_text[index] if index < len(dps_text) else "",
                ehp_text=ehp_text[index] if index < len(ehp_text) else "",
                ninja_url=f"{league.page_url}?{query}",
                weapon=weapons[0] if weapons else "",
                main_skill=main_skill,
            )
        )
    row.samples = samples
    extra = [
        *row.items,
        *row.keystones,
        *row.skills,
        *row.supports,
        *row.spirit_gems,
        *row.traits,
        *row.second_ascendancy,
        *row.bandit,
        *row.pantheon,
        *row.weapon_modes,
        *row.anointed,
    ]
    row.search_blob = _search_blob(
        row.name,
        row.name_zh,
        row.extra,
        row.extra_zh,
        league.name,
        *extra,
        *[sample.name for sample in samples],
    )


def _set_trend(row: RankRow, points: list[float]) -> None:
    row.trend = points
    if len(points) >= 2:
        row.yesterday = points[-2]
        row.delta = points[-1] - points[-2]
    elif points:
        row.yesterday = 0.0
        row.delta = 0.0


def _dim_percents(result: list[tuple[int, str, object]], dim_id: str, names: list[str], total: int) -> dict[str, float]:
    mapping: dict[str, float] = {}
    for key, count in _dimension_counts(result, dim_id):
        if key < 0 or key >= len(names):
            continue
        mapping[names[key]] = (count / total * 100) if total else 0.0
    return mapping


def _decode_astro(node):
    if isinstance(node, list) and len(node) == 2 and isinstance(node[0], int):
        tag, value = node
        if tag == 0:
            return _decode_astro(value) if isinstance(value, (list, dict)) else value
        if tag == 1 and isinstance(value, list):
            return [_decode_astro(item) for item in value]
        return _decode_astro(value)
    if isinstance(node, dict):
        return {key: _decode_astro(val) for key, val in node.items()}
    if isinstance(node, list):
        return [_decode_astro(item) for item in node]
    return node


def _parse_snapshots(html: str) -> list[BuildLeague]:
    leagues: list[BuildLeague] = []
    seen: set[tuple[str, str]] = set()
    for attrs in _ISLAND_RE.findall(html):
        props = dict(_ATTR_RE.findall(attrs))
        if props.get("component-export") != "TopBar":
            continue
        raw = html_lib.unescape(props.get("props") or "").replace("&quot;", '"')
        if not raw:
            continue
        decoded = _decode_astro(json.loads(raw))
        state = decoded.get("poe1IndexState") if isinstance(decoded, dict) else None
        versions = (state or {}).get("snapshotVersions") if isinstance(state, dict) else None
        if not isinstance(versions, list):
            continue
        for item in versions:
            if not isinstance(item, dict):
                continue
            ladder = str(item.get("type") or "")
            if ladder not in LADDER_LABELS:
                continue
            name = str(item.get("name") or "")
            url = str(item.get("url") or "")
            version = str(item.get("version") or "")
            snapshot = str(item.get("snapshotName") or url)
            labels = item.get("timeMachineLabels") if isinstance(item.get("timeMachineLabels"), list) else []
            time_labels = [str(label) for label in labels]
            if not (name and url and version):
                continue
            stamp = (url, ladder)
            if stamp in seen:
                continue
            seen.add(stamp)
            leagues.append(
                BuildLeague(
                    name=name,
                    url=url,
                    snapshot_name=snapshot,
                    version=version,
                    ladder=ladder,
                    time_labels=time_labels,
                    game="poe1",
                )
            )
    return leagues


def _parse_poe2_index() -> list[BuildLeague]:
    payload = _request(f"{api_root('poe2')}/data/index-state", accept="application/json")
    if not payload:
        raise RuntimeError("poe.ninja 沒有回傳 PoE2 聯盟索引。")
    data = json.loads(payload.decode("utf-8"))
    versions = data.get("snapshotVersions") if isinstance(data, dict) else None
    if not isinstance(versions, list) or not versions:
        raise RuntimeError("poe.ninja PoE2 索引沒有聯盟快照。")
    totals: dict[str, int] = {}
    try:
        meta = json.loads(
            _request(f"{api_root('poe2')}/data/build-index-state", accept="application/json").decode("utf-8")
        )
        for item in meta.get("leagueBuilds") or []:
            if isinstance(item, dict) and item.get("leagueUrl"):
                totals[str(item["leagueUrl"])] = int(item.get("total") or 0)
    except Exception:
        totals = {}
    leagues: list[BuildLeague] = []
    seen: set[str] = set()
    for item in versions:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        url = str(item.get("url") or "")
        version = str(item.get("version") or "")
        snapshot = str(item.get("snapshotName") or url)
        labels = item.get("timeMachineLabels") if isinstance(item.get("timeMachineLabels"), list) else []
        time_labels = [str(label) for label in labels]
        if not (name and url and version) or url in seen:
            continue
        seen.add(url)
        leagues.append(
            BuildLeague(
                name=name,
                url=url,
                snapshot_name=snapshot,
                version=version,
                ladder="exp",
                time_labels=time_labels,
                game="poe2",
                character_count=totals.get(url),
            )
        )
    leagues.sort(
        key=lambda league: (
            0 if (league.character_count or 0) > 1000 else 1,
            0 if not any(token in (league.name or "") for token in ("Qualifier", "Race", "Exilecon")) else 1,
            -(league.character_count or 0),
            *_league_sort_key(league),
        )
    )
    return leagues


def _league_sort_key(league: BuildLeague) -> tuple:
    """Prefer public challenge leagues, then Standard, then private (PLxxxxx) / races."""
    name = league.name or ""
    if _PRIVATE_LEAGUE_RE.search(name) or "Race" in name or name.startswith("0."):
        group = 2
    elif "Standard" in name or name in {"Hardcore", "Solo Self-Found"}:
        group = 1
    else:
        group = 0
    ladder_rank = 0 if league.ladder == "exp" else 1
    return (group, ladder_rank, name.lower())


def is_private_league(name: str) -> bool:
    return bool(_PRIVATE_LEAGUE_RE.search(name or ""))


def fetch_index(game: str = "poe1", force: bool = False) -> BuildIndex:
    game = "poe2" if game == "poe2" else "poe1"
    with _cache_lock:
        cached = _index_cache.get(game)
        if not force and cached and _fresh(cached[0]):
            return cached[1]
    if game == "poe2":
        leagues = _parse_poe2_index()
    else:
        html = _request(builds_page("poe1"), accept="text/html").decode("utf-8", "replace")
        if not html:
            raise RuntimeError("poe.ninja 沒有回傳流派頁。")
        leagues = _parse_snapshots(html)
        leagues.sort(key=_league_sort_key)
    if not leagues:
        raise RuntimeError("poe.ninja 頁面上沒有聯盟榜資料。")
    index = BuildIndex(leagues=leagues)
    with _cache_lock:
        _index_cache[game] = (time.time(), index)
    return index


def clear_cache() -> None:
    with _cache_lock:
        _index_cache.clear()
        _rank_cache.clear()
        _dict_cache.clear()
        _history_cache.clear()


def _read_varint(buf: bytes, index: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        byte = buf[index]
        index += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return result, index
        shift += 7


def _decode_message(buf: bytes) -> list[tuple[int, str, object]]:
    index = 0
    fields: list[tuple[int, str, object]] = []
    while index < len(buf):
        key, index = _read_varint(buf, index)
        field = key >> 3
        wire = key & 7
        if wire == 0:
            value, index = _read_varint(buf, index)
            fields.append((field, "varint", value))
        elif wire == 1:
            index += 8
        elif wire == 2:
            length, index = _read_varint(buf, index)
            blob = buf[index : index + length]
            index += length
            fields.append((field, "bytes", blob))
        elif wire == 5:
            index += 4
        else:
            break
    return fields


def _as_text(blob: object) -> str:
    if not isinstance(blob, (bytes, bytearray)):
        return str(blob or "")
    try:
        text = bytes(blob).decode("utf-8")
    except UnicodeDecodeError:
        return ""
    if text and all(ch.isprintable() or ch in "\n\r\t" for ch in text):
        return text
    return ""


def _unwrap_result(payload: bytes) -> list[tuple[int, str, object]]:
    fields = _decode_message(payload)
    for field, kind, value in fields:
        if field == 1 and kind == "bytes" and isinstance(value, (bytes, bytearray)):
            return _decode_message(bytes(value))
    return fields


def _decode_native_strings(blob: bytes) -> list[str]:
    if len(blob) < 36 or blob[:4] != b"NDIC":
        return []
    count = int.from_bytes(blob[12:16], "little")
    table = int.from_bytes(blob[28:32], "little")
    lengths_size = int.from_bytes(blob[32:36], "little")
    cursor = 36 + table * 8
    data_at = cursor + lengths_size
    names: list[str] = []
    for _ in range(count):
        size = 0
        shift = 0
        while cursor < len(blob):
            byte = blob[cursor]
            cursor += 1
            size |= (byte & 127) << shift
            if not (byte & 128):
                break
            shift += 7
        names.append(blob[data_at : data_at + size].decode("utf-8", "replace"))
        data_at += size
    return names


def _dictionary_names(hash_value: str, game: str = "poe1") -> list[str]:
    if not hash_value:
        return []
    with _cache_lock:
        cached = _dict_cache.get(hash_value)
        if cached is not None:
            return cached
    blob = _request(f"{api_root(game)}/builds/dictionary/{hash_value}", accept="*/*")
    names = _decode_native_strings(blob)
    with _cache_lock:
        _dict_cache[hash_value] = names
    return names


def _dimension_counts(result: list[tuple[int, str, object]], dim_id: str) -> list[tuple[int, int]]:
    found: list[tuple[int, int]] = []
    for field, kind, value in result:
        if field != 2 or kind != "bytes" or not isinstance(value, (bytes, bytearray)):
            continue
        sub = _decode_message(bytes(value))
        ident = ""
        counts: list[tuple[int, int]] = []
        for sub_field, sub_kind, sub_value in sub:
            if sub_field in {1, 2} and sub_kind == "bytes" and not ident:
                ident = _as_text(sub_value)
            if sub_field == 3 and sub_kind == "bytes" and isinstance(sub_value, (bytes, bytearray)):
                rec = {item[0]: item[2] for item in _decode_message(bytes(sub_value)) if item[1] == "varint"}
                key = int(rec.get(1) or 0)
                count = int(rec.get(2) or 0)
                if count:
                    counts.append((key, count))
        if ident == dim_id:
            found = counts
            break
    return found


def _dictionaries(result: list[tuple[int, str, object]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for field, kind, value in result:
        if field != 6 or kind != "bytes" or not isinstance(value, (bytes, bytearray)):
            continue
        rec: dict[int, str] = {}
        for sub_field, sub_kind, sub_value in _decode_message(bytes(value)):
            if sub_kind == "bytes" and sub_field not in rec:
                rec[sub_field] = _as_text(sub_value)
        name = rec.get(1) or ""
        digest = rec.get(2) or ""
        if name and digest:
            mapping[name] = digest
    return mapping


def _rank_rows(
    league: BuildLeague,
    kind: str,
    dim_id: str,
    names: list[str],
    counts: list[tuple[int, int]],
    total: int,
    query_key: str,
) -> list[RankRow]:
    rows: list[RankRow] = []
    ordered = sorted(counts, key=lambda item: item[1], reverse=True)
    for index, (key, count) in enumerate(ordered, start=1):
        if key < 0 or key >= len(names):
            continue
        name = names[key]
        name_zh = translate_class(name, league.game) if kind == "class" else translate_skill(name, league.game)
        query = urllib.parse.urlencode({query_key: name})
        percent = (count / total * 100) if total else 0.0
        rows.append(
            RankRow(
                rank=index,
                name=name,
                name_zh=name_zh,
                count=count,
                percent=percent,
                kind=kind,
                ninja_url=f"{league.page_url}?{query}",
                search_blob=_search_blob(name, name_zh, league.name),
            )
        )
    return rows


def _search_result(league: BuildLeague, extra: dict[str, str] | None = None) -> list[tuple[int, str, object]]:
    params = {"overview": league.snapshot_name or league.url, "type": league.ladder}
    if extra:
        params.update(extra)
    query = urllib.parse.urlencode(params)
    url = f"{api_root(league.game)}/builds/{urllib.parse.quote(league.version)}/search?{query}"
    payload = _request(url, accept="application/x-protobuf,*/*")
    if not payload:
        return []
    return _unwrap_result(payload)


def _result_total(result: list[tuple[int, str, object]]) -> int:
    for field, kind, value in result:
        if field == 1 and kind == "varint":
            return int(value)
    return 0


def _skill_counts(result: list[tuple[int, str, object]]) -> list[tuple[int, int]]:
    return _dimension_counts(result, "skills") or _dimension_counts(result, "allgems")


def _combo_for_class(
    league: BuildLeague,
    class_row: RankRow,
    gem_names: list[str],
    global_total: int,
) -> list[RankRow]:
    try:
        result = _search_result(league, {"class": class_row.name})
    except RuntimeError:
        return []
    if result:
        _apply_table_stats(league, result, class_row)
    counts = _skill_counts(result)
    if not counts:
        return []
    names = gem_names
    ordered = sorted(counts, key=lambda item: item[1], reverse=True)
    if any(key < 0 or key >= len(names) for key, _count in ordered[:COMBO_SKILLS_PER_CLASS]):
        dicts = _dictionaries(result)
        names = _dictionary_names(dicts.get("gem", ""), game=league.game)
    rows: list[RankRow] = []
    for key, count in ordered[:COMBO_SKILLS_PER_CLASS]:
        if key < 0 or key >= len(names):
            continue
        skill = names[key]
        skill_zh = translate_skill(skill, league.game)
        query = urllib.parse.urlencode({"class": class_row.name, "skills": skill})
        percent = (count / global_total * 100) if global_total else 0.0
        rows.append(
            RankRow(
                rank=0,
                name=class_row.name,
                name_zh=class_row.name_zh,
                count=count,
                percent=percent,
                kind="combo",
                extra=skill,
                extra_zh=skill_zh,
                ninja_url=f"{league.page_url}?{query}",
                search_blob=_search_blob(class_row.name, class_row.name_zh, skill, skill_zh, league.name),
            )
        )
    return rows


def _combo_rows(league: BuildLeague, class_rows: list[RankRow], gem_names: list[str], total: int) -> list[RankRow]:
    if not class_rows or not total:
        return []
    combos: list[RankRow] = []
    with ThreadPoolExecutor(max_workers=COMBO_WORKERS) as pool:
        futures = [
            pool.submit(_combo_for_class, league, row, gem_names, total)
            for row in class_rows[:COMBO_CLASSES]
        ]
        for future in as_completed(futures):
            try:
                combos.extend(future.result())
            except Exception:
                continue
    combos.sort(key=lambda row: row.percent, reverse=True)
    ranked: list[RankRow] = []
    seen: set[tuple[str, str]] = set()
    for row in combos:
        stamp = (row.name, row.extra)
        if stamp in seen:
            continue
        seen.add(stamp)
        row.rank = len(ranked) + 1
        ranked.append(row)
        if len(ranked) >= COMBO_LIMIT:
            break
    return ranked


def _fill_combo_stats(league: BuildLeague, row: RankRow) -> None:
    try:
        result = _search_result(league, {"class": row.name, "skills": row.extra})
    except RuntimeError:
        return
    if result:
        _apply_table_stats(league, result, row)


def _fill_class_stats(league: BuildLeague, row: RankRow) -> None:
    try:
        result = _search_result(league, {"class": row.name})
    except RuntimeError:
        return
    if result:
        _apply_table_stats(league, result, row)


def _fill_skill_stats(league: BuildLeague, row: RankRow) -> None:
    try:
        result = _search_result(league, {"skills": row.name})
    except RuntimeError:
        return
    if not result:
        return
    saved = row.extra
    row.extra = row.name
    _apply_table_stats(league, result, row)
    row.extra = saved


def enrich_row(league: BuildLeague, row: RankRow) -> RankRow:
    """Fill DPS / items / samples for a rank row (safe to call from UI)."""
    if row.kind == "combo" and row.extra:
        _fill_combo_stats(league, row)
    elif row.kind == "class":
        _fill_class_stats(league, row)
    else:
        _fill_skill_stats(league, row)
    return row


def _history_snapshot(league: BuildLeague, label: str) -> tuple[str, int, dict[str, float], dict[str, float]]:
    cache_key = (league.game, league.version, league.ladder, label)
    with _cache_lock:
        cached = _history_cache.get(cache_key)
        if cached and _fresh(cached[0]):
            total, class_pcts, skill_pcts = cached[1]
            return label, total, class_pcts, skill_pcts
    try:
        result = _search_result(league, {"timeMachine": label})
    except RuntimeError:
        return label, 0, {}, {}
    if not result:
        return label, 0, {}, {}
    total = _result_total(result)
    dicts = _dictionaries(result)
    class_names = _dictionary_names(dicts.get("class", ""), game=league.game)
    gem_names = _dictionary_names(dicts.get("gem", ""), game=league.game)
    class_pcts = _dim_percents(result, "class", class_names, total)
    skill_pcts = _dim_percents(result, "skills", gem_names, total)
    if not skill_pcts:
        skill_pcts = _dim_percents(result, "allgems", gem_names, total)
    with _cache_lock:
        _history_cache[cache_key] = (time.time(), (total, class_pcts, skill_pcts))
    return label, total, class_pcts, skill_pcts


def _apply_history(
    class_rows: list[RankRow],
    skill_rows: list[RankRow],
    snapshots: list[tuple[str, int, dict[str, float], dict[str, float]]],
) -> dict[str, int]:
    totals: dict[str, int] = {}
    for row in class_rows:
        points = [mapping.get(row.name, 0.0) for _label, _total, mapping, _skills in snapshots]
        points.append(row.percent)
        _set_trend(row, points)
    for row in skill_rows:
        points = [mapping.get(row.name, 0.0) for _label, _total, _classes, mapping in snapshots]
        points.append(row.percent)
        _set_trend(row, points)
    for label, total, _classes, _skills in snapshots:
        totals[label] = total
    return totals


def _combo_day_percent(league: BuildLeague, row: RankRow, label: str, day_total: int) -> float:
    if not day_total:
        return 0.0
    try:
        result = _search_result(league, {"class": row.name, "skills": row.extra, "timeMachine": label})
    except RuntimeError:
        return 0.0
    if not result:
        return 0.0
    return _result_total(result) / day_total * 100


def fetch_combo_trends(
    league: BuildLeague,
    combo_rows: list[RankRow],
    day_totals: dict[str, int],
    *,
    limit: int | None = None,
) -> list[RankRow]:
    labels = [label for label in TREND_DAYS if label in day_totals]
    if not labels or not combo_rows:
        return combo_rows
    pending = [row for row in combo_rows if not row.trend]
    if limit is not None:
        pending = pending[: max(0, limit)]
    if not pending:
        return combo_rows

    def one(row: RankRow) -> RankRow:
        points = [_combo_day_percent(league, row, label, day_totals.get(label, 0)) for label in labels]
        points.append(row.percent)
        _set_trend(row, points)
        return row

    # Sequential-ish: gate already serializes network; keep workers low.
    with ThreadPoolExecutor(max_workers=COMBO_WORKERS) as pool:
        list(pool.map(one, pending))
    return combo_rows


def enrich_combo_trend(
    league: BuildLeague,
    row: RankRow,
    day_totals: dict[str, int],
) -> RankRow:
    """Fill day-by-day share for one combo row (avoids blasting all combos at once)."""
    if row.kind != "combo" or row.trend or not day_totals:
        return row
    fetch_combo_trends(league, [row], day_totals, limit=1)
    return row


def fetch_ranks(
    league: BuildLeague, force: bool = False
) -> tuple[int, list[RankRow], list[RankRow], list[RankRow], dict[str, int]]:
    cache_key = (league.game, league.version, league.ladder)
    with _cache_lock:
        cached = _rank_cache.get(cache_key)
        if not force and cached and _fresh(cached[0]):
            return cached[1]
    result = _search_result(league)
    if not result:
        raise RuntimeError("poe.ninja 沒有回傳這個聯盟的流派資料。")
    total = _result_total(result)
    dicts = _dictionaries(result)
    class_names = _dictionary_names(dicts.get("class", ""), game=league.game)
    gem_names = _dictionary_names(dicts.get("gem", ""), game=league.game)
    class_rows = _rank_rows(
        league,
        "class",
        "class",
        class_names,
        _dimension_counts(result, "class"),
        total,
        "class",
    )
    skill_rows = _rank_rows(
        league,
        "skill",
        "skills",
        gem_names,
        _skill_counts(result),
        total,
        "skills",
    )
    combo_rows = _combo_rows(league, class_rows, gem_names, total)
    labels = [label for label in TREND_DAYS if label in (league.time_labels or TREND_DAYS)]
    # History first (drives class/skill sparklines); keep concurrency low via gate.
    snapshots: list[tuple[str, int, dict[str, float], dict[str, float]]] = []
    with ThreadPoolExecutor(max_workers=COMBO_WORKERS) as pool:
        hist_futures = [pool.submit(_history_snapshot, league, label) for label in labels]
        for future in as_completed(hist_futures):
            try:
                snapshots.append(future.result())
            except Exception:
                continue
    snapshots.sort(key=lambda item: labels.index(item[0]) if item[0] in labels else 99)
    day_totals = _apply_history(class_rows, skill_rows, snapshots)
    # Only prefetch a few combo detail payloads; the rest load when the user selects a row.
    for row in combo_rows[:COMBO_STAT_PREFETCH]:
        try:
            _fill_combo_stats(league, row)
        except Exception:
            continue
    if CLASS_STAT_LIMIT:
        for row in class_rows[:CLASS_STAT_LIMIT]:
            try:
                _fill_class_stats(league, row)
            except Exception:
                continue
    if SKILL_STAT_LIMIT:
        for row in skill_rows[:SKILL_STAT_LIMIT]:
            try:
                _fill_skill_stats(league, row)
            except Exception:
                continue
    if COMBO_TREND_PREFETCH:
        fetch_combo_trends(league, combo_rows, day_totals, limit=COMBO_TREND_PREFETCH)
    packed = (total, class_rows, skill_rows, combo_rows, day_totals)
    with _cache_lock:
        _rank_cache[cache_key] = (time.time(), packed)
    return packed
