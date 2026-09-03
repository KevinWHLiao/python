"""Main menu for affix, vendor recipe, and crafting unlock tools."""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser

import customtkinter as ctk

from . import ROOT
from .theme import (
    BG,
    BG_CARD,
    FONT_CARD,
    FONT_FAMILY,
    FONT_HERO,
    FONT_SMALL,
    GOLD,
    GOLD_HI,
    LINE_SOFT,
    MUTED,
    TEXT,
    ghost_button,
    primary_button,
    setup_appearance,
    setup_window,
)

CRAFT_OF_EXILE_URL = "https://www.craftofexile.com/"
TIMELESS_JEWELS_URL = "https://vilsol.github.io/timeless-jewels/tree"

MENU_CARDS = [
    ("詞綴查詢", "查 PoE1／PoE2 裝備詞綴階層、物等、部位、權重與汙染詞", "open_affix", True),
    ("商店配方", "查商人交易配方：獎勵、需要物品與分類", "open_vendor", True),
    ("工藝解鎖區域", "查工藝台配方解鎖區域、消耗與適用部位", "open_craft", True),
    ("價格查詢", "poe.ninja 估價：PoE1 通貨傳奇輿圖寶石、PoE2 通貨符文傳奇飾品族裔寶石等", "open_economy", True),
    ("官方賣場", "pathofexile.com/trade：即時上架、價格與密語", "open_trade", True),
    ("流派排名", "poe.ninja 熱門流派、DPS、EHP 與逐日占比", "open_builds", True),
    ("每季開荒推薦", "PoE1 開荒 Build 篩選，PoE2 為 Maxroll 開荒昇華 tier list", "open_starters", True),
    ("中文化 PIN", "poedb.tw 繁中／簡中 PIN 與遊戲版本", "open_chinese", True),
    ("Craft of Exile", "開啟做裝模擬器（Calculator / Simulator）", "open_craftofexile", False),
    ("軍團珠寶查詢", "開啟 Timeless Jewel 天賦樹與 Seed 查詢", "open_timeless_jewels", False),
]


