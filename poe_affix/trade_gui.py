"""Official Path of Exile trade lookup window."""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

import customtkinter as ctk

from .search_combo import bind_searchable_combo, bind_structured_suggest, choice_matches
from .theme import (
    FONT_SMALL,
    FONT_UI,
    GOLD,
    MUTED,
    TEXT,
    content_panel,
    filter_panel,
    ghost_button,
    make_header,
    make_status_bar,
    muted_hint,
    primary_button,
    set_progress,
    setup_window,
    sort_tree,
)
from .trade import (
    CATEGORY_LABELS,
    CORRUPT_LABELS,
    DEFAULT_STATUS_LABEL,
    PRICE_CURRENCY_LABELS,
    RARITY_LABELS,
    STATUS_LABELS,
    TRADE_PAGE,
    SearchFilters,
    StatFilter,
    SuggestRow,
    TradeItem,
    TradeLeague,
    TradeRateLimitError,
    TradeSearchResult,
    TradeStat,
    cooldown_remaining,
    fetch_items,
    fetch_leagues,
    fetch_stats,
    optional_int,
    optional_number,
    resolve_category,
    resolve_corrupt,
    resolve_english_query,
    resolve_price_currency,
    resolve_rarity,
    resolve_status,
    search_items,
    status_label,
    suggest_items,
    suggest_stats,
    trade_search_url,
)


class _StatRow:
    def __init__(self, parent, on_remove, get_suggest) -> None:
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.stat: TradeStat | None = None
        self.text_var = tk.StringVar()
        self.min_var = tk.StringVar()
        self.max_var = tk.StringVar()
        self.text_var.trace_add("write", self._on_typed)

        self.entry = ttk.Entry(self.frame, textvariable=self.text_var, width=36)
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        bind_structured_suggest(
            self.entry,
            get_rows=get_suggest,
            on_pick=self._on_pick,
            on_commit=None,
        )
        ttk.Entry(self.frame, textvariable=self.min_var, width=6).grid(row=0, column=1, padx=2)
        ctk.CTkLabel(self.frame, text="~", font=FONT_SMALL, text_color=MUTED, width=12).grid(row=0, column=2)
        ttk.Entry(self.frame, textvariable=self.max_var, width=6).grid(row=0, column=3, padx=2)
        ghost_button(self.frame, "×", command=lambda: on_remove(self), width=36).grid(row=0, column=4, padx=(4, 0))
        self.frame.grid_columnconfigure(0, weight=1)

    def _on_typed(self, *_args) -> None:
        if self.stat is None:
            return
        if self.text_var.get().strip() != self.stat.text:
            self.stat = None

    def _on_pick(self, row: SuggestRow) -> None:
        if row.stat is None:
            return
        self.stat = row.stat
        self.text_var.set(row.stat.text)
        self.entry.icursor("end")

    def to_filter(self) -> StatFilter | None:
        if self.stat is None:
            return None
        return StatFilter(
            stat_id=self.stat.id,
            text=self.stat.text,
            min_value=optional_number(self.min_var.get()),
            max_value=optional_number(self.max_var.get()),
        )

    def clear(self) -> None:
        self.stat = None
        self.text_var.set("")
        self.min_var.set("")
        self.max_var.set("")

    def destroy(self) -> None:
        self.frame.destroy()


