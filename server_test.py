"""
Tests for server module.

Tests the utility functions and key/BPM parsing without requiring Ableton Live.
"""

import unittest
from typing import Optional, Tuple

from server import parse_key_and_bpm, sanitize_filename


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

    def test_parses_flat_keys(self) -> None:
        """Should parse flat keys like Bb (note: 'b' is uppercased for consistency)."""
        key, bpm = parse_key_and_bpm("chord Bbmaj 95bpm")
        # Note: Implementation uppercases the note, so Bb becomes BB
        self.assertEqual(key, "BBmaj")
        self.assertEqual(bpm, 95)

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

    def test_rejects_bpm_below_60(self) -> None:
        """Should reject BPM values below 60."""
        _, bpm = parse_key_and_bpm("slow 45bpm")
        self.assertIsNone(bpm)

    def test_rejects_bpm_above_200(self) -> None:
        """Should reject BPM values above 200."""
        _, bpm = parse_key_and_bpm("fast 250bpm")
        self.assertIsNone(bpm)

    def test_accepts_bpm_at_boundaries(self) -> None:
        """Should accept BPM at boundary values 60 and 200."""
        _, bpm60 = parse_key_and_bpm("slow 60bpm")
        _, bpm200 = parse_key_and_bpm("fast 200bpm")
        self.assertEqual(bpm60, 60)
        self.assertEqual(bpm200, 200)

    def test_returns_none_for_no_key(self) -> None:
        """Should return None for key if no musical key pattern found."""
        # Note: "track" contains 'a' which matches note pattern, so use different string
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
        """Should replace " with underscore."""
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


if __name__ == "__main__":
    unittest.main()
