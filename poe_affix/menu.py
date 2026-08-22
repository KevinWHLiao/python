"""Main menu for affix, vendor recipe, and crafting unlock tools."""

from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import ttk

from .theme import BG, BG_HEAD, BG_PANEL, FONT_SMALL, FONT_UI, GOLD, MUTED, TEXT, apply_theme

CRAFT_OF_EXILE_URL = "https://www.craftofexile.com/"
TIMELESS_JEWELS_URL = "https://vilsol.github.io/timeless-jewels/tree"


class MenuApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("流亡黯道 · 查詢工具")
        self.geometry("760x820")
        self.minsize(640, 680)
        self.configure(bg=BG)
        self.option_add("*Font", FONT_UI)
        apply_theme(self)
        self._child = None
        self._build()

    def _build(self) -> None:
        header = tk.Frame(self, bg=BG_HEAD)
        header.pack(fill="x")
        tk.Frame(self, bg=GOLD, height=3).pack(fill="x")
        ttk.Label(header, text="流亡黯道  ·  查詢工具", style="Gold.TLabel", background=BG_HEAD).pack(
            pady=(22, 6)
        )
        tk.Label(header, text="選擇要使用的功能", bg=BG_HEAD, fg=MUTED, font=FONT_SMALL).pack(pady=(0, 18))

        body = ttk.Frame(self, padding=28)
        body.pack(fill="both", expand=True)

        cards = [
            ("詞綴查詢", "查裝備詞綴的階層、物等、部位、權重與汙染詞", self.open_affix),
            ("商店配方", "查商人交易配方：獎勵、需要物品與分類", self.open_vendor),
            ("工藝解鎖區域", "查工藝台配方要在哪個區域解鎖、消耗與適用部位", self.open_craft),
            ("價格查詢", "查 poe.ninja 估價：通貨、傳奇、寶石與輿圖", self.open_economy),
            ("開啟 Craft of Exile", "用瀏覽器開啟做裝模擬器（Calculator / Simulator / Emulator）", self.open_craftofexile),
            ("開啟軍團珠寶查詢", "用瀏覽器開啟 Timeless Jewel 天賦樹與 Seed 查詢", self.open_timeless_jewels),
        ]
        for title, desc, command in cards:
            card = tk.Frame(body, bg=BG_PANEL, highlightbackground=GOLD, highlightthickness=1)
            card.pack(fill="x", pady=8)
            inner = tk.Frame(card, bg=BG_PANEL)
            inner.pack(fill="x", padx=18, pady=14)
            ttk.Button(inner, text=title, style="Menu.TButton", command=command).pack(side="left")
            tk.Label(inner, text=desc, bg=BG_PANEL, fg=TEXT, font=FONT_UI, wraplength=420, justify="left").pack(
                side="left", padx=18
            )

        tk.Label(
            self,
            text="資料來源：poedb.tw / poe.ninja　　做裝模擬：craftofexile.com　　軍團珠寶：vilsol.github.io",
            bg=BG,
            fg=MUTED,
            font=FONT_SMALL,
        ).pack(pady=(0, 16))

    def _hide(self) -> None:
        self.withdraw()

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

    def open_craftofexile(self) -> None:
        webbrowser.open(CRAFT_OF_EXILE_URL)

    def open_timeless_jewels(self) -> None:
        webbrowser.open(TIMELESS_JEWELS_URL)


def main() -> None:
    MenuApp().mainloop()
