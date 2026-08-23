"""poe.ninja build ranking window."""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from .builds import (
    BUILDS_PAGE,
    LADDER_DELVE,
    LADDER_EXP,
    BuildLeague,
    RankRow,
    clear_cache,
    fetch_combo_trends,
    fetch_index,
    fetch_ranks,
    format_stat,
    matches,
    parse_stat,
    sparkline,
)
from .search_combo import bind_searchable_combo, filter_choices
from .theme import BG, BG_HEAD, BG_PANEL, FONT_SMALL, FONT_UI, GOLD, MUTED, PREFIX, SUFFIX, apply_theme

VIEW_CLASS = "熱門昇華"
VIEW_SKILL = "熱門技能"
VIEW_COMBO = "熱門流派"
TREND_TITLES = ("6日前", "5日前", "4日前", "3日前", "2日前", "昨日", "今日")
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


class BuildsApp(tk.Toplevel):
    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master)
        self._on_back = on_back
        self.title("流亡黯道 · 流派排名")
        self.geometry("1480x860")
        self.minsize(1100, 640)
        self.configure(bg=BG)
        self.option_add("*Font", FONT_UI)
        apply_theme(self)
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

        self.league_var = tk.StringVar()
        self.ladder_var = tk.StringVar(value=LADDER_EXP)
        self.view_var = tk.StringVar(value=VIEW_COMBO)
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="正在連線 poe.ninja…")
        self.detail_title_var = tk.StringVar(value="選擇一列看 DPS、EHP 與逐日占比")
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
        header = tk.Frame(self, bg=BG_HEAD)
        header.pack(fill="x")
        tk.Frame(self, bg=GOLD, height=3).pack(fill="x")
        ttk.Button(header, text="← 主選單", command=self.go_back).pack(side="left", padx=16, pady=12)
        ttk.Label(header, text="流派排名", style="Gold.TLabel", background=BG_HEAD).pack(side="left", pady=12)
        ttk.Button(header, text="重新整理", command=self.reload).pack(side="right", padx=16, pady=12)
        ttk.Button(header, text="開啟 poe.ninja", command=self.open_league_page).pack(side="right", padx=(0, 8), pady=12)

        filters = ttk.Frame(self, padding=(16, 12, 16, 8))
        filters.pack(fill="x")
        ttk.Label(filters, text="聯盟", style="Muted.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.league_combo = ttk.Combobox(filters, textvariable=self.league_var, state="normal", width=22)
        self.league_combo.grid(row=0, column=1, padx=(0, 16))
        bind_searchable_combo(self.league_combo, lambda: self._league_options, self.load_ranks)

        ttk.Label(filters, text="榜單", style="Muted.TLabel").grid(row=0, column=2, sticky="w", padx=(0, 6))
        self.ladder_combo = ttk.Combobox(
            filters, textvariable=self.ladder_var, state="normal", width=10, values=self._ladder_options
        )
        self.ladder_combo.grid(row=0, column=3, padx=(0, 16))
        bind_searchable_combo(self.ladder_combo, lambda: self._ladder_options, self.load_ranks)

        ttk.Label(filters, text="檢視", style="Muted.TLabel").grid(row=0, column=4, sticky="w", padx=(0, 6))
        self.view_combo = ttk.Combobox(
            filters, textvariable=self.view_var, state="normal", width=12, values=self._view_options
        )
        self.view_combo.grid(row=0, column=5, padx=(0, 16))
        bind_searchable_combo(self.view_combo, lambda: self._view_options, self.refresh)

        ttk.Label(filters, text="搜尋", style="Muted.TLabel").grid(row=0, column=6, sticky="w", padx=(0, 6))
        ttk.Entry(filters, textvariable=self.search_var, width=28).grid(row=0, column=7, sticky="ew")
        filters.columnconfigure(7, weight=1)

        ttk.Label(
            self,
            text="資料來自 poe.ninja。DPS／EHP 是樣本角色的中位數（PoB 模擬值）。占比趨勢來自近 6 日快照。雙擊列開流派頁，雙擊角色開該角色。",
            style="Muted.TLabel",
        ).pack(anchor="w", padx=16)

        pane = ttk.Panedwindow(self, orient="vertical")
        pane.pack(fill="both", expand=True, padx=16, pady=8)

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
        self.tree = ttk.Treeview(wrap, columns=columns, show="headings", selectmode="browse")
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
        pane.add(detail, weight=1)
        top = tk.Frame(detail, bg=BG_PANEL)
        top.pack(fill="x", padx=12, pady=(8, 4))
        tk.Label(top, textvariable=self.detail_title_var, bg=BG_PANEL, fg=GOLD, font=FONT_UI, anchor="w").pack(fill="x")
        tk.Label(top, textvariable=self.detail_stats_var, bg=BG_PANEL, fg=PREFIX, font=FONT_SMALL, anchor="w").pack(fill="x")
        tk.Label(top, textvariable=self.detail_items_var, bg=BG_PANEL, fg=MUTED, font=FONT_SMALL, anchor="w", wraplength=1400, justify="left").pack(fill="x")

        body = tk.Frame(detail, bg=BG_PANEL)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        chart_wrap = tk.Frame(body, bg=BG_PANEL)
        chart_wrap.pack(side="left", fill="both", expand=True, padx=(0, 12))
        tk.Label(chart_wrap, text="近 7 日占比", bg=BG_PANEL, fg=MUTED, font=FONT_SMALL, anchor="w").pack(fill="x")
        self.chart = tk.Canvas(chart_wrap, bg=BG, highlightthickness=0, height=160)
        self.chart.pack(fill="both", expand=True)
        self.chart.bind("<Configure>", lambda _event: self._draw_chart(self._selected))

        sample_wrap = tk.Frame(body, bg=BG_PANEL)
        sample_wrap.pack(side="right", fill="both", expand=True)
        tk.Label(sample_wrap, text="樣本角色（雙擊開啟）", bg=BG_PANEL, fg=MUTED, font=FONT_SMALL, anchor="w").pack(fill="x")
        sample_cols = ("name", "account", "dps", "ehp", "life", "es")
        self.sample_tree = ttk.Treeview(sample_wrap, columns=sample_cols, show="headings", selectmode="browse", height=6)
        sample_heads = {"name": "角色", "account": "帳號", "dps": "DPS", "ehp": "EHP", "life": "生命", "es": "能盾"}
        for key, title in sample_heads.items():
            self.sample_tree.heading(key, text=title)
            self.sample_tree.column(key, width=90 if key != "account" else 140, stretch=True, anchor="w")
        self.sample_tree.pack(fill="both", expand=True)
        self.sample_tree.bind("<Double-1>", self.open_sample)
        self._sample_urls: dict[str, str] = {}

        status = tk.Frame(self, bg=BG_HEAD)
        status.pack(fill="x")
        tk.Label(status, textvariable=self.status_var, bg=BG_HEAD, fg=MUTED, font=FONT_SMALL, anchor="w").pack(
            side="left", padx=16, pady=6
        )
        self.progress = ttk.Progressbar(status, mode="indeterminate", length=180)
        self.progress.pack(side="right", padx=16, pady=8)

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
            index = fetch_index()
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
        self._league_options = names
        self.league_combo.configure(values=names)
        if names and self.league_var.get() not in names:
            self.league_var.set(names[0])
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
        self.progress.start(12)
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
        self.progress.stop()
        self.total = total
        self.class_rows = class_rows
        self.skill_rows = skill_rows
        self.combo_rows = combo_rows
        self.day_totals = day_totals
        league.character_count = total
        self.refresh()
        self._select_first()
        if combo_rows and day_totals:
            self.status_var.set(self.status_var.get() + "　正在補齊流派逐日占比…")
            threading.Thread(target=self._trend_worker, args=(league, combo_rows, day_totals), daemon=True).start()
        if self._pending_load:
            self._pending_load = False
            self.load_ranks()

    def _trend_worker(self, league: BuildLeague, rows: list[RankRow], day_totals: dict[str, int]) -> None:
        try:
            fetch_combo_trends(league, rows, day_totals)
        except Exception:
            return
        self.after(0, self._on_combo_trends)

    def _on_combo_trends(self) -> None:
        selected = self._selected
        self.refresh()
        if selected:
            self._restore_selection(selected)
        league = self.current_league()
        if league and self.total:
            self.status_var.set(f"{league.name} · {league.ladder_label} · {self.total:,} 名角色 · poe.ninja")

    def _fail(self, message: str) -> None:
        self._loading = False
        self.progress.stop()
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
        self.detail_stats_var.set("　　".join(bits))
        extras = []
        if row.items:
            extras.append("熱門傳奇：" + "、".join(row.items))
        if row.keystones:
            extras.append("鑰石：" + "、".join(row.keystones))
        self.detail_items_var.set("　　".join(extras) or "這列還沒有傳奇／鑰石樣本。")
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
                    sample.dps_text or format_stat(sample.dps),
                    sample.ehp_text or format_stat(sample.ehp),
                    format_stat(sample.life) if sample.life else "—",
                    format_stat(sample.es),
                ),
            )
            self._sample_urls[item_id] = sample.ninja_url

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
        webbrowser.open(league.page_url if league else BUILDS_PAGE)

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
