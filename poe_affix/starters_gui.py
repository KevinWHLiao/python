"""League-start build recommender window."""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

import customtkinter as ctk

from . import load_settings, save_settings
from .starters import (
    ALL,
    GAME_LABELS,
    MODE_LABEL,
    RecommendQuery,
    ScoredBuild,
    StarterCatalog,
    catalog_summary,
    format_mode_list,
    load_catalog,
    recommend,
)
from .theme import (
    BG_PANEL,
    FONT_FAMILY,
    FONT_SECTION,
    FONT_SMALL,
    GOLD,
    GOLD_HI,
    LINE_SOFT,
    MUTED,
    PREFIX,
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

RESULT_LIMITS = ("8", "12", "20", "全部")
GAME_IDS = {label: game_id for game_id, label in GAME_LABELS.items()}
MAXROLL_TIERLIST_URL = "https://maxroll.gg/poe2/tierlists/league-starter-ascendancy-tier-list"


class CheckGroup(ctk.CTkFrame):
    """A titled row/wrap of toggle chips."""

    def __init__(self, master, title: str, options: list[str], *, columns: int = 4) -> None:
        super().__init__(master, fg_color="transparent")
        self._vars: dict[str, tk.BooleanVar] = {}
        ctk.CTkLabel(self, text=title, font=FONT_SMALL, text_color=MUTED, anchor="w").grid(
            row=0, column=0, columnspan=columns, sticky="w", pady=(0, 4)
        )
        for index, label in enumerate(options):
            var = tk.BooleanVar(value=False)
            self._vars[label] = var
            btn = ctk.CTkCheckBox(
                self,
                text=label,
                variable=var,
                font=FONT_SMALL,
                text_color=TEXT,
                fg_color=GOLD,
                hover_color=GOLD_HI,
                border_color=LINE_SOFT,
                checkmark_color="#1a1408",
                checkbox_width=18,
                checkbox_height=18,
            )
            row = 1 + index // columns
            col = index % columns
            btn.grid(row=row, column=col, sticky="w", padx=(0, 12), pady=2)
        for col in range(columns):
            self.grid_columnconfigure(col, weight=1)

    def selected(self) -> list[str]:
        return [label for label, var in self._vars.items() if var.get()]

    def clear(self) -> None:
        for var in self._vars.values():
            var.set(False)

    def bind_change(self, callback) -> None:
        for var in self._vars.values():
            var.trace_add("write", lambda *_a, _c=callback: _c())


class StartersApp(ctk.CTkToplevel):
    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master)
        self._on_back = on_back
        self.title("流亡黯道 · 每季開荒推薦")
        self.geometry("1380x860")
        self.minsize(1080, 680)
        setup_window(self)
        self.protocol("WM_DELETE_WINDOW", self.go_back)

        self.catalog: StarterCatalog | None = None
        self.results: list[ScoredBuild] = []
        self._row_by_id: dict[str, ScoredBuild] = {}
        self._selected: ScoredBuild | None = None
        saved_game = str(load_settings().get("starters_game") or "poe1")
        self.game_id = saved_game if saved_game in GAME_LABELS else "poe1"
        self._syncing = False

        self.budget_var = tk.StringVar(value=ALL)
        self.difficulty_var = tk.StringVar(value=ALL)
        self.mode_var = tk.StringVar(value=ALL)
        self.limit_var = tk.StringVar(value="12")
        self.search_var = tk.StringVar()
        self.diversify_var = tk.BooleanVar(value=True)
        self.prefer_start_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="載入開荒目錄中…")
        self.detail_title_var = tk.StringVar(value="選擇一列查看推薦理由與路線")
        self.detail_summary_var = tk.StringVar(value="")

        self._budget_labels: list[str] = [ALL]
        self._budget_id_by_label: dict[str, str] = {}
        self._difficulty_labels: list[str] = [ALL]
        self._difficulty_id_by_label: dict[str, str] = {}
        self._mode_labels = [ALL, *MODE_LABEL.values()]
        self._mode_id_by_label = {label: key for key, label in MODE_LABEL.items()}

        self._build()
        self.after(40, self._load)

    def go_back(self) -> None:
        self.destroy()
        self._on_back()

    def _build(self) -> None:
        make_header(
            self,
            "每季開荒推薦",
            on_back=self.go_back,
            hint="依類型／流派手感／預算篩選，一次給多個方向",
            right_actions=[
                ("重新整理推薦", self.refresh),
                ("更新 PoE2 資料", self.start_poe2_sync),
                ("清除條件", self.clear_filters),
            ],
        )
        make_status_bar(self, self.status_var)

        filters = filter_panel(self)
        filters.grid_columnconfigure(1, weight=1)

        top = ctk.CTkFrame(filters, fg_color="transparent")
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        for col in range(10):
            top.grid_columnconfigure(col, weight=1 if col in {3, 5, 7, 9} else 0)

        ctk.CTkLabel(top, text="遊戲", font=FONT_SMALL, text_color=MUTED).grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.game_switch = GameToggle(
            top,
            values=["PoE1", "PoE2"],
            width=168,
            height=30,
            command=self.on_game_changed,
        )
        self.game_switch.grid(row=0, column=1, sticky="w", padx=(0, 14))
        self.game_switch.set(GAME_LABELS[self.game_id])

        ctk.CTkLabel(top, text="預算上限", font=FONT_SMALL, text_color=MUTED).grid(row=0, column=2, sticky="w", padx=(0, 6))
        self.budget_combo = ttk.Combobox(top, textvariable=self.budget_var, state="readonly", width=16, values=self._budget_labels)
        self.budget_combo.grid(row=0, column=3, sticky="w", padx=(0, 14))
        self.budget_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        ctk.CTkLabel(top, text="難度", font=FONT_SMALL, text_color=MUTED).grid(row=0, column=4, sticky="w", padx=(0, 6))
        self.difficulty_combo = ttk.Combobox(
            top, textvariable=self.difficulty_var, state="readonly", width=10, values=self._difficulty_labels
        )
        self.difficulty_combo.grid(row=0, column=5, sticky="w", padx=(0, 14))
        self.difficulty_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        ctk.CTkLabel(top, text="模式", font=FONT_SMALL, text_color=MUTED).grid(row=0, column=6, sticky="w", padx=(0, 6))
        self.mode_combo = ttk.Combobox(top, textvariable=self.mode_var, state="readonly", width=12, values=self._mode_labels)
        self.mode_combo.grid(row=0, column=7, sticky="w", padx=(0, 14))
        self.mode_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        ctk.CTkLabel(top, text="顯示數量", font=FONT_SMALL, text_color=MUTED).grid(row=0, column=8, sticky="w", padx=(0, 6))
        self.limit_combo = ttk.Combobox(top, textvariable=self.limit_var, state="readonly", width=8, values=RESULT_LIMITS)
        self.limit_combo.grid(row=0, column=9, sticky="w")
        self.limit_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        search_row = ctk.CTkFrame(filters, fg_color="transparent")
        search_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        search_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(search_row, text="關鍵字", font=FONT_SMALL, text_color=MUTED).grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(search_row, textvariable=self.search_var, width=40).grid(row=0, column=1, sticky="ew", padx=(0, 12))
        self.search_var.trace_add("write", lambda *_: self.refresh())

        ctk.CTkCheckBox(
            search_row,
            text="優先適合開荒",
            variable=self.prefer_start_var,
            command=self.refresh,
            font=FONT_SMALL,
            text_color=TEXT,
            fg_color=GOLD,
            hover_color=GOLD_HI,
            border_color=LINE_SOFT,
            checkmark_color="#1a1408",
        ).grid(row=0, column=2, sticky="w", padx=(0, 12))
        ctk.CTkCheckBox(
            search_row,
            text="多樣化類型",
            variable=self.diversify_var,
            command=self.refresh,
            font=FONT_SMALL,
            text_color=TEXT,
            fg_color=GOLD,
            hover_color=GOLD_HI,
            border_color=LINE_SOFT,
            checkmark_color="#1a1408",
        ).grid(row=0, column=3, sticky="w")

        self.chip_host = ctk.CTkFrame(filters, fg_color="transparent")
        self.chip_host.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.style_group = CheckGroup(self.chip_host, "類型流派", [])
        self.damage_group = CheckGroup(self.chip_host, "傷害類型", [])
        self.play_group = CheckGroup(self.chip_host, "手感標籤", [])
        self.goal_group = CheckGroup(self.chip_host, "目標", [], columns=4)

        muted_hint(
            self,
            "可多選類型／傷害／手感／目標。預算是上限：選低預算不會出現高投資後期。顯示數量可改「全部」一次看完。"
            "PoE2 是 Maxroll 開荒昇華 tier list（依角色分類，梯隊即 Maxroll 評級），按「更新 PoE2 資料」可重新抓最新版。",
        )

        body = content_panel(self)
        pane = ttk.Panedwindow(body, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=10, pady=10)

        left = ttk.Frame(pane)
        pane.add(left, weight=3)
        columns = ("rank", "score", "name", "style", "budget", "diff", "tier", "why")
        self.tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse")
        headings = {
            "rank": "#",
            "score": "分數",
            "name": "Build",
            "style": "類型",
            "budget": "預算",
            "diff": "難度",
            "tier": "梯隊",
            "why": "匹配理由",
        }
        widths = {"rank": 40, "score": 54, "name": 200, "style": 90, "budget": 90, "diff": 60, "tier": 48, "why": 260}
        for key, title in headings.items():
            self.tree.heading(key, text=title)
            stretch = key in {"name", "why"}
            self.tree.column(key, width=widths[key], stretch=stretch, anchor="w" if stretch or key == "name" else "center")
        yscroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")
        self.tree.tag_configure("s", foreground=GOLD)
        self.tree.tag_configure("a", foreground=PREFIX)
        self.tree.tag_configure("b", foreground=TEXT)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self.open_guide)

        right = tk.Frame(pane, bg=BG_PANEL)
        pane.add(right, weight=2)
        detail_wrap = ctk.CTkFrame(right, fg_color=BG_PANEL, corner_radius=12, border_width=1, border_color=LINE_SOFT)
        detail_wrap.pack(fill="both", expand=True, padx=4, pady=4)
        self.detail_scroll = ctk.CTkScrollableFrame(
            detail_wrap,
            fg_color=BG_PANEL,
            corner_radius=0,
            scrollbar_button_color=LINE_SOFT,
            scrollbar_button_hover_color=GOLD,
        )
        self.detail_scroll.pack(fill="both", expand=True, padx=8, pady=8)

        ctk.CTkLabel(
            self.detail_scroll, textvariable=self.detail_title_var, font=FONT_SECTION, text_color=GOLD, anchor="w"
        ).pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(
            self.detail_scroll,
            textvariable=self.detail_summary_var,
            font=FONT_SMALL,
            text_color=PREFIX,
            anchor="w",
            justify="left",
            wraplength=420,
        ).pack(fill="x", pady=(0, 8))

        self._detail_labels: dict[str, ctk.CTkLabel] = {}
        for key, title in (
            ("meta", "基本資訊"),
            ("reasons", "為什麼推薦你"),
            ("pros", "優點"),
            ("cons", "缺點"),
            ("leveling", "開荒路線"),
        ):
            block = ctk.CTkFrame(
                self.detail_scroll, fg_color="#12161f", corner_radius=10, border_width=1, border_color=LINE_SOFT
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
                wraplength=400,
            )
            label.pack(fill="x", padx=10, pady=(0, 8))
            self._detail_labels[key] = label

        actions = ctk.CTkFrame(self.detail_scroll, fg_color="transparent")
        actions.pack(fill="x", pady=(10, 0))
        primary_button(actions, "開啟 Guide", command=self.open_guide, width=120).pack(side="left")
        ghost_button(actions, "開啟 PoB", command=self.open_pob, width=100).pack(side="left", padx=8)
        ghost_button(actions, "複製摘要", command=self.copy_detail, width=100).pack(side="left")

    def on_game_changed(self, value: str) -> None:
        game = GAME_IDS.get(str(value).strip(), "poe1")
        if game == self.game_id:
            return
        self.game_id = game
        save_settings({"starters_game": game})
        self.clear_filters(refresh=False)
        self._load()

    def start_poe2_sync(self) -> None:
        if self._syncing:
            return
        if not messagebox.askyesno(
            "更新 PoE2 開荒推薦",
            "要從 Maxroll 重新抓取 PoE2 開荒昇華 tier list 嗎？\n"
            "昇華名稱會再向 poe2db.tw 對應繁中，約需 30 秒。",
            parent=self,
        ):
            return
        self._syncing = True
        self.status_var.set("正在從 Maxroll 下載 PoE2 開荒 tier list…")
        threading.Thread(target=self._poe2_sync_worker, daemon=True).start()

    def _poe2_sync_worker(self) -> None:
        from .starters_sync import sync_league_starters_poe2

        def progress(done: int, total: int, message: str) -> None:
            self.after(0, lambda: self.status_var.set(f"[{done}/{total}] {message}"))

        try:
            sync_league_starters_poe2(progress=progress)
        except (RuntimeError, OSError) as error:
            self.after(0, lambda message=str(error): self._sync_failed(message))
            return
        self.after(0, self._sync_done)

    def _sync_failed(self, message: str) -> None:
        self._syncing = False
        self.status_var.set(f"更新失敗：{message}")
        messagebox.showerror("更新 PoE2 開荒推薦", message, parent=self)

    def _sync_done(self) -> None:
        self._syncing = False
        self.game_id = "poe2"
        save_settings({"starters_game": "poe2"})
        self.game_switch.set(GAME_LABELS["poe2"])
        self.clear_filters(refresh=False)
        self._load()

    def _load(self) -> None:
        try:
            catalog = load_catalog(game=self.game_id)
        except RuntimeError as error:
            self.status_var.set(str(error))
            if self.game_id == "poe2":
                if messagebox.askyesno(
                    "還沒有 PoE2 開荒資料",
                    f"{error}\n\n要現在從 Maxroll 下載 PoE2 開荒昇華 tier list 嗎？",
                    parent=self,
                ):
                    self.start_poe2_sync()
                    return
                self.game_id = "poe1"
                save_settings({"starters_game": "poe1"})
                self.game_switch.set(GAME_LABELS["poe1"])
                self._load()
            else:
                messagebox.showerror("開荒推薦", str(error), parent=self)
            return
        self.catalog = catalog
        self._budget_id_by_label = {label: key for key, label in catalog.budget_options}
        self._budget_labels = [ALL] + [label for _key, label in catalog.budget_options]
        self.budget_combo.configure(values=self._budget_labels)
        if self.budget_var.get() not in self._budget_labels:
            self.budget_var.set(ALL)

        self._difficulty_id_by_label = {label: key for key, label in catalog.difficulty_options}
        self._difficulty_labels = [ALL] + [label for _key, label in catalog.difficulty_options]
        self.difficulty_combo.configure(values=self._difficulty_labels)
        if self.difficulty_var.get() not in self._difficulty_labels:
            self.difficulty_var.set(ALL)

        for child in self.chip_host.winfo_children():
            child.destroy()

        self.style_group = CheckGroup(self.chip_host, "類型流派", catalog.styles or [], columns=4)
        self.style_group.pack(fill="x", pady=(0, 8))
        self.damage_group = CheckGroup(self.chip_host, "傷害類型", catalog.damage_types or [], columns=5)
        self.damage_group.pack(fill="x", pady=(0, 8))
        self.play_group = CheckGroup(self.chip_host, "手感標籤", catalog.playstyles or [], columns=4)
        self.play_group.pack(fill="x", pady=(0, 8))
        self.goal_group = CheckGroup(self.chip_host, "目標", catalog.goals or [], columns=4)
        self.goal_group.pack(fill="x")

        for group in (self.style_group, self.damage_group, self.play_group, self.goal_group):
            group.bind_change(self.refresh)

        self.status_var.set(
            f"{GAME_LABELS[self.game_id]}　·　"
            + catalog_summary(catalog)
            + (f"　·　{catalog.notes}" if catalog.notes else "")
        )
        self.refresh()

    def clear_filters(self, refresh: bool = True) -> None:
        self.budget_var.set(ALL)
        self.difficulty_var.set(ALL)
        self.mode_var.set(ALL)
        self.limit_var.set("12")
        self.search_var.set("")
        self.diversify_var.set(True)
        self.prefer_start_var.set(True)
        for group in (self.style_group, self.damage_group, self.play_group, self.goal_group):
            group.clear()
        if refresh:
            self.refresh()

    def _query(self) -> RecommendQuery:
        budget_label = self.budget_var.get()
        difficulty_label = self.difficulty_var.get()
        mode_label = self.mode_var.get()
        limit_raw = self.limit_var.get()
        if limit_raw == "全部":
            limit = 999
        else:
            try:
                limit = int(limit_raw)
            except ValueError:
                limit = 8
        return RecommendQuery(
            styles=self.style_group.selected(),
            damage=self.damage_group.selected(),
            playstyles=self.play_group.selected(),
            goals=self.goal_group.selected(),
            max_budget="" if budget_label == ALL else self._budget_id_by_label.get(budget_label, ""),
            difficulty="" if difficulty_label == ALL else self._difficulty_id_by_label.get(difficulty_label, ""),
            mode="" if mode_label == ALL else self._mode_id_by_label.get(mode_label, ""),
            search=self.search_var.get(),
            prefer_league_start=bool(self.prefer_start_var.get()),
            diversify=bool(self.diversify_var.get()),
            limit=limit,
        )

    def refresh(self) -> None:
        if not self.catalog:
            return
        query = self._query()
        self.results = recommend(self.catalog, query)
        self.tree.delete(*self.tree.get_children(""))
        self._row_by_id.clear()
        for index, item in enumerate(self.results, start=1):
            build = item.build
            tag = build.tier.lower() if build.tier.lower() in {"s", "a", "b"} else "b"
            item_id = self.tree.insert(
                "",
                "end",
                values=(
                    index,
                    f"{item.score:.0f}",
                    build.name_zh,
                    "、".join(build.styles) or "—",
                    build.budget_label,
                    build.difficulty_label,
                    build.tier,
                    "；".join(item.reasons[:3]) or "—",
                ),
                tags=(tag,),
            )
            self._row_by_id[item_id] = item
        total = len(self.catalog.builds)
        shown = len(self.results)
        self.status_var.set(
            f"{GAME_LABELS[self.game_id]}　·　{catalog_summary(self.catalog)}　·　符合 {shown}/{total}"
            + ("　·　已啟用多樣化" if query.diversify else "")
        )
        children = self.tree.get_children("")
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
            self._show_detail(self._row_by_id[children[0]])
        else:
            self._selected = None
            self.detail_title_var.set("沒有符合條件的 Build")
            self.detail_summary_var.set("試著少選幾個標籤，或把預算／難度改回「全部」。")
            for label in self._detail_labels.values():
                label.configure(text="—")

    def _on_select(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        item = self._row_by_id.get(selected[0])
        if item:
            self._show_detail(item)

    def _show_detail(self, item: ScoredBuild) -> None:
        self._selected = item
        build = item.build
        self.detail_title_var.set(f"{build.name_zh}　·　{build.tier} 梯隊　·　分數 {item.score:.0f}")
        self.detail_summary_var.set(build.summary or build.name)

        meta_lines = [f"昇華：{build.ascendancy_zh}（{build.ascendancy}）"]
        if build.skill or build.skill_zh:
            meta_lines.append(f"主技能：{build.skill_zh}（{build.skill}）")
        meta_lines.append(f"類型：{'、'.join(build.styles) or '—'}")
        for title, values in (("傷害", build.damage), ("手感", build.playstyles), ("目標", build.goals)):
            if values:
                meta_lines.append(f"{title}：{'、'.join(values)}")
        meta_lines += [
            f"預算：{build.budget_label}",
            f"難度：{build.difficulty_label}",
            f"模式：{format_mode_list(build.modes)}",
        ]
        self._detail_labels["meta"].configure(text="\n".join(meta_lines))
        self._detail_labels["reasons"].configure(text="\n".join(f"· {reason}" for reason in item.reasons) or "—")
        self._detail_labels["pros"].configure(text="\n".join(f"· {text}" for text in build.pros) or "—")
        self._detail_labels["cons"].configure(text="\n".join(f"· {text}" for text in build.cons) or "—")
        self._detail_labels["leveling"].configure(text=build.leveling or "—")

    def open_guide(self, _event=None) -> None:
        item = self._selected
        if not item:
            return
        url = item.build.guide_url
        if not url:
            messagebox.showinfo("沒有 Guide", "這一筆尚未填 Guide 連結，可之後在資料檔補上。", parent=self)
            return
        webbrowser.open(url)

    def open_pob(self) -> None:
        item = self._selected
        if not item:
            return
        url = item.build.pob_url
        if not url:
            messagebox.showinfo("沒有 PoB", "這一筆尚未填 PoB 連結。", parent=self)
            return
        webbrowser.open(url)

    def copy_detail(self) -> None:
        item = self._selected
        if not item:
            messagebox.showinfo("沒有資料", "請先選一筆推薦。", parent=self)
            return
        build = item.build
        lines = [
            build.name_zh,
            build.summary,
            f"昇華：{build.ascendancy_zh}　技能：{build.skill_zh}",
            f"預算：{build.budget_label}　難度：{build.difficulty_label}　梯隊：{build.tier}",
            "匹配：" + "；".join(item.reasons),
            "優點：" + "、".join(build.pros),
            "缺點：" + "、".join(build.cons),
            "開荒：" + build.leveling,
        ]
        if build.guide_url:
            lines.append(build.guide_url)
        if build.pob_url:
            lines.append(build.pob_url)
        text = "\n".join(line for line in lines if line)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set("已複製開荒推薦摘要")
