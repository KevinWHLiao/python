"""PoEDB Chinese localization PIN lookup window."""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from .chinese import CHINESE_PAGE, ChinesePins, PinInfo, fetch_pins
from .theme import BG, BG_HEAD, BG_PANEL, FONT_SMALL, FONT_UI, GOLD, GOLD_HI, MUTED, TEXT, apply_theme

FONT_PIN = ("Consolas", 42, "bold")


class ChineseApp(tk.Toplevel):
    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master)
        self._on_back = on_back
        self.title("流亡黯道 · 中文化 PIN")
        self.geometry("860x560")
        self.minsize(720, 480)
        self.configure(bg=BG)
        self.option_add("*Font", FONT_UI)
        apply_theme(self)
        self.protocol("WM_DELETE_WINDOW", self.go_back)

        self._loading = False
        self.status_var = tk.StringVar(value="正在讀取 poedb.tw…")
        self._pin_vars = {
            "tw": {
                "pin": tk.StringVar(value="—"),
                "server": tk.StringVar(value="伺服器版本：—"),
                "patch": tk.StringVar(value="中文化版本：—"),
            },
            "cn": {
                "pin": tk.StringVar(value="—"),
                "server": tk.StringVar(value="伺服器版本：—"),
                "patch": tk.StringVar(value="中文化版本：—"),
            },
        }

        self._build()
        self.after(80, self.reload)

    def go_back(self) -> None:
        self.destroy()
        self._on_back()

    def _build(self) -> None:
        header = tk.Frame(self, bg=BG_HEAD)
        header.pack(fill="x")
        tk.Frame(self, bg=GOLD, height=3).pack(fill="x")
        ttk.Button(header, text="← 主選單", command=self.go_back).pack(side="left", padx=16, pady=12)
        ttk.Label(header, text="中文化 PIN", style="Gold.TLabel", background=BG_HEAD).pack(side="left", pady=12)
        ttk.Button(header, text="重新整理", command=self.reload).pack(side="right", padx=16, pady=12)
        ttk.Button(header, text="開啟 PoEDB 中文化頁", command=lambda: webbrowser.open(CHINESE_PAGE)).pack(
            side="right", padx=(0, 8), pady=12
        )

        ttk.Label(
            self,
            text="PIN 來自 poedb.tw，每次遊戲更新都會變。點複製可貼到中文化工具；安裝步驟請看 PoEDB 原頁。",
            style="Muted.TLabel",
        ).pack(anchor="w", padx=16, pady=(12, 4))

        cards = ttk.Frame(self, padding=(16, 8, 16, 8))
        cards.pack(fill="both", expand=True)
        cards.columnconfigure(0, weight=1)
        cards.columnconfigure(1, weight=1)
        self._make_card(cards, 0, "tw", "繁體中文  ·  tw PIN")
        self._make_card(cards, 1, "cn", "簡體中文  ·  cn PIN")

        status = tk.Frame(self, bg=BG_HEAD)
        status.pack(fill="x")
        tk.Label(status, textvariable=self.status_var, bg=BG_HEAD, fg=MUTED, font=FONT_SMALL, anchor="w").pack(
            side="left", padx=16, pady=8
        )

    def _make_card(self, parent: ttk.Frame, column: int, locale: str, title: str) -> None:
        card = tk.Frame(parent, bg=BG_PANEL, highlightbackground=GOLD, highlightthickness=1)
        card.grid(row=0, column=column, sticky="nsew", padx=(0, 12) if column == 0 else (12, 0), pady=8)
        inner = tk.Frame(card, bg=BG_PANEL)
        inner.pack(fill="both", expand=True, padx=22, pady=22)
        tk.Label(inner, text=title, bg=BG_PANEL, fg=GOLD, font=("Microsoft JhengHei UI", 12, "bold")).pack(anchor="w")
        tk.Label(inner, textvariable=self._pin_vars[locale]["pin"], bg=BG_PANEL, fg=GOLD_HI, font=FONT_PIN).pack(
            pady=(18, 10)
        )
        tk.Label(inner, textvariable=self._pin_vars[locale]["server"], bg=BG_PANEL, fg=TEXT, font=FONT_UI).pack(
            anchor="w"
        )
        tk.Label(inner, textvariable=self._pin_vars[locale]["patch"], bg=BG_PANEL, fg=TEXT, font=FONT_UI).pack(
            anchor="w", pady=(2, 16)
        )
        ttk.Button(inner, text="複製 PIN", command=lambda key=locale: self.copy_pin(key)).pack(anchor="w")

    def copy_pin(self, locale: str) -> None:
        pin = self._pin_vars[locale]["pin"].get().strip()
        if not pin or pin == "—":
            messagebox.showinfo("還沒有 PIN", "請先重新整理，等 PIN 載入後再複製。", parent=self)
            return
        self.clipboard_clear()
        self.clipboard_append(pin)
        self.status_var.set(f"已複製 {locale.upper()} PIN：{pin}")

    def reload(self) -> None:
        if self._loading:
            return
        self._loading = True
        self.status_var.set("正在從 poedb.tw 讀取 PIN…")
        threading.Thread(target=self._load_worker, daemon=True).start()

    def _load_worker(self) -> None:
        try:
            pins = fetch_pins(force=True)
        except RuntimeError as error:
            self.after(0, lambda message=str(error): self._fail(message))
            return
        self.after(0, lambda: self._on_pins(pins))

    def _on_pins(self, pins: ChinesePins) -> None:
        self._loading = False
        self._apply_pin("tw", pins.tw)
        self._apply_pin("cn", pins.cn)
        stamp = pins.fetched_at or "未知時間"
        if pins.from_cache:
            self.status_var.set(f"目前連不上 PoEDB，顯示上次成功的 PIN（{stamp}）")
        else:
            self.status_var.set(f"已更新  ·  {stamp}  ·  {pins.source}")

    def _apply_pin(self, locale: str, info: PinInfo | None) -> None:
        vars_ = self._pin_vars[locale]
        if not info:
            vars_["pin"].set("—")
            vars_["server"].set("伺服器版本：—")
            vars_["patch"].set("中文化版本：—")
            return
        vars_["pin"].set(info.pin)
        vars_["server"].set(f"伺服器版本：{info.server_version}")
        vars_["patch"].set(f"中文化版本：{info.patch_version}")

    def _fail(self, message: str) -> None:
        self._loading = False
        self.status_var.set(message)
        messagebox.showerror("讀取 PIN 失敗", message, parent=self)
