"""Shared dark theme for PoE lookup windows."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

FONT_UI = ("Microsoft JhengHei UI", 10)
FONT_TITLE = ("Microsoft JhengHei UI", 16, "bold")
FONT_SECTION = ("Microsoft JhengHei UI", 11, "bold")
FONT_SMALL = ("Microsoft JhengHei UI", 9)
FONT_HERO = ("Microsoft JhengHei UI", 22, "bold")

BG = "#101218"
BG_PANEL = "#171a22"
BG_RAISED = "#1f2430"
BG_INPUT = "#141821"
BG_HEAD = "#2a2418"
LINE = "#3a3324"
GOLD = "#e0b15a"
GOLD_HI = "#ffd37a"
TEXT = "#ece7da"
MUTED = "#9b9586"
PREFIX = "#7ecbff"
SUFFIX = "#86e0b0"
CORRUPT = "#d9a5ff"
T1_BG = "#4a3210"
T1_FG = "#ffd37a"
T2_BG = "#322a16"
T2_FG = "#e8c07a"
T3_BG = "#1c2738"
T3_FG = "#9ab8ea"
TN_FG = "#c9c3b4"
CORRUPT_BG = "#2c1836"
CORRUPT_T1_BG = "#4a2048"
CORRUPT_T1_FG = "#f3c6ff"


def apply_theme(widget: tk.Misc) -> None:
    style = ttk.Style(widget)
    style.theme_use("clam")
    style.configure(".", background=BG, foreground=TEXT, fieldbackground=BG_INPUT, bordercolor=LINE)
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=BG_PANEL)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Panel.TLabel", background=BG_PANEL, foreground=TEXT)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED)
    style.configure("PanelMuted.TLabel", background=BG_PANEL, foreground=MUTED)
    style.configure("Gold.TLabel", background=BG, foreground=GOLD, font=FONT_TITLE)
    style.configure("Hero.TLabel", background=BG, foreground=GOLD, font=FONT_HERO)
    style.configure("Section.TLabel", background=BG_PANEL, foreground=GOLD, font=FONT_SECTION)
    style.configure(
        "TButton",
        background=BG_RAISED,
        foreground=GOLD_HI,
        bordercolor=GOLD,
        lightcolor=BG_RAISED,
        darkcolor=BG_RAISED,
        padding=(12, 6),
    )
    style.map("TButton", background=[("active", "#3a3324")], foreground=[("active", GOLD_HI)])
    style.configure(
        "Menu.TButton",
        background=BG_RAISED,
        foreground=GOLD_HI,
        bordercolor=GOLD,
        lightcolor=BG_RAISED,
        darkcolor=BG_RAISED,
        padding=(12, 6),
        font=("Microsoft JhengHei UI", 11, "bold"),
    )
    style.map("Menu.TButton", background=[("active", "#3a3324")], foreground=[("active", GOLD_HI)])
    style.configure(
        "TCombobox",
        fieldbackground=BG_INPUT,
        background=BG_RAISED,
        foreground=TEXT,
        arrowcolor=GOLD,
        bordercolor=LINE,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", BG_INPUT)],
        foreground=[("readonly", TEXT)],
        selectbackground=[("readonly", BG_HEAD)],
        selectforeground=[("readonly", GOLD_HI)],
    )
    style.configure(
        "TEntry",
        fieldbackground=BG_INPUT,
        foreground=TEXT,
        bordercolor=LINE,
        insertcolor=GOLD_HI,
    )
    style.configure(
        "Treeview",
        background=BG_INPUT,
        foreground=TEXT,
        fieldbackground=BG_INPUT,
        bordercolor=LINE,
        rowheight=30,
        font=FONT_UI,
    )
    style.configure(
        "Treeview.Heading",
        background=BG_HEAD,
        foreground=GOLD,
        relief="flat",
        font=("Microsoft JhengHei UI", 10, "bold"),
        bordercolor=LINE,
    )
    style.map(
        "Treeview",
        background=[("selected", "#5a3e14")],
        foreground=[("selected", GOLD_HI)],
    )
    style.map("Treeview.Heading", background=[("active", "#3d3420")])
    style.configure(
        "TProgressbar",
        background=GOLD,
        troughcolor=BG_INPUT,
        bordercolor=LINE,
        lightcolor=GOLD,
        darkcolor=GOLD,
    )
    style.configure("TPanedwindow", background=BG)
    style.configure("TSeparator", background=LINE)
    widget.option_add("*TCombobox*Listbox.background", BG_INPUT)
    widget.option_add("*TCombobox*Listbox.foreground", TEXT)
    widget.option_add("*TCombobox*Listbox.selectBackground", "#5a3e14")
    widget.option_add("*TCombobox*Listbox.selectForeground", GOLD_HI)


def sort_tree(tree: ttk.Treeview, column: str, numeric: bool) -> None:
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
