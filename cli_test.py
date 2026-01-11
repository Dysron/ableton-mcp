"""
Tests for CLI module.

Tests the command line interface without requiring Ableton Live.
"""

import unittest
from unittest.mock import patch, MagicMock
from io import StringIO

from cli import (
    main,
    create_parser,
    EXIT_SUCCESS,
    EXIT_ERROR,
    EXIT_CONNECTION_FAILED,
)
from core import (
    TrackType,
    TrackInfo,
    ConnectionStatus,
    ExportResult,
)


class TestParser(unittest.TestCase):
    """Test argument parser configuration."""

    def test_parser_has_all_commands(self) -> None:
        """Parser should have all expected subcommands."""
        parser = create_parser()
        # Parse each command to ensure it exists
        commands = [
            "status",
            "tracks",
            "groups",
            "info 0",
            "find bass",
            "select 0",
            "range 0 64",
            "prepare 0",
            "export",
        ]
        for cmd in commands:
            args = parser.parse_args(cmd.split())
            self.assertIsNotNone(args.command)

    def test_tracks_clips_flag(self) -> None:
        """tracks command should accept --clips flag."""
        parser = create_parser()
        args = parser.parse_args(["tracks", "--clips"])
        self.assertTrue(args.clips)

    def test_export_options(self) -> None:
        """export command should accept all options."""
        parser = create_parser()
        args = parser.parse_args([
            "export",
            "--track", "5",
            "--output", "/tmp",
            "--filename", "test",
        ])
        self.assertEqual(args.track, 5)
        self.assertEqual(args.output, "/tmp")
        self.assertEqual(args.filename, "test")


class TestStatusCommand(unittest.TestCase):
    """Test status command."""

    @patch("cli.check_connection")
    @patch("cli.get_osc_client")
    def test_status_connected(
        self, mock_client: MagicMock, mock_test: MagicMock
    ) -> None:
        """status should return success when connected."""
        mock_test.return_value = ConnectionStatus(
            connected=True,
            tempo=120.0,
            track_count=10,
            message="Connected!",
        )

        result = main(["status"])

        self.assertEqual(result, EXIT_SUCCESS)

    @patch("cli.check_connection")
    @patch("cli.get_osc_client")
    def test_status_disconnected(
        self, mock_client: MagicMock, mock_test: MagicMock
    ) -> None:
        """status should return connection failed when disconnected."""
        mock_test.return_value = ConnectionStatus(
            connected=False,
            message="Could not connect",
        )

        result = main(["status"])

        self.assertEqual(result, EXIT_CONNECTION_FAILED)


class TestTracksCommand(unittest.TestCase):
    """Test tracks command."""

    @patch("cli.get_all_tracks")
    @patch("cli.check_connection")
    @patch("cli.get_osc_client")
    def test_tracks_lists_all(
        self,
        mock_client: MagicMock,
        mock_test: MagicMock,
        mock_tracks: MagicMock,
    ) -> None:
        """tracks should list all tracks."""
        mock_test.return_value = ConnectionStatus(connected=True, message="OK")
        mock_tracks.return_value = [
            TrackInfo(0, "Bass", TrackType.TRACK, False),
            TrackInfo(1, "Drums", TrackType.GROUP, True),
        ]

        result = main(["tracks"])

        self.assertEqual(result, EXIT_SUCCESS)
        mock_tracks.assert_called_once()

    @patch("cli.check_connection")
    @patch("cli.get_osc_client")
    def test_tracks_handles_disconnection(
        self, mock_client: MagicMock, mock_test: MagicMock
    ) -> None:
        """tracks should handle disconnection."""
        mock_test.return_value = ConnectionStatus(
            connected=False,
            message="Not connected",
        )

        result = main(["tracks"])

        self.assertEqual(result, EXIT_CONNECTION_FAILED)


