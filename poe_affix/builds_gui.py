"""poe.ninja build ranking window."""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

import customtkinter as ctk

from .builds import (
    GAME_LABELS,
    LADDER_DELVE,
    LADDER_EXP,
    TREND_DAY_LABELS,
    BuildLeague,
    RankRow,
    builds_page,
    clear_cache,
    enrich_row,
    enrich_combo_trend,
    fetch_index,
    fetch_ranks,
    format_daily_trend,
    format_stat,
    is_private_league,
    matches,
    parse_stat,
    sparkline,
)
from . import load_settings, save_settings
from .builds_icons import preload_class_icons
from .search_combo import bind_searchable_combo, filter_choices
from .theme import (
    BG,
    BG_PANEL,
    FONT_FAMILY,
    FONT_SECTION,
    FONT_SMALL,
    GOLD,
    GOLD_HI,
    LINE_SOFT,
    MUTED,
    PREFIX,
    SUFFIX,
    TEXT,
    GameToggle,
    content_panel,
    filter_panel,
    ghost_button,
    make_header,
    make_status_bar,
    muted_hint,
    primary_button,
    setup_window,
)

VIEW_CLASS = "熱門昇華"
VIEW_SKILL = "熱門技能"
VIEW_COMBO = "熱門流派"
TREND_TITLES = TREND_DAY_LABELS
NUMERIC_COLUMNS = {"rank", "count", "percent", "yesterday", "delta", "dps", "ehp", "life", "es"}


def format_count(value: int) -> str:
    if not value:
        return "—"
    return f"{value:,}"


def format_percent(value: float) -> str:
    if value <= 0:
        return "—"
    return f"{value:.1f}%"


def format_delta(value: float) -> str:
    if not value:
        return "0.0%"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


