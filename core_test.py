"""
Tests for core module.

Tests the core business logic functions without requiring Ableton Live.
"""

import unittest
from unittest.mock import MagicMock, patch

from core import (
    # Constants
    BPM_MIN,
    BPM_MAX,
    # Enums and dataclasses
    TrackType,
    TrackInfo,
    ExportInfo,
    ConnectionStatus,
    ExportResult,
    # Functions
    parse_key_and_bpm,
    sanitize_filename,
    check_connection,
    get_all_tracks,
    get_groups,
    get_track_details,
    find_tracks_by_name,
    select_track_by_index,
)


class TestConstants(unittest.TestCase):
    """Test BPM constants."""

    def test_bpm_min_is_60(self) -> None:
        """BPM_MIN should be 60."""
        self.assertEqual(BPM_MIN, 60)

    def test_bpm_max_is_200(self) -> None:
        """BPM_MAX should be 200."""
        self.assertEqual(BPM_MAX, 200)


class TestTrackType(unittest.TestCase):
    """Test TrackType enum."""

    def test_track_type_values(self) -> None:
        """TrackType should have TRACK and GROUP values."""
        self.assertEqual(TrackType.TRACK.value, "track")
        self.assertEqual(TrackType.GROUP.value, "group")


class TestDataclasses(unittest.TestCase):
    """Test dataclass structures."""

    def test_track_info_creation(self) -> None:
        """TrackInfo should store all fields."""
        track = TrackInfo(
            index=5,
            name="Bass",
            track_type=TrackType.TRACK,
            muted=False,
            clip_count=3,
            audio_start=0.0,
            audio_end=64.0,
        )
        self.assertEqual(track.index, 5)
        self.assertEqual(track.name, "Bass")
        self.assertEqual(track.track_type, TrackType.TRACK)
        self.assertFalse(track.muted)
        self.assertEqual(track.clip_count, 3)

    def test_export_info_creation(self) -> None:
        """ExportInfo should store all fields."""
        info = ExportInfo(
            track_name="Bass",
            group_name="Rhythm",
            key="Amin",
            bpm=128,
            suggested_filename="Bass_Amin_128bpm",
        )
        self.assertEqual(info.track_name, "Bass")
        self.assertEqual(info.suggested_filename, "Bass_Amin_128bpm")

    def test_connection_status_defaults(self) -> None:
        """ConnectionStatus should have sensible defaults."""
        status = ConnectionStatus(connected=True, message="OK")
        self.assertTrue(status.connected)
        self.assertIsNone(status.tempo)
        self.assertIsNone(status.track_count)

    def test_export_result_creation(self) -> None:
        """ExportResult should store all fields."""
        result = ExportResult(
            success=True,
            filename="track.wav",
            message="Export complete",
        )
        self.assertTrue(result.success)
        self.assertEqual(result.filename, "track.wav")


