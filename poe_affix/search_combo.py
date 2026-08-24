"""Trade-style searchable combobox: type freely, pick from a suggestion list."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .theme import BG_HEAD, BG_INPUT, FONT_UI, GOLD_HI, LINE, MUTED, TEXT

_NAV_KEYS = {
    "Return",
    "Escape",
    "Up",
    "Down",
    "Left",
    "Right",
    "Tab",
    "Home",
    "End",
    "Prior",
    "Next",
    "Shift_L",
    "Shift_R",
    "Control_L",
    "Control_R",
    "Alt_L",
    "Alt_R",
}


def choice_matches(typed: str, candidate: str) -> bool:
    text = (typed or "").strip().replace("　", " ")
    if not text:
        return True
    hay = (candidate or "").casefold()
    return all(token.casefold() in hay for token in text.split() if token)


def filter_choices(typed: str, options: list[str]) -> list[str]:
    return [item for item in options if choice_matches(typed, item)]


def bind_searchable_combo(combo: ttk.Combobox, get_options, on_commit=None) -> "SearchableCombo":
    return SearchableCombo(combo, get_options, on_commit)


class SearchableCombo:
    """Keep typing in the field; suggestions appear without stealing the caret."""

    def __init__(self, combo: ttk.Combobox, get_options, on_commit=None) -> None:
        self.combo = combo
        self.get_options = get_options
        self.on_commit = on_commit
        self._popup: tk.Toplevel | None = None
        self._listbox: tk.Listbox | None = None
        self._hide_job: str | None = None
        self._replace_on_type = False
        combo.configure(state="normal", exportselection=False)
        combo.bind("<FocusIn>", self._on_focus_in, add="+")
        combo.bind("<KeyPress>", self._on_keypress, add="+")
        combo.bind("<KeyRelease>", self._on_keyrelease, add="+")
        combo.bind("<Down>", self._on_down, add="+")
        combo.bind("<Up>", self._on_up, add="+")
        combo.bind("<Return>", self._on_return, add="+")
        combo.bind("<Escape>", self._on_escape, add="+")
        combo.bind("<FocusOut>", self._on_focus_out, add="+")
        combo.bind("<<ComboboxSelected>>", self._on_native_select, add="+")
        combo.bind("<MouseWheel>", self._on_wheel, add="+")

    def _options(self) -> list[str]:
        return list(self.get_options() or [])

    def _on_focus_in(self, _event=None) -> None:
        self._cancel_hide()
        if self.combo.get() in self._options():
            self._replace_on_type = True
        self.combo.after_idle(self._show_caret)

    def _show_caret(self) -> None:
        try:
            if self.combo.selection_present():
                self.combo.selection_clear()
            self.combo.icursor("end")
        except tk.TclError:
            pass

    def _on_keypress(self, event) -> None:
        if event.keysym in _NAV_KEYS or event.keysym in {"BackSpace", "Delete"}:
            if event.keysym in {"BackSpace", "Delete"}:
                self._replace_on_type = False
            return
        if not self._replace_on_type:
            return
        current = self.combo.get()
        if current not in self._options():
            self._replace_on_type = False
            return
        if event.keysym in {"Process", "??"} or (event.char and event.char.isprintable()):
            self.combo.delete(0, "end")
            self._replace_on_type = False

    def _on_keyrelease(self, event) -> None:
        if event.keysym in _NAV_KEYS:
            return
        self._undo_autocomplete()
        typed = self.combo.get()
        if typed.strip():
            self._show_popup(filter_choices(typed, self._options()))
        else:
            self._hide_popup()

    def _undo_autocomplete(self) -> None:
        combo = self.combo
        value = combo.get()
        try:
            if not combo.selection_present():
                return
            start = combo.index("sel.first")
            end = combo.index("sel.last")
            if end != len(value) or start <= 0 or start >= end:
                return
            if value not in self._options():
                return
            combo.delete(start, "end")
            combo.icursor(start)
        except tk.TclError:
            pass

    def _on_down(self, _event=None) -> str:
        items = filter_choices(self.combo.get(), self._options()) or self._options()
        if not self._popup_open():
            self._show_popup(items)
            self._highlight(0)
        else:
            self._move(1)
        return "break"

    def _on_up(self, _event=None) -> str:
        if self._popup_open():
            self._move(-1)
        return "break"

    def _on_return(self, _event=None) -> str:
        picked = self._highlighted()
        if picked:
            self._apply(picked)
            return "break"
        typed = self.combo.get().strip()
        options = self._options()
        exact = [item for item in options if item.casefold() == typed.casefold()]
        matches = filter_choices(typed, options)
        if exact:
            self._apply(exact[0])
        elif len(matches) == 1:
            self._apply(matches[0])
        else:
            self._hide_popup()
            if self.on_commit:
                self.on_commit()
        return "break"

    def _on_escape(self, _event=None) -> str:
        self._hide_popup()
        return "break"

    def _on_focus_out(self, _event=None) -> None:
        self._hide_job = self.combo.after(160, self._hide_if_idle)

    def _on_native_select(self, _event=None) -> None:
        self._replace_on_type = True
        self._hide_popup()
        if self.on_commit:
            self.on_commit()

    def _on_wheel(self, event) -> str | None:
        if not self._popup_open() or self._listbox is None:
            return None
        step = -1 if event.delta > 0 else 1
        self._move(step)
        return "break"

    def _cancel_hide(self) -> None:
        if self._hide_job:
            self.combo.after_cancel(self._hide_job)
            self._hide_job = None

    def _hide_if_idle(self) -> None:
        self._hide_job = None
        try:
            if self.combo.focus_get() is self.combo:
                return
        except (tk.TclError, KeyError):
            pass
        if self._popup_open() and self._pointer_over_popup():
            return
        self._hide_popup()

    def _pointer_over_popup(self) -> bool:
        popup = self._popup
        if popup is None or not popup.winfo_exists():
            return False
        try:
            x, y = popup.winfo_pointerxy()
            return (
                popup.winfo_rootx() <= x <= popup.winfo_rootx() + popup.winfo_width()
                and popup.winfo_rooty() <= y <= popup.winfo_rooty() + popup.winfo_height()
            )
        except tk.TclError:
            return False

    def _popup_open(self) -> bool:
        return bool(self._popup and self._popup.winfo_exists() and self._popup.winfo_ismapped())

    def _create_popup(self) -> None:
        popup = tk.Toplevel(self.combo.winfo_toplevel())
        popup.withdraw()
        popup.overrideredirect(True)
        try:
            popup.attributes("-topmost", True)
        except tk.TclError:
            pass
        frame = tk.Frame(popup, bg=LINE, bd=1, highlightthickness=0)
        frame.pack(fill="both", expand=True)
        listbox = tk.Listbox(
            frame,
            font=FONT_UI,
            background=BG_INPUT,
            foreground=TEXT,
            selectbackground=BG_HEAD,
            selectforeground=GOLD_HI,
            activestyle="none",
            relief="flat",
            highlightthickness=0,
            exportselection=False,
            takefocus=0,
            bd=0,
        )
        listbox.pack(fill="both", expand=True)
        listbox.bind("<ButtonPress-1>", self._on_list_press)
        listbox.bind("<ButtonRelease-1>", self._on_list_click)
        self._popup = popup
        self._listbox = listbox

    def _show_popup(self, items: list[str]) -> None:
        self._cancel_hide()
        if not items:
            self._hide_popup()
            return
        if self._popup is None or not self._popup.winfo_exists():
            self._create_popup()
        assert self._listbox is not None
        self._listbox.delete(0, "end")
        for item in items[:80]:
            self._listbox.insert("end", item)
        self._listbox.configure(height=max(1, min(8, len(items))))
        self._place_popup()
        assert self._popup is not None
        self._popup.deiconify()
        self._popup.lift()

    def _place_popup(self) -> None:
        popup = self._popup
        listbox = self._listbox
        if popup is None or listbox is None:
            return
        combo = self.combo
        combo.update_idletasks()
        width = max(combo.winfo_width(), 120)
        line_height = FONT_UI[1] + 12
        height = listbox.size() * line_height + 4
        popup.geometry(f"{width}x{height}+{combo.winfo_rootx()}+{combo.winfo_rooty() + combo.winfo_height()}")

    def _hide_popup(self) -> None:
        self._cancel_hide()
        if self._popup is not None and self._popup.winfo_exists():
            self._popup.withdraw()

    def _highlight(self, index: int) -> None:
        listbox = self._listbox
        if listbox is None or listbox.size() == 0:
            return
        index = max(0, min(index, listbox.size() - 1))
        listbox.selection_clear(0, "end")
        listbox.selection_set(index)
        listbox.activate(index)
        listbox.see(index)

    def _move(self, step: int) -> None:
        listbox = self._listbox
        if listbox is None or listbox.size() == 0:
            return
        current = listbox.curselection()
        index = int(current[0]) + step if current else 0
        self._highlight(index)

    def _highlighted(self) -> str:
        listbox = self._listbox
        if listbox is None or not self._popup_open():
            return ""
        current = listbox.curselection()
        if not current:
            return ""
        return str(listbox.get(current[0]))

    def _on_list_press(self, _event=None) -> None:
        self._cancel_hide()

    def _on_list_click(self, event) -> str:
        listbox = self._listbox
        if listbox is None:
            return "break"
        index = listbox.nearest(event.y)
        if 0 <= index < listbox.size():
            self._apply(str(listbox.get(index)))
        return "break"

    def _apply(self, value: str) -> None:
        self.combo.set(value)
        self.combo.icursor("end")
        self._replace_on_type = True
        self._hide_popup()
        if self.on_commit:
            self.on_commit()


def bind_structured_suggest(entry: tk.Entry | ttk.Entry, get_rows, on_pick, on_commit=None) -> "StructuredSuggest":
    """Autocomplete popup with non-selectable section headers (trade-style)."""
    return StructuredSuggest(entry, get_rows, on_pick, on_commit)


class StructuredSuggest:
    """Type-ahead list for Entry widgets; headers are skipped when navigating."""

    def __init__(self, entry, get_rows, on_pick, on_commit=None) -> None:
        self.entry = entry
        self.get_rows = get_rows
        self.on_pick = on_pick
        self.on_commit = on_commit
        self._popup: tk.Toplevel | None = None
        self._listbox: tk.Listbox | None = None
        self._hide_job: str | None = None
        self._rows: list = []
        self._debounce: str | None = None
        entry.bind("<KeyRelease>", self._on_keyrelease, add="+")
        entry.bind("<Down>", self._on_down, add="+")
        entry.bind("<Up>", self._on_up, add="+")
        entry.bind("<Return>", self._on_return, add="+")
        entry.bind("<Escape>", self._on_escape, add="+")
        entry.bind("<FocusOut>", self._on_focus_out, add="+")
        entry.bind("<MouseWheel>", self._on_wheel, add="+")

    def _on_keyrelease(self, event) -> None:
        if event.keysym in _NAV_KEYS:
            return
        if self._debounce:
            self.entry.after_cancel(self._debounce)
        self._debounce = self.entry.after(120, self._refresh)

    def _refresh(self) -> None:
        self._debounce = None
        typed = self.entry.get().strip()
        if not typed:
            self._hide_popup()
            return
        rows = list(self.get_rows(typed) or [])
        self._show_popup(rows)

    def _on_down(self, _event=None) -> str:
        if not self._popup_open():
            self._refresh()
        self._move(1)
        return "break"

    def _on_up(self, _event=None) -> str:
        if self._popup_open():
            self._move(-1)
        return "break"

    def _on_return(self, _event=None) -> str:
        row = self._highlighted_row()
        if row is not None and getattr(row, "kind", "") == "item":
            self._apply_row(row)
            return "break"
        self._hide_popup()
        if self.on_commit:
            self.on_commit()
        return "break"

    def _on_escape(self, _event=None) -> str:
        self._hide_popup()
        return "break"

    def _on_focus_out(self, _event=None) -> None:
        self._hide_job = self.entry.after(160, self._hide_if_idle)

    def _on_wheel(self, event) -> str | None:
        if not self._popup_open() or self._listbox is None:
            return None
        step = -1 if event.delta > 0 else 1
        self._move(step)
        return "break"

    def _cancel_hide(self) -> None:
        if self._hide_job:
            self.entry.after_cancel(self._hide_job)
            self._hide_job = None

    def _hide_if_idle(self) -> None:
        self._hide_job = None
        try:
            if self.entry.focus_get() is self.entry:
                return
        except (tk.TclError, KeyError):
            pass
        if self._popup_open() and self._pointer_over_popup():
            return
        self._hide_popup()

    def _pointer_over_popup(self) -> bool:
        popup = self._popup
        if popup is None or not popup.winfo_exists():
            return False
        try:
            x, y = popup.winfo_pointerxy()
            return (
                popup.winfo_rootx() <= x <= popup.winfo_rootx() + popup.winfo_width()
                and popup.winfo_rooty() <= y <= popup.winfo_rooty() + popup.winfo_height()
            )
        except tk.TclError:
            return False

    def _popup_open(self) -> bool:
        return bool(self._popup and self._popup.winfo_exists() and self._popup.winfo_ismapped())

    def _create_popup(self) -> None:
        popup = tk.Toplevel(self.entry.winfo_toplevel())
        popup.withdraw()
        popup.overrideredirect(True)
        try:
            popup.attributes("-topmost", True)
        except tk.TclError:
            pass
        frame = tk.Frame(popup, bg=LINE, bd=1, highlightthickness=0)
        frame.pack(fill="both", expand=True)
        listbox = tk.Listbox(
            frame,
            font=FONT_UI,
            background=BG_INPUT,
            foreground=TEXT,
            selectbackground=BG_HEAD,
            selectforeground=GOLD_HI,
            activestyle="none",
            relief="flat",
            highlightthickness=0,
            exportselection=False,
            takefocus=0,
            bd=0,
        )
        listbox.pack(fill="both", expand=True)
        listbox.bind("<ButtonPress-1>", self._on_list_press)
        listbox.bind("<ButtonRelease-1>", self._on_list_click)
        self._popup = popup
        self._listbox = listbox

    def _show_popup(self, rows: list) -> None:
        self._cancel_hide()
        items = [row for row in rows if getattr(row, "kind", "") == "item"]
        if not items:
            self._hide_popup()
            return
        if self._popup is None or not self._popup.winfo_exists():
            self._create_popup()
        assert self._listbox is not None
        self._rows = list(rows)
        self._listbox.delete(0, "end")
        for row in self._rows:
            if getattr(row, "kind", "") == "header":
                self._listbox.insert("end", f"  {row.text}")
                self._listbox.itemconfig("end", foreground=MUTED, selectbackground=BG_INPUT, selectforeground=MUTED)
            else:
                self._listbox.insert("end", f"  {row.text}")
        visible = min(14, max(4, len(self._rows)))
        self._listbox.configure(height=visible)
        self._place_popup()
        assert self._popup is not None
        self._popup.deiconify()
        self._popup.lift()
        # Highlight first selectable item.
        for index, row in enumerate(self._rows):
            if getattr(row, "kind", "") == "item":
                self._highlight(index)
                break

    def _place_popup(self) -> None:
        popup = self._popup
        listbox = self._listbox
        if popup is None or listbox is None:
            return
        entry = self.entry
        entry.update_idletasks()
        width = max(entry.winfo_width(), 460)
        line_height = FONT_UI[1] + 12
        height = listbox.size() * line_height + 4
        popup.geometry(f"{width}x{height}+{entry.winfo_rootx()}+{entry.winfo_rooty() + entry.winfo_height()}")

    def _hide_popup(self) -> None:
        self._cancel_hide()
        if self._popup is not None and self._popup.winfo_exists():
            self._popup.withdraw()

    def _highlight(self, index: int) -> None:
        listbox = self._listbox
        if listbox is None or listbox.size() == 0:
            return
        index = max(0, min(index, listbox.size() - 1))
        listbox.selection_clear(0, "end")
        listbox.selection_set(index)
        listbox.activate(index)
        listbox.see(index)

    def _move(self, step: int) -> None:
        listbox = self._listbox
        if listbox is None or not self._rows:
            return
        current = listbox.curselection()
        index = int(current[0]) if current else -1
        for _ in range(len(self._rows)):
            index = (index + step) % len(self._rows)
            if getattr(self._rows[index], "kind", "") == "item":
                self._highlight(index)
                return

    def _highlighted_row(self):
        listbox = self._listbox
        if listbox is None or not self._popup_open() or not self._rows:
            return None
        current = listbox.curselection()
        if not current:
            return None
        index = int(current[0])
        if 0 <= index < len(self._rows):
            return self._rows[index]
        return None

    def _on_list_press(self, _event=None) -> None:
        self._cancel_hide()

    def _on_list_click(self, event) -> str:
        listbox = self._listbox
        if listbox is None:
            return "break"
        index = listbox.nearest(event.y)
        if 0 <= index < len(self._rows):
            row = self._rows[index]
            if getattr(row, "kind", "") == "item":
                self._apply_row(row)
        return "break"

    def _apply_row(self, row) -> None:
        self._hide_popup()
        self.on_pick(row)
