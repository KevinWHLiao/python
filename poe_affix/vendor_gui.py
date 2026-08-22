"""Vendor recipe lookup window."""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from .theme import BG, BG_HEAD, FONT_SMALL, FONT_UI, GOLD, MUTED, apply_theme
from .vendor import VENDOR_URL, load_vendor, sync_vendor

ALL = "全部"


class VendorApp(tk.Toplevel):
    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master)
        self._on_back = on_back
        self.title("流亡黯道 · 商店配方")
        self.geometry("1280x780")
        self.minsize(980, 600)
        self.configure(bg=BG)
        self.option_add("*Font", FONT_UI)
        apply_theme(self)
        self.protocol("WM_DELETE_WINDOW", self.go_back)

        self.catalog: dict | None = None
        self.rows: list[dict] = []
        self._syncing = False
        self.sort_col = "category"
        self.sort_desc = False

        self.category_var = tk.StringVar(value=ALL)
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="尚未載入資料")

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
        ttk.Label(header, text="商店配方", style="Gold.TLabel", background=BG_HEAD).pack(side="left", pady=12)
        ttk.Button(header, text="從 PoEDB 更新商店配方", command=self.start_sync).pack(side="right", padx=16, pady=12)
        ttk.Button(
            header,
            text="開啟商店配方頁",
            command=lambda: webbrowser.open(VENDOR_URL),
        ).pack(side="right", padx=(0, 8), pady=12)

        filters = ttk.Frame(self, padding=(16, 12, 16, 8))
        filters.pack(fill="x")
        ttk.Label(filters, text="分類", style="Muted.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.category_combo = ttk.Combobox(filters, textvariable=self.category_var, state="readonly", width=28)
        self.category_combo.grid(row=0, column=1, padx=(0, 16))
        self.category_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        ttk.Label(filters, text="搜尋獎勵 / 材料", style="Muted.TLabel").grid(row=0, column=2, sticky="w", padx=(0, 6))
        ttk.Entry(filters, textvariable=self.search_var, width=40).grid(row=0, column=3, sticky="ew")
        filters.columnconfigure(3, weight=1)

        ttk.Label(self, text="可依分類或關鍵字查商人配方，例如「機會石」「六孔」「未鑑定」。", style="Muted.TLabel").pack(
            anchor="w", padx=16
        )

        wrap = ttk.Frame(self, padding=(16, 8, 16, 8))
        wrap.pack(fill="both", expand=True)
        columns = ("category", "reward", "materials", "note")
        self.tree = ttk.Treeview(wrap, columns=columns, show="headings", selectmode="browse")
        self.headings = {"category": "分類", "reward": "獎勵", "materials": "需要物品", "note": "備註"}
        widths = {"category": 160, "reward": 260, "materials": 480, "note": 220}
        for key, title in self.headings.items():
            self.tree.heading(key, text=title, command=lambda column=key: self.sort_by(column))
            self.tree.column(key, width=widths[key], stretch=key in {"reward", "materials"}, anchor="w")
        yscroll = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        status = tk.Frame(self, bg=BG_HEAD)
        status.pack(fill="x")
        tk.Label(status, textvariable=self.status_var, bg=BG_HEAD, fg=MUTED, font=FONT_SMALL, anchor="w").pack(
            side="left", padx=16, pady=6
        )
        self.progress = ttk.Progressbar(status, mode="determinate", length=220)
        self.progress.pack(side="right", padx=16, pady=8)

    def _startup(self) -> None:
        catalog = load_vendor()
        if catalog:
            self.set_catalog(catalog)
            return
        if messagebox.askyesno("尚未下載商店配方", "第一次使用需要從 PoEDB 商店配方頁下載。現在更新嗎？"):
            self.start_sync()

    def set_catalog(self, catalog: dict) -> None:
        self.catalog = catalog
        categories = [ALL] + list(catalog.get("categories") or [])
        self.category_combo.configure(values=categories)
        if self.category_var.get() not in categories:
            self.category_var.set(ALL)
        self.refresh()

    def matching(self) -> list[dict]:
        if not self.catalog:
            return []
        category = self.category_var.get()
        tokens = [token for token in self.search_var.get().strip().lower().split() if token]
        rows = []
        for recipe in self.catalog.get("recipes") or []:
            if category != ALL and recipe.get("category") != category:
                continue
            haystack = " ".join(
                [
                    recipe.get("category", ""),
                    recipe.get("reward", ""),
                    recipe.get("materials", ""),
                    recipe.get("note", ""),
                ]
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
        self.refresh()

    def refresh(self) -> None:
        self.rows = self.matching()
        self.rows.sort(key=lambda item: item.get(self.sort_col) or "", reverse=self.sort_desc)
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, recipe in enumerate(self.rows):
            self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    recipe.get("category"),
                    recipe.get("reward"),
                    recipe.get("materials"),
                    recipe.get("note"),
                ),
            )
        for col, title in self.headings.items():
            mark = ""
            if col == self.sort_col:
                mark = " ▼" if self.sort_desc else " ▲"
            self.tree.heading(col, text=f"{title}{mark}")
        synced = (self.catalog or {}).get("synced_at", "")
        self.status_var.set(f"符合 {len(self.rows)} 筆商店配方　更新時間 {synced}")

    def start_sync(self) -> None:
        if self._syncing:
            return
        self._syncing = True

        def run() -> None:
            def progress(message: str, current: int, total: int) -> None:
                self.after(0, lambda: self._on_progress(message, current, total))

            try:
                catalog = sync_vendor(progress=progress)
                self.after(0, lambda: self._on_sync_done(catalog, None))
            except Exception as error:  # noqa: BLE001
                self.after(0, lambda: self._on_sync_done(None, error))

        threading.Thread(target=run, daemon=True).start()

    def _on_progress(self, message: str, current: int, total: int) -> None:
        self.status_var.set(message)
        self.progress.configure(maximum=max(total, 1), value=current)

    def _on_sync_done(self, catalog: dict | None, error: Exception | None) -> None:
        self._syncing = False
        if error:
            messagebox.showerror("更新失敗", str(error))
            self.status_var.set(f"更新失敗：{error}")
            return
        assert catalog is not None
        self.set_catalog(catalog)
        messagebox.showinfo("更新完成", f"已下載 {catalog.get('recipe_count', 0)} 筆商店配方。")
