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
COMBO_CLASSES = 10
COMBO_SKILLS_PER_CLASS = 2
COMBO_LIMIT = 12
COMBO_WORKERS = 4
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

    @property
    def ladder_label(self) -> str:
        return LADDER_LABELS.get(self.ladder, self.ladder)

    @property
    def page_url(self) -> str:
        return f"{BUILDS_PAGE}/{self.url}"


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


@dataclass
class BuildIndex:
    leagues: list[BuildLeague]


_cache_lock = threading.Lock()
_index_cache: tuple[float, BuildIndex] | None = None
_rank_cache: dict[tuple[str, str], tuple[float, tuple[int, list[RankRow], list[RankRow], list[RankRow]]]] = {}
_dict_cache: dict[str, list[str]] = {}


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
            if not (name and url and version):
                continue
            stamp = (url, ladder)
            if stamp in seen:
                continue
            seen.add(stamp)
            leagues.append(
                BuildLeague(name=name, url=url, snapshot_name=snapshot, version=version, ladder=ladder)
            )
    return leagues


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


def fetch_ranks(league: BuildLeague, force: bool = False) -> tuple[int, list[RankRow], list[RankRow], list[RankRow]]:
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
    gem_names = _dictionary_names(dicts.get("gem", ""))
    class_rows = _rank_rows(
        league,
        "class",
        "class",
        _dictionary_names(dicts.get("class", "")),
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
    packed = (total, class_rows, skill_rows, combo_rows)
    with _cache_lock:
        _rank_cache[cache_key] = (time.time(), packed)
    return packed
