"""Main factory UI: keyboard map, 5s capture, PASS/FAIL overlay."""

from __future__ import annotations

import json
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from . import __version__
from .judge import JudgeResult, judge
from .keycodes import name_to_vk, normalize_key_name, vk_to_name
from .layout import KeyGeom, layout_for
from .logger import TestLogger
from .raw_input import KeyEvent, KeyboardDevice, RawInputListener, list_keyboard_devices

COLOR_IDLE = "#F5F5F5"
COLOR_EXPECTED = "#E8EEF7"
COLOR_PRESSED = "#E53935"
COLOR_MISSING = "#FF9800"
COLOR_GHOST = "#8E24AA"
COLOR_JUDGE = "#FF80AB"
COLOR_PASS = "#2E7D32"
COLOR_FAIL = "#C62828"


class NkroApp(tk.Tk):
    def __init__(self, root_dir: Path) -> None:
        super().__init__()
        self.root_dir = root_dir
        self.config_dir = root_dir / "config"
        self.profiles_dir = self.config_dir / "profiles"
        self.devices_cfg_path = self.config_dir / "devices.json"
        self.logger = TestLogger(root_dir / "logs")

        self.profiles = self._load_profiles()
        self.devices_cfg = self._load_devices_cfg()
        self.profile_id = self.devices_cfg.get("default_profile") or next(iter(self.profiles))
        self.profile = self.profiles[self.profile_id]

        self.listener = RawInputListener()
        self.devices: list[KeyboardDevice] = []
        self.operator_handle: int | None = None
        self.dut_handle: int | None = None

        self.state = "idle"  # idle | running | done
        self.detected: set[int] = set()
        self.result: JudgeResult | None = None
        self.run_started_at = 0.0
        self.hold_seconds = float(self.profile.get("hold_seconds", 5))
        self.last_vk_line = ""

        self.title(f"NKRO Ghost Key Test  v{__version__}")
        self.geometry("1280x780")
        self.minsize(1100, 700)
        self.configure(bg="#FAFAFA")

        self._build_ui()
        self._refresh_devices()
        self._apply_saved_device_paths()
        self._redraw_keyboard()

        try:
            self.listener.start()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Raw Input", f"無法啟動鍵盤擷取：\n{exc}")

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(20, self._poll_input)
        self.after(100, self._tick_timer)

    # --- config ---

    def _load_profiles(self) -> dict[str, dict[str, Any]]:
        profiles: dict[str, dict[str, Any]] = {}
        for path in sorted(self.profiles_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            profiles[data["id"]] = data
        if not profiles:
            raise RuntimeError(f"No profiles found in {self.profiles_dir}")
        return profiles

    def _load_devices_cfg(self) -> dict[str, Any]:
        if not self.devices_cfg_path.exists():
            return {}
        return json.loads(self.devices_cfg_path.read_text(encoding="utf-8"))

    def _save_devices_cfg(self) -> None:
        op = next((d for d in self.devices if d.handle == self.operator_handle), None)
        dut = next((d for d in self.devices if d.handle == self.dut_handle), None)
        data = {
            "operator_path": op.path if op else "",
            "dut_path": dut.path if dut else "",
            "default_profile": self.profile_id,
            "comment": "Auto-saved device paths for line setup.",
        }
        self.devices_cfg_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    # --- UI construction ---

    def _build_ui(self) -> None:
        top = tk.Frame(self, bg="#FAFAFA")
        top.pack(fill="x", padx=12, pady=(10, 4))

        self.title_var = tk.StringVar(value=self.profile["title"])
        tk.Label(
            top,
            textvariable=self.title_var,
            font=("Segoe UI", 22, "bold"),
            fg="#1565C0",
            bg="#FAFAFA",
        ).pack(side="left")

        right = tk.Frame(top, bg="#FAFAFA")
        right.pack(side="right")
        tk.Label(right, text="Profile", bg="#FAFAFA").pack(side="left", padx=(0, 6))
        self.profile_var = tk.StringVar(value=self.profile_id)
        self.profile_combo = ttk.Combobox(
            right,
            textvariable=self.profile_var,
            values=list(self.profiles.keys()),
            state="readonly",
            width=28,
        )
        self.profile_combo.pack(side="left")
        self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_change)

        self.vk_var = tk.StringVar(value="")
        tk.Label(
            self,
            textvariable=self.vk_var,
            font=("Consolas", 10),
            fg="#555555",
            bg="#FAFAFA",
            anchor="w",
        ).pack(fill="x", padx=14)

        mid = tk.Frame(self, bg="#FAFAFA")
        mid.pack(fill="both", expand=True, padx=12, pady=4)

        self.canvas = tk.Canvas(mid, bg="#FFFFFF", highlightthickness=1, highlightbackground="#BDBDBD")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self._redraw_keyboard())

        self.prompt = tk.Label(
            self,
            text="按壓外接鍵盤 SPACE 鍵 開始測試\nPress SPACE on operator keyboard to start.",
            font=("Microsoft JhengHei UI", 16, "bold"),
            bg="#FFF59D",
            fg="#212121",
            pady=12,
        )
        self.prompt.pack(fill="x", padx=12, pady=6)

        bottom = tk.Frame(self, bg="#FAFAFA")
        bottom.pack(fill="x", padx=12, pady=(0, 10))

        form = tk.Frame(bottom, bg="#FAFAFA")
        form.pack(side="left", fill="x", expand=True)

        row1 = tk.Frame(form, bg="#FAFAFA")
        row1.pack(fill="x", pady=2)
        tk.Label(row1, text="P/N", width=6, anchor="w", bg="#FAFAFA").pack(side="left")
        self.pn_var = tk.StringVar()
        tk.Entry(row1, textvariable=self.pn_var, width=28).pack(side="left", padx=(0, 16))
        tk.Label(row1, text="SN", width=4, anchor="w", bg="#FAFAFA").pack(side="left")
        self.sn_var = tk.StringVar()
        tk.Entry(row1, textvariable=self.sn_var, width=28).pack(side="left", padx=(0, 16))

        row2 = tk.Frame(form, bg="#FAFAFA")
        row2.pack(fill="x", pady=2)
        self.count_var = tk.StringVar(value="Detect Key Count: 0")
        tk.Label(row2, textvariable=self.count_var, font=("Segoe UI", 11, "bold"), bg="#FAFAFA").pack(
            side="left", padx=(0, 20)
        )
        self.key_test_var = tk.StringVar(value="Key Test =")
        tk.Label(row2, textvariable=self.key_test_var, font=("Segoe UI", 11, "bold"), bg="#FAFAFA").pack(
            side="left", padx=(0, 20)
        )
        self.detail_var = tk.StringVar(value="")
        tk.Label(row2, textvariable=self.detail_var, font=("Segoe UI", 10), fg="#444", bg="#FAFAFA").pack(
            side="left"
        )

        row3 = tk.Frame(form, bg="#FAFAFA")
        row3.pack(fill="x", pady=4)
        tk.Label(row3, text="Operator KB", width=12, anchor="w", bg="#FAFAFA").pack(side="left")
        self.op_var = tk.StringVar()
        self.op_combo = ttk.Combobox(row3, textvariable=self.op_var, state="readonly", width=55)
        self.op_combo.pack(side="left", padx=(0, 8))
        self.op_combo.bind("<<ComboboxSelected>>", self._on_device_change)
        tk.Label(row3, text="DUT KB", width=8, anchor="w", bg="#FAFAFA").pack(side="left")
        self.dut_var = tk.StringVar()
        self.dut_combo = ttk.Combobox(row3, textvariable=self.dut_var, state="readonly", width=55)
        self.dut_combo.pack(side="left", padx=(0, 8))
        self.dut_combo.bind("<<ComboboxSelected>>", self._on_device_change)
        ttk.Button(row3, text="Refresh Devices", command=self._refresh_devices).pack(side="left")

        btns = tk.Frame(bottom, bg="#FAFAFA")
        btns.pack(side="right", padx=(12, 0))
        self.time_var = tk.StringVar(value="Time 00:00")
        tk.Label(btns, textvariable=self.time_var, font=("Segoe UI", 14, "bold"), bg="#FAFAFA").pack(
            pady=(0, 8)
        )
        ttk.Button(btns, text="Clear Test", command=self.clear_test).pack(fill="x", pady=2)
        ttk.Button(btns, text="Next Test", command=self.next_test).pack(fill="x", pady=2)
        ttk.Button(btns, text="Save Devices", command=self._save_devices_cfg).pack(fill="x", pady=2)

        self.overlay = tk.Label(
            self.canvas,
            text="",
            font=("Segoe UI", 72, "bold"),
            bg="#FFFFFF",
        )

    # --- devices / profile ---

    def _refresh_devices(self) -> None:
        try:
            self.devices = list_keyboard_devices()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Devices", f"列舉鍵盤失敗：\n{exc}")
            self.devices = []
        labels = [d.label for d in self.devices]
        self.op_combo["values"] = labels
        self.dut_combo["values"] = labels
        if labels and not self.op_var.get():
            self.op_combo.current(0)
            self._on_device_change()
        if len(labels) > 1 and not self.dut_var.get():
            self.dut_combo.current(1)
            self._on_device_change()
        elif labels and not self.dut_var.get():
            self.dut_combo.current(0)
            self._on_device_change()

    def _apply_saved_device_paths(self) -> None:
        op_path = (self.devices_cfg.get("operator_path") or "").strip()
        dut_path = (self.devices_cfg.get("dut_path") or "").strip()
        if op_path:
            for i, d in enumerate(self.devices):
                if d.path == op_path:
                    self.op_combo.current(i)
                    break
        if dut_path:
            for i, d in enumerate(self.devices):
                if d.path == dut_path:
                    self.dut_combo.current(i)
                    break
        self._on_device_change()

    def _on_device_change(self, _event: object | None = None) -> None:
        self.operator_handle = self._handle_for_label(self.op_var.get())
        self.dut_handle = self._handle_for_label(self.dut_var.get())

    def _handle_for_label(self, label: str) -> int | None:
        for d in self.devices:
            if d.label == label:
                return d.handle
        return None

    def _on_profile_change(self, _event: object | None = None) -> None:
        self.profile_id = self.profile_var.get()
        self.profile = self.profiles[self.profile_id]
        self.hold_seconds = float(self.profile.get("hold_seconds", 5))
        self.title_var.set(self.profile["title"])
        self.clear_test()

    # --- keyboard drawing ---

    def _unit(self) -> float:
        # canvas width maps to ~23.5 key units
        w = max(self.canvas.winfo_width(), 800)
        return (w - 24) / 23.5

    def _key_rect(self, geom: KeyGeom) -> tuple[float, float, float, float]:
        u = self._unit()
        pad = 12
        x0 = pad + geom.x * u
        y0 = pad + geom.y * u
        x1 = x0 + geom.w * u - 3
        y1 = y0 + geom.h * u - 3
        return x0, y0, x1, y1

    def _key_fill(self, name: str) -> str:
        vk = name_to_vk(name)
        judgment = normalize_key_name(self.profile.get("judgment_key", "NUM_DECIMAL"))
        if name == judgment or normalize_key_name(name) == judgment:
            if self.state == "done":
                return COLOR_JUDGE
        if self.result:
            if vk in self.result.missing:
                return COLOR_MISSING
            if vk in self.result.ghost:
                return COLOR_GHOST
            if vk in self.result.detected:
                return COLOR_PRESSED
        if vk in self.detected:
            return COLOR_PRESSED
        expected = {name_to_vk(n) for n in self.profile["expected_keys"]}
        if vk in expected:
            return COLOR_EXPECTED
        return COLOR_IDLE

    def _redraw_keyboard(self) -> None:
        self.canvas.delete("all")
        keys = layout_for(self.profile.get("layout", "fullsize_us"))
        for geom in keys:
            x0, y0, x1, y1 = self._key_rect(geom)
            fill = self._key_fill(geom.name)
            self.canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline="#757575", width=1)
            self.canvas.create_text(
                (x0 + x1) / 2,
                (y0 + y1) / 2,
                text=geom.label,
                font=("Segoe UI", max(7, int(self._unit() * 0.28))),
                fill="#212121",
            )
        if self.state == "done" and self.result is not None:
            text = "PASS" if self.result.passed else "FAIL"
            color = COLOR_PASS if self.result.passed else COLOR_FAIL
            self.canvas.create_rectangle(
                80,
                120,
                self.canvas.winfo_width() - 80,
                280,
                fill="#FFFFFF",
                outline=color,
                width=6,
            )
            self.canvas.create_text(
                self.canvas.winfo_width() / 2,
                200,
                text=text,
                font=("Segoe UI", 64, "bold"),
                fill=color,
            )

    # --- test state machine ---

    def clear_test(self) -> None:
        self.state = "idle"
        self.detected.clear()
        self.result = None
        self.run_started_at = 0.0
        self.count_var.set("Detect Key Count: 0")
        self.key_test_var.set("Key Test =")
        self.detail_var.set("")
        self.time_var.set("Time 00:00")
        self.prompt.configure(
            text="按壓外接鍵盤 SPACE 鍵 開始測試\nPress SPACE on operator keyboard to start.",
            bg="#FFF59D",
            fg="#212121",
        )
        self._redraw_keyboard()

    def next_test(self) -> None:
        self.sn_var.set("")
        self.clear_test()

    def _start_run(self) -> None:
        if self.operator_handle is None or self.dut_handle is None:
            messagebox.showwarning("Devices", "請先選擇 Operator KB 與 DUT KB。")
            return
        self.state = "running"
        self.detected.clear()
        self.result = None
        self.run_started_at = time.perf_counter()
        self.key_test_var.set("Key Test = Running")
        self.detail_var.set("")
        self.prompt.configure(
            text="測試中：請用 jig 壓住對應鍵 5 秒\nTesting: hold jig on expected keys for 5 seconds",
            bg="#BBDEFB",
            fg="#0D47A1",
        )
        self._redraw_keyboard()

    def _finish_run(self) -> None:
        duration_ms = int((time.perf_counter() - self.run_started_at) * 1000)
        allowed = list(self.profile.get("allowed_extra") or [])
        # Single-keyboard lab mode: ignore start-key auto-repeat as ghost.
        if self.operator_handle == self.dut_handle:
            start_name = self.profile.get("start_key", "SPACE")
            if start_name not in allowed:
                allowed.append(start_name)
        self.result = judge(
            self.detected,
            self.profile["expected_keys"],
            allowed,
        )
        self.state = "done"
        self.count_var.set(f"Detect Key Count: {self.result.detected_count}")
        if self.result.passed:
            self.key_test_var.set("Key Test = PASS")
            self.detail_var.set("All expected keys detected; no ghost keys.")
            self.prompt.configure(text="結果：PASS", bg="#C8E6C9", fg=COLOR_PASS)
        else:
            self.key_test_var.set("Key Test = NG")
            miss = ",".join(self.result.missing_names()[:12])
            ghost = ",".join(self.result.ghost_names()[:12])
            self.detail_var.set(f"Missing: {miss or '-'} | Ghost: {ghost or '-'}")
            self.prompt.configure(text="結果：FAIL / NG", bg="#FFCDD2", fg=COLOR_FAIL)

        try:
            self.logger.write(
                profile=self.profile_id,
                pn=self.pn_var.get().strip(),
                sn=self.sn_var.get().strip(),
                result="PASS" if self.result.passed else "FAIL",
                detected_count=self.result.detected_count,
                missing=self.result.missing_names(),
                ghost=self.result.ghost_names(),
                duration_ms=duration_ms,
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showwarning("Log", f"寫入 log 失敗：{exc}")

        self._redraw_keyboard()

    # --- input polling ---

    def _poll_input(self) -> None:
        try:
            for event in self.listener.drain():
                self._on_key_event(event)
        finally:
            self.after(20, self._poll_input)

    def _on_key_event(self, event: KeyEvent) -> None:
        now = time.strftime("%H:%M:%S")
        ms = int((time.time() % 1) * 1000)
        self.vk_var.set(
            f"[{now}.{ms:03d}] vkCode=0x{event.vk:02X} flags=0x{event.flags:02X} "
            f"key={vk_to_name(event.vk)} device=0x{event.device_handle:X}"
        )
        if not event.is_keydown:
            return

        start_vk = name_to_vk(self.profile.get("start_key", "SPACE"))

        if self.state == "idle":
            if event.vk == start_vk and self._is_operator(event):
                self._start_run()
            return

        if self.state == "running":
            if self._is_dut(event):
                self.detected.add(event.vk & 0xFF)
                self.count_var.set(f"Detect Key Count: {len(self.detected)}")
                self._redraw_keyboard()
            return

    def _is_operator(self, event: KeyEvent) -> bool:
        if self.operator_handle is None:
            return True
        # Handles can change after unplug; also accept path rematch via refresh
        return event.device_handle == self.operator_handle

    def _is_dut(self, event: KeyEvent) -> bool:
        if self.dut_handle is None:
            return True
        # If operator and DUT are the same device (lab single-keyboard), accept all
        if self.operator_handle == self.dut_handle:
            return True
        return event.device_handle == self.dut_handle

    def _tick_timer(self) -> None:
        try:
            if self.state == "running":
                elapsed = time.perf_counter() - self.run_started_at
                secs = min(int(elapsed), int(self.hold_seconds))
                self.time_var.set(f"Time 00:{secs:02d}")
                if elapsed >= self.hold_seconds:
                    self._finish_run()
            elif self.state == "idle":
                self.time_var.set("Time 00:00")
        finally:
            self.after(100, self._tick_timer)

    def _on_close(self) -> None:
        try:
            self.listener.stop()
        except Exception:  # noqa: BLE001
            pass
        self.destroy()
