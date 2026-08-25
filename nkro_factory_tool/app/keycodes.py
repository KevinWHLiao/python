"""Windows virtual-key names used by profiles and the on-screen layout."""

from __future__ import annotations

# name -> VK code
VK: dict[str, int] = {
    "LBUTTON": 0x01,
    "RBUTTON": 0x02,
    "CANCEL": 0x03,
    "MBUTTON": 0x04,
    "BACK": 0x08,
    "TAB": 0x09,
    "CLEAR": 0x0C,
    "RETURN": 0x0D,
    "SHIFT": 0x10,
    "CONTROL": 0x11,
    "MENU": 0x12,
    "PAUSE": 0x13,
    "CAPITAL": 0x14,
    "ESCAPE": 0x1B,
    "SPACE": 0x20,
    "PRIOR": 0x21,
    "NEXT": 0x22,
    "END": 0x23,
    "HOME": 0x24,
    "LEFT": 0x25,
    "UP": 0x26,
    "RIGHT": 0x27,
    "DOWN": 0x28,
    "SNAPSHOT": 0x2C,
    "INSERT": 0x2D,
    "DELETE": 0x2E,
    "0": 0x30,
    "1": 0x31,
    "2": 0x32,
    "3": 0x33,
    "4": 0x34,
    "5": 0x35,
    "6": 0x36,
    "7": 0x37,
    "8": 0x38,
    "9": 0x39,
    "A": 0x41,
    "B": 0x42,
    "C": 0x43,
    "D": 0x44,
    "E": 0x45,
    "F": 0x46,
    "G": 0x47,
    "H": 0x48,
    "I": 0x49,
    "J": 0x4A,
    "K": 0x4B,
    "L": 0x4C,
    "M": 0x4D,
    "N": 0x4E,
    "O": 0x4F,
    "P": 0x50,
    "Q": 0x51,
    "R": 0x52,
    "S": 0x53,
    "T": 0x54,
    "U": 0x55,
    "V": 0x56,
    "W": 0x57,
    "X": 0x58,
    "Y": 0x59,
    "Z": 0x5A,
    "LWIN": 0x5B,
    "RWIN": 0x5C,
    "APPS": 0x5D,
    "NUMPAD0": 0x60,
    "NUMPAD1": 0x61,
    "NUMPAD2": 0x62,
    "NUMPAD3": 0x63,
    "NUMPAD4": 0x64,
    "NUMPAD5": 0x65,
    "NUMPAD6": 0x66,
    "NUMPAD7": 0x67,
    "NUMPAD8": 0x68,
    "NUMPAD9": 0x69,
    "MULTIPLY": 0x6A,
    "ADD": 0x6B,
    "SEPARATOR": 0x6C,
    "SUBTRACT": 0x6D,
    "DECIMAL": 0x6E,
    "NUM_DECIMAL": 0x6E,
    "DIVIDE": 0x6F,
    "F1": 0x70,
    "F2": 0x71,
    "F3": 0x72,
    "F4": 0x73,
    "F5": 0x74,
    "F6": 0x75,
    "F7": 0x76,
    "F8": 0x77,
    "F9": 0x78,
    "F10": 0x79,
    "F11": 0x7A,
    "F12": 0x7B,
    "NUMLOCK": 0x90,
    "SCROLL": 0x91,
    "LSHIFT": 0xA0,
    "RSHIFT": 0xA1,
    "LCONTROL": 0xA2,
    "RCONTROL": 0xA3,
    "LMENU": 0xA4,
    "RMENU": 0xA5,
    "OEM_1": 0xBA,  # ; :
    "OEM_PLUS": 0xBB,
    "OEM_COMMA": 0xBC,
    "OEM_MINUS": 0xBD,
    "MINUS": 0xBD,
    "OEM_PERIOD": 0xBE,
    "PERIOD": 0xBE,
    "OEM_2": 0xBF,  # / ?
    "OEM_3": 0xC0,  # ` ~
    "OEM_4": 0xDB,  # [ {
    "OEM_5": 0xDC,  # \ |
    "OEM_6": 0xDD,  # ] }
    "OEM_7": 0xDE,  # ' "
}

# aliases used in profiles / display labels
ALIASES: dict[str, str] = {
    "[": "OEM_4",
    "]": "OEM_6",
    "-": "MINUS",
    "_": "MINUS",
    ".": "PERIOD",
    ">": "PERIOD",
    ";": "OEM_1",
    "'": "OEM_7",
    "`": "OEM_3",
    "\\": "OEM_5",
    "/": "OEM_2",
    "=": "OEM_PLUS",
    ",": "OEM_COMMA",
    "ENTER": "RETURN",
    "ESC": "ESCAPE",
    "CTRL": "CONTROL",
    "ALT": "MENU",
    "WIN": "LWIN",
    "DEL": "DELETE",
    "INS": "INSERT",
    "PGUP": "PRIOR",
    "PGDN": "NEXT",
    "NUM.": "NUM_DECIMAL",
    "NUM_DEL": "NUM_DECIMAL",
}

VK_TO_NAME: dict[int, str] = {}
for _name, _vk in VK.items():
    VK_TO_NAME.setdefault(_vk, _name)


def normalize_key_name(name: str) -> str:
    key = name.strip().upper()
    if key in ALIASES:
        key = ALIASES[key]
    if key not in VK:
        raise KeyError(f"Unknown key name: {name!r}")
    return key


def name_to_vk(name: str) -> int:
    return VK[normalize_key_name(name)]


def vk_to_name(vk: int) -> str:
    return VK_TO_NAME.get(vk & 0xFF, f"VK_{vk & 0xFF:02X}")


def names_to_vk_set(names: list[str]) -> set[int]:
    return {name_to_vk(n) for n in names}
