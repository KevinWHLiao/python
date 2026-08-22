"""Build poe_affix_data/names_zh.json from PoeCharm Traditional Chinese maps."""

from __future__ import annotations

import csv
import io
import json
import re
import urllib.request
from pathlib import Path

UA = {"User-Agent": "PoELookupTool/1.0 (Windows desktop; personal local app)"}
BASE = "https://raw.githubusercontent.com/Chuanhsing/PoeCharm/main/Data/Translate/zh-rTW"
ITEM_FILES = [
    "Uniques.txt.csv",
    "Items_Gems.txt.csv",
    "Gems_data.txt.csv",
    "Items_Accessories.txt.csv",
    "Items_Armour.txt.csv",
    "Items_Weapons.txt.csv",
    "Items_Jewels.txt.csv",
    "Items_Oils.csv",
    "Z.csv",
]
CJK = re.compile(r"[\u4e00-\u9fff]")
PLACEHOLDER = re.compile(r"[{}]|%\d|%s", re.I)


def fetch(name: str) -> str:
    request = urllib.request.Request(f"{BASE}/{name}", headers=UA)
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8", "replace")


def parse_rows(text: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 2:
            continue
        english = row[0].strip().strip('"')
        chinese = row[1].strip().strip('"')
        if not english or not chinese or english == chinese:
            continue
        if PLACEHOLDER.search(english) or PLACEHOLDER.search(chinese):
            continue
        if not CJK.search(chinese):
            continue
        rows.append((english, chinese))
    return rows


def gui_usable(english: str, chinese: str) -> bool:
    if len(english) < 3 or len(english) > 70:
        return False
    if len(chinese) > 24:
        return False
    if english.endswith((".", "!", "?")):
        return False
    if english[:1].islower():
        return False
    return True


def build() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for name in ITEM_FILES:
        print("fetch", name)
        for english, chinese in parse_rows(fetch(name)):
            mapping.setdefault(english, chinese)
    print("fetch GUI.csv")
    for english, chinese in parse_rows(fetch("GUI.csv")):
        if gui_usable(english, chinese):
            mapping.setdefault(english, chinese)
    return mapping


def main() -> None:
    mapping = build()
    out = Path("poe_affix_data/names_zh.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(mapping, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("wrote", out, "entries", len(mapping), "bytes", out.stat().st_size)
    for sample in ["Chaos Orb", "Headhunter", "Mageblood", "Watcher's Eye", "Fireball", "Clear Oil", "Orb of Fusing"]:
        print(f"  {sample} -> {mapping.get(sample)}")


if __name__ == "__main__":
    main()
