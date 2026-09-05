"""Crafting bench unlock lookup window."""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

import customtkinter as ctk

from .craft import CRAFT_URL, load_crafting, sync_crafting
from .theme import (
    FONT_SMALL,
    MUTED,
    content_panel,
    filter_panel,
    make_header,
    make_status_bar,
    muted_hint,
    set_progress,
    setup_window,
)

ALL = "全部"


class CraftApp(ctk.CTkToplevel):
    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master)
        self._on_back = on_back
        self.title("流亡黯道 · 工藝解鎖區域")
        self.geometry("1280x780")
        self.minsize(980, 600)
        setup_window(self)
        self.protocol("WM_DELETE_WINDOW", self.go_back)

        self.catalog: dict | None = None
        self.rows: list[dict] = []
        self._syncing = False
        self.sort_col = "unlock"
        self.sort_desc = False

        self.area_var = tk.StringVar(value=ALL)
        self.class_var = tk.StringVar(value=ALL)
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="尚未載入資料")

        self._build()
        self.search_var.trace_add("write", lambda *_: self.refresh())
        self.after(80, self._startup)

    def go_back(self) -> None:
        self.destroy()
        self._on_back()

    def _build(self) -> None:
        make_header(
            self,
            "工藝解鎖區域",
            on_back=self.go_back,
            right_actions=[
                ("從 PoEDB 更新工藝資料", self.start_sync),
                ("開啟工藝台頁", lambda: webbrowser.open(CRAFT_URL)),
            ],
        )
        _, self.progress = make_status_bar(self, self.status_var, with_progress=True)

        filters = filter_panel(self)
        ctk.CTkLabel(filters, text="解鎖區域", font=FONT_SMALL, text_color=MUTED).grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        self.area_combo = ttk.Combobox(filters, textvariable=self.area_var, state="readonly", width=28)
        self.area_combo.grid(row=0, column=1, padx=(0, 16))
        self.area_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        ctk.CTkLabel(filters, text="適用部位", font=FONT_SMALL, text_color=MUTED).grid(
            row=0, column=2, sticky="w", padx=(0, 8)
        )
        self.class_combo = ttk.Combobox(filters, textvariable=self.class_var, state="readonly", width=22)
        self.class_combo.grid(row=0, column=3, padx=(0, 16))
        self.class_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        ctk.CTkLabel(filters, text="搜尋配方", font=FONT_SMALL, text_color=MUTED).grid(
            row=0, column=4, sticky="w", padx=(0, 8)
        )
        ttk.Entry(filters, textvariable=self.search_var, width=32).grid(row=0, column=5, sticky="ew")
        filters.grid_columnconfigure(5, weight=1)

        muted_hint(self, "點欄位標題可排序。選解鎖區域可查出該處能解鎖的工藝。")

        wrap = content_panel(self)
        inner = ctk.CTkFrame(wrap, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=10, pady=10)
        columns = ("affix", "cost", "item_classes", "unlock")
        self.tree = ttk.Treeview(inner, columns=columns, show="headings", selectmode="browse")
        self.headings = {"affix": "工藝詞綴", "cost": "消耗", "item_classes": "適用部位", "unlock": "解鎖區域"}
        widths = {"affix": 280, "cost": 160, "item_classes": 360, "unlock": 220}
        for key, title in self.headings.items():
            self.tree.heading(key, text=title, command=lambda column=key: self.sort_by(column))
            self.tree.column(key, width=widths[key], stretch=key in {"affix", "item_classes"}, anchor="w")
        yscroll = ttk.Scrollbar(inner, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

    def _startup(self) -> None:
        catalog = load_crafting()
        if catalog:
            self.set_catalog(catalog)
            return
        if messagebox.askyesno("尚未下載工藝資料", "第一次使用需要從 PoEDB 工藝台頁下載配方。現在更新嗎？"):
            self.start_sync()

    def set_catalog(self, catalog: dict) -> None:
        self.catalog = catalog
        areas = [ALL] + list(catalog.get("areas") or [])
        self.area_combo.configure(values=areas)
        if self.area_var.get() not in areas:
            self.area_var.set(ALL)
        classes = {ALL}
        for recipe in catalog.get("recipes") or []:
            for part in (recipe.get("item_classes") or "").replace("·", ",").split(","):
                name = part.strip()
                if name:
                    classes.add(name)
        class_list = [ALL] + sorted(name for name in classes if name != ALL)
        self.class_combo.configure(values=class_list)
        if self.class_var.get() not in class_list:
            self.class_var.set(ALL)
        self.refresh()

    def matching(self) -> list[dict]:
        if not self.catalog:
            return []
        area = self.area_var.get()
        item_class = self.class_var.get()
        tokens = [token for token in self.search_var.get().strip().lower().split() if token]
        rows = []
        for recipe in self.catalog.get("recipes") or []:
            if area != ALL and recipe.get("unlock") != area:
                continue
            classes = recipe.get("item_classes") or ""
            if item_class != ALL and item_class not in classes:
                continue
            haystack = " ".join(
                [recipe.get("affix", ""), recipe.get("cost", ""), classes, recipe.get("unlock", "")]
            ).lower()
            if tokens and not all(token in haystack for token in tokens):
                continue
            rows.append(recipe)
        return rows

    def sort_by(self, column: str) -> None:
        if self.sort_col == column:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_col = column
            self.sort_desc = False
        self.refresh(keep_sort=True)

    def refresh(self, keep_sort: bool = False) -> None:
        self.rows = self.matching()
        key = {
            "affix": lambda item: item.get("affix") or "",
            "cost": lambda item: item.get("cost") or "",
            "item_classes": lambda item: item.get("item_classes") or "",
            "unlock": lambda item: item.get("unlock") or "",
        }.get(self.sort_col, lambda item: item.get("unlock") or "")
        self.rows.sort(key=key, reverse=self.sort_desc)
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, recipe in enumerate(self.rows):
            self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(recipe.get("affix"), recipe.get("cost"), recipe.get("item_classes"), recipe.get("unlock")),
            )
        for col, title in self.headings.items():
            mark = ""
            if col == self.sort_col:
                mark = " ▼" if self.sort_desc else " ▲"
            self.tree.heading(col, text=f"{title}{mark}")
        synced = (self.catalog or {}).get("synced_at", "")
        self.status_var.set(f"符合 {len(self.rows)} 筆工藝配方　更新時間 {synced}")

    def start_sync(self) -> None:
        if self._syncing:
            return
        self._syncing = True

        def run() -> None:
            def progress(message: str, current: int, total: int) -> None:
                self.after(0, lambda: self._on_progress(message, current, total))

            try:
                catalog = sync_crafting(progress=progress)
                self.after(0, lambda: self._on_sync_done(catalog, None))
            except Exception as error:  # noqa: BLE001
                self.after(0, lambda: self._on_sync_done(None, error))

        threading.Thread(target=run, daemon=True).start()

    def _on_progress(self, message: str, current: int, total: int) -> None:
        self.status_var.set(message)
        set_progress(self.progress, current, total)

    def _on_sync_done(self, catalog: dict | None, error: Exception | None) -> None:
        self._syncing = False
        if error:
            messagebox.showerror("更新失敗", str(error))
            self.status_var.set(f"更新失敗：{error}")
            return
        assert catalog is not None
        self.set_catalog(catalog)
        set_progress(self.progress, 1, 1)
        messagebox.showinfo("更新完成", f"已下載 {catalog.get('recipe_count', 0)} 筆工藝配方。")
