"""Download modifier tables from poedb.tw."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Callable

from . import DATA_DIR, DATA_FILE, INDEX_URL, POEDB_BASE
from .catalog import FALLBACK_SLOTS, collect_index_links, extract_mods_view, parse_slot
from .net import fetch

ProgressCb = Callable[[str, int, int], None]


def sync_catalog(progress: ProgressCb | None = None, delay: float = 0.25) -> dict:
    if progress:
        progress("正在讀取詞綴索引…", 0, 1)
    index_html = fetch(INDEX_URL)
    links = collect_index_links(index_html)
    if not links:
        links = list(FALLBACK_SLOTS)

    slots = []
    skipped = []
    total = len(links)
    for index, (name, slug) in enumerate(links, start=1):
        if progress:
            progress(f"正在下載 {name}（{index}/{total}）", index - 1, total)
        try:
            page_html = fetch(f"{POEDB_BASE}/{slug}")
            payload = extract_mods_view(page_html)
            if not payload:
                skipped.append(name)
                continue
            slot = parse_slot(name, slug, payload)
            if slot["groups"]:
                slots.append(slot)
            else:
                skipped.append(name)
        except Exception as error:  # noqa: BLE001 - keep syncing remaining slots
            skipped.append(f"{name}（{error}）")
        time.sleep(delay)

    if not slots:
        raise RuntimeError("沒有成功下載任何部位的詞綴資料。")

    catalog = {
        "synced_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "source": INDEX_URL,
        "slot_count": len(slots),
        "group_count": sum(len(slot["groups"]) for slot in slots),
        "skipped": skipped,
        "slots": slots,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    if progress:
        progress(f"完成，共 {len(slots)} 個部位", total, total)
    return catalog


if __name__ == "__main__":
    def _print(message: str, current: int, total: int) -> None:
        print(f"[{current}/{total}] {message}", flush=True)

    result = sync_catalog(progress=_print)
    print(
        f"saved {DATA_FILE} slots={result['slot_count']} groups={result['group_count']}",
        flush=True,
    )
