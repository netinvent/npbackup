# -*- coding: utf-8 -*-
#
# Window size utilities for small screens
# Ensures windows fit within screen bounds with proper margins

import os
import FreeSimpleGUI as sg
from typing import Tuple, Optional

# Fallback margin for window decorations (used if system method fails)
FALLBACK_MARGIN = 60


def get_work_area() -> Optional[Tuple[int, int]]:
    """
    Get work area size (screen minus taskbar) using OS-specific methods.
    Returns None if not available.
    """
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", wintypes.LONG),
                    ("top", wintypes.LONG),
                    ("right", wintypes.LONG),
                    ("bottom", wintypes.LONG),
                ]

            rect = RECT()
            # SPI_GETWORKAREA = 0x0030
            ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            if width > 0 and height > 0:
                return width, height
        except Exception:
            pass
    return None


def get_screen_size() -> Tuple[int, int]:
    """Get screen dimensions."""
    try:
        # Create a small temporary window to get screen size
        temp_window = sg.Window(
            "", [[]], alpha_channel=0, finalize=True, no_titlebar=True, size=(50, 50)
        )
        screen_width, screen_height = temp_window.get_screen_size()
        temp_window.close()
        return screen_width, screen_height
    except Exception:
        # Fallback to minimum supported resolution
        return 1024, 768


def get_available_size(margin: int = 0) -> Tuple[int, int]:
    """
    Get available window size accounting for decorations and taskbar.
    Uses OS work area if available, otherwise falls back to screen size minus margin.

    Args:
        margin: Additional pixels to subtract for window decorations

    Returns:
        Tuple of (width, height) in pixels
    """
    # Try OS-specific work area first (excludes taskbar)
    work_area = get_work_area()
    if work_area:
        return work_area[0] - margin, work_area[1] - margin

    # Fallback: full screen minus default margin
    screen_width, screen_height = get_screen_size()
    return screen_width - FALLBACK_MARGIN - margin, screen_height - FALLBACK_MARGIN - margin


def fit_window_to_screen(
    window: sg.Window,
    margin: int = 0,
    center: bool = True
) -> None:
    """
    Resize window to fit within screen bounds if it's too large.
    Should be called after window.finalize() or window.read(timeout=0).

    Args:
        window: The window to resize
        margin: Pixels margin for decorations
        center: Whether to center the window after resizing
    """
    try:
        available_width, available_height = get_available_size(margin)
        current_size = window.size

        if current_size is None:
            return

        current_width, current_height = current_size

        new_width = min(current_width, available_width)
        new_height = min(current_height, available_height)

        if new_width < current_width or new_height < current_height:
            window.set_size((new_width, new_height))
            if center:
                center_window(window)
    except Exception:
        # Silently fail - window sizing is not critical
        pass


def center_window(window: sg.Window) -> None:
    """Center window on screen."""
    try:
        screen_width, screen_height = get_screen_size()
        window_size = window.size
        if window_size:
            win_width, win_height = window_size
            x = (screen_width - win_width) // 2
            y = (screen_height - win_height) // 2
            window.move(x, y)
    except Exception:
        pass


def make_scrollable_layout(
    layout: list,
    max_size: Optional[Tuple[int, int]] = None,
    margin: int = 0
) -> list:
    """
    Wrap layout in a scrollable column if it would exceed screen size.

    Args:
        layout: The original layout
        max_size: Maximum size (width, height) or None to use screen size
        margin: Margin for decorations

    Returns:
        Layout wrapped in scrollable Column if needed, otherwise original layout
    """
    if max_size is None:
        max_size = get_available_size(margin)

    max_width, max_height = max_size

    # Wrap in scrollable column with size limit
    scrollable_layout = [
        [
            sg.Column(
                layout,
                scrollable=True,
                vertical_scroll_only=False,
                size=(max_width, max_height),
                expand_x=True,
                expand_y=True,
            )
        ]
    ]

    return scrollable_layout
