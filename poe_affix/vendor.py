"""Vendor recipes from poedb.tw/tw/Vendor_recipe_system."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Callable

from . import DATA_DIR, POEDB_BASE, VENDOR_FILE
from .net import fetch
from .tables import extract_tables

VENDOR_URL = f"{POEDB_BASE}/Vendor_recipe_system"
ProgressCb = Callable[[str, int, int], None]


def parse_vendor(html: str) -> list[dict]:
    recipes: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    for table in extract_tables(html):
        rows = table.get("rows") or []
        if len(rows) < 2:
            continue
        header = rows[0]
        if not (any("獎勵" in cell for cell in header) and any("你的物品" in cell or "物品" in cell for cell in header)):
            continue
        category = table.get("heading") or "商店配方"
        if "幫助" in category or "Markdown" in category or "傳奇 /" in category:
            continue
        category = re.sub(r"\s*Recipe\s*", " ", category)
        category = re.sub(r"\s*/\d+\s*$", "", category).strip() or "商店配方"
        reward_i = next((i for i, name in enumerate(header) if "獎勵" in name), 0)
        input_i = next((i for i, name in enumerate(header) if "你的物品" in name or name == "物品"), 1)
        note_i = next((i for i, name in enumerate(header) if "note" in name.lower() or "備註" in name or "註" in name), 2)
        for row in rows[1:]:
            reward = _cell(row, reward_i)
            materials = _cell(row, input_i)
            note = _cell(row, note_i)
            if not reward:
                continue
            stamp = (category, reward, materials, note)
            if stamp in seen:
                continue
            seen.add(stamp)
            recipes.append(
                {
                    "category": category.replace(" Recipe", "").strip(),
                    "reward": reward,
                    "materials": materials,
                    "note": note,
                }
            )
    return recipes


def _cell(row: list[str], index: int) -> str:
    if index < 0 or index >= len(row):
        return ""
    return row[index]


def sync_vendor(progress: ProgressCb | None = None) -> dict:
    if progress:
        progress("正在下載商店配方…", 0, 1)
    html = fetch(VENDOR_URL)
    recipes = parse_vendor(html)
    if not recipes:
        raise RuntimeError("商店配方頁面沒有解析到資料。")
    categories = []
    seen_cat: set[str] = set()
    for item in recipes:
        name = item["category"]
        if name not in seen_cat:
            seen_cat.add(name)
            categories.append(name)
    catalog = {
        "synced_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "source": VENDOR_URL,
        "recipe_count": len(recipes),
        "categories": categories,
        "recipes": recipes,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    VENDOR_FILE.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    if progress:
        progress(f"完成，共 {len(recipes)} 筆商店配方", 1, 1)
    return catalog


def load_vendor() -> dict | None:
    from . import resolve_named_data

    path = resolve_named_data("vendor.json")
    if not path:
        return None
    return json.loads(path.read_text(encoding="utf-8"))
