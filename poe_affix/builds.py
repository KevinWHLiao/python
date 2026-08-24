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
BUILDS_PAGE = f"{NINJA_BASE}/poe1/builds"
CACHE_TTL = 15 * 60
COMBO_CLASSES = 12
COMBO_SKILLS_PER_CLASS = 2
COMBO_LIMIT = 20
COMBO_WORKERS = 6
CLASS_STAT_LIMIT = 16
SKILL_STAT_LIMIT = 16
_PRIVATE_LEAGUE_RE = re.compile(r"\(PL\d+\)", re.I)
DPS_ELEMENTS = (
    ("physical", "物理"),
    ("fire", "火焰"),
    ("cold", "冰冷"),
    ("lightning", "閃電"),
    ("chaos", "混沌"),
)
TREND_DAYS = ("day-6", "day-5", "day-4", "day-3", "day-2", "day-1")
GENERIC_ITEM_PREFIXES = ("Rare ", "Magic ", "Normal ", "White ")
USER_AGENT = "PoELookupTool/1.0 (Windows desktop; personal local app)"

ALL = "全部"
LADDER_EXP = "經驗榜"
LADDER_DELVE = "挖掘榜"
LADDER_LABELS = {
    "exp": LADDER_EXP,
    "depthsolo": LADDER_DELVE,
}

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

    @property
    def ladder_label(self) -> str:
        return LADDER_LABELS.get(self.ladder, self.ladder)

    @property
    def page_url(self) -> str:
        return f"{BUILDS_PAGE}/{self.url}"


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


@dataclass
class BuildIndex:
    leagues: list[BuildLeague]


_cache_lock = threading.Lock()
_index_cache: tuple[float, BuildIndex] | None = None
_rank_cache: dict[
    tuple[str, str],
    tuple[float, tuple[int, list[RankRow], list[RankRow], list[RankRow], dict[str, int]]],
] = {}
_dict_cache: dict[str, list[str]] = {}
_history_cache: dict[tuple[str, str, str], tuple[float, tuple[int, dict[str, float], dict[str, float]]]] = {}


def _request(url: str, timeout: int = 45, accept: str = "application/json") -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Referer": BUILDS_PAGE,
        },
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return b""
            last_error = error
            time.sleep(1.0 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
            time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"無法讀取 poe.ninja：{last_error}")


def _fresh(stamp: float) -> bool:
    return (time.time() - stamp) < CACHE_TTL


def translate_class(name: str) -> str:
    return CLASS_ZH.get(name) or translate_name(name) or name


def translate_skill(name: str) -> str:
    return translate_name(name) or name


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


def _unique_names(result: list[tuple[int, str, object]], dim_id: str, dict_name: str, limit: int = 4) -> list[str]:
    dicts = _dictionaries(result)
    names = _dictionary_names(dicts.get(dict_name, ""))
    ordered = sorted(_dimension_counts(result, dim_id), key=lambda item: item[1], reverse=True)
    picked: list[str] = []
    for key, _count in ordered:
        if key < 0 or key >= len(names):
            continue
        name = names[key]
        if any(name.startswith(prefix) for prefix in GENERIC_ITEM_PREFIXES):
            continue
        if name in {"None", "無", ""}:
            continue
        label = translate_name(name) or translate_class(name) or name
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
    row.level = int(_median(levels)) if levels else 0
    row.life = int(_median(lives)) if lives else 0
    row.es = int(_median(shields)) if shields else 0
    dps_values = [parse_stat(text) for text in dps_text]
    ehp_values = [parse_stat(text) for text in ehp_text]
    row.dps = _median(dps_values)
    row.ehp = _median(ehp_values)
    row.dps_share = _dps_share_map(columns, row.extra)
    row.items = _unique_names(result, "items", "item", limit=8)
    row.keystones = _unique_names(result, "keypassives", "keypassive", limit=8)
    row.skills = _unique_names(result, "skills", "gem", limit=10)
    row.supports = [name for name in _unique_names(result, "allgems", "gem", limit=16) if name not in row.skills][:10]
    row.second_ascendancy = _unique_names(result, "secondascendancy", "secondascendancy", limit=5)
    row.bandit = _unique_names(result, "bandit", "bandit", limit=4)
    row.pantheon = _unique_names(result, "pantheon", "pantheon", limit=6)
    row.weapon_modes = _unique_names(result, "weaponmode", "weaponmode", limit=5)
    row.anointed = _unique_names(result, "anointed", "anointed", limit=6)
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
                )
            )
    return leagues


