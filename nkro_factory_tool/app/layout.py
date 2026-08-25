"""Full-size US keyboard layout geometry for the on-screen map."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KeyGeom:
    name: str
    label: str
    x: float
    y: float
    w: float = 1.0
    h: float = 1.0


# Unit grid: 1.0 = standard key width. Rows from top.
FULLSIZE_US: list[KeyGeom] = [
    # Function row
    KeyGeom("ESCAPE", "Esc", 0, 0, 1.0),
    KeyGeom("F1", "F1", 2.0, 0),
    KeyGeom("F2", "F2", 3.0, 0),
    KeyGeom("F3", "F3", 4.0, 0),
    KeyGeom("F4", "F4", 5.0, 0),
    KeyGeom("F5", "F5", 6.5, 0),
    KeyGeom("F6", "F6", 7.5, 0),
    KeyGeom("F7", "F7", 8.5, 0),
    KeyGeom("F8", "F8", 9.5, 0),
    KeyGeom("F9", "F9", 11.0, 0),
    KeyGeom("F10", "F10", 12.0, 0),
    KeyGeom("F11", "F11", 13.0, 0),
    KeyGeom("F12", "F12", 14.0, 0),
    KeyGeom("SNAPSHOT", "Prt", 15.5, 0),
    KeyGeom("SCROLL", "Scr", 16.5, 0),
    KeyGeom("PAUSE", "Pse", 17.5, 0),
    # Number row
    KeyGeom("OEM_3", "`", 0, 1.5),
    KeyGeom("1", "1", 1, 1.5),
    KeyGeom("2", "2", 2, 1.5),
    KeyGeom("3", "3", 3, 1.5),
    KeyGeom("4", "4", 4, 1.5),
    KeyGeom("5", "5", 5, 1.5),
    KeyGeom("6", "6", 6, 1.5),
    KeyGeom("7", "7", 7, 1.5),
    KeyGeom("8", "8", 8, 1.5),
    KeyGeom("9", "9", 9, 1.5),
    KeyGeom("0", "0", 10, 1.5),
    KeyGeom("OEM_MINUS", "-", 11, 1.5),
    KeyGeom("OEM_PLUS", "=", 12, 1.5),
    KeyGeom("BACK", "Bksp", 13, 1.5, 2.0),
    KeyGeom("INSERT", "Ins", 15.5, 1.5),
    KeyGeom("HOME", "Hm", 16.5, 1.5),
    KeyGeom("PRIOR", "Pu", 17.5, 1.5),
    KeyGeom("NUMLOCK", "Num", 19.0, 1.5),
    KeyGeom("DIVIDE", "/", 20.0, 1.5),
    KeyGeom("MULTIPLY", "*", 21.0, 1.5),
    KeyGeom("SUBTRACT", "-", 22.0, 1.5),
    # Q row
    KeyGeom("TAB", "Tab", 0, 2.5, 1.5),
    KeyGeom("Q", "Q", 1.5, 2.5),
    KeyGeom("W", "W", 2.5, 2.5),
    KeyGeom("E", "E", 3.5, 2.5),
    KeyGeom("R", "R", 4.5, 2.5),
    KeyGeom("T", "T", 5.5, 2.5),
    KeyGeom("Y", "Y", 6.5, 2.5),
    KeyGeom("U", "U", 7.5, 2.5),
    KeyGeom("I", "I", 8.5, 2.5),
    KeyGeom("O", "O", 9.5, 2.5),
    KeyGeom("P", "P", 10.5, 2.5),
    KeyGeom("OEM_4", "[", 11.5, 2.5),
    KeyGeom("OEM_6", "]", 12.5, 2.5),
    KeyGeom("OEM_5", "\\", 13.5, 2.5, 1.5),
    KeyGeom("DELETE", "Del", 15.5, 2.5),
    KeyGeom("END", "End", 16.5, 2.5),
    KeyGeom("NEXT", "Pd", 17.5, 2.5),
    KeyGeom("NUMPAD7", "7", 19.0, 2.5),
    KeyGeom("NUMPAD8", "8", 20.0, 2.5),
    KeyGeom("NUMPAD9", "9", 21.0, 2.5),
    KeyGeom("ADD", "+", 22.0, 2.5, 1.0, 2.0),
    # A row
    KeyGeom("CAPITAL", "Caps", 0, 3.5, 1.75),
    KeyGeom("A", "A", 1.75, 3.5),
    KeyGeom("S", "S", 2.75, 3.5),
    KeyGeom("D", "D", 3.75, 3.5),
    KeyGeom("F", "F", 4.75, 3.5),
    KeyGeom("G", "G", 5.75, 3.5),
    KeyGeom("H", "H", 6.75, 3.5),
    KeyGeom("J", "J", 7.75, 3.5),
    KeyGeom("K", "K", 8.75, 3.5),
    KeyGeom("L", "L", 9.75, 3.5),
    KeyGeom("OEM_1", ";", 10.75, 3.5),
    KeyGeom("OEM_7", "'", 11.75, 3.5),
    KeyGeom("RETURN", "Enter", 12.75, 3.5, 2.25),
    KeyGeom("NUMPAD4", "4", 19.0, 3.5),
    KeyGeom("NUMPAD5", "5", 20.0, 3.5),
    KeyGeom("NUMPAD6", "6", 21.0, 3.5),
    # Z row
    KeyGeom("LSHIFT", "Shift", 0, 4.5, 2.25),
    KeyGeom("Z", "Z", 2.25, 4.5),
    KeyGeom("X", "X", 3.25, 4.5),
    KeyGeom("C", "C", 4.25, 4.5),
    KeyGeom("V", "V", 5.25, 4.5),
    KeyGeom("B", "B", 6.25, 4.5),
    KeyGeom("N", "N", 7.25, 4.5),
    KeyGeom("M", "M", 8.25, 4.5),
    KeyGeom("OEM_COMMA", ",", 9.25, 4.5),
    KeyGeom("OEM_PERIOD", ".", 10.25, 4.5),
    KeyGeom("OEM_2", "/", 11.25, 4.5),
    KeyGeom("RSHIFT", "Shift", 12.25, 4.5, 2.75),
    KeyGeom("UP", "↑", 16.5, 4.5),
    KeyGeom("NUMPAD1", "1", 19.0, 4.5),
    KeyGeom("NUMPAD2", "2", 20.0, 4.5),
    KeyGeom("NUMPAD3", "3", 21.0, 4.5),
    # Bottom
    KeyGeom("LCONTROL", "Ctrl", 0, 5.5, 1.25),
    KeyGeom("LWIN", "Win", 1.25, 5.5, 1.25),
    KeyGeom("LMENU", "Alt", 2.5, 5.5, 1.25),
    KeyGeom("SPACE", "Space", 3.75, 5.5, 6.25),
    KeyGeom("RMENU", "Alt", 10.0, 5.5, 1.25),
    KeyGeom("RWIN", "Win", 11.25, 5.5, 1.25),
    KeyGeom("APPS", "Menu", 12.5, 5.5, 1.25),
    KeyGeom("RCONTROL", "Ctrl", 13.75, 5.5, 1.25),
    KeyGeom("LEFT", "←", 15.5, 5.5),
    KeyGeom("DOWN", "↓", 16.5, 5.5),
    KeyGeom("RIGHT", "→", 17.5, 5.5),
    KeyGeom("NUMPAD0", "0", 19.0, 5.5, 2.0),
    KeyGeom("NUM_DECIMAL", ".", 21.0, 5.5),
]


def layout_for(name: str) -> list[KeyGeom]:
    if name == "fullsize_us":
        return FULLSIZE_US
    raise KeyError(f"Unknown layout: {name}")