class BuildsApp(ctk.CTkToplevel):
    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master)
        self._on_back = on_back
        self.title("流亡黯道 · 流派排名")
        self.geometry("1480x860")
        self.minsize(1100, 640)
        setup_window(self)
        self.protocol("WM_DELETE_WINDOW", self.go_back)

        self.leagues: list[BuildLeague] = []
        self.class_rows: list[RankRow] = []
        self.skill_rows: list[RankRow] = []
        self.combo_rows: list[RankRow] = []
        self.total = 0
        self.day_totals: dict[str, int] = {}
        self._loading = False
        self._pending_load = False
        self._row_by_id: dict[str, RankRow] = {}
        self._selected: RankRow | None = None
        self._class_photos: dict[str, tk.PhotoImage] = {}
        self._class_ctk_icons: dict[str, ctk.CTkImage] = {}
        self._blank_photo: tk.PhotoImage | None = None
        self._detail_icon_ref = None
        saved_game = str(load_settings().get("builds_game") or "poe1")
        self.game_id = "poe2" if saved_game == "poe2" else "poe1"

        self.league_var = tk.StringVar()
        self.ladder_var = tk.StringVar(value=LADDER_EXP)
        self.view_var = tk.StringVar(value=VIEW_COMBO)
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="正在連線 poe.ninja…")
        self.detail_title_var = tk.StringVar(value="選擇一列看 DPS、EHP、逐日占比與傳奇")
        self.detail_stats_var = tk.StringVar(value="")
        self.detail_items_var = tk.StringVar(value="")
        self._league_options: list[str] = []
        self._ladder_options = [LADDER_EXP, LADDER_DELVE]
        self._view_options = [VIEW_COMBO, VIEW_CLASS, VIEW_SKILL]

        self._build()
        self.search_var.trace_add("write", lambda *_: self.refresh())
        self.after(80, self._startup)

    def go_back(self) -> None:
        self.destroy()
        self._on_back()

    def _build(self) -> None:
        make_header(
            self,
            "流派排名",
            on_back=self.go_back,
            right_actions=[
                ("重新整理", self.reload),
                ("開啟 poe.ninja", self.open_league_page),
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
        bind_searchable_combo(self.league_combo, lambda: self._league_options, self.load_ranks)

        ctk.CTkLabel(filters, text="榜單", font=FONT_SMALL, text_color=MUTED).grid(row=0, column=4, sticky="w", padx=(0, 6))
        self.ladder_combo = ttk.Combobox(
            filters, textvariable=self.ladder_var, state="normal", width=10, values=self._ladder_options
        )
        self.ladder_combo.grid(row=0, column=5, padx=(0, 16))
        bind_searchable_combo(self.ladder_combo, lambda: self._ladder_options, self.load_ranks)

        ctk.CTkLabel(filters, text="檢視", font=FONT_SMALL, text_color=MUTED).grid(row=0, column=6, sticky="w", padx=(0, 6))
        self.view_combo = ttk.Combobox(
            filters, textvariable=self.view_var, state="normal", width=12, values=self._view_options
        )
        self.view_combo.grid(row=0, column=7, padx=(0, 16))
        bind_searchable_combo(self.view_combo, lambda: self._view_options, self.refresh)

        ctk.CTkLabel(filters, text="搜尋", font=FONT_SMALL, text_color=MUTED).grid(row=0, column=8, sticky="w", padx=(0, 6))
        ttk.Entry(filters, textvariable=self.search_var, width=28).grid(row=0, column=9, sticky="ew")
        filters.grid_columnconfigure(9, weight=1)

        self.hint_label = muted_hint(
            self,
            "資料來自 poe.ninja Builds（會節流請求，避免被 rate limit）。"
            "列表會顯示昇華職業頭像；傳奇與流派逐日在點選列時再補抓。雙擊列開官網。",
        )
        self._apply_ladder_options()

        body = content_panel(self)
        pane = ttk.Panedwindow(body, orient="vertical")
        pane.pack(fill="both", expand=True, padx=10, pady=10)

        wrap = ttk.Frame(pane)
        columns = (
            "rank",
            "name_zh",
            "skill_zh",
            "count",
            "percent",
            "yesterday",
            "delta",
            "spark",
            "dps",
            "ehp",
            "life",
            "es",
            "items",
        )
        self.tree = ttk.Treeview(wrap, columns=columns, show="tree headings", selectmode="browse")
        self.headings = {
            "rank": "排名",
            "name_zh": "昇華／名稱",
            "skill_zh": "技能",
            "count": "人數",
            "percent": "占比",
            "yesterday": "昨日",
            "delta": "漲跌",
            "spark": "趨勢",
            "dps": "DPS",
            "ehp": "EHP",
            "life": "生命",
            "es": "能盾",
            "items": "熱門傳奇",
        }
        widths = {
            "rank": 52,
            "name_zh": 110,
            "skill_zh": 160,
            "count": 72,
            "percent": 64,
            "yesterday": 58,
            "delta": 64,
            "spark": 90,
            "dps": 72,
            "ehp": 72,
            "life": 64,
            "es": 64,
            "items": 240,
        }
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=40, minwidth=36, stretch=False, anchor="center")
        style = ttk.Style(self)
        style.configure("Treeview", rowheight=34)
        for key, title in self.headings.items():
            self.tree.heading(key, text=title, command=lambda column=key: self.sort_by(column))
            stretch = key in {"name_zh", "skill_zh", "items"}
            anchor = "e" if key in NUMERIC_COLUMNS else "w"
            self.tree.column(key, width=widths[key], stretch=stretch, anchor=anchor)
        yscroll = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")
        self.tree.tag_configure("top", foreground=GOLD)
        self.tree.tag_configure("row", foreground=PREFIX)
        self.tree.tag_configure("up", foreground=SUFFIX)
        self.tree.tag_configure("down", foreground="#e08a8a")
        self.tree.bind("<Double-1>", self.open_selected)
        self.tree.bind("<Return>", self.open_selected)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        pane.add(wrap, weight=3)

        detail = tk.Frame(pane, bg=BG_PANEL, highlightbackground=GOLD, highlightthickness=1)
        pane.add(detail, weight=2)

        detail_split = ttk.Panedwindow(detail, orient="horizontal")
        detail_split.pack(fill="both", expand=True, padx=8, pady=8)

        info_host = ttk.Frame(detail_split)
        detail_split.add(info_host, weight=3)
        info_wrap = ctk.CTkFrame(info_host, fg_color=BG_PANEL, corner_radius=12, border_width=1, border_color=LINE_SOFT)
        info_wrap.pack(fill="both", expand=True)
        self.detail_scroll = ctk.CTkScrollableFrame(
            info_wrap,
            fg_color=BG_PANEL,
            corner_radius=0,
            scrollbar_button_color=LINE_SOFT,
            scrollbar_button_hover_color=GOLD,
        )
        self.detail_scroll.pack(fill="both", expand=True, padx=8, pady=8)
        title_row = ctk.CTkFrame(self.detail_scroll, fg_color="transparent")
        title_row.pack(fill="x", pady=(0, 6))
        self.detail_icon_label = ctk.CTkLabel(title_row, text="", width=40, height=40)
        self.detail_icon_label.pack(side="left", padx=(0, 8))
        self.detail_title = ctk.CTkLabel(
            title_row, textvariable=self.detail_title_var, font=FONT_SECTION, text_color=GOLD, anchor="w"
        )
        self.detail_title.pack(side="left", fill="x", expand=True)
        self.detail_stats = ctk.CTkLabel(
            self.detail_scroll,
            textvariable=self.detail_stats_var,
            font=FONT_SMALL,
            text_color=PREFIX,
            anchor="w",
            justify="left",
        )
        self.detail_stats.pack(fill="x", pady=(0, 8))
        self.detail_sections = ctk.CTkFrame(self.detail_scroll, fg_color="transparent")
        self.detail_sections.pack(fill="both", expand=True)
        self._detail_labels: dict[str, ctk.CTkLabel] = {}
        for key, title in (
            ("trend", "逐日占比變化"),
            ("dps", "傷害組成（中位占比）"),
            ("skills", "熱門技能"),
            ("supports", "常見寶石／輔助／精魂"),
            ("keys", "關鍵被動／鑰石"),
            ("items", "熱門傳奇（含使用占比）"),
            ("meta", "武器／塗油／特性／其他"),
        ):
            block = ctk.CTkFrame(
                self.detail_sections, fg_color="#12161f", corner_radius=10, border_width=1, border_color=LINE_SOFT
            )
            block.pack(fill="x", pady=4)
            ctk.CTkLabel(block, text=title, font=(FONT_FAMILY, 12, "bold"), text_color=GOLD_HI, anchor="w").pack(
                fill="x", padx=10, pady=(8, 2)
            )
            label = ctk.CTkLabel(
                block,
                text="—",
                font=FONT_SMALL,
                text_color=TEXT,
                anchor="w",
                justify="left",
                wraplength=720,
            )
            label.pack(fill="x", padx=10, pady=(0, 8))
            self._detail_labels[key] = label

        action_row = ctk.CTkFrame(self.detail_scroll, fg_color="transparent")
        action_row.pack(fill="x", pady=(8, 0))
        primary_button(action_row, "在 poe.ninja 開啟此流派", command=self.open_selected, width=180).pack(side="left")
        ghost_button(action_row, "複製摘要", command=self.copy_detail, width=100).pack(side="left", padx=8)

        right_wrap = tk.Frame(detail_split, bg=BG_PANEL)
        detail_split.add(right_wrap, weight=2)
        chart_wrap = tk.Frame(right_wrap, bg=BG_PANEL)
        chart_wrap.pack(side="top", fill="both", expand=True, padx=(8, 0), pady=(0, 8))
        tk.Label(chart_wrap, text="近 7 日占比", bg=BG_PANEL, fg=MUTED, font=FONT_SMALL, anchor="w").pack(fill="x")
        self.chart = tk.Canvas(chart_wrap, bg=BG, highlightthickness=0, height=160)
        self.chart.pack(fill="both", expand=True)
        self.chart.bind("<Configure>", lambda _event: self._draw_chart(self._selected))

        sample_wrap = tk.Frame(right_wrap, bg=BG_PANEL)
        sample_wrap.pack(side="bottom", fill="both", expand=True, padx=(8, 0))
        tk.Label(sample_wrap, text="樣本角色（雙擊開啟）", bg=BG_PANEL, fg=MUTED, font=FONT_SMALL, anchor="w").pack(fill="x")
        sample_cols = ("name", "account", "level", "dps", "ehp", "life", "es", "weapon")
        self.sample_tree = ttk.Treeview(sample_wrap, columns=sample_cols, show="headings", selectmode="browse", height=8)
        sample_heads = {
            "name": "角色",
            "account": "帳號",
            "level": "等級",
            "dps": "DPS",
            "ehp": "EHP",
            "life": "生命",
            "es": "能盾",
            "weapon": "武器",
        }
        for key, title in sample_heads.items():
            self.sample_tree.heading(key, text=title)
            width = 70
            if key == "account":
                width = 120
            elif key == "weapon":
                width = 110
            elif key == "name":
                width = 110
            self.sample_tree.column(key, width=width, stretch=True, anchor="w")
        self.sample_tree.pack(fill="both", expand=True)
        self.sample_tree.bind("<Double-1>", self.open_sample)
        self._sample_urls: dict[str, str] = {}

    def _apply_ladder_options(self) -> None:
        if self.game_id == "poe2":
            self._ladder_options = [LADDER_EXP]
            self.ladder_var.set(LADDER_EXP)
            self.ladder_combo.configure(values=self._ladder_options, state="disabled")
        else:
            self._ladder_options = [LADDER_EXP, LADDER_DELVE]
            self.ladder_combo.configure(values=self._ladder_options, state="normal")
            if self.ladder_var.get() not in self._ladder_options:
                self.ladder_var.set(LADDER_EXP)

    def on_game_changed(self, value: str | None = None) -> None:
        label = (value or self.game_switch.get() or "PoE1").strip()
        game = "poe2" if label == "PoE2" else "poe1"
        if game == self.game_id and self.leagues and self.leagues[0].game == game:
            return
        self.game_id = game
        save_settings({"builds_game": game})
        self._apply_ladder_options()
        self.class_rows = []
        self.skill_rows = []
        self.combo_rows = []
        self.total = 0
        self.day_totals = {}
        self._selected = None
        self._class_photos.clear()
        self._class_ctk_icons.clear()
        self._detail_icon_ref = None
        self.league_var.set("")
        self.status_var.set(f"正在載入 {GAME_LABELS[game]} 聯盟列表…")
        self._startup()

    def current_league(self) -> BuildLeague | None:
        name = (self.league_var.get() or "").strip()
        ladder = self._resolved_ladder()
        hits = [league for league in self.leagues if league.name == name and league.ladder_label == ladder]
        if hits:
            return hits[0]
        named = [league for league in self.leagues if league.name == name]
        if len(named) == 1:
            return named[0]
        matches_name = filter_choices(name, [league.name for league in self.leagues])
        if len(matches_name) == 1:
            self.league_var.set(matches_name[0])
            return self.current_league()
        return next(
            (league for league in self.leagues if league.ladder_label == ladder),
            self.leagues[0] if self.leagues else None,
        )

    def _resolved_ladder(self) -> str:
        typed = (self.ladder_var.get() or "").strip()
        if typed in self._ladder_options:
            return typed
        hits = filter_choices(typed, self._ladder_options)
        if len(hits) == 1:
            self.ladder_var.set(hits[0])
            return hits[0]
        return LADDER_EXP

    def _resolved_view(self) -> str:
        typed = (self.view_var.get() or "").strip()
        if typed in self._view_options:
            return typed
        hits = filter_choices(typed, self._view_options)
        if len(hits) == 1:
            self.view_var.set(hits[0])
            return hits[0]
        return VIEW_COMBO

    def _startup(self) -> None:
        threading.Thread(target=self._index_worker, daemon=True).start()

    def _index_worker(self) -> None:
        try:
            index = fetch_index(game=self.game_id)
        except RuntimeError as error:
            self.after(0, lambda message=str(error): self._fail(message))
            return
        self.after(0, lambda: self._on_index(index.leagues))

    def _on_index(self, leagues: list[BuildLeague]) -> None:
        self.leagues = leagues
        names: list[str] = []
        for league in leagues:
            if league.name not in names:
                names.append(league.name)
        # Prefer public leagues in the combobox; keep private ones at the end.
        public = [name for name in names if not is_private_league(name)]
        private = [name for name in names if is_private_league(name)]
        self._league_options = public + private
        self.league_combo.configure(values=self._league_options)
        if self._league_options and (
            not self.league_var.get() or self.league_var.get() not in self._league_options
        ):
            self.league_var.set(public[0] if public else self._league_options[0])
        self.load_ranks()

    def reload(self) -> None:
        clear_cache()
        self._startup()

    def load_ranks(self) -> None:
        league = self.current_league()
        if not league:
            return
        if self._loading:
            self._pending_load = True
            return
        self._loading = True
        self._pending_load = False
        self.status_var.set(f"正在下載 {league.name} / {league.ladder_label} 的流派、DPS 與逐日資料…")
        try:
            self.progress.start()
        except Exception:
            pass
        threading.Thread(target=self._ranks_worker, args=(league,), daemon=True).start()

    def _ranks_worker(self, league: BuildLeague) -> None:
        try:
            total, class_rows, skill_rows, combo_rows, day_totals = fetch_ranks(league)
        except RuntimeError as error:
            self.after(0, lambda message=str(error): self._fail(message))
            return
        self.after(0, lambda: self._on_ranks(league, total, class_rows, skill_rows, combo_rows, day_totals))

    def _on_ranks(
        self,
        league: BuildLeague,
        total: int,
        class_rows: list[RankRow],
        skill_rows: list[RankRow],
        combo_rows: list[RankRow],
        day_totals: dict[str, int],
    ) -> None:
        self._loading = False
        try:
            self.progress.stop()
            self.progress.set(1)
        except Exception:
            pass
        self.total = total
        self.class_rows = class_rows
        self.skill_rows = skill_rows
        self.combo_rows = combo_rows
        self.day_totals = day_totals
        league.character_count = total
        self.refresh()
        self._select_first()
        self._start_icon_preload()
        if self._pending_load:
            self._pending_load = False
            self.load_ranks()

    def _class_names_for_icons(self) -> list[str]:
        names: list[str] = []
        for row in (*self.class_rows, *self.combo_rows):
            if row.name and row.name not in names:
                names.append(row.name)
        return names

    def _start_icon_preload(self) -> None:
        names = self._class_names_for_icons()
        if not names:
            return
        missing = [name for name in names if name not in self._class_photos]
        if not missing:
            return
        game = self.game_id
        threading.Thread(target=self._icon_worker, args=(game, missing), daemon=True).start()

    def _icon_worker(self, game: str, names: list[str]) -> None:
        try:
            loaded = preload_class_icons(game, names)
        except Exception:
            return
        self.after(0, lambda: self._on_icons_loaded(game, loaded))

    def _on_icons_loaded(self, game: str, loaded: dict[str, bytes]) -> None:
        if game != self.game_id or not loaded:
            return
        try:
            from PIL import Image, ImageTk
            import io
        except Exception:
            return
        for name, png in loaded.items():
            try:
                image = Image.open(io.BytesIO(png)).convert("RGBA")
                tree_img = image.resize((28, 28), Image.Resampling.LANCZOS)
                detail_img = image.resize((40, 40), Image.Resampling.LANCZOS)
                self._class_photos[name] = ImageTk.PhotoImage(tree_img, master=self)
                self._class_ctk_icons[name] = ctk.CTkImage(light_image=detail_img, dark_image=detail_img, size=(40, 40))
            except Exception:
                continue
        selected = self._selected
        self.refresh()
        if selected:
            self._restore_selection(selected)

    def _row_icon(self, row: RankRow):
        if row.kind in {"class", "combo"} and row.name in self._class_photos:
            return self._class_photos[row.name]
        if self._blank_photo is None:
            # 1x1 transparent placeholder keeps column alignment stable.
            self._blank_photo = tk.PhotoImage(master=self, width=1, height=1)
        return self._blank_photo

    def _fail(self, message: str) -> None:
        self._loading = False
        try:
            self.progress.stop()
            self.progress.set(0)
        except Exception:
            pass
        self.status_var.set(message)
        messagebox.showerror("流派排名失敗", message, parent=self)

    def _current_rows(self) -> list[RankRow]:
        view = self._resolved_view()
        if view == VIEW_CLASS:
            return self.class_rows
        if view == VIEW_SKILL:
            return self.skill_rows
        return self.combo_rows

    def refresh(self) -> None:
        query = self.search_var.get()
        rows = [row for row in self._current_rows() if matches(row, query)]
        self.tree.delete(*self.tree.get_children(""))
        self._row_by_id.clear()
        view = self._resolved_view()
        for row in rows:
            if row.delta > 0.05:
                tag = "up"
            elif row.delta < -0.05:
                tag = "down"
            else:
                tag = "top" if row.rank <= 3 else "row"
            item_id = self.tree.insert(
                "",
                "end",
                image=self._row_icon(row),
                values=(
                    row.rank,
                    row.name_zh,
                    row.extra_zh or "—",
                    format_count(row.count),
                    format_percent(row.percent),
                    format_percent(row.yesterday),
                    format_delta(row.delta),
                    sparkline(row.trend) if row.trend else "…",
                    format_stat(row.dps),
                    format_stat(row.ehp),
                    format_stat(row.life) if row.life else "—",
                    format_stat(row.es),
                    "、".join(row.items[:3]) or "—",
                ),
                tags=(tag,),
            )
            self._row_by_id[item_id] = row
        league = self.current_league()
        league_name = league.name if league else ""
        ladder = league.ladder_label if league else ""
        if view == VIEW_COMBO and not self._current_rows():
            self.status_var.set(f"{league_name} 目前沒有流派組合，可改看熱門昇華或熱門技能。")
        elif self.total:
            self.status_var.set(f"{league_name} · {ladder} · {self.total:,} 名角色 · 顯示 {len(rows):,} 筆 · poe.ninja")
        else:
            self.status_var.set(f"{league_name} · 顯示 {len(rows):,} 筆 · poe.ninja")

    def _select_first(self) -> None:
        children = self.tree.get_children("")
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
            self.tree.see(children[0])

    def _restore_selection(self, row: RankRow) -> None:
        for item_id, mapped in self._row_by_id.items():
            if mapped is row:
                self.tree.selection_set(item_id)
                self._show_detail(row)
                return
        self._select_first()

    def _on_select(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        row = self._row_by_id.get(selected[0])
        if row:
            self._show_detail(row)

    def _show_detail(self, row: RankRow) -> None:
        self._selected = row
        title = row.name_zh
        if row.extra_zh:
            title = f"{row.name_zh}  ·  {row.extra_zh}"
        self.detail_title_var.set(f"{row.rank}. {title}")
        icon = self._class_ctk_icons.get(row.name) if row.kind in {"class", "combo"} else None
        self._detail_icon_ref = icon
        if icon is not None:
            self.detail_icon_label.configure(image=icon, text="")
        else:
            self.detail_icon_label.configure(image=None, text="")
        bits = [
            f"占比 {format_percent(row.percent)}",
            f"人數 {format_count(row.count)}",
            f"中位 DPS {format_stat(row.dps)}",
            f"中位 EHP {format_stat(row.ehp)}",
            f"生命 {format_stat(row.life) if row.life else '—'}",
            f"能盾 {format_stat(row.es)}",
        ]
        if row.level:
            bits.append(f"等級 {row.level}")
        if row.yesterday:
            bits.append(f"昨日 {format_percent(row.yesterday)}（{format_delta(row.delta)}）")
        self.detail_stats_var.set("　·　".join(bits))

        if row.dps_share:
            dps_text = "　".join(f"{name} {value:.0f}%" for name, value in row.dps_share.items())
        else:
            dps_text = "尚無元素占比樣本（可能還在載入，或此列沒有 DPS 細項）。"
        trend_text = format_daily_trend(row)
        if trend_text:
            self._detail_labels["trend"].configure(text=trend_text)
        else:
            self._detail_labels["trend"].configure(text="尚無逐日快照（新聯盟可能只有小時標籤，或資料仍在載入）。")
        self._detail_labels["dps"].configure(text=dps_text)
        self._detail_labels["skills"].configure(text="、".join(row.skills) if row.skills else "尚無技能樣本")
        support_bits = list(row.supports)
        for gem in row.spirit_gems:
            if gem not in support_bits:
                support_bits.append(gem)
        self._detail_labels["supports"].configure(text="、".join(support_bits) if support_bits else "尚無寶石樣本")
        self._detail_labels["keys"].configure(text="、".join(row.keystones) if row.keystones else "尚無關鍵被動樣本")
        self._detail_labels["items"].configure(text="、".join(row.items) if row.items else "尚無傳奇樣本")
        meta_bits = []
        if row.weapon_modes:
            meta_bits.append("武器：" + "、".join(row.weapon_modes))
        if row.traits:
            meta_bits.append("特性：" + "、".join(row.traits))
        if row.anointed:
            meta_bits.append("塗油／注能：" + "、".join(row.anointed))
        if row.second_ascendancy:
            meta_bits.append("血脈：" + "、".join(row.second_ascendancy))
        if row.pantheon:
            meta_bits.append("神殿：" + "、".join(row.pantheon))
        if row.bandit:
            meta_bits.append("強盜：" + "、".join(row.bandit))
        self._detail_labels["meta"].configure(text="\n".join(meta_bits) if meta_bits else "尚無額外配置樣本")
        self.detail_items_var.set("")

        self._draw_chart(row)
        self.sample_tree.delete(*self.sample_tree.get_children(""))
        self._sample_urls.clear()
        for sample in row.samples:
            item_id = self.sample_tree.insert(
                "",
                "end",
                values=(
                    sample.name,
                    sample.account,
                    sample.level or "—",
                    sample.dps_text or format_stat(sample.dps),
                    sample.ehp_text or format_stat(sample.ehp),
                    format_stat(sample.life) if sample.life else "—",
                    format_stat(sample.es),
                    sample.weapon or "—",
                ),
            )
            self._sample_urls[item_id] = sample.ninja_url

        if not row.samples and not row.items and not row.dps:
            self._detail_labels["items"].configure(text="正在補抓此列細節…")
            threading.Thread(target=self._enrich_worker, args=(row,), daemon=True).start()
        elif row.kind == "combo" and not row.trend and self.day_totals:
            self._detail_labels["trend"].configure(text="正在補抓此流派逐日占比…")
            threading.Thread(target=self._enrich_worker, args=(row,), daemon=True).start()

    def _enrich_worker(self, row: RankRow) -> None:
        league = self.current_league()
        if not league:
            return
        try:
            enrich_row(league, row)
            if row.kind == "combo" and self.day_totals:
                enrich_combo_trend(league, row, self.day_totals)
        except Exception:
            return
        self.after(0, lambda: self._after_enrich(row))

    def _after_enrich(self, row: RankRow) -> None:
        if self._selected is not row:
            return
        self._show_detail(row)
        # Refresh sparkline column for this row without rebuilding the whole table selection.
        for item_id, mapped in self._row_by_id.items():
            if mapped is row:
                values = list(self.tree.item(item_id, "values"))
                # columns: rank name skill count percent yesterday delta spark ...
                if len(values) >= 8:
                    values[5] = format_percent(row.yesterday)
                    values[6] = format_delta(row.delta)
                    values[7] = sparkline(row.trend) if row.trend else "…"
                    values[8] = format_stat(row.dps)
                    values[9] = format_stat(row.ehp)
                    values[12] = "、".join(row.items[:3]) or "—"
                    self.tree.item(item_id, values=values)
                break

    def copy_detail(self) -> None:
        row = self._selected
        if not row:
            messagebox.showinfo("沒有資料", "請先選一列流派。", parent=self)
            return
        lines = [
            self.detail_title_var.get(),
            self.detail_stats_var.get(),
            "逐日占比：" + self._detail_labels["trend"].cget("text"),
            "傷害組成：" + self._detail_labels["dps"].cget("text"),
            "熱門技能：" + self._detail_labels["skills"].cget("text"),
            "常見寶石：" + self._detail_labels["supports"].cget("text"),
            "關鍵被動：" + self._detail_labels["keys"].cget("text"),
            "傳奇：" + self._detail_labels["items"].cget("text"),
            self._detail_labels["meta"].cget("text"),
        ]
        if row.ninja_url:
            lines.append(row.ninja_url)
        text = "\n".join(line for line in lines if line)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set("已複製流派摘要到剪貼簿")

    def _draw_chart(self, row: RankRow | None) -> None:
        canvas = self.chart
        canvas.delete("all")
        width = max(canvas.winfo_width(), 120)
        height = max(canvas.winfo_height(), 80)
        if row is None or not row.trend:
            canvas.create_text(width / 2, height / 2, text="尚無逐日占比", fill=MUTED, font=FONT_SMALL)
            return
        values = list(row.trend)
        labels = list(TREND_TITLES[-len(values) :])
        pad_l, pad_r, pad_t, pad_b = 42, 16, 10, 26
        chart_w = max(width - pad_l - pad_r, 10)
        chart_h = max(height - pad_t - pad_b, 10)
        high = max(values) * 1.15 if max(values) > 0 else 1.0
        low = 0.0
        points = []
        for index, value in enumerate(values):
            x = pad_l + chart_w * index / max(len(values) - 1, 1)
            y = pad_t + chart_h * (1 - (value - low) / (high - low))
            points.append((x, y, value, labels[index] if index < len(labels) else ""))
        if len(points) >= 2:
            area = [points[0][0], pad_t + chart_h]
            for x, y, _value, _label in points:
                area.extend([x, y])
            area.extend([points[-1][0], pad_t + chart_h])
            canvas.create_polygon(*area, fill="#2a2418", outline="")
            flat = []
            for x, y, _value, _label in points:
                flat.extend([x, y])
            canvas.create_line(*flat, fill=GOLD, width=2, smooth=True)
        for x, y, value, label in points:
            canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=GOLD, outline=BG)
            canvas.create_text(x, pad_t + chart_h + 12, text=label, fill=MUTED, font=FONT_SMALL)
            canvas.create_text(x, y - 12, text=f"{value:.1f}%", fill=PREFIX, font=FONT_SMALL)
        canvas.create_text(18, pad_t, text=f"{high:.1f}%", fill=MUTED, font=FONT_SMALL, anchor="nw")
        canvas.create_text(18, pad_t + chart_h, text="0%", fill=MUTED, font=FONT_SMALL, anchor="sw")

    def sort_by(self, column: str) -> None:
        state = getattr(self.tree, "_sort_state", {"col": None, "desc": True})
        descending = not state["desc"] if state["col"] == column else True
        self.tree._sort_state = {"col": column, "desc": descending}

        def value_of(item_id: str):
            row = self._row_by_id.get(item_id)
            if row is not None:
                mapping = {
                    "rank": row.rank,
                    "count": row.count,
                    "percent": row.percent,
                    "yesterday": row.yesterday,
                    "delta": row.delta,
                    "dps": row.dps,
                    "ehp": row.ehp,
                    "life": row.life,
                    "es": row.es,
                    "spark": row.percent,
                }
                if column in mapping:
                    return mapping[column]
            raw = str(self.tree.set(item_id, column)).replace("—", "").replace(",", "").replace("%", "").replace("+", "")
            if column in NUMERIC_COLUMNS:
                return parse_stat(raw) if raw else 0.0
            return raw.lower()

        rows = list(self.tree.get_children(""))
        rows.sort(key=value_of, reverse=descending)
        for index, item_id in enumerate(rows):
            self.tree.move(item_id, "", index)

    def open_league_page(self) -> None:
        league = self.current_league()
        webbrowser.open(league.page_url if league else builds_page(self.game_id))

    def open_selected(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        row = self._row_by_id.get(selected[0])
        if row and row.ninja_url:
            webbrowser.open(row.ninja_url)

    def open_sample(self, _event=None) -> None:
        selected = self.sample_tree.selection()
        if not selected:
            return
        url = self._sample_urls.get(selected[0])
        if url:
            webbrowser.open(url)
