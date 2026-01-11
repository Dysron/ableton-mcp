"""
GUI automation for Ableton Live export dialog.

Uses AppleScript on macOS, PyAutoGUI as fallback.
"""

import subprocess
import time
import platform
from pathlib import Path
from typing import Optional


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
    except Exception as e:
        return False, str(e)


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
    tell application "System Events"
        keystroke "r" using {shift down, command down}
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

    safe_windows = ["Save", "Export Audio/Video", "Export"]
    is_safe = any(safe in window_name for safe in safe_windows)

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
    steps_completed = []

    try:
        # Step 1: Activate Ableton
        if not activate_ableton():
            return False, "Failed to activate Ableton Live"
        steps_completed.append("activated")
        time.sleep(0.5)

        # Step 2: Verify Ableton is frontmost
        is_frontmost, app_name = _check_frontmost_app()
        if not is_frontmost:
            return False, f"Ableton is not frontmost (found: {app_name})"
        steps_completed.append("verified_frontmost")

        # Step 3: Open export dialog
        if not open_export_dialog():
            return False, "Failed to open export dialog"
        steps_completed.append("opened_export_dialog")
        time.sleep(1.5)

        # Step 4: Verify Export dialog is open
        is_safe, window_name = verify_in_dialog()
        if "Export" not in window_name:
            _abort_and_escape()
            return False, f"Expected Export dialog, found: '{window_name}'"
        steps_completed.append("verified_export_dialog")

        # Step 5: Click Export button (press Enter)
        press_enter()
        time.sleep(1.0)
        steps_completed.append("clicked_export")

        # Step 6: Verify Save dialog is open
        is_safe, window_name = verify_in_dialog()
        if "Save" not in window_name:
            _abort_and_escape()
            return False, f"Expected Save dialog, found: '{window_name}'"
        steps_completed.append("verified_save_dialog")

        # Step 7: Navigate to folder if specified
        if output_folder:
            set_file_save_location(Path(output_folder))
            time.sleep(0.5)
            steps_completed.append("navigated_to_folder")

        # Step 8: Type filename (Cmd+A is safe here - we verified we're in Save dialog)
        _type_filename_in_save_dialog(filename)
        time.sleep(0.3)
        steps_completed.append("typed_filename")

        # Step 9: Start export
        press_enter()
        steps_completed.append("started_export")

        # Step 10: Wait for export to complete (progress dialog closes)
        # The "Export Audio..." progress dialog may appear briefly
        max_wait = 120  # Max 2 minutes for export
        waited = 0
        while waited < max_wait:
            time.sleep(1.0)
            waited += 1
            _, window_name = verify_in_dialog()

            # Save dialog still open = something went wrong
            if "Save" in window_name:
                return False, f"Save dialog still open after {waited}s - export may have failed"

            # No export-related dialog = export complete
            if "Export" not in window_name:
                break

            # Progress dialog still showing - keep waiting
            if waited % 10 == 0:
                print(f"  Exporting... {waited}s")

        # Final check
        _, window_name = verify_in_dialog()
        if "Save" in window_name or "Export" in window_name:
            return False, f"Export timed out after {max_wait}s - dialog: '{window_name}'"

        return True, f"Export complete: {filename}.wav"

    except Exception as e:
        _abort_and_escape()
        return False, f"Error after steps {steps_completed}: {str(e)}"


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
