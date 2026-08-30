"""Download modifier tables from poedb.tw or poe2db.tw."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from typing import Callable

from . import DATA_DIR, GAMES, game_spec
from .catalog import collect_index_links, extract_mods_view, fallback_slots_for, parse_slot, rematerialize_catalog
from .net import fetch

ProgressCb = Callable[[str, int, int], None]


def sync_catalog(
    progress: ProgressCb | None = None,
    delay: float = 0.25,
    game: str = "poe1",
) -> dict:
    spec = game_spec(game)
    base = spec["base"]
    index_url = spec["index_url"]
    site_name = spec["site_name"]
    out_path = DATA_DIR / spec["filename"]

    if progress:
        progress(f"正在讀取{site_name}詞綴索引…", 0, 1)
    index_html = fetch(index_url)
    links = collect_index_links(index_html)
    if not links:
        links = list(fallback_slots_for(spec["id"]))

    slots = []
    skipped = []
    total = len(links)
    for index, (name, slug) in enumerate(links, start=1):
        if progress:
            progress(f"正在下載 {name}（{index}/{total}）", index - 1, total)
        try:
            page_html = fetch(f"{base}/{slug}")
            payload = extract_mods_view(page_html)
            if not payload:
                skipped.append(name)
                continue
            slot = parse_slot(name, slug, payload, base_url=base)
            if slot["groups"]:
                slots.append(slot)
            else:
                skipped.append(name)
        except Exception as error:  # noqa: BLE001 - keep syncing remaining slots
            skipped.append(f"{name}（{error}）")
        time.sleep(delay)

    if not slots:
        raise RuntimeError(f"沒有成功下載任何部位的詞綴資料（{site_name}）。")

    catalog = {
        "game": spec["id"],
        "synced_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "source": index_url,
        "slot_count": len(slots),
        "group_count": sum(len(slot["groups"]) for slot in slots),
        "skipped": skipped,
        "slots": slots,
    }
    # Split shared ModFamilyList rows (e.g. 火焰／冰冷／閃電技能等級) into separate labels.
    catalog = rematerialize_catalog(catalog)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    if progress:
        progress(f"完成，共 {len(slots)} 個部位", total, total)
    return catalog


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download affix tables from PoEDB / PoE2DB.")
    parser.add_argument(
        "game",
        nargs="?",
        default="poe1",
        choices=sorted(GAMES),
        help="poe1 = poedb.tw，poe2 = poe2db.tw",
    )
    args = parser.parse_args()

    def _print(message: str, current: int, total: int) -> None:
        print(f"[{current}/{total}] {message}", flush=True)

    result = sync_catalog(progress=_print, game=args.game)
    spec = game_spec(args.game)
    print(
        f"saved {DATA_DIR / spec['filename']} "
        f"slots={result['slot_count']} groups={result['group_count']}",
        flush=True,
    )
