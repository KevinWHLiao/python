"""PoEDB Chinese localization PIN lookup window."""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox

import customtkinter as ctk

from .chinese import CHINESE_PAGE, ChinesePins, PinInfo, fetch_pins
from .theme import (
    BG_CARD,
    FONT_FAMILY,
    FONT_UI,
    GOLD,
    GOLD_HI,
    LINE_SOFT,
    TEXT,
    make_header,
    make_status_bar,
    primary_button,
    setup_window,
)

FONT_PIN = ("Consolas", 44, "bold")


class ChineseApp(ctk.CTkToplevel):
    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master)
        self._on_back = on_back
        self.title("流亡黯道 · 中文化 PIN")
        self.geometry("900x580")
        self.minsize(740, 500)
        setup_window(self)
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
        make_header(
            self,
            "中文化 PIN",
            on_back=self.go_back,
            right_actions=[
                ("重新整理", self.reload),
                ("開啟 PoEDB 中文化頁", lambda: webbrowser.open(CHINESE_PAGE)),
            ],
            hint="每次遊戲更新 PIN 都會變；點複製可貼到中文化工具",
        )
        make_status_bar(self, self.status_var)

        cards = ctk.CTkFrame(self, fg_color="transparent")
        cards.pack(fill="both", expand=True, padx=18, pady=16)
        cards.grid_columnconfigure(0, weight=1)
        cards.grid_columnconfigure(1, weight=1)
        cards.grid_rowconfigure(0, weight=1)
        self._make_card(cards, 0, "tw", "繁體中文  ·  tw PIN")
        self._make_card(cards, 1, "cn", "簡體中文  ·  cn PIN")

    def _make_card(self, parent, column: int, locale: str, title: str) -> None:
        card = ctk.CTkFrame(
            parent,
            fg_color=BG_CARD,
            corner_radius=18,
            border_width=1,
            border_color=LINE_SOFT,
        )
        card.grid(row=0, column=column, sticky="nsew", padx=(0, 10) if column == 0 else (10, 0))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=24, pady=24)
        ctk.CTkLabel(inner, text=title, font=(FONT_FAMILY, 14, "bold"), text_color=GOLD, anchor="w").pack(anchor="w")
        ctk.CTkLabel(inner, textvariable=self._pin_vars[locale]["pin"], font=FONT_PIN, text_color=GOLD_HI).pack(
            pady=(22, 12)
        )
        ctk.CTkLabel(
            inner, textvariable=self._pin_vars[locale]["server"], font=FONT_UI, text_color=TEXT, anchor="w"
        ).pack(anchor="w")
        ctk.CTkLabel(
            inner, textvariable=self._pin_vars[locale]["patch"], font=FONT_UI, text_color=TEXT, anchor="w"
        ).pack(anchor="w", pady=(4, 18))
        primary_button(inner, "複製 PIN", command=lambda key=locale: self.copy_pin(key), width=120).pack(anchor="w")

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
