import ctypes
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import windows_cast


@pytest.fixture
def user32(monkeypatch):
    fake = SimpleNamespace(GetAsyncKeyState=Mock(return_value=0), SendInput=Mock(return_value=4))
    monkeypatch.setattr(windows_cast.sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: fake, raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 0, raising=False)
    monkeypatch.setattr(ctypes, "set_last_error", lambda _error: None, raising=False)
    return fake


def key_events(call):
    count, inputs, structure_size = call.args
    assert count == len(inputs)
    assert structure_size == ctypes.sizeof(windows_cast._Input)
    assert all(event.type == 1 for event in inputs)
    return [(event.data.keyboard.virtual_key, event.data.keyboard.flags) for event in inputs]


@pytest.mark.parametrize(
    ("action", "letter"),
    [(windows_cast.open_cast_panel, "K"), (windows_cast.open_project_panel, "P")],
)
def test_panels_use_windows_shortcuts(user32, action, letter):
    action()

    user32.SendInput.assert_called_once()
    assert key_events(user32.SendInput.call_args) == [
        (0x5B, 1), (ord(letter), 0), (ord(letter), 2), (0x5B, 3),
    ]


@pytest.mark.parametrize(
    ("accepted", "expected_release"),
    [(1, [(0x5B, 3)]), (2, [(ord("K"), 2), (0x5B, 3)]), (3, [(0x5B, 3)])],
)
def test_partial_shortcut_releases_pressed_keys(user32, accepted, expected_release):
    user32.SendInput.side_effect = [accepted, len(expected_release)]

    with pytest.raises(OSError, match=f"accepted {accepted} of 4"):
        windows_cast.open_cast_panel()

    assert key_events(user32.SendInput.call_args) == expected_release


def test_blocked_shortcut_reports_failure(user32):
    user32.SendInput.return_value = 0

    with pytest.raises(OSError, match="accepted 0 of 4"):
        windows_cast.open_cast_panel()

    user32.SendInput.assert_called_once()


def test_held_modifier_prevents_an_unintended_shortcut(user32):
    user32.GetAsyncKeyState.side_effect = lambda key: -32768 if key == 0x11 else 0

    with pytest.raises(OSError, match="Release"):
        windows_cast.open_project_panel()

    user32.SendInput.assert_not_called()


def test_other_platforms_report_unsupported(monkeypatch):
    monkeypatch.setattr(windows_cast.sys, "platform", "linux")

    with pytest.raises(OSError, match="require Windows"):
        windows_cast.open_cast_panel()


@pytest.mark.skipif(sys.platform != "win32", reason="Checks the native Win32 ctypes ABI")
def test_input_matches_windows_structure_size():
    expected_size = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28

    assert ctypes.sizeof(windows_cast._Input) == expected_size
