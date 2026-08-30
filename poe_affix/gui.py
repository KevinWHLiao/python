"""Affix lookup GUI: pick a slot, then pick an affix to see tiers and item levels."""

from __future__ import annotations

import json
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

import customtkinter as ctk

from . import game_spec, load_settings, resolve_data_file, save_settings
from .catalog import SOURCE_TITLES, format_tag_text, format_tag_text_marked, group_categories, source_order_for
from .search_combo import bind_searchable_combo, choice_matches
from .sync import sync_catalog
from .theme import (
    BG,
    BG_INPUT,
    BG_PANEL,
    CORRUPT,
    CORRUPT_BG,
    CORRUPT_T1_BG,
    CORRUPT_T1_FG,
    FONT_SMALL,
    FONT_UI,
    GOLD,
    MUTED,
    PREFIX,
    SUFFIX,
    T1_BG,
    T1_FG,
    T2_BG,
    T2_FG,
    T3_BG,
    T3_FG,
    TEXT,
    TN_FG,
    GameToggle,
    content_panel,
    filter_panel,
    make_header,
    make_status_bar,
    set_progress,
    setup_appearance,
    setup_window,
    tag_color,
)

ALL = "全部"
GAME_LABELS = {"poe1": "PoE1", "poe2": "PoE2"}
GAME_IDS = {label: game_id for game_id, label in GAME_LABELS.items()}


