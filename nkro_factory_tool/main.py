"""Entry point for the NKRO Ghost Key factory test tool."""

from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """Directory that contains config/ and logs/ for runtime.

    Prefer the folder next to the executable so production can edit
    devices.json without re-packing. Fall back to PyInstaller _MEIPASS.
    """
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if (exe_dir / "config").is_dir():
            return exe_dir
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass and (Path(meipass) / "config").is_dir():
            return Path(meipass)
        return exe_dir
    return Path(__file__).resolve().parent


def main() -> int:
    from app.ui import NkroApp

    root = app_root()
    app = NkroApp(root)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
