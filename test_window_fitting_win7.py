#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for window fitting on Windows 7
Run this on Windows 7 to verify window sizing works correctly
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeSimpleGUI as sg
from npbackup.gui.window_utils import (
    get_screen_size,
    get_work_area,
    get_available_size,
    fit_window_to_screen,
)


def main():
    """Test window fitting functionality"""
    print("Testing window fitting on Windows 7")
    print("=" * 50)
    
    # Get screen information
    screen_size = get_screen_size()
    work_area = get_work_area()
    available_size = get_available_size()
    
    print(f"Screen size: {screen_size}")
    print(f"Work area: {work_area}")
    print(f"Available size: {available_size}")
    print()
    
    # Test with a large window that should be resized
    layout = [
        [sg.Text("Testing Window Fitting", font=("Arial", 16))],
        [sg.Text("This window should fit within the available screen area")],
        [sg.Text("")],
        [sg.Text(f"Screen size: {screen_size}")],
        [sg.Text(f"Work area: {work_area}")],
        [sg.Text(f"Available size: {available_size}")],
        [sg.Text("")],
        [sg.Multiline(
            "This is a test window.\n\n"
            "If this window fits entirely on your screen without going\n"
            "behind the taskbar or off-screen, then the window fitting\n"
            "functionality is working correctly!\n\n"
            "Try resizing the window manually to test if resizing works.\n"
            "The window should be resizable.",
            size=(60, 15),
            disabled=True
        )],
        [sg.Button("Test fit_window_to_screen"), sg.Button("Close")],
    ]
    
    window = sg.Window(
        "Window Fitting Test - Windows 7",
        layout,
        resizable=True,
        finalize=True,
    )
    
    # Get initial window size
    window.read(timeout=0)
    initial_size = window.size
    print(f"Initial window size: {initial_size}")
    
    # Apply fit_window_to_screen
    fit_window_to_screen(window)
    
    # Get size after fitting
    window.read(timeout=0)
    fitted_size = window.size
    print(f"Fitted window size: {fitted_size}")
    
    if fitted_size != initial_size:
        print(f"Window was resized from {initial_size} to {fitted_size}")
    else:
        print("Window size unchanged (already fits)")
    
    print()
    print("Please verify:")
    print("1. The window is fully visible (not cut off)")
    print("2. The window is not hidden behind the taskbar")
    print("3. You can resize the window manually")
    print()
    
    # Event loop
    while True:
        event, values = window.read()
        
        if event in (sg.WIN_CLOSED, "Close"):
            break
        elif event == "Test fit_window_to_screen":
            window.read(timeout=0)
            before = window.size
            fit_window_to_screen(window)
            window.read(timeout=0)
            after = window.size
            print(f"Before: {before}, After: {after}")
            sg.popup(
                f"Window size:\nBefore: {before}\nAfter: {after}",
                title="Test Result"
            )
    
    window.close()
    print("\nTest completed successfully!")


if __name__ == "__main__":
    main()
