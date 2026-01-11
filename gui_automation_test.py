"""
Tests for gui_automation module.

Tests the safety mechanisms and helper functions without requiring Ableton Live.
"""

import subprocess
import unittest
from unittest.mock import patch, MagicMock

from gui_automation import (
    # Constants
    SAFE_DIALOG_WINDOWS,
    EXPORT_DIALOG_PREFIX,
    SAVE_DIALOG_NAME,
    INVALID_FILENAME_CHARS,
    # Exceptions
    ExportError,
    DialogVerificationError,
    AbletonActivationError,
    # Functions
    run_applescript,
    verify_in_dialog,
    select_all_and_delete,
)


class TestConstants(unittest.TestCase):
    """Test that constants are properly defined."""

    def test_safe_dialog_windows_is_frozenset(self) -> None:
        """SAFE_DIALOG_WINDOWS should be immutable."""
        self.assertIsInstance(SAFE_DIALOG_WINDOWS, frozenset)

    def test_safe_dialog_windows_contains_expected_values(self) -> None:
        """SAFE_DIALOG_WINDOWS should contain Save and Export dialogs."""
        self.assertIn("Save", SAFE_DIALOG_WINDOWS)
        self.assertIn("Export", SAFE_DIALOG_WINDOWS)
        self.assertIn("Export Audio/Video", SAFE_DIALOG_WINDOWS)

    def test_export_dialog_prefix(self) -> None:
        """EXPORT_DIALOG_PREFIX should be Export."""
        self.assertEqual(EXPORT_DIALOG_PREFIX, "Export")

    def test_save_dialog_name(self) -> None:
        """SAVE_DIALOG_NAME should be Save."""
        self.assertEqual(SAVE_DIALOG_NAME, "Save")

    def test_invalid_filename_chars_contains_dangerous_chars(self) -> None:
        """INVALID_FILENAME_CHARS should contain filesystem-unsafe characters."""
        for char in ['<', '>', ':', '"', '/', '\\', '|', '?', '*']:
            self.assertIn(char, INVALID_FILENAME_CHARS)


class TestExceptionHierarchy(unittest.TestCase):
    """Test custom exception classes."""

    def test_export_error_is_exception(self) -> None:
        """ExportError should inherit from Exception."""
        self.assertTrue(issubclass(ExportError, Exception))

    def test_dialog_verification_error_is_export_error(self) -> None:
        """DialogVerificationError should inherit from ExportError."""
        self.assertTrue(issubclass(DialogVerificationError, ExportError))

    def test_ableton_activation_error_is_export_error(self) -> None:
        """AbletonActivationError should inherit from ExportError."""
        self.assertTrue(issubclass(AbletonActivationError, ExportError))

    def test_can_catch_all_with_export_error(self) -> None:
        """All custom exceptions should be catchable with ExportError."""
        for exc_class in [ExportError, DialogVerificationError, AbletonActivationError]:
            with self.assertRaises(ExportError):
                raise exc_class("test message")


class TestRunApplescript(unittest.TestCase):
    """Test AppleScript execution wrapper."""

    @patch("gui_automation.subprocess.run")
    def test_returns_success_on_zero_returncode(self, mock_run: MagicMock) -> None:
        """run_applescript should return (True, output) on success."""
        mock_run.return_value = MagicMock(returncode=0, stdout="output\n")
        success, output = run_applescript("test script")
        self.assertTrue(success)
        self.assertEqual(output, "output")

    @patch("gui_automation.subprocess.run")
    def test_returns_failure_on_nonzero_returncode(self, mock_run: MagicMock) -> None:
        """run_applescript should return (False, output) on failure."""
        mock_run.return_value = MagicMock(returncode=1, stdout="error\n")
        success, output = run_applescript("test script")
        self.assertFalse(success)

    @patch("gui_automation.subprocess.run")
    def test_handles_timeout(self, mock_run: MagicMock) -> None:
        """run_applescript should handle timeout gracefully."""
        mock_run.side_effect = subprocess.TimeoutExpired("osascript", 30)
        success, output = run_applescript("test script")
        self.assertFalse(success)
        self.assertEqual(output, "Timeout")

    @patch("gui_automation.subprocess.run")
    def test_handles_subprocess_error(self, mock_run: MagicMock) -> None:
        """run_applescript should handle SubprocessError gracefully."""
        mock_run.side_effect = subprocess.SubprocessError("test error")
        success, output = run_applescript("test script")
        self.assertFalse(success)
        self.assertIn("Subprocess error", output)

    @patch("gui_automation.subprocess.run")
    def test_handles_os_error(self, mock_run: MagicMock) -> None:
        """run_applescript should handle OSError gracefully."""
        mock_run.side_effect = OSError("test error")
        success, output = run_applescript("test script")
        self.assertFalse(success)
        self.assertIn("OS error", output)


class TestVerifyInDialog(unittest.TestCase):
    """Test dialog verification function."""

    @patch("gui_automation.run_applescript")
    def test_returns_safe_for_save_dialog(self, mock_run: MagicMock) -> None:
        """verify_in_dialog should return (True, 'Save') for Save dialog."""
        mock_run.return_value = (True, "Save")
        is_safe, window_name = verify_in_dialog()
        self.assertTrue(is_safe)
        self.assertEqual(window_name, "Save")

    @patch("gui_automation.run_applescript")
    def test_returns_safe_for_export_dialog(self, mock_run: MagicMock) -> None:
        """verify_in_dialog should return True for Export dialogs."""
        mock_run.return_value = (True, "Export Audio/Video")
        is_safe, window_name = verify_in_dialog()
        self.assertTrue(is_safe)

    @patch("gui_automation.run_applescript")
    def test_returns_unsafe_for_main_window(self, mock_run: MagicMock) -> None:
        """verify_in_dialog should return False for main arrangement window."""
        mock_run.return_value = (True, "")
        is_safe, window_name = verify_in_dialog()
        self.assertFalse(is_safe)

    @patch("gui_automation.run_applescript")
    def test_returns_unsafe_for_browser_window(self, mock_run: MagicMock) -> None:
        """verify_in_dialog should return False for browser window."""
        mock_run.return_value = (True, "Browser")
        is_safe, window_name = verify_in_dialog()
        self.assertFalse(is_safe)


class TestSelectAllAndDelete(unittest.TestCase):
    """Test that dangerous function is disabled."""

    def test_raises_runtime_error(self) -> None:
        """select_all_and_delete should raise RuntimeError."""
        with self.assertRaises(RuntimeError) as context:
            select_all_and_delete()
        self.assertIn("disabled", str(context.exception).lower())
        self.assertIn("delete tracks", str(context.exception).lower())


if __name__ == "__main__":
    unittest.main()
