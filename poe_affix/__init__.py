"""Path of Exile 裝備詞綴查詢（資料來自 poedb.tw / poe2db.tw）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _bundle_dir() -> Path | None:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return None


ROOT = _runtime_root()
DATA_DIR = ROOT / "poe_affix_data"
DATA_FILE = DATA_DIR / "mods.json"
DATA_FILE_POE2 = DATA_DIR / "mods_poe2.json"
CRAFT_FILE = DATA_DIR / "crafting.json"
VENDOR_FILE = DATA_DIR / "vendor.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
POEDB_BASE = "https://poedb.tw/tw"
POE2DB_BASE = "https://poe2db.tw/tw"
INDEX_URL = f"{POEDB_BASE}/Modifiers"
INDEX_URL_POE2 = f"{POE2DB_BASE}/Modifiers"

GAMES = {
    "poe1": {
        "id": "poe1",
        "label": "PoE1",
        "title": "流亡黯道",
        "site_name": "PoEDB",
        "base": POEDB_BASE,
        "index_url": INDEX_URL,
        "filename": "mods.json",
    },
    "poe2": {
        "id": "poe2",
        "label": "PoE2",
        "title": "流亡黯道 2",
        "site_name": "PoE2DB",
        "base": POE2DB_BASE,
        "index_url": INDEX_URL_POE2,
        "filename": "mods_poe2.json",
    },
}


def game_spec(game: str) -> dict:
    return GAMES.get(game) or GAMES["poe1"]


def load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(updates: dict) -> None:
    data = load_settings()
    data.update(updates)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_data_file(game: str = "poe1") -> Path | None:
    return resolve_named_data(game_spec(game)["filename"])


def resolve_named_data(filename: str) -> Path | None:
    """Prefer a writable copy next to the app; fall back to bundled data."""
    local = DATA_DIR / filename
    if local.exists():
        return local
    bundled = _bundle_dir()
    if bundled:
        candidate = bundled / "poe_affix_data" / filename
        if candidate.exists():
            return candidate
    return None


def resolve_app_icon() -> Path | None:
    """Return the bundled PoE-themed .ico for window / taskbar icons."""
    candidates = [
        ROOT / "assets" / "poe_lookup.ico",
        Path(__file__).resolve().parent.parent / "assets" / "poe_lookup.ico",
    ]
    bundled = _bundle_dir()
    if bundled:
        candidates.insert(0, bundled / "assets" / "poe_lookup.ico")
    for path in candidates:
        if path.exists():
            return path
    return None