def _league_sort_key(league: BuildLeague) -> tuple:
    """Prefer public challenge leagues, then Standard, then private (PLxxxxx)."""
    name = league.name or ""
    if _PRIVATE_LEAGUE_RE.search(name):
        group = 2
    elif "Standard" in name or name in {"Hardcore", "Solo Self-Found"}:
        group = 1
    else:
        group = 0
    ladder_rank = 0 if league.ladder == "exp" else 1
    return (group, ladder_rank, name.lower())


def is_private_league(name: str) -> bool:
    return bool(_PRIVATE_LEAGUE_RE.search(name or ""))


def fetch_index(force: bool = False) -> BuildIndex:
    global _index_cache
    with _cache_lock:
        if not force and _index_cache and _fresh(_index_cache[0]):
            return _index_cache[1]
    html = _request(BUILDS_PAGE, accept="text/html").decode("utf-8", "replace")
    if not html:
        raise RuntimeError("poe.ninja 沒有回傳流派頁。")
    leagues = _parse_snapshots(html)
    if not leagues:
        raise RuntimeError("poe.ninja 頁面上沒有聯盟榜資料。")
    leagues.sort(key=_league_sort_key)
    index = BuildIndex(leagues=leagues)
    with _cache_lock:
        _index_cache = (time.time(), index)
    return index


def clear_cache() -> None:
    global _index_cache
    with _cache_lock:
        _index_cache = None
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


def _dictionary_names(hash_value: str) -> list[str]:
    if not hash_value:
        return []
    with _cache_lock:
        cached = _dict_cache.get(hash_value)
        if cached is not None:
            return cached
    blob = _request(f"{NINJA_BASE}/poe1/api/builds/dictionary/{hash_value}", accept="*/*")
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
        name_zh = translate_class(name) if kind == "class" else translate_skill(name)
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
    url = f"{NINJA_BASE}/poe1/api/builds/{urllib.parse.quote(league.version)}/search?{query}"
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
        names = _dictionary_names(dicts.get("gem", ""))
    rows: list[RankRow] = []
    for key, count in ordered[:COMBO_SKILLS_PER_CLASS]:
        if key < 0 or key >= len(names):
            continue
        skill = names[key]
        skill_zh = translate_skill(skill)
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
    cache_key = (league.version, league.ladder, label)
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
    class_names = _dictionary_names(dicts.get("class", ""))
    gem_names = _dictionary_names(dicts.get("gem", ""))
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
) -> list[RankRow]:
    labels = [label for label in TREND_DAYS if label in day_totals]
    if not labels or not combo_rows:
        return combo_rows

    def one(row: RankRow) -> RankRow:
        points = [_combo_day_percent(league, row, label, day_totals.get(label, 0)) for label in labels]
        points.append(row.percent)
        _set_trend(row, points)
        return row

    with ThreadPoolExecutor(max_workers=COMBO_WORKERS) as pool:
        list(pool.map(one, combo_rows))
    return combo_rows


def fetch_ranks(
    league: BuildLeague, force: bool = False
) -> tuple[int, list[RankRow], list[RankRow], list[RankRow], dict[str, int]]:
    cache_key = (league.version, league.ladder)
    with _cache_lock:
        cached = _rank_cache.get(cache_key)
        if not force and cached and _fresh(cached[0]):
            return cached[1]
    result = _search_result(league)
    if not result:
        raise RuntimeError("poe.ninja 沒有回傳這個聯盟的流派資料。")
    total = _result_total(result)
    dicts = _dictionaries(result)
    class_names = _dictionary_names(dicts.get("class", ""))
    gem_names = _dictionary_names(dicts.get("gem", ""))
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
    snapshots: list[tuple[str, int, dict[str, float], dict[str, float]]] = []
    with ThreadPoolExecutor(max_workers=COMBO_WORKERS) as pool:
        stat_futures = [pool.submit(_fill_combo_stats, league, row) for row in combo_rows]
        stat_futures.extend(pool.submit(_fill_class_stats, league, row) for row in class_rows[:CLASS_STAT_LIMIT])
        stat_futures.extend(pool.submit(_fill_skill_stats, league, row) for row in skill_rows[:SKILL_STAT_LIMIT])
        hist_futures = [
            pool.submit(_history_snapshot, league, label) for label in labels
        ]
        for future in as_completed(stat_futures):
            try:
                future.result()
            except Exception:
                continue
        for future in hist_futures:
            try:
                snapshots.append(future.result())
            except Exception:
                continue
    snapshots.sort(key=lambda item: labels.index(item[0]) if item[0] in labels else 99)
    day_totals = _apply_history(class_rows, skill_rows, snapshots)
    packed = (total, class_rows, skill_rows, combo_rows, day_totals)
    with _cache_lock:
        _rank_cache[cache_key] = (time.time(), packed)
    return packed
