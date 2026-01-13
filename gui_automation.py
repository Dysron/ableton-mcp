"""
GUI automation for Ableton Live export dialog.

Uses AppleScript on macOS, PyAutoGUI as fallback.
"""

import subprocess
import time
import platform
from pathlib import Path
from typing import Optional

# Dialog window name constants
SAFE_DIALOG_WINDOWS = frozenset(["Save", "Export Audio/Video", "Export"])
EXPORT_DIALOG_PREFIX = "Export"
SAVE_DIALOG_NAME = "Save"

# Filename sanitization
INVALID_FILENAME_CHARS = '<>:"/\\|?*'


class ExportError(Exception):
    """Raised when export automation fails."""
    pass


class DialogVerificationError(ExportError):
    """Raised when dialog verification fails."""
    pass


class AbletonActivationError(ExportError):
    """Raised when Ableton cannot be activated."""
    pass


def run_applescript(script: str) -> tuple[bool, str]:
    """
    Run an AppleScript and return success status and output.
    """
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0, result.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except subprocess.SubprocessError as e:
        return False, f"Subprocess error: {e}"
    except OSError as e:
        return False, f"OS error: {e}"


def activate_ableton() -> bool:
    """Bring Ableton Live to the foreground."""
    script = '''
    tell application "Ableton Live 12 Suite"
        activate
    end tell
    delay 0.5
    '''
    success, _ = run_applescript(script)
    return success


def open_export_dialog() -> bool:
    """
    Open the Export Audio/Video dialog using Cmd+Shift+R.
    """
    script = '''
    tell application "Ableton Live 12 Suite" to activate
    delay 0.5
    tell application "System Events"
        tell process "Live"
            keystroke "r" using {shift down, command down}
        end tell
    end tell
    delay 1.5
    '''
    success, _ = run_applescript(script)
    return success


def wait_for_export_dialog(timeout: float = 5.0) -> bool:
    """
    Wait for the export dialog to appear.

    Note: Ableton uses non-native windows, so dialogs appear as window ""
    """
    script = f'''
    set maxWait to {timeout}
    set waited to 0
    tell application "System Events"
        repeat while waited < maxWait
            if (exists window "" of application process "Live") then
                return true
            end if
            delay 0.5
            set waited to waited + 0.5
        end repeat
    end tell
    return false
    '''
    success, output = run_applescript(script)
    return success and output == "true"


def close_dialog_with_escape() -> bool:
    """Close any open dialog with Escape key."""
    script = '''
    tell application "System Events"
        key code 53
    end tell
    delay 0.3
    '''
    success, _ = run_applescript(script)
    return success


def press_enter() -> bool:
    """Press Enter to confirm dialog."""
    script = '''
    tell application "System Events"
        keystroke return
    end tell
    '''
    success, _ = run_applescript(script)
    return success


def press_tab(count: int = 1) -> bool:
    """Press Tab key to navigate dialog."""
    script = f'''
    tell application "System Events"
        repeat {count} times
            keystroke tab
            delay 0.1
        end repeat
    end tell
    '''
    success, _ = run_applescript(script)
    return success


def press_down_arrow(count: int = 1) -> bool:
    """Press Down arrow key."""
    script = f'''
    tell application "System Events"
        repeat {count} times
            key code 125
            delay 0.1
        end repeat
    end tell
    '''
    success, _ = run_applescript(script)
    return success


def press_space() -> bool:
    """Press Space to toggle checkbox or activate button."""
    script = '''
    tell application "System Events"
        keystroke space
    end tell
    '''
    success, _ = run_applescript(script)
    return success