class TestParseKeyAndBpm(unittest.TestCase):
    """Test key and BPM parsing from track/group names."""

    def test_parses_amin_143bpm_format(self) -> None:
        """Should parse 'Amin - 143bpm' format."""
        key, bpm = parse_key_and_bpm("Amin - 143bpm")
        self.assertEqual(key, "Amin")
        self.assertEqual(bpm, 143)

    def test_parses_cmaj_120_format(self) -> None:
        """Should parse 'Song Cmaj 120' format (word boundaries required)."""
        key, bpm = parse_key_and_bpm("Song Cmaj 120")
        self.assertEqual(key, "Cmaj")
        self.assertEqual(bpm, 120)

    def test_parses_bpm_first_format(self) -> None:
        """Should parse 'Track 140bpm Fmin' format."""
        key, bpm = parse_key_and_bpm("Track 140bpm Fmin")
        self.assertEqual(key, "Fmin")
        self.assertEqual(bpm, 140)

    def test_parses_sharp_keys(self) -> None:
        """Should parse sharp keys like F#min."""
        key, bpm = parse_key_and_bpm("melody F#min 128")
        self.assertEqual(key, "F#min")
        self.assertEqual(bpm, 128)

    def test_parses_minor_as_min(self) -> None:
        """Should normalize 'minor' to 'min'."""
        key, _ = parse_key_and_bpm("A minor song")
        self.assertEqual(key, "Amin")

    def test_parses_major_as_maj(self) -> None:
        """Should normalize 'major' to 'maj'."""
        key, _ = parse_key_and_bpm("C major melody")
        self.assertEqual(key, "Cmaj")

    def test_parses_m_as_min(self) -> None:
        """Should normalize 'm' to 'min'."""
        key, _ = parse_key_and_bpm("Em track")
        self.assertEqual(key, "Emin")

    def test_rejects_bpm_below_min(self) -> None:
        """Should reject BPM values below BPM_MIN."""
        _, bpm = parse_key_and_bpm("slow 45bpm")
        self.assertIsNone(bpm)

    def test_rejects_bpm_above_max(self) -> None:
        """Should reject BPM values above BPM_MAX."""
        _, bpm = parse_key_and_bpm("fast 250bpm")
        self.assertIsNone(bpm)

    def test_accepts_bpm_at_boundaries(self) -> None:
        """Should accept BPM at boundary values."""
        _, bpm60 = parse_key_and_bpm(f"slow {BPM_MIN}bpm")
        _, bpm200 = parse_key_and_bpm(f"fast {BPM_MAX}bpm")
        self.assertEqual(bpm60, BPM_MIN)
        self.assertEqual(bpm200, BPM_MAX)

    def test_returns_none_for_no_key(self) -> None:
        """Should return None for key if no musical key pattern found."""
        key, _ = parse_key_and_bpm("just some drums 120bpm")
        self.assertIsNone(key)

    def test_returns_none_for_no_bpm(self) -> None:
        """Should return None for BPM if no BPM found."""
        _, bpm = parse_key_and_bpm("Amin melody")
        self.assertIsNone(bpm)

    def test_returns_none_for_empty_string(self) -> None:
        """Should return (None, None) for empty string."""
        key, bpm = parse_key_and_bpm("")
        self.assertIsNone(key)
        self.assertIsNone(bpm)

    def test_case_insensitive(self) -> None:
        """Should parse keys case-insensitively."""
        key, bpm = parse_key_and_bpm("AMIN - 143BPM")
        self.assertEqual(key, "Amin")
        self.assertEqual(bpm, 143)


class TestSanitizeFilename(unittest.TestCase):
    """Test filename sanitization."""

    def test_replaces_less_than(self) -> None:
        """Should replace < with underscore."""
        result = sanitize_filename("test<file")
        self.assertEqual(result, "test_file")

    def test_replaces_greater_than(self) -> None:
        """Should replace > with underscore."""
        result = sanitize_filename("test>file")
        self.assertEqual(result, "test_file")

    def test_replaces_colon(self) -> None:
        """Should replace : with underscore."""
        result = sanitize_filename("test:file")
        self.assertEqual(result, "test_file")

    def test_replaces_double_quote(self) -> None:
        """Should replace \" with underscore."""
        result = sanitize_filename('test"file')
        self.assertEqual(result, "test_file")

    def test_replaces_forward_slash(self) -> None:
        """Should replace / with underscore."""
        result = sanitize_filename("test/file")
        self.assertEqual(result, "test_file")

    def test_replaces_backslash(self) -> None:
        """Should replace \\ with underscore."""
        result = sanitize_filename("test\\file")
        self.assertEqual(result, "test_file")

    def test_replaces_pipe(self) -> None:
        """Should replace | with underscore."""
        result = sanitize_filename("test|file")
        self.assertEqual(result, "test_file")

    def test_replaces_question_mark(self) -> None:
        """Should replace ? with underscore."""
        result = sanitize_filename("test?file")
        self.assertEqual(result, "test_file")

    def test_replaces_asterisk(self) -> None:
        """Should replace * with underscore."""
        result = sanitize_filename("test*file")
        self.assertEqual(result, "test_file")

    def test_replaces_multiple_invalid_chars(self) -> None:
        """Should replace multiple invalid characters."""
        result = sanitize_filename("test<>:file")
        self.assertEqual(result, "test___file")

    def test_strips_whitespace(self) -> None:
        """Should strip leading and trailing whitespace."""
        result = sanitize_filename("  test file  ")
        self.assertEqual(result, "test file")

    def test_preserves_valid_chars(self) -> None:
        """Should preserve valid filename characters."""
        result = sanitize_filename("test_file-123.wav")
        self.assertEqual(result, "test_file-123.wav")

    def test_empty_string(self) -> None:
        """Should handle empty string."""
        result = sanitize_filename("")
        self.assertEqual(result, "")


