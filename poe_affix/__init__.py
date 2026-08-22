"""Path of Exile 裝備詞綴查詢（資料來自 poedb.tw）。"""

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
CRAFT_FILE = DATA_DIR / "crafting.json"
VENDOR_FILE = DATA_DIR / "vendor.json"
POEDB_BASE = "https://poedb.tw/tw"
INDEX_URL = f"{POEDB_BASE}/Modifiers"


def resolve_data_file() -> Path | None:
    return resolve_named_data("mods.json")


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