def type_text(text: str) -> bool:
    """Type text into the focused field."""
    # Escape special characters for AppleScript
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
    tell application "System Events"
        keystroke "{escaped}"
    end tell
    '''
    success, _ = run_applescript(script)
    return success


def select_all_and_delete() -> bool:
    """
    DANGEROUS - DO NOT USE. Kept for reference only.

    This function can delete all tracks if focus is on the arrangement.
    Use select_text_in_field() instead.
    """
    raise RuntimeError(
        "select_all_and_delete() is disabled - it can delete tracks. "
        "Use select_text_in_field() instead."
    )


def select_text_in_field() -> bool:
    """
    Safely select text in a text field, only if we're in a safe dialog.

    Verifies we're in a Save/Export dialog before using Cmd+A.
    Aborts with error if not in a safe context.
    """
    script = '''
    tell application "System Events"
        tell process "Live"
            -- Use Cmd+A only if we're in a Save dialog window
            set frontWindow to name of front window
            if frontWindow is "Save" or frontWindow contains "Export" then
                keystroke "a" using {command down}
                delay 0.1
            else
                -- SAFETY: Not in a dialog, do NOT use Cmd+A
                error "Not in a safe dialog window - aborting to prevent track deletion"
            end if
        end tell
    end tell
    '''
    success, _ = run_applescript(script)
    return success


def verify_in_dialog() -> tuple[bool, str]:
    """
    Verify we're in a dialog window before performing potentially dangerous operations.

    Returns:
        (is_safe, window_name) - True if in a safe dialog, False otherwise
    """
    script = '''
    tell application "System Events"
        tell process "Live"
            set frontWindow to name of front window
            return frontWindow
        end tell
    end tell
    '''
    success, window_name = run_applescript(script)

    is_safe = any(safe in window_name for safe in SAFE_DIALOG_WINDOWS)

    return is_safe, window_name


def set_file_save_location(path: Path) -> bool:
    """
    In a save dialog, navigate to the specified folder.

    Uses Cmd+Shift+G to open "Go to folder" dialog.
    """
    script = f'''
    tell application "System Events"
        -- Open Go to Folder dialog
        keystroke "g" using {{shift down, command down}}
        delay 0.5

        -- Type the path
        keystroke "{path}"
        delay 0.3

        -- Press Enter to go to folder
        keystroke return
        delay 0.5
    end tell
    '''
    success, _ = run_applescript(script)
    return success


class AbletonExportAutomation:
    """
    Handles GUI automation for exporting tracks from Ableton Live.
    """

    def __init__(self, output_folder: Path):
        self.output_folder = Path(output_folder)
        self.output_folder.mkdir(parents=True, exist_ok=True)

        if platform.system() != "Darwin":
            raise RuntimeError("This automation only works on macOS")

    def export_track(
        self,
        track_name: str,
        filename: Optional[str] = None,
        wait_for_completion: bool = True,
        export_timeout: float = 60.0,
    ) -> bool:
        """
        Export the currently selected track.

        The track should already be selected via OSC before calling this.

        Args:
            track_name: Name of the track (for filename)
            filename: Override filename (default: sanitized track name)
            wait_for_completion: Whether to wait for export to finish
            export_timeout: Max seconds to wait for export

        Returns:
            True if export was triggered successfully
        """
        if filename is None:
            # Sanitize track name for filename
            filename = self._sanitize_filename(track_name)

        print(f"  Exporting: {track_name} -> {filename}.wav")

        # Activate Ableton
        if not activate_ableton():
            print("    ERROR: Could not activate Ableton Live")
            return False

        time.sleep(0.3)

        # Open export dialog
        if not open_export_dialog():
            print("    ERROR: Could not open export dialog")
            return False

        time.sleep(1.5)

        # The export dialog should now be open
        # We need to:
        # 1. Ensure "Selected Tracks Only" is chosen (may need Tab navigation)
        # 2. Press Export button
        # 3. Handle the file save dialog

        # For now, just press Enter to accept defaults
        # This assumes the user has configured their export settings
        if not press_enter():
            print("    ERROR: Could not press Enter")
            return False

        time.sleep(0.5)

        # File save dialog should appear
        # Navigate to output folder and set filename
        if not self._handle_save_dialog(filename):
            print("    WARNING: Could not set save location, using default")

        # Press Enter to save
        time.sleep(0.3)
        press_enter()

        if wait_for_completion:
            # Wait for export to complete
            # The dialog closes when done, but we can't easily detect this
            # For now, just wait a reasonable time based on expected length
            print(f"    Waiting for export (max {export_timeout}s)...")
            time.sleep(min(export_timeout, 10))  # Simple wait for now

        return True

    def _handle_save_dialog(self, filename: str) -> bool:
        """Handle the file save dialog."""
        time.sleep(0.5)

        # Go to output folder
        set_file_save_location(self.output_folder)
        time.sleep(0.5)

        # Use safe filename typing (verifies we're in Save dialog)
        _type_filename_in_save_dialog(filename)

        return True

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize a string for use as filename."""
        # Remove/replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        result = name
        for char in invalid_chars:
            result = result.replace(char, "_")
        return result.strip()


def set_export_render_range(start_bar: int, length_bars: int) -> tuple[bool, str]:
    """
    Set the Render Start and Render Length in the Export dialog.

    This function must be called when the Export Audio/Video dialog is already open.
    Uses click-and-type approach since direct slider value setting doesn't work
    in Ableton's custom UI.

    Args:
        start_bar: Bar number to start rendering (1-indexed, e.g., 1 for beginning)
        length_bars: Number of bars to render

    Returns:
        (success, message) tuple
    """
    # Verify we're in the Export dialog
    is_safe, window_name = verify_in_dialog()
    if EXPORT_DIALOG_PREFIX not in window_name:
        return False, f"Not in Export dialog (found: {window_name})"

    # Use click-and-type approach since direct slider setting doesn't work
    return _set_render_range_via_clicks(start_bar, length_bars)


def _set_render_range_via_clicks(start_bar: int, length_bars: int) -> tuple[bool, str]:
    """
    Set render range using click and type approach.

    This mimics user interaction which is more reliable than direct value setting.
    Uses proper triple-click with click state for reliable text selection.
    """
    try:
        from Quartz import (
            CGEventCreateMouseEvent, CGEventPost, CGEventSetIntegerValueField,
            kCGEventMouseMoved, kCGEventLeftMouseDown, kCGEventLeftMouseUp,
            kCGHIDEventTap, kCGMouseEventClickState
        )
    except ImportError:
        return False, "Quartz module not available"

    def triple_click(x: float, y: float):
        """Triple-click with proper click state for text selection."""
        # Move mouse to position first
        move = CGEventCreateMouseEvent(None, kCGEventMouseMoved, (x, y), 0)
        CGEventPost(kCGHIDEventTap, move)
        time.sleep(0.05)

        # Three clicks with incrementing click state
        for click_num in range(1, 4):
            down = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, (x, y), 0)
            CGEventSetIntegerValueField(down, kCGMouseEventClickState, click_num)
            CGEventPost(kCGHIDEventTap, down)
            time.sleep(0.02)
            up = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, (x, y), 0)
            CGEventSetIntegerValueField(up, kCGMouseEventClickState, click_num)
            CGEventPost(kCGHIDEventTap, up)
            time.sleep(0.02)
        time.sleep(0.1)

    # Get slider 4 position (Render Length bar) - using cleaner AppleScript
    script = '''
    tell application "System Events"
        tell process "Live"
            tell front window
                tell group 1
                    set p to position of slider 4
                    set s to size of slider 4
                    set result to ((item 1 of p) as string) & "," & ((item 2 of p) as string)
                    set result to result & "," & ((item 1 of s) as string) & "," & ((item 2 of s) as string)
                    return result
                end tell
            end tell
        end tell
    end tell
    '''
    success, result = run_applescript(script)

    if success and result:
        try:
            parts = result.split(',')
            sl4_x = float(parts[0])
            sl4_y = float(parts[1])
            sl4_w = float(parts[2])
            sl4_h = float(parts[3])
            render_length_x = sl4_x + sl4_w / 2
            render_length_y = sl4_y + sl4_h / 2
        except (ValueError, IndexError):
            render_length_x, render_length_y = 1032, 334
    else:
        render_length_x, render_length_y = 1032, 334

    # Set Render Length bar only (start bar is usually correct at 1)
    # Step 1: Triple-click to select field
    triple_click(render_length_x, render_length_y)
    time.sleep(0.3)

    # Step 2: Cmd+A to select all content in the field
    select_all_script = '''
    tell application "System Events"
        keystroke "a" using command down
    end tell
    '''
    run_applescript(select_all_script)
    time.sleep(0.2)

    # Step 3: Type the new value
    type_text(str(length_bars))
    time.sleep(0.2)

    # Step 4: Press Tab to CONFIRM the value (NOT Return - Return triggers Export!)
    press_tab()
    time.sleep(0.3)  # Wait for UI to commit the value

    # Verify the value was set correctly
    verify_script = '''
    tell application "System Events"
        tell process "Live"
            tell front window
                tell group 1
                    set s4 to value of slider 4
                    return (s4 as string)
                end tell
            end tell
        end tell
    end tell
    '''
    success, result = run_applescript(verify_script)

    if success and result:
        try:
            verified_length = float(result)
            if abs(verified_length - length_bars) < 0.5:
                return True, f"Set render length: {verified_length:.0f} bars"
            else:
                return False, f"Value not set correctly: expected {length_bars}, got {verified_length}"
        except ValueError:
            pass

    return True, f"Set render length (unverified): {length_bars} bars"


def trigger_export_simple() -> bool:
    """
    Simple export trigger - just opens dialog and presses Enter.

    For testing purposes.
    """
    activate_ableton()
    time.sleep(0.5)
    open_export_dialog()
    time.sleep(2)
    press_enter()
    return True


def _activate_and_verify(max_retries: int = 5) -> None:
    """Activate Ableton and verify it's frontmost. Raises on failure."""
    for attempt in range(max_retries):
        if not activate_ableton():
            raise AbletonActivationError("Failed to activate Ableton Live")
        time.sleep(0.8)

        is_frontmost, app_name = _check_frontmost_app()
        if is_frontmost:
            return  # Success

        if attempt < max_retries - 1:
            print(f"  Retry {attempt + 1}: Ableton not frontmost (found: {app_name}), retrying...")
            time.sleep(0.5)

    # Skip strict check - dialog verification provides safety
    print(f"  Warning: Proceeding despite {app_name} being frontmost - dialog verification will catch errors")


def _open_and_verify_export_dialog() -> None:
    """Open export dialog and verify it appeared. Raises on failure."""
    if not open_export_dialog():
        raise DialogVerificationError("Failed to open export dialog")
    time.sleep(1.5)

    _, window_name = verify_in_dialog()
    if EXPORT_DIALOG_PREFIX not in window_name:
        _abort_and_escape()
        raise DialogVerificationError(f"Expected Export dialog, found: '{window_name}'")


def _click_export_and_verify_save_dialog() -> None:
    """Click Export button and verify Save dialog appears. Raises on failure."""
    press_enter()
    time.sleep(1.0)

    _, window_name = verify_in_dialog()
    if SAVE_DIALOG_NAME not in window_name:
        _abort_and_escape()
        raise DialogVerificationError(f"Expected Save dialog, found: '{window_name}'")


def _wait_for_export_completion(max_wait: int = 120) -> None:
    """Wait for export to complete. Raises on timeout."""
    waited = 0
    while waited < max_wait:
        time.sleep(1.0)
        waited += 1
        _, window_name = verify_in_dialog()

        if SAVE_DIALOG_NAME in window_name:
            raise ExportError(f"Save dialog still open after {waited}s - export may have failed")

        if EXPORT_DIALOG_PREFIX not in window_name:
            return  # Export complete

        if waited % 10 == 0:
            print(f"  Exporting... {waited}s")

    _, window_name = verify_in_dialog()
    if SAVE_DIALOG_NAME in window_name or EXPORT_DIALOG_PREFIX in window_name:
        raise ExportError(f"Export timed out after {max_wait}s - dialog: '{window_name}'")


def safe_export_with_filename(filename: str, output_folder: Optional[str] = None) -> tuple[bool, str]:
    """
    Safely export with full verification at each step.

    This function verifies the window state before each action to prevent
    accidental track deletion or other destructive operations.

    Args:
        filename: The filename to save (without extension)
        output_folder: Optional folder path to save to

    Returns:
        (success, message) tuple
    """
    try:
        # Step 1-2: Activate Ableton and verify
        _activate_and_verify()

        # Step 3-4: Open export dialog and verify
        _open_and_verify_export_dialog()

        # Step 5-6: Click Export and check what dialog appears
        press_enter()
        time.sleep(1.0)

        _, window_name = verify_in_dialog()

        # Ableton Live 12 may show Save dialog OR export directly
        if SAVE_DIALOG_NAME in window_name:
            # Traditional workflow with Save dialog
            if output_folder:
                set_file_save_location(Path(output_folder))
                time.sleep(0.5)

            _type_filename_in_save_dialog(filename)
            time.sleep(0.3)
            press_enter()
            _wait_for_export_completion()

        elif EXPORT_DIALOG_PREFIX not in window_name:
            # Export started directly (no Save dialog in Live 12)
            # Just wait for export to complete
            _wait_for_export_completion_live12(max_wait=120)

        else:
            # Still in Export dialog - might need to handle confirmation
            _handle_export_confirmation_and_wait()

        return True, f"Export complete: {filename}.wav"

    except (AbletonActivationError, DialogVerificationError, ExportError) as e:
        _abort_and_escape()
        return False, str(e)
    except subprocess.SubprocessError as e:
        _abort_and_escape()
        return False, f"Subprocess error: {e}"
    except OSError as e:
        _abort_and_escape()
        return False, f"OS error: {e}"


def _handle_export_confirmation_and_wait() -> None:
    """Handle any confirmation dialog and wait for export completion."""
    # Check for "stop audio" confirmation
    script = '''
    tell application "System Events"
        tell process "Live"
            tell front window
                tell group 1
                    try
                        set firstText to value of static text 1
                        if firstText contains "stop audio" then
                            return "confirmation"
                        end if
                    end try
                    return "no_confirmation"
                end tell
            end tell
        end tell
    end tell
    '''
    success, result = run_applescript(script)

    if success and "confirmation" in result:
        # Click Proceed button (button 2)
        script = '''
        tell application "System Events"
            tell process "Live"
                tell front window
                    tell group 1
                        click button 2
                    end tell
                end tell
            end tell
        end tell
        '''
        run_applescript(script)
        time.sleep(1.0)

    # Now wait for export to complete
    _wait_for_export_completion_live12(max_wait=120)


def _wait_for_export_completion_live12(max_wait: int = 120) -> None:
    """Wait for export completion in Live 12 (no Save dialog workflow)."""
    waited = 0
    while waited < max_wait:
        time.sleep(1.0)
        waited += 1

        _, window_name = verify_in_dialog()

        # If we're back to the main project window, export is complete
        if EXPORT_DIALOG_PREFIX not in window_name and SAVE_DIALOG_NAME not in window_name:
            return  # Export complete

        if waited % 10 == 0:
            print(f"  Exporting... {waited}s")

    raise ExportError(f"Export timed out after {max_wait}s")


def _check_frontmost_app() -> tuple[bool, str]:
    """Check if Ableton is the frontmost application."""
    script = '''
    tell application "System Events"
        set frontApp to name of first application process whose frontmost is true
        return frontApp
    end tell
    '''
    success, app_name = run_applescript(script)
    return app_name == "Live", app_name


def _abort_and_escape():
    """Abort current operation by pressing Escape multiple times."""
    for _ in range(3):
        close_dialog_with_escape()
        time.sleep(0.2)


def _type_filename_in_save_dialog(filename: str) -> bool:
    """
    Type a filename in the Save dialog.

    ONLY call this after verifying we're in a Save dialog!
    Uses Cmd+A to select existing text, which is safe in a text field.
    """
    script = f'''
    tell application "System Events"
        tell process "Live"
            -- Verify we're still in Save dialog
            set frontWindow to name of front window
            if frontWindow is not "Save" then
                error "Not in Save dialog - aborting for safety"
            end if

            -- Select all text in filename field and replace
            keystroke "a" using {{command down}}
            delay 0.1
            keystroke "{filename}"
        end tell
    end tell
    '''
    success, _ = run_applescript(script)
    return success
