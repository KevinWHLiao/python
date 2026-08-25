"""CSV test result logging for the production line."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path


LOG_FIELDS = [
    "timestamp",
    "profile",
    "pn",
    "sn",
    "result",
    "detected_count",
    "missing",
    "ghost",
    "duration_ms",
]


class TestLogger:
    def __init__(self, log_dir: Path) -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _path_for_today(self) -> Path:
        day = datetime.now().strftime("%Y%m%d")
        return self.log_dir / f"nkro_{day}.csv"

    def write(
        self,
        *,
        profile: str,
        pn: str,
        sn: str,
        result: str,
        detected_count: int,
        missing: list[str],
        ghost: list[str],
        duration_ms: int,
    ) -> Path:
        path = self._path_for_today()
        new_file = not path.exists()
        with path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=LOG_FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow(
                {
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "profile": profile,
                    "pn": pn,
                    "sn": sn,
                    "result": result,
                    "detected_count": detected_count,
                    "missing": "|".join(missing),
                    "ghost": "|".join(ghost),
                    "duration_ms": duration_ms,
                }
            )
        return path