class TestConnectionFunctions(unittest.TestCase):
    """Test connection-related functions."""

    @patch("core.get_tempo")
    @patch("core.get_track_count")
    def test_check_connection_success(
        self, mock_count: MagicMock, mock_tempo: MagicMock
    ) -> None:
        """check_connection should return success when connected."""
        mock_client = MagicMock()
        mock_client.test_connection.return_value = True
        mock_tempo.return_value = 120.0
        mock_count.return_value = 10

        status = check_connection(mock_client)

        self.assertTrue(status.connected)
        self.assertEqual(status.tempo, 120.0)
        self.assertEqual(status.track_count, 10)

    def test_check_connection_failure(self) -> None:
        """check_connection should return failure when not connected."""
        mock_client = MagicMock()
        mock_client.test_connection.return_value = False

        status = check_connection(mock_client)

        self.assertFalse(status.connected)
        self.assertIn("Could not connect", status.message)


class TestTrackFunctions(unittest.TestCase):
    """Test track-related functions."""

    @patch("core.get_arrangement_clips")
    @patch("core.get_track_muted")
    @patch("core.get_track_is_foldable")
    @patch("core.get_track_name")
    @patch("core.get_track_count")
    def test_get_all_tracks(
        self,
        mock_count: MagicMock,
        mock_name: MagicMock,
        mock_foldable: MagicMock,
        mock_muted: MagicMock,
        mock_clips: MagicMock,
    ) -> None:
        """get_all_tracks should return list of TrackInfo."""
        mock_client = MagicMock()
        mock_count.return_value = 2
        mock_name.side_effect = ["Bass", "Drums Group"]
        mock_foldable.side_effect = [False, True]
        mock_muted.side_effect = [False, True]
        mock_clips.return_value = []

        tracks = get_all_tracks(mock_client)

        self.assertEqual(len(tracks), 2)
        self.assertEqual(tracks[0].name, "Bass")
        self.assertEqual(tracks[0].track_type, TrackType.TRACK)
        self.assertEqual(tracks[1].name, "Drums Group")
        self.assertEqual(tracks[1].track_type, TrackType.GROUP)

    @patch("core.get_all_tracks")
    def test_get_groups(self, mock_all_tracks: MagicMock) -> None:
        """get_groups should filter to only group tracks."""
        mock_client = MagicMock()
        mock_all_tracks.return_value = [
            TrackInfo(0, "Bass", TrackType.TRACK, False),
            TrackInfo(1, "Drums", TrackType.GROUP, False),
            TrackInfo(2, "Lead", TrackType.TRACK, False),
        ]

        groups = get_groups(mock_client)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].name, "Drums")

    @patch("core.get_all_tracks")
    def test_find_tracks_by_name(self, mock_all_tracks: MagicMock) -> None:
        """find_tracks_by_name should filter by partial match."""
        mock_client = MagicMock()
        mock_all_tracks.return_value = [
            TrackInfo(0, "Bass", TrackType.TRACK, False),
            TrackInfo(1, "Sub Bass", TrackType.TRACK, False),
            TrackInfo(2, "Lead", TrackType.TRACK, False),
        ]

        matches = find_tracks_by_name(mock_client, "bass")

        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].name, "Bass")
        self.assertEqual(matches[1].name, "Sub Bass")

    @patch("core.select_track")
    @patch("core.get_track_name")
    @patch("core.get_track_count")
    def test_select_track_by_index_success(
        self,
        mock_count: MagicMock,
        mock_name: MagicMock,
        mock_select: MagicMock,
    ) -> None:
        """select_track_by_index should succeed for valid index."""
        mock_client = MagicMock()
        mock_count.return_value = 10
        mock_name.return_value = "Bass"

        success, message = select_track_by_index(mock_client, 5)

        self.assertTrue(success)
        self.assertIn("Bass", message)
        mock_select.assert_called_once_with(mock_client, 5)

    @patch("core.get_track_count")
    def test_select_track_by_index_invalid(self, mock_count: MagicMock) -> None:
        """select_track_by_index should fail for invalid index."""
        mock_client = MagicMock()
        mock_count.return_value = 5

        success, message = select_track_by_index(mock_client, 10)

        self.assertFalse(success)
        self.assertIn("Invalid", message)


if __name__ == "__main__":
    unittest.main()