class TestFindCommand(unittest.TestCase):
    """Test find command."""

    @patch("cli.find_tracks_by_name")
    @patch("cli.check_connection")
    @patch("cli.get_osc_client")
    def test_find_returns_matches(
        self,
        mock_client: MagicMock,
        mock_test: MagicMock,
        mock_find: MagicMock,
    ) -> None:
        """find should return matching tracks."""
        mock_test.return_value = ConnectionStatus(connected=True, message="OK")
        mock_find.return_value = [
            TrackInfo(0, "Bass", TrackType.TRACK, False),
            TrackInfo(5, "Sub Bass", TrackType.TRACK, False),
        ]

        result = main(["find", "bass"])

        self.assertEqual(result, EXIT_SUCCESS)
        mock_find.assert_called_once()


class TestSelectCommand(unittest.TestCase):
    """Test select command."""

    @patch("cli.select_track_by_index")
    @patch("cli.check_connection")
    @patch("cli.get_osc_client")
    def test_select_success(
        self,
        mock_client: MagicMock,
        mock_test: MagicMock,
        mock_select: MagicMock,
    ) -> None:
        """select should succeed for valid index."""
        mock_test.return_value = ConnectionStatus(connected=True, message="OK")
        mock_select.return_value = (True, "Selected track 5: Bass")

        result = main(["select", "5"])

        self.assertEqual(result, EXIT_SUCCESS)

    @patch("cli.select_track_by_index")
    @patch("cli.check_connection")
    @patch("cli.get_osc_client")
    def test_select_invalid_index(
        self,
        mock_client: MagicMock,
        mock_test: MagicMock,
        mock_select: MagicMock,
    ) -> None:
        """select should fail for invalid index."""
        mock_test.return_value = ConnectionStatus(connected=True, message="OK")
        mock_select.return_value = (False, "Invalid track index")

        result = main(["select", "999"])

        self.assertEqual(result, EXIT_ERROR)


class TestExportCommand(unittest.TestCase):
    """Test export command."""

    @patch("cli.platform")
    @patch("cli.export_track")
    @patch("cli.check_connection")
    @patch("cli.get_osc_client")
    def test_export_success(
        self,
        mock_client: MagicMock,
        mock_test: MagicMock,
        mock_export: MagicMock,
        mock_platform: MagicMock,
    ) -> None:
        """export should succeed on macOS."""
        mock_platform.system.return_value = "Darwin"
        mock_test.return_value = ConnectionStatus(connected=True, message="OK")
        mock_export.return_value = ExportResult(
            success=True,
            filename="track.wav",
            message="Export complete",
        )

        result = main(["export", "--track", "5"])

        self.assertEqual(result, EXIT_SUCCESS)

    @patch("cli.platform")
    def test_export_fails_on_non_macos(self, mock_platform: MagicMock) -> None:
        """export should fail on non-macOS."""
        mock_platform.system.return_value = "Linux"

        result = main(["export"])

        self.assertEqual(result, EXIT_ERROR)

    @patch("cli.platform")
    @patch("cli.export_track")
    @patch("cli.check_connection")
    @patch("cli.get_osc_client")
    def test_export_failure(
        self,
        mock_client: MagicMock,
        mock_test: MagicMock,
        mock_export: MagicMock,
        mock_platform: MagicMock,
    ) -> None:
        """export should return error on failure."""
        mock_platform.system.return_value = "Darwin"
        mock_test.return_value = ConnectionStatus(connected=True, message="OK")
        mock_export.return_value = ExportResult(
            success=False,
            filename="",
            message="Export failed",
        )

        result = main(["export"])

        self.assertEqual(result, EXIT_ERROR)


class TestNoCommand(unittest.TestCase):
    """Test behavior with no command."""

    def test_no_command_shows_help(self) -> None:
        """Running without command should show help and succeed."""
        result = main([])
        self.assertEqual(result, EXIT_SUCCESS)


if __name__ == "__main__":
    unittest.main()
