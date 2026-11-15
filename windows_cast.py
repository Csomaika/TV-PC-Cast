"""Open the Windows wireless display and projection panels from the GUI."""

import ctypes
import sys
from ctypes import wintypes


_INPUT_KEYBOARD = 1
_KEYEVENTF_EXTENDEDKEY = 0x0001
_KEYEVENTF_KEYUP = 0x0002
_VK_LWIN = 0x5B
_MODIFIER_KEYS = (0x10, 0x11, 0x12, _VK_LWIN, 0x5C)  # Shift, Ctrl, Alt, Win


class _KeyboardInput(ctypes.Structure):
    _fields_ = [
        ("virtual_key", wintypes.WORD),
        ("scan_code", wintypes.WORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("extra_info", ctypes.c_size_t),
    ]


class _MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouse_data", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("extra_info", ctypes.c_size_t),
    ]


class _HardwareInput(ctypes.Structure):
    _fields_ = [
        ("message", wintypes.DWORD),
        ("parameter_low", wintypes.WORD),
        ("parameter_high", wintypes.WORD),
    ]


class _InputData(ctypes.Union):
    _fields_ = [("keyboard", _KeyboardInput), ("mouse", _MouseInput), ("hardware", _HardwareInput)]


class _Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("data", _InputData)]


def _key_event(virtual_key, flags):
    return _Input(_INPUT_KEYBOARD, _InputData(keyboard=_KeyboardInput(virtual_key, 0, flags, 0, 0)))


def _send_windows_shortcut(virtual_key):
    if sys.platform != "win32":
        raise OSError("Windows keyboard shortcuts require Windows.")

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    key_state = user32.GetAsyncKeyState
    key_state.argtypes = (ctypes.c_int,)
    key_state.restype = ctypes.c_short
    if any(key_state(key) & 0x8000 for key in (*_MODIFIER_KEYS, virtual_key)):
        raise OSError("Release the shortcut keys and try again.")

    send_input = user32.SendInput
    send_input.argtypes = (wintypes.UINT, ctypes.POINTER(_Input), ctypes.c_int)
    send_input.restype = wintypes.UINT
    events = (_Input * 4)(
        _key_event(_VK_LWIN, _KEYEVENTF_EXTENDEDKEY),
        _key_event(virtual_key, 0),
        _key_event(virtual_key, _KEYEVENTF_KEYUP),
        _key_event(_VK_LWIN, _KEYEVENTF_EXTENDEDKEY | _KEYEVENTF_KEYUP),
    )
    input_size = ctypes.sizeof(_Input)
    ctypes.set_last_error(0)
    sent = send_input(len(events), events, input_size)
    if sent == len(events):
        return

    error_code = ctypes.get_last_error()
    if 0 < sent < len(events):
        # If Windows queued part of the sequence, release any keys we pressed.
        releases = events[2:] if sent == 2 else events[3:]
        send_input(len(releases), (_Input * len(releases))(*releases), input_size)
    if error_code:
        raise ctypes.WinError(error_code)
    raise OSError(f"Windows accepted {sent} of {len(events)} shortcut events.")


def open_cast_panel():
    """Request device discovery and connection controls using Windows + K."""
    _send_windows_shortcut(ord("K"))


def open_project_panel():
    """Request the Windows projection modes using Windows + P."""
    _send_windows_shortcut(ord("P"))
