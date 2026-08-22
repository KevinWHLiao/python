"""Crafting bench recipes and unlock areas from poedb.tw."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Callable

from . import CRAFT_FILE, DATA_DIR, POEDB_BASE
from .net import fetch
from .tables import extract_tables

CRAFT_URL = f"{POEDB_BASE}/Crafting_Bench"
ProgressCb = Callable[[str, int, int], None]


def parse_crafting(html: str) -> list[dict]:
    recipes: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    for table in extract_tables(html):
        rows = table.get("rows") or []
        if not rows:
            continue
        header = rows[0]
        if not (any("詞綴" in cell for cell in header) and any("解鎖" in cell for cell in header)):
            continue
        affix_i = next((i for i, name in enumerate(header) if "詞綴" in name), 0)
        cost_i = next((i for i, name in enumerate(rows[0]) if name.lower() in {"require", "requires"} or "消耗" in name), 1)
        class_i = next((i for i, name in enumerate(rows[0]) if "itemclass" in name.lower() or "適用" in name or "物品" in name), 2)
        unlock_i = next((i for i, name in enumerate(rows[0]) if "解鎖" in name), 3)
        for row in rows[1:]:
            affix = _cell(row, affix_i)
            if not affix or affix == "詞綴":
                continue
            cost = _cell(row, cost_i)
            classes = _cell(row, class_i)
            unlock = _cell(row, unlock_i)
            if unlock.lower() == "default":
                unlock = "預設解鎖"
            stamp = (affix, cost, classes, unlock)
            if stamp in seen:
                continue
            seen.add(stamp)
            recipes.append(
                {
                    "affix": affix,
                    "cost": cost,
                    "item_classes": classes,
                    "unlock": unlock or "（未標示）",
                }
            )
        break
    return recipes


def _cell(row: list[str], index: int) -> str:
    if index < 0 or index >= len(row):
        return ""
    return row[index]


def sync_crafting(progress: ProgressCb | None = None) -> dict:
    if progress:
        progress("正在下載工藝台資料…", 0, 1)
    html = fetch(CRAFT_URL)
    recipes = parse_crafting(html)
    if not recipes:
        raise RuntimeError("工藝台頁面沒有解析到配方。")
    areas = sorted({item["unlock"] for item in recipes if item["unlock"]})
    catalog = {
        "synced_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "source": CRAFT_URL,
        "recipe_count": len(recipes),
        "areas": areas,
        "recipes": recipes,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CRAFT_FILE.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    if progress:
        progress(f"完成，共 {len(recipes)} 筆工藝配方", 1, 1)
    return catalog


def load_crafting() -> dict | None:
    from . import resolve_named_data

    path = resolve_named_data("crafting.json")
    if not path:
        return None
    return json.loads(path.read_text(encoding="utf-8"))