class TradeApp(ctk.CTkToplevel):
    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master)
        self._on_back = on_back
        self.title("流亡黯道 · 官方賣場")
        self.geometry("1480x860")
        self.minsize(1100, 640)
        setup_window(self)
        self.protocol("WM_DELETE_WINDOW", self.go_back)

        self.leagues: list[TradeLeague] = []
        self.listings: list[TradeListing] = []
        self._last_result: TradeSearchResult | None = None
        self._loading = False
        self._row_whispers: dict[str, str] = {}
        self._picked: TradeItem | None = None
        self._catalog_ready = False
        self._stats_ready = False
        self._cooldown_job: str | None = None
        self._stat_rows: list[_StatRow] = []

        self.league_var = tk.StringVar()
        self.search_var = tk.StringVar()
        self.status_mode_var = tk.StringVar(value=DEFAULT_STATUS_LABEL)
        self.category_var = tk.StringVar(value="不限")
        self.rarity_var = tk.StringVar(value="不限")
        self.corrupt_var = tk.StringVar(value="不限")
        self.ilvl_min_var = tk.StringVar()
        self.ilvl_max_var = tk.StringVar()
        self.price_currency_var = tk.StringVar(value="混沌石")
        self.price_min_var = tk.StringVar()
        self.price_max_var = tk.StringVar()
        self.status_var = tk.StringVar(value="正在連線官方賣場…")
        self.query_hint_var = tk.StringVar(value="")
        self._league_options: list[str] = []
        self._status_options = list(STATUS_LABELS)
        self._category_options = list(CATEGORY_LABELS)
        self._rarity_options = list(RARITY_LABELS)
        self._corrupt_options = list(CORRUPT_LABELS)
        self._price_currency_options = list(PRICE_CURRENCY_LABELS)

        self._build()
        self.search_var.trace_add("write", self._on_search_typed)
        self.after(80, self._startup)

    def go_back(self) -> None:
        self.destroy()
        self._on_back()

    def _build(self) -> None:
        make_header(
            self,
            "官方賣場",
            on_back=self.go_back,
            right_actions=[
                ("清除過濾", self.clear_filters),
                ("開啟搜尋頁", self.open_current_search),
                ("開啟賣場首頁", self.open_league_home),
            ],
        )
        _, self.progress = make_status_bar(self, self.status_var, with_progress=True)

        filters = filter_panel(self)
        ctk.CTkLabel(filters, text="聯盟", font=FONT_SMALL, text_color=MUTED).grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.league_combo = ttk.Combobox(filters, textvariable=self.league_var, state="normal", width=18)
        self.league_combo.grid(row=0, column=1, padx=(0, 12))
        bind_searchable_combo(self.league_combo, lambda: self._league_options)

        ctk.CTkLabel(filters, text="物品名", font=FONT_SMALL, text_color=MUTED).grid(row=0, column=2, sticky="w", padx=(0, 6))
        self.search_entry = ttk.Entry(filters, textvariable=self.search_var, width=34)
        self.search_entry.grid(row=0, column=3, sticky="ew", padx=(0, 12))
        bind_structured_suggest(
            self.search_entry,
            get_rows=self._suggest_item_rows,
            on_pick=self._on_suggest_pick,
            on_commit=self.run_search,
        )

        ctk.CTkLabel(filters, text="賣家", font=FONT_SMALL, text_color=MUTED).grid(row=0, column=4, sticky="w", padx=(0, 6))
        self.status_combo = ttk.Combobox(
            filters,
            textvariable=self.status_mode_var,
            state="normal",
            width=22,
            values=self._status_options,
        )
        self.status_combo.grid(row=0, column=5, padx=(0, 12))
        bind_searchable_combo(self.status_combo, lambda: self._status_options)

        primary_button(filters, "搜尋上架", command=self.run_search, width=100).grid(row=0, column=6)
        filters.grid_columnconfigure(3, weight=1)

        muted_hint(
            self,
            "資料來自 pathofexile.com/trade。左側可設分類／稀有度／物等／汙染／價格／詞綴。"
            "物品名可留空（只用過濾條件）。請勿連續猛按搜尋。雙擊列可複製密語。",
        )
        ctk.CTkLabel(self, textvariable=self.query_hint_var, font=FONT_SMALL, text_color=MUTED, anchor="w").pack(
            fill="x", padx=20, pady=(0, 2)
        )

        body = content_panel(self)
        pane = ttk.Panedwindow(body, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=8, pady=8)

        left = ttk.Frame(pane)
        right = ttk.Frame(pane)
        pane.add(left, weight=1)
        pane.add(right, weight=3)

        self._build_filter_side(left)
        self._build_results(right)

    def _build_filter_side(self, parent) -> None:
        ctk.CTkLabel(parent, text="過濾條件", font=FONT_UI, text_color=GOLD, anchor="w").pack(
            fill="x", padx=8, pady=(6, 4)
        )
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent", corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=4, pady=4)

        def row(label: str, widget, r: int) -> None:
            ctk.CTkLabel(scroll, text=label, font=FONT_SMALL, text_color=MUTED, anchor="w").grid(
                row=r, column=0, sticky="w", pady=3, padx=(4, 6)
            )
            widget.grid(row=r, column=1, sticky="ew", pady=3)
            scroll.grid_columnconfigure(1, weight=1)

        self.category_combo = ttk.Combobox(
            scroll, textvariable=self.category_var, state="normal", width=22, values=self._category_options
        )
        bind_searchable_combo(self.category_combo, lambda: self._category_options)
        row("分類", self.category_combo, 0)

        self.rarity_combo = ttk.Combobox(
            scroll, textvariable=self.rarity_var, state="normal", width=22, values=self._rarity_options
        )
        bind_searchable_combo(self.rarity_combo, lambda: self._rarity_options)
        row("稀有度", self.rarity_combo, 1)

        self.corrupt_combo = ttk.Combobox(
            scroll, textvariable=self.corrupt_var, state="normal", width=22, values=self._corrupt_options
        )
        bind_searchable_combo(self.corrupt_combo, lambda: self._corrupt_options)
        row("汙染", self.corrupt_combo, 2)

        ilvl = ctk.CTkFrame(scroll, fg_color="transparent")
        ttk.Entry(ilvl, textvariable=self.ilvl_min_var, width=8).pack(side="left")
        ctk.CTkLabel(ilvl, text=" ~ ", font=FONT_SMALL, text_color=MUTED).pack(side="left")
        ttk.Entry(ilvl, textvariable=self.ilvl_max_var, width=8).pack(side="left")
        row("物等", ilvl, 3)

        price = ctk.CTkFrame(scroll, fg_color="transparent")
        self.price_currency_combo = ttk.Combobox(
            price,
            textvariable=self.price_currency_var,
            state="normal",
            width=10,
            values=self._price_currency_options,
        )
        self.price_currency_combo.pack(side="left", padx=(0, 4))
        bind_searchable_combo(self.price_currency_combo, lambda: self._price_currency_options)
        ttk.Entry(price, textvariable=self.price_min_var, width=7).pack(side="left")
        ctk.CTkLabel(price, text=" ~ ", font=FONT_SMALL, text_color=MUTED).pack(side="left")
        ttk.Entry(price, textvariable=self.price_max_var, width=7).pack(side="left")
        row("價格", price, 4)

        ctk.CTkLabel(scroll, text="詞綴（and）", font=FONT_SMALL, text_color=TEXT, anchor="w").grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(12, 4), padx=4
        )
        self.stat_list = ctk.CTkFrame(scroll, fg_color="transparent")
        self.stat_list.grid(row=6, column=0, columnspan=2, sticky="ew")
        scroll.grid_columnconfigure(1, weight=1)

        btns = ctk.CTkFrame(scroll, fg_color="transparent")
        btns.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(8, 4))
        primary_button(btns, "新增詞綴", command=self.add_stat_row, width=100).pack(side="left", padx=(0, 8))
        ghost_button(btns, "清除過濾", command=self.clear_filters, width=100).pack(side="left")

        self.add_stat_row()

    def _build_results(self, parent) -> None:
        inner = ctk.CTkFrame(parent, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=4, pady=4)
        columns = ("name_zh", "name", "price", "method", "ilvl", "flags", "account", "indexed")
        self.tree = ttk.Treeview(inner, columns=columns, show="headings", selectmode="browse")
        self.headings = {
            "name_zh": "中文",
            "name": "英文",
            "price": "價格",
            "method": "交易方式",
            "ilvl": "物等",
            "flags": "標記",
            "account": "帳號",
            "indexed": "上架時間",
        }
        widths = {
            "name_zh": 150,
            "name": 170,
            "price": 100,
            "method": 110,
            "ilvl": 52,
            "flags": 70,
            "account": 140,
            "indexed": 150,
        }
        for key, title in self.headings.items():
            self.tree.heading(key, text=title, command=lambda column=key: self.sort_by(column))
            stretch = key in {"name_zh", "name", "account", "indexed"}
            anchor = "e" if key in {"price", "ilvl"} else "w"
            self.tree.column(key, width=widths[key], stretch=stretch, anchor=anchor)
        yscroll = ttk.Scrollbar(inner, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self.copy_whisper)
        self.tree.bind("<Return>", self.copy_whisper)

    def add_stat_row(self) -> None:
        row = _StatRow(self.stat_list, on_remove=self.remove_stat_row, get_suggest=self._suggest_stat_rows)
        row.frame.pack(fill="x", pady=3)
        self._stat_rows.append(row)

    def remove_stat_row(self, row: _StatRow) -> None:
        if row in self._stat_rows:
            self._stat_rows.remove(row)
        row.destroy()
        if not self._stat_rows:
            self.add_stat_row()

    def clear_filters(self) -> None:
        self.category_var.set("不限")
        self.rarity_var.set("不限")
        self.corrupt_var.set("不限")
        self.ilvl_min_var.set("")
        self.ilvl_max_var.set("")
        self.price_currency_var.set("混沌石")
        self.price_min_var.set("")
        self.price_max_var.set("")
        for row in list(self._stat_rows):
            row.destroy()
        self._stat_rows.clear()
        self.add_stat_row()
        self.query_hint_var.set("已清除過濾條件")

    def collect_filters(self) -> SearchFilters:
        stats: list[StatFilter] = []
        for row in self._stat_rows:
            hit = row.to_filter()
            if hit is not None:
                stats.append(hit)
        return SearchFilters(
            category=resolve_category(self.category_var.get()),
            rarity=resolve_rarity(self.rarity_var.get()),
            ilvl_min=optional_int(self.ilvl_min_var.get()),
            ilvl_max=optional_int(self.ilvl_max_var.get()),
            corrupted=resolve_corrupt(self.corrupt_var.get()),
            price_currency=resolve_price_currency(self.price_currency_var.get()),
            price_min=optional_number(self.price_min_var.get()),
            price_max=optional_number(self.price_max_var.get()),
            stats=tuple(stats),
        )

    def _on_search_typed(self, *_args) -> None:
        if self._picked is None:
            return
        current = self.search_var.get().strip()
        if current != self._picked.search_text:
            self._picked = None

    def _suggest_item_rows(self, typed: str) -> list[SuggestRow]:
        if not self._catalog_ready:
            return []
        return suggest_items(typed)

    def _suggest_stat_rows(self, typed: str) -> list[SuggestRow]:
        if not self._stats_ready:
            return []
        return suggest_stats(typed)

    def _on_suggest_pick(self, row: SuggestRow) -> None:
        item = row.item
        if item is None:
            return
        self._picked = item
        self.search_var.set(item.search_text)
        self.search_entry.icursor("end")
        self.query_hint_var.set(f"已選：{item.display}")
        self.run_search()

    def current_league(self) -> TradeLeague | None:
        name = (self.league_var.get() or "").strip()
        for league in self.leagues:
            if league.name == name or league.id == name:
                return league
        hits = [league for league in self.leagues if choice_matches(name, league.name)]
        if len(hits) == 1:
            self.league_var.set(hits[0].name)
            return hits[0]
        return self.leagues[0] if self.leagues else None

    def _startup(self) -> None:
        threading.Thread(target=self._load_leagues_worker, daemon=True).start()
        threading.Thread(target=self._load_catalog_worker, daemon=True).start()
        threading.Thread(target=self._load_stats_worker, daemon=True).start()

    def _load_catalog_worker(self) -> None:
        try:
            items = fetch_items()
        except RuntimeError as error:
            self.after(0, lambda message=str(error): self._on_catalog_fail(message))
            return
        self.after(0, lambda: self._on_catalog(len(items)))

    def _load_stats_worker(self) -> None:
        try:
            stats = fetch_stats()
        except RuntimeError as error:
            self.after(0, lambda message=str(error): self.query_hint_var.set(f"詞綴清單載入失敗：{message}"))
            return
        self.after(0, lambda: self._on_stats(len(stats)))

    def _on_catalog(self, count: int) -> None:
        self._catalog_ready = True
        if "正在連線" in self.status_var.get() or "已連上" in self.status_var.get():
            base = self.status_var.get()
            if "物品提示" not in base:
                self.status_var.set(f"{base}　物品提示 {count:,}")

    def _on_stats(self, count: int) -> None:
        self._stats_ready = True
        if "詞綴" not in self.status_var.get():
            self.status_var.set(f"{self.status_var.get()}　詞綴 {count:,}")

    def _on_catalog_fail(self, message: str) -> None:
        self._catalog_ready = False
        self.query_hint_var.set(f"物品提示載入失敗：{message}")

    def _load_leagues_worker(self) -> None:
        try:
            leagues = fetch_leagues()
        except RuntimeError as error:
            self.after(0, lambda message=str(error): self._fail(message))
            return
        self.after(0, lambda: self._on_leagues(leagues))

    def _on_leagues(self, leagues: list[TradeLeague]) -> None:
        self.leagues = leagues
        names = [league.name for league in leagues]
        self._league_options = names
        self.league_combo.configure(values=names)
        preferred = next((n for n in names if n == "Allflame"), None) or (names[0] if names else "")
        if preferred and self.league_var.get() not in names:
            self.league_var.set(preferred)
        self.status_var.set(f"已連上官方賣場，共 {len(names)} 個聯盟。")
        set_progress(self.progress, 1, 1)

    def open_league_home(self) -> None:
        league = self.current_league()
        url = trade_search_url(league.id) if league else TRADE_PAGE
        webbrowser.open(url)

    def open_current_search(self) -> None:
        if self._last_result and self._last_result.url:
            webbrowser.open(self._last_result.url)
            return
        league = self.current_league()
        if not league:
            webbrowser.open(TRADE_PAGE)
            return
        query = resolve_english_query(self.search_var.get())
        filters = self.collect_filters()
        if query or not filters.is_empty():
            self.run_search(open_after=True)
            return
        webbrowser.open(trade_search_url(league.id))

    def current_status(self) -> str:
        return resolve_status(self.status_mode_var.get())

    def run_search(self, open_after: bool = False) -> None:
        if self._loading:
            return
        remaining = cooldown_remaining()
        if remaining > 0:
            self._start_cooldown_ui(remaining)
            return
        league = self.current_league()
        if not league:
            self.status_var.set("請先選擇聯盟")
            return
        query = self.search_var.get().strip()
        search_filters = self.collect_filters()
        if not query and search_filters.is_empty() and self._picked is None:
            self.status_var.set("請輸入物品名，或至少設定一項過濾條件")
            return
        status_option = self.current_status()
        self.status_mode_var.set(status_label(status_option))
        picked = self._picked
        if picked is not None:
            self.query_hint_var.set(f"精確：{picked.display}")
            label = picked.search_text
        elif query:
            hint = resolve_english_query(query)
            self.query_hint_var.set(f"對照：{hint}" if hint != query else f"關鍵字：{query}")
            label = query
        else:
            label = "過濾搜尋"
            self.query_hint_var.set("僅使用左側過濾條件")
        self._loading = True
        self.status_var.set(f"正在搜尋 {league.name} / {label}…")
        set_progress(self.progress, 0, 1)
        threading.Thread(
            target=self._search_worker,
            args=(
                league.id,
                query,
                status_option,
                open_after,
                picked.exact_name if picked else None,
                picked.exact_type if picked else None,
                search_filters,
            ),
            daemon=True,
        ).start()

    def _search_worker(
        self,
        league_id: str,
        query: str,
        status_option: str,
        open_after: bool,
        exact_name: str | None,
        exact_type: str | None,
        search_filters: SearchFilters,
    ) -> None:
        try:
            result = search_items(
                league_id,
                query,
                status=status_option,
                exact_name=exact_name,
                exact_type=exact_type,
                filters=search_filters,
            )
        except TradeRateLimitError as error:
            seconds = error.retry_after
            self.after(0, lambda wait=seconds: self._on_rate_limited(wait))
            return
        except RuntimeError as error:
            self.after(0, lambda message=str(error): self._fail(message))
            return
        self.after(0, lambda: self._on_search(result, open_after))

    def _on_search(self, result: TradeSearchResult, open_after: bool) -> None:
        self._loading = False
        self._last_result = result
        self.listings = result.listings
        set_progress(self.progress, 1, 1)
        self.refresh()
        shown = len(result.listings)
        cache_note = "（快取）" if result.from_cache else ""
        self.status_var.set(
            f"{result.query_en}：共 {result.total:,} 筆，顯示最低價 {shown} 筆{cache_note}。"
            " 可按「開啟搜尋頁」看完整結果。"
        )
        if open_after and result.url:
            webbrowser.open(result.url)

    def _on_rate_limited(self, seconds: int) -> None:
        self._loading = False
        set_progress(self.progress, 1, 1)
        self._start_cooldown_ui(seconds)
        messagebox.showwarning(
            "官方賣場限流",
            f"官方賣場暫時限制請求頻率。\n請約 {int(seconds)} 秒後再搜尋，或改開官方網頁。",
            parent=self,
        )

    def _start_cooldown_ui(self, seconds: float) -> None:
        if self._cooldown_job:
            self.after_cancel(self._cooldown_job)
            self._cooldown_job = None
        remaining = max(1, int(seconds + 0.999))
        self.status_var.set(f"官方限流中，請等待約 {remaining} 秒後再搜尋…")
        self._tick_cooldown()

    def _tick_cooldown(self) -> None:
        remaining = cooldown_remaining()
        if remaining <= 0:
            self._cooldown_job = None
            if not self._loading:
                self.status_var.set("限流已解除，可以再搜尋了。")
            return
        self.status_var.set(f"官方限流中，請等待約 {int(remaining + 0.999)} 秒後再搜尋…")
        self._cooldown_job = self.after(1000, self._tick_cooldown)

    def _fail(self, message: str) -> None:
        self._loading = False
        self.status_var.set(message)
        set_progress(self.progress, 1, 1)
        if "請求過快" in message or "限流" in message:
            messagebox.showwarning("官方賣場限流", message, parent=self)
            return
        messagebox.showerror("官方賣場失敗", message, parent=self)

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._row_whispers.clear()
        for index, row in enumerate(self.listings):
            flags = []
            if row.corrupted:
                flags.append("汙染")
            if row.mirrors:
                flags.append("鏡像")
            iid = str(index)
            self._row_whispers[iid] = row.whisper
            method = row.method_zh
            if row.fee is not None:
                method = f"{method}（金{row.fee:,}）"
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    row.name_zh or "—",
                    row.name,
                    row.price_text,
                    method,
                    row.ilvl if row.ilvl is not None else "—",
                    "／".join(flags) if flags else "—",
                    row.account or "—",
                    row.indexed or "—",
                ),
            )

    def sort_by(self, column: str) -> None:
        sort_tree(self.tree, column, numeric=column in {"ilvl"})

    def copy_whisper(self, *_args) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        whisper = self._row_whispers.get(selection[0], "")
        if not whisper:
            self.status_var.set("這筆沒有密語可複製")
            return
        self.clipboard_clear()
        self.clipboard_append(whisper)
        self.status_var.set("已複製密語到剪貼簿")
