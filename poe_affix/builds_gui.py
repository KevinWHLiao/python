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
    fetch_index,
    fetch_ranks,
    matches,
)
from .search_combo import bind_searchable_combo, filter_choices
from .theme import BG, BG_HEAD, FONT_SMALL, FONT_UI, GOLD, MUTED, PREFIX, apply_theme, sort_tree

VIEW_CLASS = "熱門昇華"
VIEW_SKILL = "熱門技能"
VIEW_COMBO = "熱門流派"
NUMERIC_COLUMNS = {"rank", "count", "percent"}


def format_count(value: int) -> str:
    if not value:
        return "—"
    return f"{value:,}"


def format_percent(value: float) -> str:
    if value <= 0:
        return "—"
    return f"{value:.1f}%"


class BuildsApp(tk.Toplevel):
    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master)
        self._on_back = on_back
        self.title("流亡黯道 · 流派排名")
        self.geometry("1280x760")
        self.minsize(960, 560)
        self.configure(bg=BG)
        self.option_add("*Font", FONT_UI)
        apply_theme(self)
        self.protocol("WM_DELETE_WINDOW", self.go_back)

        self.leagues: list[BuildLeague] = []
        self.class_rows: list[RankRow] = []
        self.skill_rows: list[RankRow] = []
        self.combo_rows: list[RankRow] = []
        self.total = 0
        self._loading = False
        self._pending_load = False
        self._row_urls: dict[str, str] = {}

        self.league_var = tk.StringVar()
        self.ladder_var = tk.StringVar(value=LADDER_EXP)
        self.view_var = tk.StringVar(value=VIEW_COMBO)
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="正在連線 poe.ninja…")
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
            text="資料來自 poe.ninja 公開流派榜。熱門流派是昇華＋最熱門技能的組合，占比與官網首頁相同（占全體角色）。雙擊列可開官網。",
            style="Muted.TLabel",
        ).pack(anchor="w", padx=16)

        wrap = ttk.Frame(self, padding=(16, 8, 16, 8))
        wrap.pack(fill="both", expand=True)
        columns = ("rank", "name_zh", "name", "skill_zh", "skill", "count", "percent")
        self.tree = ttk.Treeview(wrap, columns=columns, show="headings", selectmode="browse")
        self.headings = {
            "rank": "排名",
            "name_zh": "昇華／中文",
            "name": "英文",
            "skill_zh": "技能中文",
            "skill": "技能英文",
            "count": "人數",
            "percent": "占比",
        }
        widths = {
            "rank": 60,
            "name_zh": 140,
            "name": 140,
            "skill_zh": 220,
            "skill": 220,
            "count": 90,
            "percent": 80,
        }
        for key, title in self.headings.items():
            self.tree.heading(key, text=title, command=lambda column=key: self.sort_by(column))
            stretch = key in {"name_zh", "name", "skill_zh", "skill"}
            anchor = "e" if key in NUMERIC_COLUMNS else "w"
            self.tree.column(key, width=widths[key], stretch=stretch, anchor=anchor)
        yscroll = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")
        self.tree.tag_configure("top", foreground=GOLD)
        self.tree.tag_configure("row", foreground=PREFIX)
        self.tree.bind("<Double-1>", self.open_selected)
        self.tree.bind("<Return>", self.open_selected)

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
        hits = [
            league
            for league in self.leagues
            if league.name == name and league.ladder_label == ladder
        ]
        if hits:
            return hits[0]
        named = [league for league in self.leagues if league.name == name]
        if len(named) == 1:
            return named[0]
        matches_name = filter_choices(name, [league.name for league in self.leagues])
        if len(matches_name) == 1:
            self.league_var.set(matches_name[0])
            return self.current_league()
        return next((league for league in self.leagues if league.ladder_label == ladder), self.leagues[0] if self.leagues else None)

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
        self.status_var.set(f"正在下載 {league.name} / {league.ladder_label}…")
        self.progress.start(12)
        threading.Thread(target=self._ranks_worker, args=(league,), daemon=True).start()

    def _ranks_worker(self, league: BuildLeague) -> None:
        try:
            total, class_rows, skill_rows, combo_rows = fetch_ranks(league)
        except RuntimeError as error:
            self.after(0, lambda message=str(error): self._fail(message))
            return
        self.after(0, lambda: self._on_ranks(league, total, class_rows, skill_rows, combo_rows))

    def _on_ranks(
        self,
        league: BuildLeague,
        total: int,
        class_rows: list[RankRow],
        skill_rows: list[RankRow],
        combo_rows: list[RankRow],
    ) -> None:
        self._loading = False
        self.progress.stop()
        self.total = total
        self.class_rows = class_rows
        self.skill_rows = skill_rows
        self.combo_rows = combo_rows
        league.character_count = total
        self.refresh()
        if self._pending_load:
            self._pending_load = False
            self.load_ranks()

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
        self._row_urls.clear()
        view = self._resolved_view()
        for row in rows:
            tag = "top" if row.rank <= 3 else "row"
            item_id = self.tree.insert(
                "",
                "end",
                values=(
                    row.rank,
                    row.name_zh,
                    row.name,
                    row.extra_zh or "—",
                    row.extra or "—",
                    format_count(row.count),
                    format_percent(row.percent),
                ),
                tags=(tag,),
            )
            self._row_urls[item_id] = row.ninja_url
        league = self.current_league()
        league_name = league.name if league else ""
        ladder = league.ladder_label if league else ""
        if view == VIEW_COMBO and not self._current_rows():
            self.status_var.set(f"{league_name} 目前沒有流派組合，可改看熱門昇華或熱門技能。")
        elif self.total:
            self.status_var.set(f"{league_name} · {ladder} · {self.total:,} 名角色 · 顯示 {len(rows):,} 筆 · poe.ninja")
        else:
            self.status_var.set(f"{league_name} · 顯示 {len(rows):,} 筆 · poe.ninja")

    def sort_by(self, column: str) -> None:
        sort_tree(self.tree, column, numeric=column in NUMERIC_COLUMNS)

    def open_league_page(self) -> None:
        league = self.current_league()
        webbrowser.open(league.page_url if league else BUILDS_PAGE)

    def open_selected(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        url = self._row_urls.get(selected[0])
        if url:
            webbrowser.open(url)
