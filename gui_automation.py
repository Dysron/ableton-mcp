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
    """Select all text in current field and delete it."""
    script = '''
    tell application "System Events"
        keystroke "a" using {command down}
        delay 0.1
        key code 51
    end tell
    '''
    success, _ = run_applescript(script)
    return success


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

        # Clear filename field and type new name
        # The filename field should be focused after folder navigation
        select_all_and_delete()
        time.sleep(0.1)
        type_text(filename)

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
