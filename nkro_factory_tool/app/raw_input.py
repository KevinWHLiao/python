"""Windows Raw Input keyboard capture with per-device filtering."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import queue
import threading
from dataclasses import dataclass
from typing import Callable

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_INPUT = 0x00FF
WM_DESTROY = 0x0002
WM_QUIT = 0x0012
WM_CLOSE = 0x0010
RID_INPUT = 0x10000003
RIDI_DEVICENAME = 0x20000007
RIDI_DEVICEINFO = 0x2000000B
RIM_TYPEKEYBOARD = 1
RIDEV_INPUTSINK = 0x00000100
RI_KEY_BREAK = 0x01
HWND_MESSAGE = wintypes.HWND(-3)

WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", wintypes.USHORT),
        ("usUsage", wintypes.USHORT),
        ("dwFlags", wintypes.DWORD),
        ("hwndTarget", wintypes.HWND),
    ]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [
        ("dwType", wintypes.DWORD),
        ("dwSize", wintypes.DWORD),
        ("hDevice", wintypes.HANDLE),
        ("wParam", wintypes.WPARAM),
    ]


class RAWKEYBOARD(ctypes.Structure):
    _fields_ = [
        ("MakeCode", wintypes.USHORT),
        ("Flags", wintypes.USHORT),
        ("Reserved", wintypes.USHORT),
        ("VKey", wintypes.USHORT),
        ("Message", wintypes.UINT),
        ("ExtraInformation", wintypes.ULONG),
    ]


class RAWINPUT(ctypes.Structure):
    class _DATA(ctypes.Union):
        _fields_ = [("keyboard", RAWKEYBOARD)]

    _anonymous_ = ("data",)
    _fields_ = [("header", RAWINPUTHEADER), ("data", _DATA)]


class RAWINPUTDEVICELIST(ctypes.Structure):
    _fields_ = [
        ("hDevice", wintypes.HANDLE),
        ("dwType", wintypes.DWORD),
    ]


class RID_DEVICE_INFO_KEYBOARD(ctypes.Structure):
    _fields_ = [
        ("dwType", wintypes.DWORD),
        ("dwSubType", wintypes.DWORD),
        ("dwKeyboardMode", wintypes.DWORD),
        ("dwNumberOfFunctionKeys", wintypes.DWORD),
        ("dwNumberOfIndicators", wintypes.DWORD),
        ("dwNumberOfKeysTotal", wintypes.DWORD),
    ]


class RID_DEVICE_INFO(ctypes.Structure):
    class _DATA(ctypes.Union):
        _fields_ = [("keyboard", RID_DEVICE_INFO_KEYBOARD)]

    _anonymous_ = ("data",)
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("dwType", wintypes.DWORD),
        ("data", _DATA),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DefWindowProcW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.GetMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
]
user32.GetMessageW.restype = ctypes.c_int
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.PostMessageW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.RegisterRawInputDevices.argtypes = [
    ctypes.POINTER(RAWINPUTDEVICE),
    wintypes.UINT,
    wintypes.UINT,
]
user32.RegisterRawInputDevices.restype = wintypes.BOOL
user32.GetRawInputData.argtypes = [
    wintypes.HANDLE,
    wintypes.UINT,
    wintypes.LPVOID,
    ctypes.POINTER(wintypes.UINT),
    wintypes.UINT,
]
user32.GetRawInputData.restype = wintypes.UINT
user32.GetRawInputDeviceList.argtypes = [
    ctypes.POINTER(RAWINPUTDEVICELIST),
    ctypes.POINTER(wintypes.UINT),
    wintypes.UINT,
]
user32.GetRawInputDeviceList.restype = wintypes.UINT
user32.GetRawInputDeviceInfoW.argtypes = [
    wintypes.HANDLE,
    wintypes.UINT,
    wintypes.LPVOID,
    ctypes.POINTER(wintypes.UINT),
]
user32.GetRawInputDeviceInfoW.restype = wintypes.UINT
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE


@dataclass(frozen=True)
class KeyboardDevice:
    handle: int
    name: str
    path: str

    @property
    def label(self) -> str:
        short = self.path
        if len(short) > 72:
            short = "..." + short[-69:]
        return f"{self.name} [{short}]"


@dataclass(frozen=True)
class KeyEvent:
    device_handle: int
    vk: int
    make_code: int
    is_keydown: bool
    flags: int


def list_keyboard_devices() -> list[KeyboardDevice]:
    count = wintypes.UINT(0)
    size = ctypes.sizeof(RAWINPUTDEVICELIST)
    if user32.GetRawInputDeviceList(None, ctypes.byref(count), size) == 0xFFFFFFFF:
        raise ctypes.WinError(ctypes.get_last_error())
    if count.value == 0:
        return []

    buf = (RAWINPUTDEVICELIST * count.value)()
    if user32.GetRawInputDeviceList(buf, ctypes.byref(count), size) == 0xFFFFFFFF:
        raise ctypes.WinError(ctypes.get_last_error())

    devices: list[KeyboardDevice] = []
    for entry in buf:
        if entry.dwType != RIM_TYPEKEYBOARD:
            continue
        path = _device_path(entry.hDevice)
        name = _friendly_name(path)
        devices.append(
            KeyboardDevice(
                handle=int(entry.hDevice),
                name=name,
                path=path,
            )
        )
    return devices


def _device_path(hdevice: wintypes.HANDLE) -> str:
    needed = wintypes.UINT(0)
    user32.GetRawInputDeviceInfoW(hdevice, RIDI_DEVICENAME, None, ctypes.byref(needed))
    if needed.value == 0:
        return ""
    buf = ctypes.create_unicode_buffer(needed.value)
    if user32.GetRawInputDeviceInfoW(hdevice, RIDI_DEVICENAME, buf, ctypes.byref(needed)) <= 0:
        return ""
    return buf.value


def _friendly_name(path: str) -> str:
    if not path:
        return "Keyboard"
    upper = path.upper()
    if "ROOT\\RDP_KBD" in upper or "TERMINAL_SERVER" in upper:
        return "Remote Desktop Keyboard"
    if "HID#" in upper or "HID\\" in upper:
        return "HID Keyboard"
    if "ACPI" in upper or "KBD" in upper:
        return "Built-in / PS2 Keyboard"
    return "Keyboard"


class RawInputListener:
    """Background message-only window that enqueues keyboard Raw Input events."""

    def __init__(self) -> None:
        self._queue: queue.Queue[KeyEvent] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._hwnd: int | None = None
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self._wndproc = None  # keep reference alive

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._ready.clear()
        self._error = None
        self._thread = threading.Thread(target=self._thread_main, name="RawInput", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5.0):
            raise RuntimeError("Raw Input listener failed to start")
        if self._error:
            raise RuntimeError(f"Raw Input listener error: {self._error}") from self._error

    def stop(self) -> None:
        hwnd = self._hwnd
        if hwnd:
            user32.PostMessageW(wintypes.HWND(hwnd), WM_CLOSE, 0, 0)
        if self._thread:
            self._thread.join(timeout=2.0)
        self._thread = None
        self._hwnd = None

    def drain(self) -> list[KeyEvent]:
        events: list[KeyEvent] = []
        while True:
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return events

    def poll(self, callback: Callable[[KeyEvent], None]) -> None:
        for event in self.drain():
            callback(event)

    def _thread_main(self) -> None:
        try:
            self._run_message_loop()
        except BaseException as exc:  # noqa: BLE001 — surface to starter
            self._error = exc
            self._ready.set()

    def _run_message_loop(self) -> None:
        class_name = f"NKRORawInputWnd_{id(self)}"
        hinstance = kernel32.GetModuleHandleW(None)

        def _wndproc(hwnd, msg, wparam, lparam):
            if msg == WM_INPUT:
                self._handle_input(lparam)
                return 0
            if msg == WM_CLOSE:
                user32.DestroyWindow(hwnd)
                return 0
            if msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc = WNDPROC(_wndproc)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = hinstance
        wc.lpszClassName = class_name
        atom = user32.RegisterClassW(ctypes.byref(wc))
        if not atom:
            err = ctypes.get_last_error()
            # class may already exist from previous run in same process
            if err not in (0, 1410):  # ERROR_CLASS_ALREADY_EXISTS
                raise ctypes.WinError(err)

        hwnd = user32.CreateWindowExW(
            0,
            class_name,
            "NKRO Raw Input",
            0,
            0,
            0,
            0,
            0,
            HWND_MESSAGE,
            None,
            hinstance,
            None,
        )
        if not hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self._hwnd = int(hwnd)

        rid = RAWINPUTDEVICE()
        rid.usUsagePage = 0x01  # generic desktop
        rid.usUsage = 0x06  # keyboard
        rid.dwFlags = RIDEV_INPUTSINK
        rid.hwndTarget = hwnd
        if not user32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(rid)):
            raise ctypes.WinError(ctypes.get_last_error())

        self._ready.set()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _handle_input(self, lparam: int) -> None:
        dw_size = wintypes.UINT(0)
        header_size = ctypes.sizeof(RAWINPUTHEADER)
        user32.GetRawInputData(
            wintypes.HANDLE(lparam),
            RID_INPUT,
            None,
            ctypes.byref(dw_size),
            header_size,
        )
        if dw_size.value == 0:
            return
        buf = ctypes.create_string_buffer(dw_size.value)
        result = user32.GetRawInputData(
            wintypes.HANDLE(lparam),
            RID_INPUT,
            buf,
            ctypes.byref(dw_size),
            header_size,
        )
        if result == 0xFFFFFFFF or result == 0:
            return
        raw = ctypes.cast(buf, ctypes.POINTER(RAWINPUT)).contents
        if raw.header.dwType != RIM_TYPEKEYBOARD:
            return
        kb = raw.keyboard
        vk = int(kb.VKey) & 0xFF
        if vk == 0 or vk == 0xFF:
            return
        is_down = (kb.Flags & RI_KEY_BREAK) == 0
        self._queue.put(
            KeyEvent(
                device_handle=int(raw.header.hDevice),
                vk=vk,
                make_code=int(kb.MakeCode),
                is_keydown=is_down,
                flags=int(kb.Flags),
            )
        )
