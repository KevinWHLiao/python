"""Shared CustomTkinter + ttk theme for PoE lookup windows."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

import customtkinter as ctk

FONT_FAMILY = "Microsoft JhengHei UI"
FONT_UI = (FONT_FAMILY, 13)
FONT_TITLE = (FONT_FAMILY, 20, "bold")
FONT_SECTION = (FONT_FAMILY, 14, "bold")
FONT_SMALL = (FONT_FAMILY, 12)
FONT_HERO = (FONT_FAMILY, 28, "bold")
FONT_CARD = (FONT_FAMILY, 15, "bold")

# Refined dark palette — warm gold on deep charcoal
BG = "#0c0e13"
BG_PANEL = "#151922"
BG_RAISED = "#1e2430"
BG_CARD = "#181d28"
BG_INPUT = "#12161f"
BG_HEAD = "#16130f"
LINE = "#2e3340"
LINE_SOFT = "#252a36"
GOLD = "#d4a54a"
GOLD_HI = "#f0c56d"
TEXT = "#efe9dc"
MUTED = "#9a9488"
PREFIX = "#7ecbff"
SUFFIX = "#7fd9a8"
CORRUPT = "#d4a0f0"
T1_BG = "#3f2c12"
T1_FG = "#ffd37a"
T2_BG = "#2c2616"
T2_FG = "#e8c07a"
T3_BG = "#1a2434"
T3_FG = "#9ab8ea"
TN_FG = "#c9c3b4"
CORRUPT_BG = "#2a1834"
CORRUPT_T1_BG = "#452048"
CORRUPT_T1_FG = "#f3c6ff"

BTN_PRIMARY = "#c9963a"
BTN_PRIMARY_HOVER = "#e0b15a"
BTN_GHOST_HOVER = "#252018"
BTN_DANGER = "#8b3a3a"

_APPEARANCE_READY = False


def setup_appearance() -> None:
    global _APPEARANCE_READY
    if _APPEARANCE_READY:
        return
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    _APPEARANCE_READY = True


def setup_window(win: tk.Misc) -> None:
    """Apply CTk appearance + ttk Treeview styling to a window."""
    setup_appearance()
    try:
        win.configure(fg_color=BG)
    except tk.TclError:
        try:
            win.configure(bg=BG)
        except tk.TclError:
            pass
    apply_ttk_theme(win)


def apply_theme(widget: tk.Misc) -> None:
    """Back-compat alias used by older call sites."""
    setup_window(widget)


def apply_ttk_theme(widget: tk.Misc) -> None:
    style = ttk.Style(widget)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(".", background=BG, foreground=TEXT, fieldbackground=BG_INPUT, bordercolor=LINE)
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=BG_PANEL)
    style.configure("TLabel", background=BG, foreground=TEXT, font=FONT_UI)
    style.configure("Panel.TLabel", background=BG_PANEL, foreground=TEXT)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=FONT_SMALL)
    style.configure("PanelMuted.TLabel", background=BG_PANEL, foreground=MUTED, font=FONT_SMALL)
    style.configure("Gold.TLabel", background=BG, foreground=GOLD, font=FONT_TITLE)
    style.configure("Hero.TLabel", background=BG, foreground=GOLD, font=FONT_HERO)
    style.configure("Section.TLabel", background=BG_PANEL, foreground=GOLD, font=FONT_SECTION)
    style.configure(
        "TCombobox",
        fieldbackground=BG_INPUT,
        background=BG_RAISED,
        foreground=TEXT,
        arrowcolor=GOLD,
        bordercolor=LINE,
        lightcolor=LINE,
        darkcolor=LINE,
        insertcolor=GOLD_HI,
        insertwidth=2,
        padding=6,
        font=FONT_UI,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", BG_INPUT), ("focus", BG_INPUT)],
        foreground=[("readonly", TEXT), ("focus", TEXT)],
        bordercolor=[("focus", GOLD), ("readonly", LINE)],
        lightcolor=[("focus", GOLD)],
        darkcolor=[("focus", GOLD)],
        selectbackground=[("readonly", BG_HEAD), ("focus", BG_INPUT)],
        selectforeground=[("readonly", GOLD_HI), ("focus", TEXT)],
    )
    style.configure(
        "TEntry",
        fieldbackground=BG_INPUT,
        foreground=TEXT,
        bordercolor=LINE,
        lightcolor=LINE,
        darkcolor=LINE,
        insertcolor=GOLD_HI,
        insertwidth=2,
        padding=6,
        font=FONT_UI,
    )
    style.map(
        "TEntry",
        bordercolor=[("focus", GOLD)],
        lightcolor=[("focus", GOLD)],
        darkcolor=[("focus", GOLD)],
    )
    style.configure(
        "Treeview",
        background=BG_INPUT,
        foreground=TEXT,
        fieldbackground=BG_INPUT,
        bordercolor=LINE_SOFT,
        rowheight=34,
        font=FONT_UI,
    )
    style.configure(
        "Treeview.Heading",
        background=BG_HEAD,
        foreground=GOLD,
        relief="flat",
        font=(FONT_FAMILY, 12, "bold"),
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
        thickness=8,
    )
    style.configure("TPanedwindow", background=BG)
    style.configure("TSeparator", background=LINE)
    style.configure("Vertical.TScrollbar", background=BG_RAISED, troughcolor=BG, bordercolor=BG, arrowcolor=GOLD)
    style.configure("Horizontal.TScrollbar", background=BG_RAISED, troughcolor=BG, bordercolor=BG, arrowcolor=GOLD)
    widget.option_add("*TCombobox*Listbox.background", BG_INPUT)
    widget.option_add("*TCombobox*Listbox.foreground", TEXT)
    widget.option_add("*TCombobox*Listbox.selectBackground", "#5a3e14")
    widget.option_add("*TCombobox*Listbox.selectForeground", GOLD_HI)
    widget.option_add("*TCombobox*Listbox.font", FONT_UI)
    widget.option_add("*Font", FONT_UI)


def primary_button(parent, text: str, command=None, **kwargs) -> ctk.CTkButton:
    opts = {
        "text": text,
        "command": command,
        "fg_color": BTN_PRIMARY,
        "hover_color": BTN_PRIMARY_HOVER,
        "text_color": "#1a1408",
        "font": (FONT_FAMILY, 13, "bold"),
        "corner_radius": 10,
        "height": 36,
        "border_width": 0,
    }
    opts.update(kwargs)
    return ctk.CTkButton(parent, **opts)


def ghost_button(parent, text: str, command=None, **kwargs) -> ctk.CTkButton:
    opts = {
        "text": text,
        "command": command,
        "fg_color": "transparent",
        "hover_color": BTN_GHOST_HOVER,
        "text_color": GOLD_HI,
        "border_width": 1,
        "border_color": LINE,
        "font": (FONT_FAMILY, 13),
        "corner_radius": 10,
        "height": 36,
    }
    opts.update(kwargs)
    return ctk.CTkButton(parent, **opts)


def make_header(
    parent,
    title: str,
    *,
    on_back: Callable | None = None,
    right_actions: list[tuple[str, Callable]] | None = None,
    hint: str | None = None,
) -> ctk.CTkFrame:
    shell = ctk.CTkFrame(parent, fg_color=BG_HEAD, corner_radius=0)
    shell.pack(fill="x")
    ctk.CTkFrame(parent, fg_color=GOLD, corner_radius=0, height=2).pack(fill="x")

    row = ctk.CTkFrame(shell, fg_color="transparent")
    row.pack(fill="x", padx=18, pady=14)

    if on_back:
        ghost_button(row, "← 主選單", command=on_back, width=110).pack(side="left", padx=(0, 12))

    title_col = ctk.CTkFrame(row, fg_color="transparent")
    title_col.pack(side="left", fill="x", expand=True)
    ctk.CTkLabel(title_col, text=title, font=FONT_TITLE, text_color=GOLD, anchor="w").pack(anchor="w")
    if hint:
        ctk.CTkLabel(title_col, text=hint, font=FONT_SMALL, text_color=MUTED, anchor="w").pack(anchor="w", pady=(2, 0))

    if right_actions:
        for index, (label, command) in enumerate(reversed(right_actions)):
            btn = primary_button(row, label, command=command) if index == 0 else ghost_button(row, label, command=command)
            btn.pack(side="right", padx=(8, 0) if index else 0)

    return shell


def make_status_bar(parent, status_var: tk.Variable, *, with_progress: bool = False):
    bar = ctk.CTkFrame(parent, fg_color=BG_HEAD, corner_radius=0, height=44)
    bar.pack(fill="x", side="bottom")
    ctk.CTkLabel(
        bar,
        textvariable=status_var,
        font=FONT_SMALL,
        text_color=MUTED,
        anchor="w",
    ).pack(side="left", padx=18, pady=10, fill="x", expand=True)
    progress = None
    if with_progress:
        progress = ctk.CTkProgressBar(bar, width=220, height=8, progress_color=GOLD, fg_color=BG_INPUT)
        progress.pack(side="right", padx=18, pady=14)
        progress.set(0)
    return bar, progress


def set_progress(bar: ctk.CTkProgressBar | None, current: int, total: int) -> None:
    if bar is None:
        return
    maximum = max(total, 1)
    bar.set(min(max(current / maximum, 0.0), 1.0))


def filter_panel(parent) -> ctk.CTkFrame:
    frame = ctk.CTkFrame(parent, fg_color=BG_PANEL, corner_radius=14, border_width=1, border_color=LINE_SOFT)
    frame.pack(fill="x", padx=16, pady=(12, 6))
    inner = ctk.CTkFrame(frame, fg_color="transparent")
    inner.pack(fill="x", padx=14, pady=12)
    return inner


def muted_hint(parent, text: str) -> ctk.CTkLabel:
    label = ctk.CTkLabel(parent, text=text, font=FONT_SMALL, text_color=MUTED, anchor="w", justify="left")
    label.pack(anchor="w", padx=20, pady=(0, 4))
    return label


def content_panel(parent) -> ctk.CTkFrame:
    frame = ctk.CTkFrame(parent, fg_color=BG_PANEL, corner_radius=14, border_width=1, border_color=LINE_SOFT)
    frame.pack(fill="both", expand=True, padx=16, pady=(4, 12))
    return frame


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