def load_catalog(game: str = "poe1") -> dict | None:
    path = resolve_data_file(game)
    if not path:
        return None
    from .catalog import rematerialize_catalog

    catalog = json.loads(path.read_text(encoding="utf-8"))
    fixed = rematerialize_catalog(catalog)
    if fixed.get("group_count") != catalog.get("group_count"):
        try:
            path.write_text(json.dumps(fixed, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        return fixed
    return catalog


def _tier_number(value) -> int:
    try:
        return int(str(value).lstrip("Tt"))
    except (TypeError, ValueError):
        return 99


def _tier_tag(tier_value, corrupt: bool = False) -> str:
    number = _tier_number(tier_value)
    if corrupt and number == 1:
        return "t1_corrupt"
    if number == 1:
        return "t1"
    if number == 2:
        return "t2"
    if number == 3:
        return "t3"
    if corrupt:
        return "corrupt"
    return "tn"


class AffixApp(ctk.CTkToplevel):
    def __init__(self, master: tk.Misc | None = None, on_back=None) -> None:
        owns_root = master is None
        if owns_root:
            setup_appearance()
            master = ctk.CTk()
            master.withdraw()
        super().__init__(master)
        self._owns_root = owns_root
        self._on_back = on_back
        saved_game = str(load_settings().get("affix_game") or "poe1")
        self.game_id = saved_game if saved_game in GAME_LABELS else "poe1"
        spec = game_spec(self.game_id)
        self.title(f"{spec['title']} · 裝備詞綴查詢")
        self.geometry("1360x820")
        self.minsize(1080, 680)
        setup_window(self)
        self.protocol("WM_DELETE_WINDOW", self.go_back)

        self.catalog: dict | None = None
        self.filtered_groups: list[dict] = []
        self._syncing = False
        self._ignore_game_change = False

        self.slot_var = tk.StringVar(value=ALL)
        self.affix_var = tk.StringVar(value=ALL)
        self.source_var = tk.StringVar(value="基底")
        self.category_var = tk.StringVar(value=ALL)
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="尚未載入資料")
        self.summary_var = tk.StringVar(value="請從左側選擇一個詞綴")
        self.meta_var = tk.StringVar(value="T1 為該部位最難出的最高階詞綴")
        self.corrupt_title_var = tk.StringVar(value="此部位汙染詞")
        self.affix_sort_col = "t1"
        self.affix_sort_desc = True
        self.affix_headings = {}
        self.tier_sort_desc = True
        self.corrupt_sort_desc = True
        self._slot_options: list[str] = [ALL]
        self._affix_options: list[str] = [ALL, "前綴", "後綴", "汙染"]
        self._source_options: list[str] = [ALL, "基底"]
        self._category_options: list[str] = [ALL]

        self._build()
        self.search_var.trace_add("write", lambda *_: self.refresh_affix_list())
        self.after(100, self._startup_load)

    def go_back(self) -> None:
        self.destroy()
        if self._on_back:
            self._on_back()
        elif self._owns_root:
            self.master.destroy()

    def _tag_trees(self) -> None:
        for tree in (self.affix_tree, self.tier_tree, self.corrupt_tree):
            tree.tag_configure("t1", background=T1_BG, foreground=T1_FG)
            tree.tag_configure("t2", background=T2_BG, foreground=T2_FG)
            tree.tag_configure("t3", background=T3_BG, foreground=T3_FG)
            tree.tag_configure("tn", background=BG_INPUT, foreground=TN_FG)
            tree.tag_configure("corrupt", background=CORRUPT_BG, foreground=CORRUPT)
            tree.tag_configure("t1_corrupt", background=CORRUPT_T1_BG, foreground=CORRUPT_T1_FG)
            tree.tag_configure("prefix", background=BG_INPUT, foreground=PREFIX)
            tree.tag_configure("suffix", background=BG_INPUT, foreground=SUFFIX)
            tree.tag_configure("odd", background="#151922", foreground=TEXT)

    def _build(self) -> None:
        make_header(
            self,
            "裝備詞綴",
            on_back=self.go_back,
            right_actions=[
                ("更新資料", self.start_sync),
                ("開啟詞綴頁", self.open_source_page),
            ],
            hint="可切換 PoE1 / PoE2　　金色 = 該部位最難出的 T1　　紫色 = 汙染詞",
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

        ctk.CTkLabel(filters, text="部位", font=FONT_SMALL, text_color=MUTED).grid(row=0, column=2, sticky="w", padx=(0, 6))
        self.slot_combo = ttk.Combobox(filters, textvariable=self.slot_var, width=22, state="normal")
        self.slot_combo.grid(row=0, column=3, padx=(0, 16))
        bind_searchable_combo(self.slot_combo, lambda: self._slot_options, self.on_filters_changed)

        ctk.CTkLabel(filters, text="前後綴", font=FONT_SMALL, text_color=MUTED).grid(row=0, column=4, sticky="w", padx=(0, 6))
        self.affix_combo = ttk.Combobox(
            filters,
            textvariable=self.affix_var,
            width=10,
            values=self._affix_options,
            state="normal",
        )
        self.affix_combo.grid(row=0, column=5, padx=(0, 16))
        bind_searchable_combo(self.affix_combo, lambda: self._affix_options, self.refresh_affix_list)

        ctk.CTkLabel(filters, text="來源", font=FONT_SMALL, text_color=MUTED).grid(row=0, column=6, sticky="w", padx=(0, 6))
        self.source_combo = ttk.Combobox(filters, textvariable=self.source_var, width=14, state="normal")
        self.source_combo.grid(row=0, column=7, padx=(0, 16))
        bind_searchable_combo(self.source_combo, lambda: self._source_options, self.refresh_affix_list)

        ctk.CTkLabel(filters, text="分類", font=FONT_SMALL, text_color=MUTED).grid(row=0, column=8, sticky="w", padx=(0, 6))
        self.category_combo = ttk.Combobox(filters, textvariable=self.category_var, width=12, state="normal")
        self.category_combo.grid(row=0, column=9, padx=(0, 16))
        bind_searchable_combo(self.category_combo, lambda: self._category_options, self.refresh_affix_list)

        ctk.CTkLabel(filters, text="篩選詞綴", font=FONT_SMALL, text_color=MUTED).grid(row=0, column=10, sticky="w", padx=(0, 6))
        search = ttk.Entry(filters, textvariable=self.search_var, width=24)
        search.grid(row=0, column=11, sticky="ew")
        filters.grid_columnconfigure(11, weight=1)
        ctk.CTkLabel(
            filters,
            text="遊戲可選 PoE1（poedb.tw）或 PoE2（poe2db.tw）。部位／前後綴／來源／分類可輸入關鍵字（可多字或空格），例如「手套 力」「塑界」；點清單或 Enter 套用",
            font=FONT_SMALL,
            text_color=MUTED,
        ).grid(row=1, column=0, columnspan=12, sticky="w", pady=(8, 0))

        legend = ctk.CTkFrame(self, fg_color="transparent")
        legend.pack(fill="x", padx=20, pady=(0, 4))
        for text, color in (
            ("T1 最難出", T1_FG),
            ("T2", T2_FG),
            ("T3", T3_FG),
            ("汙染詞", CORRUPT),
            ("前綴", PREFIX),
            ("後綴", SUFFIX),
        ):
            ctk.CTkLabel(legend, text=f"● {text}", font=FONT_SMALL, text_color=color).pack(side="left", padx=(0, 14))
        ctk.CTkLabel(
            legend,
            text="多標籤時分類欄會用色點區分；右側詳情為彩色標籤",
            font=FONT_SMALL,
            text_color=MUTED,
        ).pack(side="left", padx=(8, 0))

        body = content_panel(self)
        paned = ttk.Panedwindow(body, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=10)

        left = ttk.Frame(paned, style="Panel.TFrame", padding=10)
        right = ttk.Frame(paned, style="Panel.TFrame", padding=10)
        paned.add(left, weight=1)
        paned.add(right, weight=2)

        ttk.Label(left, text="選擇詞綴　（點欄位標題可排序）", style="Section.TLabel").pack(anchor="w")
        ctk.CTkFrame(left, fg_color=GOLD, corner_radius=0, height=2).pack(fill="x", pady=(4, 8))
        list_wrap = ttk.Frame(left, style="Panel.TFrame")
        list_wrap.pack(fill="both", expand=True)
        columns = ("label", "category", "affix", "corrupt", "source", "t1", "weight", "tiers", "slots")
        self.affix_tree = ttk.Treeview(list_wrap, columns=columns, show="headings", selectmode="browse")
        self.affix_headings = {
            "label": "詞綴",
            "category": "分類",
            "affix": "前後綴",
            "corrupt": "汙染",
            "source": "來源",
            "t1": "T1 物等",
            "weight": "T1 權重",
            "tiers": "階層數",
            "slots": "部位數",
        }
        widths = {
            "label": 190,
            "category": 240,
            "affix": 58,
            "corrupt": 48,
            "source": 78,
            "t1": 72,
            "weight": 72,
            "tiers": 58,
            "slots": 58,
        }
        for key, title in self.affix_headings.items():
            self.affix_tree.heading(key, text=title, command=lambda column=key: self.sort_affix_list(column))
            stretch = key in {"label", "category"}
            self.affix_tree.column(
                key, width=widths[key], stretch=stretch, anchor="w" if key in {"label", "category"} else "center"
            )
        yscroll = ttk.Scrollbar(list_wrap, orient="vertical", command=self.affix_tree.yview)
        self.affix_tree.configure(yscrollcommand=yscroll.set)
        self.affix_tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")
        self.affix_tree.bind("<<TreeviewSelect>>", lambda _e: self.show_selected_affix())

        ttk.Label(right, textvariable=self.summary_var, style="Section.TLabel").pack(anchor="w")
        ctk.CTkFrame(right, fg_color=GOLD, corner_radius=0, height=2).pack(fill="x", pady=(4, 6))
        self.tag_chip_row = ctk.CTkFrame(right, fg_color="transparent")
        self.tag_chip_row.pack(anchor="w", fill="x", pady=(0, 4))
        ttk.Label(right, textvariable=self.meta_var, style="PanelMuted.TLabel").pack(anchor="w", pady=(0, 8))

        ttk.Label(right, text="出現部位", style="PanelMuted.TLabel").pack(anchor="w")
        slot_wrap = ttk.Frame(right, style="Panel.TFrame")
        slot_wrap.pack(fill="x", pady=(4, 10))
        self.slot_list = tk.Listbox(
            slot_wrap,
            height=5,
            exportselection=False,
            font=FONT_UI,
            bg=BG_INPUT,
            fg=TEXT,
            selectbackground="#5a3e14",
            selectforeground="#ffd37a",
            highlightthickness=0,
            bd=0,
            relief="flat",
            activestyle="none",
        )
        slot_scroll = ttk.Scrollbar(slot_wrap, orient="vertical", command=self.slot_list.yview)
        self.slot_list.configure(yscrollcommand=slot_scroll.set)
        self.slot_list.pack(side="left", fill="x", expand=True)
        slot_scroll.pack(side="right", fill="y")
        self.slot_list.bind("<<ListboxSelect>>", lambda _e: self.show_slot_table())

        ttk.Label(right, text="階層 / 物等　（金色 T1 為最難出；估計占比為同部位同前後綴的權重佔比）", style="PanelMuted.TLabel").pack(anchor="w")
        table_wrap = ttk.Frame(right, style="Panel.TFrame")
        table_wrap.pack(fill="both", expand=True, pady=(4, 0))
        tier_cols = ("tier", "level", "name", "weight", "chance", "corrupt", "text")
        self.tier_tree = ttk.Treeview(table_wrap, columns=tier_cols, show="headings", selectmode="browse")
        self.tier_tree.heading("tier", text="Tier", command=lambda: self.sort_detail_tree(self.tier_tree, "tier", True))
        self.tier_tree.heading("level", text="需要物等", command=lambda: self.sort_detail_tree(self.tier_tree, "level", True))
        self.tier_tree.heading("name", text="詞綴名稱", command=lambda: self.sort_detail_tree(self.tier_tree, "name", False))
        self.tier_tree.heading("weight", text="權重", command=lambda: self.sort_detail_tree(self.tier_tree, "weight", True))
        self.tier_tree.heading("chance", text="估計占比", command=lambda: self.sort_detail_tree(self.tier_tree, "chance", True))
        self.tier_tree.heading("corrupt", text="汙染")
        self.tier_tree.heading("text", text="數值", command=lambda: self.sort_detail_tree(self.tier_tree, "text", False))
        self.tier_tree.column("tier", width=58, stretch=False, anchor="center")
        self.tier_tree.column("level", width=78, stretch=False, anchor="center")
        self.tier_tree.column("name", width=120, stretch=False)
        self.tier_tree.column("weight", width=70, stretch=False, anchor="center")
        self.tier_tree.column("chance", width=88, stretch=False, anchor="center")
        self.tier_tree.column("corrupt", width=48, stretch=False, anchor="center")
        self.tier_tree.column("text", width=300, stretch=True)
        tier_scroll = ttk.Scrollbar(table_wrap, orient="vertical", command=self.tier_tree.yview)
        self.tier_tree.configure(yscrollcommand=tier_scroll.set)
        self.tier_tree.pack(side="left", fill="both", expand=True)
        tier_scroll.pack(side="right", fill="y")

        ttk.Label(right, textvariable=self.corrupt_title_var, style="Section.TLabel").pack(anchor="w", pady=(12, 0))
        ctk.CTkFrame(right, fg_color=CORRUPT, corner_radius=0, height=2).pack(fill="x", pady=(4, 8))
        corrupt_wrap = ttk.Frame(right, style="Panel.TFrame")
        corrupt_wrap.pack(fill="both", expand=True)
        corrupt_cols = ("tier", "level", "weight", "chance", "text")
        self.corrupt_tree = ttk.Treeview(
            corrupt_wrap, columns=corrupt_cols, show="headings", selectmode="browse", height=8
        )
        self.corrupt_tree.heading("tier", text="Tier", command=lambda: self.sort_detail_tree(self.corrupt_tree, "tier", True))
        self.corrupt_tree.heading("level", text="需要物等", command=lambda: self.sort_detail_tree(self.corrupt_tree, "level", True))
        self.corrupt_tree.heading("weight", text="權重", command=lambda: self.sort_detail_tree(self.corrupt_tree, "weight", True))
        self.corrupt_tree.heading("chance", text="估計占比", command=lambda: self.sort_detail_tree(self.corrupt_tree, "chance", True))
        self.corrupt_tree.heading("text", text="汙染詞數值", command=lambda: self.sort_detail_tree(self.corrupt_tree, "text", False))
        self.corrupt_tree.column("tier", width=58, stretch=False, anchor="center")
        self.corrupt_tree.column("level", width=78, stretch=False, anchor="center")
        self.corrupt_tree.column("weight", width=70, stretch=False, anchor="center")
        self.corrupt_tree.column("chance", width=88, stretch=False, anchor="center")
        self.corrupt_tree.column("text", width=420, stretch=True)
        corrupt_scroll = ttk.Scrollbar(corrupt_wrap, orient="vertical", command=self.corrupt_tree.yview)
        self.corrupt_tree.configure(yscrollcommand=corrupt_scroll.set)
        self.corrupt_tree.pack(side="left", fill="both", expand=True)
        corrupt_scroll.pack(side="right", fill="y")

        self._tag_trees()

    def _startup_load(self) -> None:
        self.apply_game(prompt_if_missing=True)

    def open_source_page(self) -> None:
        webbrowser.open(game_spec(self.game_id)["index_url"])

    def on_game_changed(self, value: str) -> None:
        if getattr(self, "_ignore_game_change", False):
            return
        game = GAME_IDS.get(str(value).strip(), "poe1")
        if game == self.game_id:
            return
        self.game_id = game
        save_settings({"affix_game": game})
        spec = game_spec(game)
        self.title(f"{spec['title']} · 裝備詞綴查詢")
        self.slot_var.set(ALL)
        self.source_var.set("基底")
        self.category_var.set(ALL)
        self.search_var.set("")
        self.apply_game(prompt_if_missing=True)

    def apply_game(self, *, prompt_if_missing: bool = False) -> None:
        spec = game_spec(self.game_id)
        self.title(f"{spec['title']} · 裝備詞綴查詢")
        catalog = load_catalog(self.game_id)
        if catalog:
            self.set_catalog(catalog)
            return
        self.catalog = None
        self.filtered_groups = []
        self._slot_options = [ALL]
        self.slot_combo.configure(values=[ALL])
        self.refresh_affix_list()
        if prompt_if_missing and messagebox.askyesno(
            f"尚未下載{spec['title']}詞綴",
            f"第一次使用需要從 {spec['index_url']} 下載裝備詞綴。\n現在開始更新嗎？",
        ):
            self.start_sync()
            return
        self.status_var.set(f"沒有{spec['label']}本地資料，請按「更新資料」。")

    @staticmethod
    def _choice_matches(typed: str, candidate: str) -> bool:
        text = (typed or "").strip()
        if not text or text == ALL:
            return True
        return choice_matches(text, candidate)

    def set_catalog(self, catalog: dict) -> None:
        self.catalog = catalog
        slots = [ALL] + [slot["name"] for slot in catalog.get("slots", [])]
        self._slot_options = slots
        self.slot_combo.configure(values=slots)
        if self.slot_var.get() not in slots:
            self.slot_var.set(ALL)

        sources = [ALL, "基底"]
        seen = {"全部", "基底"}
        for key in source_order_for(self.game_id):
            title = SOURCE_TITLES.get(key, key)
            if title not in seen:
                sources.append(title)
                seen.add(title)
        for slot in catalog.get("slots", []):
            for group in slot.get("groups", []):
                title = group.get("source") or ""
                if title and title not in seen:
                    sources.append(title)
                    seen.add(title)
        self._source_options = sources
        self.source_combo.configure(values=sources)
        if self.source_var.get() not in sources:
            self.source_var.set("基底")

        NO_TAG = "無標籤"
        categories = [ALL]
        seen_categories = {ALL}
        has_untagged = False
        for slot in catalog.get("slots", []):
            for group in slot.get("groups", []):
                tags = group_categories(group)
                if not tags:
                    has_untagged = True
                    continue
                for title in tags:
                    if title not in seen_categories:
                        categories.append(title)
                        seen_categories.add(title)
        extra_categories = sorted(name for name in categories if name not in {ALL, "其他", NO_TAG})
        categories = [ALL, *extra_categories]
        if "其他" in seen_categories:
            categories.append("其他")
        if has_untagged:
            categories.append(NO_TAG)
        self._category_options = categories
        self.category_combo.configure(values=categories)
        if self.category_var.get() not in categories:
            self.category_var.set(ALL)

        synced = catalog.get("synced_at", "")
        spec = game_spec(self.game_id)
        self.status_var.set(
            f"{spec['label']}　已載入 {catalog.get('slot_count', 0)} 個部位、"
            f"{catalog.get('group_count', 0)} 組詞綴　更新時間 {synced}"
        )
        self.refresh_affix_list()

    def on_filters_changed(self) -> None:
        self.refresh_affix_list()
        self.refresh_corrupt_panel()

    @staticmethod
    def _is_corrupt(group: dict) -> bool:
        return bool(group.get("is_corrupt")) or group.get("affix") == "汙染" or group.get("source") == "已汙染"

    def _slot_groups(self, slot_name: str) -> list[dict]:
        if not self.catalog:
            return []
        slot = next((item for item in self.catalog.get("slots", []) if item["name"] == slot_name), None)
        return list((slot or {}).get("groups", []))

    def _pool_chance(self, slot_name: str, group: dict, tier: dict) -> str:
        try:
            weight = int(tier.get("weight") or 0)
        except (TypeError, ValueError):
            return "—"
        if weight <= 0:
            return "—"
        try:
            ilvl = int(tier.get("level") or 0)
        except (TypeError, ValueError):
            ilvl = 0
        pool = 0
        for other in self._slot_groups(slot_name):
            if other.get("affix") != group.get("affix"):
                continue
            if other.get("source") != group.get("source"):
                continue
            for row in other.get("tiers", []):
                try:
                    required = int(row.get("level") or 0)
                except (TypeError, ValueError):
                    required = 0
                if required <= ilvl:
                    try:
                        pool += int(row.get("weight") or 0)
                    except (TypeError, ValueError):
                        continue
        if pool <= 0:
            return "—"
        return f"{weight / pool * 100:.2f}%"

    @staticmethod
    def _weight_value(tier: dict) -> str:
        weight = tier.get("weight")
        if weight in (None, ""):
            return "—"
        return str(weight)

    def iter_matching_groups(self):
        if not self.catalog:
            return
            yield  # pragma: no cover - keeps this a generator on empty catalog
        slot_filter = self.slot_var.get()
        affix_filter = self.affix_var.get()
        source_filter = self.source_var.get()
        category_filter = self.category_var.get()
        query = self.search_var.get().strip().lower()
        tokens = [token for token in query.split() if token]
        for slot in self.catalog.get("slots", []):
            if not self._choice_matches(slot_filter, slot["name"]):
                continue
            for group in slot.get("groups", []):
                corrupt = self._is_corrupt(group)
                affix_label = "汙染" if corrupt else (group.get("affix") or "")
                if not self._choice_matches(affix_filter, affix_label):
                    continue
                if affix_filter.strip() != "汙染" and not self._choice_matches(source_filter, group.get("source") or ""):
                    continue
                tags = group_categories(group)
                if category_filter.strip() and category_filter.strip() != ALL:
                    if category_filter.strip() == "無標籤":
                        if tags:
                            continue
                    elif not any(self._choice_matches(category_filter, tag) for tag in tags):
                        continue
                haystack = " ".join(
                    [
                        group.get("label", ""),
                        group.get("family", ""),
                        *tags,
                        group.get("affix", ""),
                        group.get("source", ""),
                        slot["name"],
                        *(tier.get("name", "") for tier in group.get("tiers", [])),
                        *(tier.get("text", "") for tier in group.get("tiers", [])),
                    ]
                ).lower()
                if tokens and not all(token in haystack for token in tokens):
                    continue
                yield slot["name"], group

    def current_slot_name(self) -> str | None:
        slot_filter = (self.slot_var.get() or "").strip()
        slot_names = [slot["name"] for slot in (self.catalog or {}).get("slots", [])]
        matched = [name for name in slot_names if self._choice_matches(slot_filter, name)] if slot_filter else slot_names
        row = self._selected_row()
        if row:
            selected_names = list(row["slots"].keys())
            overlap = [name for name in selected_names if name in matched] if matched else selected_names
            names = overlap or selected_names
            selection = self.slot_list.curselection()
            if selection and selection[0] < len(names):
                return names[selection[0]]
            return names[0] if names else None
        if slot_filter and slot_filter != ALL:
            if slot_filter in slot_names:
                return slot_filter
            return matched[0] if matched else None
        return None

    def refresh_corrupt_panel(self) -> None:
        for item in self.corrupt_tree.get_children():
            self.corrupt_tree.delete(item)
        if not self.catalog:
            self.corrupt_title_var.set("此部位汙染詞")
            return
        slot_name = self.current_slot_name()
        if not slot_name:
            self.corrupt_title_var.set("此部位汙染詞（請先選擇部位）")
            return
        slot = next((item for item in self.catalog.get("slots", []) if item["name"] == slot_name), None)
        groups = [group for group in (slot or {}).get("groups", []) if self._is_corrupt(group)]
        count = 0
        for group in groups:
            for tier in group.get("tiers", []):
                self.corrupt_tree.insert(
                    "",
                    "end",
                    values=(
                        f"T{tier.get('tier')}",
                        tier.get("level"),
                        self._weight_value(tier),
                        self._pool_chance(slot_name, group, tier),
                        tier.get("text"),
                    ),
                    tags=(_tier_tag(tier.get("tier"), corrupt=True),),
                )
                count += 1
        self.corrupt_title_var.set(f"{slot_name} 汙染詞（{count} 筆）")

    def refresh_affix_list(self) -> None:
        for item in self.affix_tree.get_children():
            self.affix_tree.delete(item)
        grouped: dict[tuple[str, str, str, str], dict] = {}
        for slot_name, group in self.iter_matching_groups():
            key = (
                group.get("label", ""),
                group.get("affix", ""),
                group.get("source", ""),
                group.get("family", ""),
            )
            bucket = grouped.setdefault(
                key,
                {
                    "label": key[0],
                    "affix": key[1],
                    "source": key[2],
                    "family": key[3],
                    "categories": group_categories(group),
                    "category": format_tag_text(group_categories(group)),
                    "corrupt": self._is_corrupt(group),
                    "slots": {},
                    "max_tiers": 0,
                    "best_t1": 0,
                    "t1_weight": 0,
                },
            )
            bucket["slots"][slot_name] = group
            bucket["max_tiers"] = max(bucket["max_tiers"], len(group.get("tiers", [])))
            bucket["corrupt"] = bucket["corrupt"] or self._is_corrupt(group)
            t1 = group["tiers"][0] if group.get("tiers") else {}
            bucket["best_t1"] = max(bucket["best_t1"], int(t1.get("level") or 0))
            try:
                bucket["t1_weight"] = max(bucket["t1_weight"], int(t1.get("weight") or 0))
            except (TypeError, ValueError):
                pass

        self.filtered_groups = list(grouped.values())
        self._render_affix_rows()
        count = len(self.filtered_groups)
        self.status_var.set(f"符合 {count} 組詞綴。點欄位標題可排序，目前依 {self._affix_sort_label()}。")
        self.summary_var.set("請從左側選擇一個詞綴")
        self.meta_var.set("T1 為該部位最難出的最高階詞綴")
        self._render_tag_chips([])
        self.slot_list.delete(0, "end")
        for item in self.tier_tree.get_children():
            self.tier_tree.delete(item)
        self.refresh_corrupt_panel()

    def _affix_sort_label(self) -> str:
        name = self.affix_headings.get(self.affix_sort_col, "T1 物等")
        return f"{name}{'由高到低' if self.affix_sort_desc else '由低到高'}"

    def _affix_sort_key(self, row: dict):
        column = self.affix_sort_col
        if column == "t1":
            return int(row.get("best_t1") or 0)
        if column == "weight":
            return int(row.get("t1_weight") or 0)
        if column == "tiers":
            return int(row.get("max_tiers") or 0)
        if column == "slots":
            return len(row.get("slots") or {})
        if column == "corrupt":
            return 1 if row.get("corrupt") else 0
        if column == "affix":
            return row.get("affix") or ""
        if column == "source":
            return row.get("source") or ""
        if column == "category":
            return row.get("category") or ""
        return row.get("label") or ""

    def _update_affix_headings(self) -> None:
        for key, title in self.affix_headings.items():
            mark = ""
            if key == self.affix_sort_col:
                mark = " ▼" if self.affix_sort_desc else " ▲"
            self.affix_tree.heading(key, text=f"{title}{mark}")

    def sort_affix_list(self, column: str) -> None:
        if self.affix_sort_col == column:
            self.affix_sort_desc = not self.affix_sort_desc
        else:
            self.affix_sort_col = column
            self.affix_sort_desc = column in {"t1", "weight", "tiers", "slots", "corrupt"}
        self._render_affix_rows()
        self.status_var.set(f"符合 {len(self.filtered_groups)} 組詞綴。目前依 {self._affix_sort_label()}。")

    def _render_affix_rows(self) -> None:
        self.filtered_groups.sort(key=self._affix_sort_key, reverse=self.affix_sort_desc)
        self._update_affix_headings()
        for item in self.affix_tree.get_children():
            self.affix_tree.delete(item)
        for index, row in enumerate(self.filtered_groups):
            if row["corrupt"]:
                tag = "t1_corrupt" if row["best_t1"] else "corrupt"
            elif row["affix"] == "前綴":
                tag = "prefix"
            elif row["affix"] == "後綴":
                tag = "suffix"
            else:
                tag = "tn"
            self.affix_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    row["label"],
                    format_tag_text_marked(row.get("categories") or [row.get("category") or "其他"]),
                    row["affix"],
                    "是" if row["corrupt"] else "",
                    row["source"],
                    row["best_t1"] or "—",
                    row["t1_weight"] or "—",
                    row["max_tiers"],
                    len(row["slots"]),
                ),
                tags=(tag,),
            )

    def sort_detail_tree(self, tree: ttk.Treeview, column: str, numeric: bool) -> None:
        state = getattr(tree, "_sort_state", {"col": None, "desc": True})
        descending = not state["desc"] if state["col"] == column else True
        tree._sort_state = {"col": column, "desc": descending}

        def value_of(item_id: str):
            raw = tree.set(item_id, column)
            if not numeric:
                return str(raw)
            text = str(raw).replace("%", "").replace("T", "").replace("—", "0").replace(",", "")
            try:
                return float(text)
            except ValueError:
                return 0.0

        rows = list(tree.get_children(""))
        rows.sort(key=value_of, reverse=descending)
        for index, item_id in enumerate(rows):
            tree.move(item_id, "", index)

    def _selected_row(self) -> dict | None:
        selected = self.affix_tree.selection()
        if not selected:
            return None
        try:
            return self.filtered_groups[int(selected[0])]
        except (ValueError, IndexError):
            return None

    def _render_tag_chips(self, tags: list[str]) -> None:
        for child in self.tag_chip_row.winfo_children():
            child.destroy()
        names = [str(tag) for tag in tags if tag]
        if not names:
            return
        for name in names:
            color = tag_color(name)
            chip = ctk.CTkLabel(
                self.tag_chip_row,
                text=name,
                font=FONT_SMALL,
                text_color="#101318",
                fg_color=color,
                corner_radius=6,
                padx=10,
                pady=3,
            )
            chip.pack(side="left", padx=(0, 6), pady=2)

    def show_selected_affix(self) -> None:
        row = self._selected_row()
        if not row:
            return
        tags = row.get("categories") or [row.get("category") or "其他"]
        if isinstance(tags, str):
            tags = [part for part in tags.replace("·", " ").split() if part]
        self.summary_var.set(row["label"])
        self._render_tag_chips(tags)
        corrupt_mark = "　汙染詞" if row.get("corrupt") else ""
        self.meta_var.set(
            f"{row['affix']}　{row['source']}{corrupt_mark}　家族 {row['family'] or '—'}　"
            f"T1 物等 {row.get('best_t1') or '—'}　T1 權重 {row.get('t1_weight') or '—'}"
        )
        self.slot_list.delete(0, "end")
        slot_names = list(row["slots"].keys())
        preferred = self.slot_var.get()
        chosen = 0
        for index, name in enumerate(slot_names):
            group = row["slots"][name]
            t1 = group["tiers"][0] if group.get("tiers") else {}
            self.slot_list.insert(
                "end",
                f"{name}    T1 物等 {t1.get('level', '—')}    權重 {t1.get('weight', '—')}    共 {len(group.get('tiers', []))} 階",
            )
            self.slot_list.itemconfig(index, fg=T1_FG)
            if preferred != ALL and name == preferred:
                chosen = index
        if slot_names:
            self.slot_list.selection_set(chosen)
            self.slot_list.see(chosen)
            self.show_slot_table()

    def show_slot_table(self) -> None:
        row = self._selected_row()
        if not row:
            return
        selection = self.slot_list.curselection()
        if not selection:
            return
        slot_name = list(row["slots"].keys())[selection[0]]
        group = row["slots"][slot_name]
        for item in self.tier_tree.get_children():
            self.tier_tree.delete(item)
        corrupt = self._is_corrupt(group) or bool(row.get("corrupt"))
        for tier in group.get("tiers", []):
            self.tier_tree.insert(
                "",
                "end",
                values=(
                    f"T{tier.get('tier')}",
                    tier.get("level"),
                    tier.get("name"),
                    self._weight_value(tier),
                    self._pool_chance(slot_name, group, tier),
                    "是" if corrupt else "",
                    tier.get("text"),
                ),
                tags=(_tier_tag(tier.get("tier"), corrupt=corrupt),),
            )
        t1 = group["tiers"][0] if group.get("tiers") else {}
        corrupt_mark = "　汙染詞" if corrupt else ""
        self.meta_var.set(
            f"{row['affix']}　{row['source']}{corrupt_mark}　部位 {slot_name}　"
            f"T1 需要物等 {t1.get('level', '—')}（最難出）　T1 權重 {t1.get('weight', '—')}　"
            f"估計占比 {self._pool_chance(slot_name, group, t1) if t1 else '—'}　"
            f"共 {len(group.get('tiers', []))} 階"
        )
        self.refresh_corrupt_panel()

    def start_sync(self) -> None:
        if self._syncing:
            return
        self._syncing = True
        game = self.game_id
        set_progress(self.progress, 0, 100)
        try:
            self.game_switch.configure(state="disabled")
        except (tk.TclError, ValueError, TypeError):
            pass

        def run() -> None:
            def progress(message: str, current: int, total: int) -> None:
                self.after(0, lambda: self._on_progress(message, current, total))

            try:
                catalog = sync_catalog(progress=progress, game=game)
                self.after(0, lambda: self._on_sync_done(catalog, None, game))
            except Exception as error:  # noqa: BLE001
                self.after(0, lambda: self._on_sync_done(None, error, game))

        threading.Thread(target=run, daemon=True).start()

    def _on_progress(self, message: str, current: int, total: int) -> None:
        self.status_var.set(message)
        set_progress(self.progress, current, total)

    def _on_sync_done(self, catalog: dict | None, error: Exception | None, game: str | None = None) -> None:
        self._syncing = False
        try:
            self.game_switch.configure(state="normal")
        except (tk.TclError, ValueError, TypeError):
            pass
        spec = game_spec(game or self.game_id)
        if error:
            self.status_var.set(f"更新失敗：{error}")
            messagebox.showerror("更新失敗", str(error))
            return
        assert catalog is not None
        skipped = catalog.get("skipped") or []
        extra = f"\n略過 {len(skipped)} 個沒有詞綴表的頁面。" if skipped else ""
        if game is None or game == self.game_id:
            self.set_catalog(catalog)
        messagebox.showinfo(
            "更新完成",
            f"已從 {spec['site_name']} 下載 {catalog.get('slot_count', 0)} 個部位、"
            f"{catalog.get('group_count', 0)} 組詞綴。{extra}",
        )


def main() -> None:
    from .menu import main as run_menu

    run_menu()
