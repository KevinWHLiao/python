"""poe.ninja economy price lookup window."""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from .economy import ALL, CATEGORY_LABELS, ECONOMY_PAGE, League, PriceRow, clear_cache, fetch_leagues, fetch_prices, matches
from .theme import BG, BG_HEAD, FONT_SMALL, FONT_UI, GOLD, MUTED, PREFIX, SUFFIX, apply_theme, sort_tree

NUMERIC_COLUMNS = {"chaos", "divine", "change", "listings"}


def format_price(value: float) -> str:
    if value is None or value <= 0:
        return "—"
    if value >= 1000:
        return f"{value:,.0f}"
    if value >= 10:
        return f"{value:,.1f}".rstrip("0").rstrip(".")
    if value >= 1:
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{value:.3f}".rstrip("0").rstrip(".")


def format_change(value: float | None) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


def format_listings(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value:,}"


class EconomyApp(tk.Toplevel):
    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master)
        self._on_back = on_back
        self.title("流亡黯道 · 價格查詢")
        self.geometry("1400x780")
        self.minsize(1080, 600)
        self.configure(bg=BG)
        self.option_add("*Font", FONT_UI)
        apply_theme(self)
        self.protocol("WM_DELETE_WINDOW", self.go_back)

        self.leagues: list[League] = []
        self.rows: list[PriceRow] = []
        self._loading = False
        self._pending_load: bool | None = None
        self._row_urls: dict[str, str] = {}

        self.league_var = tk.StringVar()
        self.category_var = tk.StringVar(value="通貨")
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="正在連線 poe.ninja…")

        self._build()
        self.search_var.trace_add("write", lambda *_: self.refresh())
        self.after(80, self._startup)

    def go_back(self) -> None:
        self.destroy()
        self._on_back()

    def _build(self) -> None:
        header = tk.Frame(self, bg=BG_HEAD)
        header.pack(fill="x")
        tk.Frame(self, bg=GOLD, height=3).pack(fill="x")
        ttk.Button(header, text="← 主選單", command=self.go_back).pack(side="left", padx=16, pady=12)
        ttk.Label(header, text="價格查詢", style="Gold.TLabel", background=BG_HEAD).pack(side="left", pady=12)
        ttk.Button(header, text="重新整理", command=self.reload_prices).pack(side="right", padx=16, pady=12)
        ttk.Button(header, text="開啟 poe.ninja", command=lambda: webbrowser.open(ECONOMY_PAGE)).pack(
            side="right", padx=(0, 8), pady=12
        )

        filters = ttk.Frame(self, padding=(16, 12, 16, 8))
        filters.pack(fill="x")
        ttk.Label(filters, text="聯盟", style="Muted.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.league_combo = ttk.Combobox(filters, textvariable=self.league_var, state="readonly", width=22)
        self.league_combo.grid(row=0, column=1, padx=(0, 16))
        self.league_combo.bind("<<ComboboxSelected>>", lambda _e: self.load_prices())

        ttk.Label(filters, text="分類", style="Muted.TLabel").grid(row=0, column=2, sticky="w", padx=(0, 6))
        self.category_combo = ttk.Combobox(
            filters, textvariable=self.category_var, state="readonly", width=16, values=[ALL, *CATEGORY_LABELS]
        )
        self.category_combo.grid(row=0, column=3, padx=(0, 16))
        self.category_combo.bind("<<ComboboxSelected>>", lambda _e: self.load_prices())

        ttk.Label(filters, text="搜尋物品", style="Muted.TLabel").grid(row=0, column=4, sticky="w", padx=(0, 6))
        ttk.Entry(filters, textvariable=self.search_var, width=36).grid(row=0, column=5, sticky="ew")
        filters.columnconfigure(5, weight=1)

        ttk.Label(
            self,
            text="估價來自 poe.ninja。名稱顯示中文與英文，兩邊都能搜，例如「獵首」「Headhunter」「混沌石」。雙擊列可開官網。",
            style="Muted.TLabel",
        ).pack(anchor="w", padx=16)

        wrap = ttk.Frame(self, padding=(16, 8, 16, 8))
        wrap.pack(fill="both", expand=True)
        columns = ("name_zh", "name", "category", "chaos", "divine", "change", "extra", "listings")
        self.tree = ttk.Treeview(wrap, columns=columns, show="headings", selectmode="browse")
        self.headings = {
            "name_zh": "中文",
            "name": "英文",
            "category": "分類",
            "chaos": "混沌石",
            "divine": "神聖石",
            "change": "近期漲跌",
            "extra": "細節",
            "listings": "上架數",
        }
        widths = {
            "name_zh": 220,
            "name": 220,
            "category": 100,
            "chaos": 80,
            "divine": 80,
            "change": 80,
            "extra": 220,
            "listings": 70,
        }
        for key, title in self.headings.items():
            self.tree.heading(key, text=title, command=lambda column=key: self.sort_by(column))
            stretch = key in {"name_zh", "name", "extra"}
            anchor = "e" if key in NUMERIC_COLUMNS else "w"
            self.tree.column(key, width=widths[key], stretch=stretch, anchor=anchor)
        yscroll = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")
        self.tree.tag_configure("up", foreground=SUFFIX)
        self.tree.tag_configure("down", foreground="#e08a8a")
        self.tree.tag_configure("flat", foreground=PREFIX)
        self.tree.bind("<Double-1>", self.open_selected)
        self.tree.bind("<Return>", self.open_selected)

        status = tk.Frame(self, bg=BG_HEAD)
        status.pack(fill="x")
        tk.Label(status, textvariable=self.status_var, bg=BG_HEAD, fg=MUTED, font=FONT_SMALL, anchor="w").pack(
            side="left", padx=16, pady=6
        )
        self.progress = ttk.Progressbar(status, mode="determinate", length=220)
        self.progress.pack(side="right", padx=16, pady=8)

    def current_league(self) -> League | None:
        name = self.league_var.get()
        for league in self.leagues:
            if league.name == name or league.id == name:
                return league
        return self.leagues[0] if self.leagues else None

    def _startup(self) -> None:
        threading.Thread(target=self._load_leagues_worker, daemon=True).start()

    def _load_leagues_worker(self) -> None:
        try:
            leagues = fetch_leagues()
        except RuntimeError as error:
            self.after(0, lambda message=str(error): self._fail(message))
            return
        self.after(0, lambda: self._on_leagues(leagues))

    def _on_leagues(self, leagues: list[League]) -> None:
        self.leagues = leagues
        names = [league.name for league in leagues]
        self.league_combo.configure(values=names)
        if names and self.league_var.get() not in names:
            self.league_var.set(names[0])
        self.load_prices()

    def reload_prices(self) -> None:
        league = self.current_league()
        if league:
            clear_cache(league.id)
        self.load_prices(force=True)

    def load_prices(self, force: bool = False) -> None:
        if self._loading:
            self._pending_load = force
            return
        league = self.current_league()
        if not league:
            return
        category = self.category_var.get() or "通貨"
        query = self.search_var.get().strip()
        if category == ALL and not force and len(query) < 2:
            self.rows = []
            self.refresh()
            self.status_var.set("分類選「全部」時，請輸入至少兩個字再查詢，避免一次下載所有分類。")
            return
        self._loading = True
        self._pending_load = None
        self.status_var.set(f"正在下載 {league.name} / {category}…")
        self.progress.configure(value=0, maximum=1)
        threading.Thread(target=self._load_prices_worker, args=(league, category, force), daemon=True).start()

    def _load_prices_worker(self, league: League, category: str, force: bool) -> None:
        def progress(done: int, total: int, message: str) -> None:
            self.after(0, lambda: self._set_progress(done, total, message))

        try:
            rows = fetch_prices(league, category, force=force, progress=progress)
        except RuntimeError as error:
            self.after(0, lambda message=str(error): self._fail(message))
            return
        self.after(0, lambda: self._on_prices(rows, league, category))

    def _set_progress(self, done: int, total: int, message: str) -> None:
        self.progress.configure(maximum=max(total, 1), value=done)
        self.status_var.set(message)

    def _on_prices(self, rows: list[PriceRow], league: League, category: str) -> None:
        self._loading = False
        self.rows = rows
        self.progress.configure(value=1, maximum=1)
        self.refresh()
        if self._pending_load is not None:
            pending = self._pending_load
            self._pending_load = None
            self.load_prices(force=pending)

    def _fail(self, message: str) -> None:
        self._loading = False
        self._pending_load = None
        self.status_var.set(message)
        messagebox.showerror("價格查詢失敗", message, parent=self)

    def refresh(self) -> None:
        query = self.search_var.get()
        category = self.category_var.get() or ALL
        if category == ALL and len(query.strip()) >= 2 and not self.rows and not self._loading:
            self.load_prices()
            return
        visible = [row for row in self.rows if matches(row, query)]
        if category == ALL and not query.strip():
            visible = []
        self.tree.delete(*self.tree.get_children(""))
        self._row_urls.clear()
        for row in visible:
            tag = "flat"
            if row.change is not None and row.change > 0.05:
                tag = "up"
            elif row.change is not None and row.change < -0.05:
                tag = "down"
            item_id = self.tree.insert(
                "",
                "end",
                values=(
                    row.display_zh,
                    row.name,
                    row.category,
                    format_price(row.chaos),
                    format_price(row.divine),
                    format_change(row.change),
                    row.extra,
                    format_listings(row.listings),
                ),
                tags=(tag,),
            )
            self._row_urls[item_id] = row.ninja_url
        self._sort_chaos_desc()
        if category == ALL and not query.strip():
            self.status_var.set("分類選「全部」時，請輸入至少兩個字再查詢。")
        elif self.rows:
            league = self.current_league()
            league_name = league.name if league else ""
            self.status_var.set(f"{league_name} · 顯示 {len(visible):,} / {len(self.rows):,} 筆 · poe.ninja")

    def _sort_chaos_desc(self) -> None:
        rows = list(self.tree.get_children(""))

        def chaos_of(item_id: str) -> float:
            text = str(self.tree.set(item_id, "chaos")).replace("—", "0").replace(",", "")
            try:
                return float(text)
            except ValueError:
                return 0.0

        rows.sort(key=chaos_of, reverse=True)
        for index, item_id in enumerate(rows):
            self.tree.move(item_id, "", index)
        self.tree._sort_state = {"col": "chaos", "desc": True}

    def sort_by(self, column: str) -> None:
        sort_tree(self.tree, column, numeric=column in NUMERIC_COLUMNS)

    def open_selected(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        url = self._row_urls.get(selected[0])
        if url:
            webbrowser.open(url)
