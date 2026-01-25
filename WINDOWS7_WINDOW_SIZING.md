# Window Sizing on Windows 7

## Overview

This document describes how the adaptive window sizing functionality works on Windows 7 and what to expect.

## Changes Made

### 1. Window Utilities (`npbackup/gui/window_utils.py`)

- **DPI Awareness**: Added automatic DPI awareness detection for Windows 7
  - Tries `SetProcessDpiAwareness(1)` for Windows 8.1+ (via shcore.dll)
  - Falls back to `SetProcessDPIAware()` for Windows 7 (via user32.dll)
  - Prevents DPI virtualization and ensures real pixel coordinates

- **Work Area Detection**: Uses Windows API `SystemParametersInfoW` with `SPI_GETWORKAREA`
  - Returns screen dimensions minus taskbar and other "always on top" panels
  - Fully compatible with Windows 7

### 2. Window Initialization Order

Updated initialization order in:
- `npbackup/gui/__main__.py` (main window)
- `npbackup/gui/config.py` (configuration window)
- `npbackup/gui/operations.py` (operations window)

**Order:**
1. Create window with `finalize=True`
2. Apply `.expand()` calls for adaptive elements
3. Call `window.read(timeout=0)` to render window
4. Call `fit_window_to_screen()` to resize if needed

## Expected Behavior on Windows 7

### Screen Size Detection

On Windows 7 with typical setup:
- **Full screen**: 1366x768, 1920x1080, etc.
- **Work area**: Full screen minus taskbar height (typically ~40 pixels)
  - Example: 1366x768 → work area 1366x728
- **Available size**: Work area minus window decorations margin

### Window Fitting

When a window opens:
1. Window is created with its natural/default size
2. If window size > available size:
   - Window is resized to fit within available area
   - Window is centered on screen
3. If window already fits: no changes made

### Minimum Supported Resolution

- **Target**: 750x500 (as specified in requirements)
- **Tested**: 640x480 minimum (with scrolling)
- **Recommended**: 800x600 or higher

## Testing on Windows 7

### Quick Test

Run the provided test script:

```cmd
python test_window_fitting_win7.py
```

This will:
- Display current screen dimensions
- Show work area information
- Open a test window that should fit on screen
- Allow manual testing of window resizing

### Expected Results

✅ Window opens fully visible (not cut off)  
✅ Window doesn't hide behind taskbar  
✅ Window can be resized manually  
✅ Content is accessible via scrollbars if needed  

### Full Application Test

1. Run NPBackup GUI:
   ```cmd
   npbackup-gui.exe
   ```

2. Check main window:
   - Should fit on screen on first open
   - All buttons visible at bottom
   - Snapshot list has scrollbar

3. Open Configuration window:
   - Should fit within available screen area
   - Tabs are scrollable
   - Bottom buttons (Cancel, Accept) always visible

4. Test on small resolution:
   ```cmd
   # Change to 800x600 in Display Settings
   npbackup-gui.exe
   ```
   - Windows should still fit
   - Content accessible via scrolling

## Known Limitations on Windows 7

### 1. DPI Scaling (125%, 150%)

- Windows 7 DPI scaling is less sophisticated than Windows 10+
- If using DPI scaling > 100%:
  - Window sizes are calculated in physical pixels
  - May appear slightly different than on Windows 10+
  - Should still fit on screen correctly

### 2. Multiple Monitors

- `get_work_area()` returns primary monitor work area
- If application opens on secondary monitor:
  - May need manual adjustment if monitors have different resolutions
  - Window will still be resizable

### 3. Taskbar Position

- Code assumes standard bottom taskbar
- If taskbar is on side/top:
  - Work area is still calculated correctly
  - Window fitting should work normally

## Compatibility Notes

### Python Version

- Requires Python 3.7+ (as per COMPATIBILITY.md)
- Python 3.7 is the last version fully supporting Windows 7

### Dependencies

- **FreeSimpleGUI 5.2.0**: Works on Windows 7
- **tkinter**: Included with Python on Windows
- **ctypes**: Standard library, fully supported on Windows 7

### Windows 7 EOL

- Windows 7 reached End of Life in January 2020
- Extended Security Updates ended January 2023
- Code maintains compatibility for legacy systems
- Tested with Windows 7 SP1

## Troubleshooting

### Issue: Window appears too large

**Cause**: DPI awareness not applied  
**Solution**: 
- Check if `get_work_area()` returns correct values
- Verify `SetProcessDPIAware()` is called (check logs)
- Try running as administrator

### Issue: Window appears off-screen

**Cause**: Multiple monitors or wrong screen detected  
**Solution**:
- Move window to primary monitor
- Restart application
- Check Windows display settings

### Issue: Content not scrollable

**Cause**: Scrollbars not initialized properly  
**Solution**:
- Resize window manually (triggers layout recalculation)
- Check if `expand_x=True, expand_y=True` are set
- Verify `window.read(timeout=0)` is called

## Summary

The adaptive window sizing functionality **should work correctly on Windows 7** with:

✅ Automatic DPI awareness  
✅ Work area detection (screen minus taskbar)  
✅ Window fitting on open  
✅ Resizable windows  
✅ Scrollable content  
✅ Support for resolutions down to 750x500  

The implementation uses only Windows 7-compatible APIs and has proper fallbacks for older systems.
