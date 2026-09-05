"""poe.ninja economy price lookup window."""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

import customtkinter as ctk

from . import load_settings, save_settings
from .economy import (
    ALL,
    GAINER_WORKERS,
    GAME_LABELS,
    MIN_GAIN_PERCENT,
    League,
    PriceRow,
    category_labels,
    clear_cache,
    currency_labels,
    economy_page,
    fetch_leagues,
    fetch_prices,
    matches,
)
from .item_icons import absolute_icon_url, preload_icon_pngs
from .search_combo import bind_searchable_combo, choice_matches, filter_choices
from .theme import (
    FONT_SMALL,
    FONT_UI,
    MUTED,
    PREFIX,
    SUFFIX,
    GameToggle,
    content_panel,
    filter_panel,
    make_header,
    make_status_bar,
    muted_hint,
    primary_button,
    set_progress,
    setup_window,
    sort_tree,
)

NUMERIC_COLUMNS = {"primary", "secondary", "change", "listings"}
GAME_IDS = {label: game_id for game_id, label in GAME_LABELS.items()}


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


class EconomyApp(ctk.CTkToplevel):
    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master)
        self._on_back = on_back
        self.title("流亡黯道 · 價格查詢")
        self.geometry("1400x780")
        self.minsize(1080, 600)
        setup_window(self)
        self.protocol("WM_DELETE_WINDOW", self.go_back)

        self.leagues: list[League] = []
        self.rows: list[PriceRow] = []
        self._loading = False
        self._pending_load: bool | None = None
        self._row_urls: dict[str, str] = {}
        self._row_by_id: dict[str, PriceRow] = {}
        self._icon_photos: dict[str, tk.PhotoImage] = {}
        self._blank_photo: tk.PhotoImage | None = None
        self._icon_job = 0
        saved_game = str(load_settings().get("economy_game") or "poe1")
        self.game_id = saved_game if saved_game in GAME_LABELS else "poe1"

        self.league_var = tk.StringVar()
        self.category_var = tk.StringVar(value="通貨")
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="正在連線 poe.ninja…")
        self.top_gainer_var = tk.StringVar(value="")
        self._allow_all = False
        self._focus_top_gainer = False
        self._league_options: list[str] = []
        self._category_options: list[str] = [ALL, *category_labels(self.game_id)]

        self._build()
        self.search_var.trace_add("write", lambda *_: self.refresh())
        self.after(80, self._startup)

    def go_back(self) -> None:
        self.destroy()
        self._on_back()

    def _build(self) -> None:
        make_header(
            self,
            "價格查詢",
            on_back=self.go_back,
            right_actions=[
                ("重新整理", self.reload_prices),
                ("開啟 poe.ninja", lambda: webbrowser.open(economy_page(self.game_id))),
            ],
        )
        _, self.progress = make_status_bar(self, self.status_var, with_progress=True)

        filters = filter_panel(self)
        ctk.CTkLabel(filters, text="遊戲", font=FONT_SMALL, text_color=MUTED).grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.game_switch = GameToggle(
            filters,
            values=["PoE1", "PoE2"],
            width=168,
            height=30,
            command=self.on_game_changed,
        )
        self.game_switch.grid(row=0, column=1, padx=(0, 16))
        self.game_switch.set(GAME_LABELS[self.game_id])

        ctk.CTkLabel(filters, text="聯盟", font=FONT_SMALL, text_color=MUTED).grid(row=0, column=2, sticky="w", padx=(0, 6))
        self.league_combo = ttk.Combobox(filters, textvariable=self.league_var, state="normal", width=22)
        self.league_combo.grid(row=0, column=3, padx=(0, 16))
        bind_searchable_combo(self.league_combo, lambda: self._league_options, self.load_prices)

        ctk.CTkLabel(filters, text="分類", font=FONT_SMALL, text_color=MUTED).grid(row=0, column=4, sticky="w", padx=(0, 6))
        self.category_combo = ttk.Combobox(
            filters, textvariable=self.category_var, state="normal", width=16, values=self._category_options
        )
        self.category_combo.grid(row=0, column=5, padx=(0, 16))
        bind_searchable_combo(self.category_combo, lambda: self._category_options, self.load_prices)

        ctk.CTkLabel(filters, text="搜尋物品", font=FONT_SMALL, text_color=MUTED).grid(row=0, column=6, sticky="w", padx=(0, 6))
        ttk.Entry(filters, textvariable=self.search_var, width=36).grid(row=0, column=7, sticky="ew")
        primary_button(filters, f"漲幅≥{MIN_GAIN_PERCENT:.0f}%", command=self.show_top_gainer, width=110).grid(
            row=0, column=8, padx=(16, 0)
        )
        filters.grid_columnconfigure(7, weight=1)

        muted_hint(
            self,
            (
                "估價來自 poe.ninja（PoE1：混沌石／神聖石；PoE2：崇高石／神聖石）。名稱顯示中文與英文，兩邊都能搜。"
                "列表會顯示品項圖標（首次會下載快取）。聯盟／分類可輸入關鍵字後從清單點選。"
                f"分類選「全部」時可按「漲幅≥{MIN_GAIN_PERCENT:.0f}%」，只列出全部分類裡漲超過 {MIN_GAIN_PERCENT:.0f}% 的物品。雙擊列可開官網。"
            ),
        )
        ctk.CTkLabel(self, textvariable=self.top_gainer_var, font=FONT_UI, text_color=SUFFIX, anchor="w").pack(
            fill="x", padx=20, pady=(0, 2)
        )

        wrap = content_panel(self)
        inner = ctk.CTkFrame(wrap, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=10, pady=10)
        columns = ("name_zh", "name", "category", "primary", "secondary", "change", "extra", "listings")
        self.tree = ttk.Treeview(inner, columns=columns, show="tree headings", selectmode="browse")
        primary_label, secondary_label = currency_labels(self.game_id)
        self.headings = {
            "name_zh": "中文",
            "name": "英文",
            "category": "分類",
            "primary": primary_label,
            "secondary": secondary_label,
            "change": "近期漲跌",
            "extra": "細節",
            "listings": "上架數",
        }
        widths = {
            "name_zh": 220,
            "name": 220,
            "category": 100,
            "primary": 80,
            "secondary": 80,
            "change": 80,
            "extra": 220,
            "listings": 70,
        }
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=40, minwidth=36, stretch=False, anchor="center")
        style = ttk.Style(self)
        style.configure("Treeview", rowheight=34)
        for key, title in self.headings.items():
            self.tree.heading(key, text=title, command=lambda column=key: self.sort_by(column))
            stretch = key in {"name_zh", "name", "extra"}
            anchor = "e" if key in NUMERIC_COLUMNS else "w"
            self.tree.column(key, width=widths[key], stretch=stretch, anchor=anchor)
        yscroll = ttk.Scrollbar(inner, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")
        self.tree.tag_configure("up", foreground=SUFFIX)
        self.tree.tag_configure("down", foreground="#e08a8a")
        self.tree.tag_configure("flat", foreground=PREFIX)
        self.tree.bind("<Double-1>", self.open_selected)
        self.tree.bind("<Return>", self.open_selected)

    def current_league(self) -> League | None:
        name = (self.league_var.get() or "").strip()
        for league in self.leagues:
            if league.name == name or league.id == name:
                return league
        hits = [league for league in self.leagues if choice_matches(name, league.name)]
        if len(hits) == 1:
            self.league_var.set(hits[0].name)
            return hits[0]
        return self.leagues[0] if self.leagues else None

    def _resolved_category(self) -> str | None:
        typed = (self.category_var.get() or "").strip()
        options = self._category_options
        if typed in options:
            return typed
        hits = filter_choices(typed, options)
        if len(hits) == 1:
            self.category_var.set(hits[0])
            return hits[0]
        if not typed:
            return "通貨"
        return None

    def _startup(self) -> None:
        threading.Thread(target=self._load_leagues_worker, args=(self.game_id,), daemon=True).start()

    def on_game_changed(self, value: str) -> None:
        game = GAME_IDS.get(str(value).strip(), "poe1")
        if game == self.game_id:
            return
        self.game_id = game
        save_settings({"economy_game": game})
        self._allow_all = False
        self._focus_top_gainer = False
        self.top_gainer_var.set("")
        self.rows = []
        self.leagues = []
        self._league_options = []
        self.league_combo.configure(values=[])
        self.league_var.set("")
        self._category_options = [ALL, *category_labels(game)]
        self.category_combo.configure(values=self._category_options)
        if self.category_var.get() not in self._category_options:
            self.category_var.set("通貨")
        primary_label, secondary_label = currency_labels(game)
        self.headings["primary"] = primary_label
        self.headings["secondary"] = secondary_label
        self.tree.heading("primary", text=primary_label)
        self.tree.heading("secondary", text=secondary_label)
        self.tree.delete(*self.tree.get_children(""))
        self._row_urls.clear()
        self._row_by_id.clear()
        self._icon_photos.clear()
        self.status_var.set(f"正在連線 poe.ninja（{GAME_LABELS[game]}）…")
        threading.Thread(target=self._load_leagues_worker, args=(game,), daemon=True).start()

    def _load_leagues_worker(self, game: str) -> None:
        try:
            leagues = fetch_leagues(game=game)
        except RuntimeError as error:
            self.after(0, lambda message=str(error): self._fail(message))
            return
        self.after(0, lambda: self._on_leagues(leagues, game))

    def _on_leagues(self, leagues: list[League], game: str) -> None:
        if game != self.game_id:
            return
        self.leagues = leagues
        names = [league.name for league in leagues]
        self._league_options = names
        self.league_combo.configure(values=names)
        if names and self.league_var.get() not in names:
            self.league_var.set(names[0])
        self.load_prices()

    def reload_prices(self) -> None:
        league = self.current_league()
        if league:
            clear_cache(league.id, game=self.game_id)
        self.load_prices(force=True)

    def load_prices(self, force: bool = False) -> None:
        if self._loading:
            self._pending_load = force
            return
        league = self.current_league()
        if not league:
            return
        category = self._resolved_category()
        if not category:
            self.status_var.set("請從分類清單點選一個項目，或再輸入更完整的關鍵字。")
            return
        query = self.search_var.get().strip()
        if category != ALL:
            self._allow_all = False
            self._focus_top_gainer = False
            self.top_gainer_var.set("")
        if category == ALL and not self._allow_all and not force and len(query) < 2:
            self.rows = []
            self.refresh()
            self.status_var.set(f"分類選「全部」時，請輸入至少兩個字再查詢，或按「漲幅≥{MIN_GAIN_PERCENT:.0f}%」。")
            return
        self._loading = True
        self._pending_load = None
        self.status_var.set(f"正在下載 {GAME_LABELS[self.game_id]} {league.name} / {category}…")
        set_progress(self.progress, 0, 1)
        threading.Thread(
            target=self._load_prices_worker,
            args=(league, category, force, self.game_id),
            daemon=True,
        ).start()

    def _load_prices_worker(self, league: League, category: str, force: bool, game: str) -> None:
        def progress(done: int, total: int, message: str) -> None:
            self.after(0, lambda: self._set_progress(done, total, message))

        workers = GAINER_WORKERS if category == ALL else None
        try:
            rows = fetch_prices(
                league,
                category,
                force=force,
                progress=progress,
                max_workers=workers,
                game=game,
            )
        except RuntimeError as error:
            self.after(0, lambda message=str(error): self._fail(message))
            return
        self.after(0, lambda: self._on_prices(rows, league, category, game))

    def _set_progress(self, done: int, total: int, message: str) -> None:
        set_progress(self.progress, done, total)
        self.status_var.set(message)

    def _on_prices(self, rows: list[PriceRow], league: League, category: str, game: str) -> None:
        self._loading = False
        if game != self.game_id:
            return
        self.rows = rows
        set_progress(self.progress, 1, 1)
        self.refresh()
        if self._pending_load is not None:
            pending = self._pending_load
            self._pending_load = None
            self.load_prices(force=pending)

    def _fail(self, message: str) -> None:
        self._loading = False
        self._pending_load = None
        self._focus_top_gainer = False
        self.status_var.set(message)
        self.top_gainer_var.set("")
        messagebox.showerror("價格查詢失敗", message, parent=self)

    def _row_icon(self, row: PriceRow):
        url = absolute_icon_url(row.icon_url)
        if url and url in self._icon_photos:
            return self._icon_photos[url]
        if self._blank_photo is None:
            self._blank_photo = tk.PhotoImage(master=self, width=1, height=1)
        return self._blank_photo

    def _start_icon_preload(self, rows: list[PriceRow]) -> None:
        urls = [row.icon_url for row in rows if row.icon_url]
        missing = [url for url in urls if absolute_icon_url(url) not in self._icon_photos]
        if not missing:
            return
        self._icon_job += 1
        job = self._icon_job
        threading.Thread(target=self._icon_worker, args=(job, missing), daemon=True).start()

    def _icon_worker(self, job: int, urls: list[str]) -> None:
        try:
            loaded = preload_icon_pngs(urls, size=48, max_workers=8)
        except Exception:
            return
        self.after(0, lambda: self._on_icons_loaded(job, loaded))

    def _on_icons_loaded(self, job: int, loaded: dict[str, bytes]) -> None:
        if job != self._icon_job or not loaded:
            return
        try:
            from PIL import Image, ImageTk
            import io
        except Exception:
            return
        for url, png in loaded.items():
            if url in self._icon_photos:
                continue
            try:
                image = Image.open(io.BytesIO(png)).convert("RGBA").resize((28, 28), Image.Resampling.LANCZOS)
                self._icon_photos[url] = ImageTk.PhotoImage(image, master=self)
            except Exception:
                continue
        for item_id, row in list(self._row_by_id.items()):
            url = absolute_icon_url(row.icon_url)
            photo = self._icon_photos.get(url)
            if photo is not None:
                try:
                    self.tree.item(item_id, image=photo)
                except tk.TclError:
                    continue

    def refresh(self) -> None:
        query = self.search_var.get()
        category = self.category_var.get() or ALL
        if category == ALL and len(query.strip()) >= 2 and not self.rows and not self._loading:
            self.load_prices()
            return
        visible = [row for row in self.rows if matches(row, query)]
        if self._allow_all:
            visible = [
                row for row in visible if row.change is not None and row.change >= MIN_GAIN_PERCENT
            ]
        if category == ALL and not query.strip() and not self._allow_all:
            visible = []
        self.tree.delete(*self.tree.get_children(""))
        self._row_urls.clear()
        self._row_by_id.clear()
        visible_for_icons: list[PriceRow] = []
        for row in visible:
            tag = "flat"
            if row.change is not None and row.change > 0.05:
                tag = "up"
            elif row.change is not None and row.change < -0.05:
                tag = "down"
            item_id = self.tree.insert(
                "",
                "end",
                image=self._row_icon(row),
                values=(
                    row.display_zh,
                    row.name,
                    row.category,
                    format_price(row.primary),
                    format_price(row.secondary),
                    format_change(row.change),
                    row.extra,
                    format_listings(row.listings),
                ),
                tags=(tag,),
            )
            self._row_urls[item_id] = row.ninja_url
            self._row_by_id[item_id] = row
            visible_for_icons.append(row)
        if self._allow_all or self._focus_top_gainer:
            self._sort_change_desc()
        else:
            self._sort_primary_desc()
        self._start_icon_preload(visible_for_icons)
        if self._focus_top_gainer and visible:
            self._select_top_gainer(visible)
            self._focus_top_gainer = False
        elif category == ALL and not query.strip() and not self._allow_all:
            self.top_gainer_var.set("")
            self.status_var.set(
                f"分類選「全部」時，請輸入至少兩個字，或按「漲幅≥{MIN_GAIN_PERCENT:.0f}%」只看大漲的物品。"
            )
        elif self._allow_all:
            self.status_var.set(f"只顯示漲幅 ≥ {MIN_GAIN_PERCENT:.0f}% · {len(visible):,} 筆 · poe.ninja")
        elif self.rows:
            league = self.current_league()
            league_name = league.name if league else ""
            self.status_var.set(
                f"{GAME_LABELS[self.game_id]} {league_name} · 顯示 {len(visible):,} / {len(self.rows):,} 筆 · poe.ninja"
            )

    def show_top_gainer(self) -> None:
        self._allow_all = True
        self._focus_top_gainer = True
        self.category_var.set(ALL)
        self.rows = []
        if self.search_var.get():
            self.search_var.set("")
        self.top_gainer_var.set(f"正在下載全部分類，只列出漲幅 ≥ {MIN_GAIN_PERCENT:.0f}% 的物品…")
        self.load_prices()

    def _select_top_gainer(self, visible: list[PriceRow]) -> None:
        if not visible:
            self.top_gainer_var.set(f"全部分類裡目前沒有漲幅 ≥ {MIN_GAIN_PERCENT:.0f}% 的物品。")
            self.status_var.set(f"已載入全部物品，沒有漲超過 {MIN_GAIN_PERCENT:.0f}% 的項目。")
            return
        children = list(self.tree.get_children(""))
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
            self.tree.see(children[0])
        top = visible[0]
        # visible is not yet sorted here; use the first tree row after change-desc sort.
        top_name = str(self.tree.set(children[0], "name_zh") if children else (top.display_zh or top.name))
        top_change = str(self.tree.set(children[0], "change") if children else format_change(top.change))
        self.top_gainer_var.set(
            f"漲幅 ≥ {MIN_GAIN_PERCENT:.0f}%：{len(visible)} 筆　最高 {top_name} {top_change}"
        )
        self.status_var.set(f"只顯示漲幅 ≥ {MIN_GAIN_PERCENT:.0f}% · {len(visible):,} 筆 · 已依漲跌排序")

    def _sort_change_desc(self) -> None:
        rows = list(self.tree.get_children(""))

        def change_of(item_id: str) -> float:
            text = str(self.tree.set(item_id, "change")).replace("%", "").replace("—", "").replace(",", "").replace("+", "")
            try:
                return float(text)
            except ValueError:
                return float("-inf")

        rows.sort(key=change_of, reverse=True)
        for index, item_id in enumerate(rows):
            self.tree.move(item_id, "", index)
        self.tree._sort_state = {"col": "change", "desc": True}

    def _sort_primary_desc(self) -> None:
        rows = list(self.tree.get_children(""))

        def primary_of(item_id: str) -> float:
            text = str(self.tree.set(item_id, "primary")).replace("—", "0").replace(",", "")
            try:
                return float(text)
            except ValueError:
                return 0.0

        rows.sort(key=primary_of, reverse=True)
        for index, item_id in enumerate(rows):
            self.tree.move(item_id, "", index)
        self.tree._sort_state = {"col": "primary", "desc": True}

    def sort_by(self, column: str) -> None:
        sort_tree(self.tree, column, numeric=column in NUMERIC_COLUMNS)

    def open_selected(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        url = self._row_urls.get(selected[0])
        if url:
            webbrowser.open(url)