class MenuApp(ctk.CTk):
    def __init__(self) -> None:
        setup_appearance()
        super().__init__()
        self.title("流亡黯道 · 查詢工具")
        self.geometry("820x880")
        self.minsize(640, 640)
        setup_window(self)
        self._child = None
        self.path_var = tk.StringVar(value=f"資料路徑：{ROOT}")
        self.version_var = tk.StringVar(value="遊戲版本：讀取中…")
        self._build()
        self.after(80, self._load_version)

    def _build(self) -> None:
        hero = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        hero.pack(fill="x", padx=28, pady=(28, 8))
        ctk.CTkLabel(hero, text="流亡黯道", font=FONT_HERO, text_color=GOLD).pack(anchor="w")
        ctk.CTkLabel(hero, text="查詢工具", font=(FONT_FAMILY, 16), text_color=GOLD_HI).pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(hero, textvariable=self.version_var, font=FONT_SMALL, text_color=GOLD).pack(anchor="w")
        ctk.CTkLabel(hero, textvariable=self.path_var, font=FONT_SMALL, text_color=MUTED).pack(anchor="w", pady=(2, 0))
        ctk.CTkLabel(hero, text="選擇功能開始查詢", font=FONT_SMALL, text_color=MUTED).pack(anchor="w", pady=(14, 0))

        scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=BG,
            corner_radius=0,
            scrollbar_button_color=LINE_SOFT,
            scrollbar_button_hover_color=GOLD,
        )
        scroll.pack(fill="both", expand=True, padx=20, pady=(8, 4))

        for title, desc, handler_name, local in MENU_CARDS:
            self._add_card(scroll, title, desc, getattr(self, handler_name), local)

        ctk.CTkLabel(
            self,
            text=(
                "資料來源：poedb.tw  ·  poe2db.tw  ·  poe.ninja  ·  maxroll.gg  ·  pathofexile.com/trade"
                "　　中文化 PIN：poedb.tw/tw/chinese"
            ),
            font=FONT_SMALL,
            text_color=MUTED,
        ).pack(side="bottom", fill="x", pady=(4, 16), padx=28)

    def _add_card(self, parent, title: str, desc: str, command, local: bool) -> None:
        card = ctk.CTkFrame(
            parent,
            fg_color=BG_CARD,
            corner_radius=16,
            border_width=1,
            border_color=LINE_SOFT,
        )
        card.pack(fill="x", pady=6, padx=4)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=14)

        text_col = ctk.CTkFrame(inner, fg_color="transparent")
        text_col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(text_col, text=title, font=FONT_CARD, text_color=TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(
            text_col,
            text=desc,
            font=FONT_SMALL,
            text_color=MUTED,
            anchor="w",
            wraplength=480,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        badge = "本地資料" if local else "開啟網頁"
        ctk.CTkLabel(
            inner,
            text=badge,
            font=(FONT_FAMILY, 11),
            text_color=GOLD if local else MUTED,
            fg_color=("#2a2418" if local else "transparent"),
            corner_radius=8,
            width=72,
            height=24,
        ).pack(side="right", padx=(12, 10))

        if local:
            primary_button(inner, "開啟", command=command, width=88).pack(side="right")
        else:
            ghost_button(inner, "前往", command=command, width=88).pack(side="right")

    def _hide(self) -> None:
        self.withdraw()

    def _load_version(self) -> None:
        threading.Thread(target=self._version_worker, daemon=True).start()

    def _version_worker(self) -> None:
        try:
            from .chinese import fetch_pins

            pins = fetch_pins()
            info = pins.tw or pins.cn
            if not info:
                raise RuntimeError("頁面上沒有版本")
            same = info.server_version == info.patch_version
            if same:
                text = f"遊戲版本：{info.server_version}"
            else:
                text = f"遊戲版本：{info.server_version}　中文化：{info.patch_version}"
            if pins.from_cache:
                text += "　（快取）"
        except Exception as error:  # noqa: BLE001
            text = f"遊戲版本：無法讀取（{error}）"
        self.after(0, lambda message=text: self.version_var.set(message))

    def show_menu(self) -> None:
        self._child = None
        self.deiconify()
        self.lift()
        self.focus_force()

    def open_affix(self) -> None:
        from .gui import AffixApp

        self._hide()
        self._child = AffixApp(self, on_back=self.show_menu)

    def open_vendor(self) -> None:
        from .vendor_gui import VendorApp

        self._hide()
        self._child = VendorApp(self, on_back=self.show_menu)

    def open_craft(self) -> None:
        from .craft_gui import CraftApp

        self._hide()
        self._child = CraftApp(self, on_back=self.show_menu)

    def open_economy(self) -> None:
        from .economy_gui import EconomyApp

        self._hide()
        self._child = EconomyApp(self, on_back=self.show_menu)

    def open_trade(self) -> None:
        from .trade_gui import TradeApp

        self._hide()
        self._child = TradeApp(self, on_back=self.show_menu)

    def open_builds(self) -> None:
        from .builds_gui import BuildsApp

        self._hide()
        self._child = BuildsApp(self, on_back=self.show_menu)

    def open_starters(self) -> None:
        from .starters_gui import StartersApp

        self._hide()
        self._child = StartersApp(self, on_back=self.show_menu)

    def open_chinese(self) -> None:
        from .chinese_gui import ChineseApp

        self._hide()
        self._child = ChineseApp(self, on_back=self.show_menu)

    def open_craftofexile(self) -> None:
        webbrowser.open(CRAFT_OF_EXILE_URL)

    def open_timeless_jewels(self) -> None:
        webbrowser.open(TIMELESS_JEWELS_URL)


def main() -> None:
    MenuApp().mainloop()
