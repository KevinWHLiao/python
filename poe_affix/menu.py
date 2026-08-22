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
        self.geometry("720x720")
        self.minsize(560, 520)
        self.configure(bg=BG)
        self.option_add("*Font", FONT_UI)
        apply_theme(self)
        self._child = None
        self._canvas = None
        self._build()

    def _build(self) -> None:
        header = tk.Frame(self, bg=BG_HEAD)
        header.pack(fill="x")
        tk.Frame(self, bg=GOLD, height=3).pack(fill="x")
        ttk.Label(header, text="流亡黯道  ·  查詢工具", style="Gold.TLabel", background=BG_HEAD).pack(
            pady=(12, 2)
        )
        tk.Label(header, text="選擇要使用的功能", bg=BG_HEAD, fg=MUTED, font=FONT_SMALL).pack(pady=(0, 10))

        tk.Label(
            self,
            text="資料來源：poedb.tw / poe.ninja　　中文化 PIN：poedb.tw/tw/chinese",
            bg=BG,
            fg=MUTED,
            font=FONT_SMALL,
        ).pack(side="bottom", fill="x", pady=(4, 10))

        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=True, padx=16, pady=(8, 4))
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0, bd=0)
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self._canvas = canvas

        body = tk.Frame(canvas, bg=BG)
        window_id = canvas.create_window((0, 0), window=body, anchor="nw")

        def sync_scroll(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all") or (0, 0, 0, 0))
            canvas.itemconfigure(window_id, width=max(canvas.winfo_width(), 1))

        body.bind("<Configure>", sync_scroll)
        canvas.bind("<Configure>", sync_scroll)

        cards = [
            ("詞綴查詢", "查裝備詞綴的階層、物等、部位、權重與汙染詞", self.open_affix),
            ("商店配方", "查商人交易配方：獎勵、需要物品與分類", self.open_vendor),
            ("工藝解鎖區域", "查工藝台配方要在哪個區域解鎖、消耗與適用部位", self.open_craft),
            ("價格查詢", "查 poe.ninja 估價：通貨、傳奇、寶石與輿圖", self.open_economy),
            ("中文化 PIN", "查 poedb.tw 目前的繁中 / 簡中 4 碼 PIN 與遊戲版本", self.open_chinese),
            ("開啟 Craft of Exile", "用瀏覽器開啟做裝模擬器（Calculator / Simulator / Emulator）", self.open_craftofexile),
            ("開啟軍團珠寶查詢", "用瀏覽器開啟 Timeless Jewel 天賦樹與 Seed 查詢", self.open_timeless_jewels),
        ]
        for title, desc, command in cards:
            card = tk.Frame(body, bg=BG_PANEL, highlightbackground=GOLD, highlightthickness=1)
            card.pack(fill="x", pady=4)
            inner = tk.Frame(card, bg=BG_PANEL)
            inner.pack(fill="x", padx=12, pady=8)
            ttk.Button(inner, text=title, style="Menu.TButton", command=command).pack(side="left")
            tk.Label(inner, text=desc, bg=BG_PANEL, fg=TEXT, font=FONT_SMALL, wraplength=400, justify="left").pack(
                side="left", padx=14
            )

        def on_mousewheel(event) -> None:
            canvas.yview_scroll(int(-event.delta / 120), "units")

        def bind_wheel(widget: tk.Misc) -> None:
            widget.bind("<MouseWheel>", on_mousewheel)
            for child in widget.winfo_children():
                bind_wheel(child)

        bind_wheel(body)
        canvas.bind("<MouseWheel>", on_mousewheel)

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
