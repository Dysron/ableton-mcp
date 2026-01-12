"""
Core logic for Ableton Live control.

This module contains the shared business logic used by both CLI and MCP interfaces.
All functions are synchronous and return structured data.
"""

import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from osc_client import (
    AbletonOSCClient,
    get_track_count,
    get_track_name,
    get_track_muted,
    get_track_is_foldable,
    get_track_is_grouped,
    get_track_group_track_index,
    get_arrangement_clips,
    get_tempo,
    select_track,
    set_loop_range,
)
from gui_automation import (
    safe_export_with_filename,
    set_export_render_range,
    open_export_dialog,
    activate_ableton,
    verify_in_dialog,
    close_dialog_with_escape,
    INVALID_FILENAME_CHARS,
    EXPORT_DIALOG_PREFIX,
)


class TrackType(Enum):
    """Track type enumeration."""
    TRACK = "track"
    GROUP = "group"


@dataclass
class TrackInfo:
    """Information about a track."""
    index: int
    name: str
    track_type: TrackType
    muted: bool
    clip_count: int = 0
    audio_start: Optional[float] = None
    audio_end: Optional[float] = None


@dataclass
class ExportInfo:
    """Information for exporting a track."""
    track_name: str
    group_name: Optional[str]
    key: Optional[str]
    bpm: Optional[int]
    suggested_filename: str


@dataclass
class ConnectionStatus:
    """Connection status result."""
    connected: bool
    tempo: Optional[float] = None
    track_count: Optional[int] = None
    message: str = ""


@dataclass
class ExportResult:
    """Result of an export operation."""
    success: bool
    filename: str
    message: str


# BPM validation constants
BPM_MIN = 60
BPM_MAX = 200


def get_osc_client() -> AbletonOSCClient:
    """Create a new OSC client."""
    return AbletonOSCClient()


def parse_key_and_bpm(name: str) -> tuple[Optional[str], Optional[int]]:
    """
    Parse musical key and BPM from a track/group name.

    Common patterns:
    - "Amin - 143bpm" -> ("Amin", 143)
    - "Song Cmaj 120" -> ("Cmaj", 120)
    - "Track 140bpm Fmin" -> ("Fmin", 140)

    Args:
        name: Track or group name to parse

    Returns:
        Tuple of (key, bpm) where either may be None if not found
    """
    key = None
    bpm = None

    # Pattern for BPM: number followed by optional "bpm"
    bpm_match = re.search(r'(\d{2,3})\s*(?:bpm)?', name, re.IGNORECASE)
    if bpm_match:
        bpm_val = int(bpm_match.group(1))
        if BPM_MIN <= bpm_val <= BPM_MAX:
            bpm = bpm_val

    # Pattern for key: note letter + optional sharp/flat + optional min/maj/m
    key_match = re.search(r'\b([A-G][#b]?)\s*(min|maj|minor|major|m)?\b', name, re.IGNORECASE)
    if key_match:
        note = key_match.group(1).upper()
        mode = key_match.group(2)
        if mode:
            mode = mode.lower()
            if mode in ('min', 'minor', 'm'):
                key = f"{note}min"
            elif mode in ('maj', 'major'):
                key = f"{note}maj"
            else:
                key = note
        else:
            key = note

    return key, bpm


def sanitize_filename(name: str) -> str:
    """
    Sanitize a string for use as filename.

    Args:
        name: String to sanitize

    Returns:
        Sanitized string safe for use as filename
    """
    result = name
    for char in INVALID_FILENAME_CHARS:
        result = result.replace(char, "_")
    return result.strip()


def check_connection(client: AbletonOSCClient) -> ConnectionStatus:
    """
    Test connection to Ableton Live.

    Args:
        client: OSC client to use

    Returns:
        ConnectionStatus with connection details
    """
    if client.test_connection():
        tempo = get_tempo(client)
        count = get_track_count(client)
        return ConnectionStatus(
            connected=True,
            tempo=tempo,
            track_count=count,
            message=f"Connected to Ableton Live! Tempo: {tempo} BPM, Tracks: {count}"
        )
    else:
        return ConnectionStatus(
            connected=False,
            message="Could not connect. Make sure Ableton Live is running with AbletonOSC enabled."
        )


@dataclass
class AudioRange:
    """Range of audio content in the arrangement."""
    start_beats: float
    end_beats: float
    length_beats: float
    duration_seconds: float
    start_bar: int
    length_bars: int


def get_arrangement_audio_range(client: AbletonOSCClient) -> Optional[AudioRange]:
    """
    Detect the actual audio range across ALL tracks in the arrangement.

    Scans all non-muted tracks to find the earliest clip start and latest clip end.
    This gives the exact range of actual audio content, avoiding silence.

    Args:
        client: OSC client to use

    Returns:
        AudioRange with the detected range, or None if no clips found
    """
    count = get_track_count(client)
    if count == 0:
        return None

    earliest_start = float('inf')
    latest_end = 0.0
    has_clips = False

    for track_idx in range(count):
        # Skip muted tracks
        if get_track_muted(client, track_idx):
            continue

        # Skip group tracks (they don't have their own clips)
        if get_track_is_foldable(client, track_idx):
            continue

        clips = get_arrangement_clips(client, track_idx)
        if clips:
            has_clips = True
            # First clip has earliest start for this track
            track_start = clips[0]['start_time']
            # Last clip end = start + length
            track_end = clips[-1]['start_time'] + clips[-1]['length']

            earliest_start = min(earliest_start, track_start)
            latest_end = max(latest_end, track_end)

    if not has_clips:
        return None

    length_beats = latest_end - earliest_start
    tempo = get_tempo(client)
    duration_seconds = (length_beats / tempo) * 60

    # Calculate bar numbers (assuming 4 beats per bar)
    beats_per_bar = 4
    start_bar = int(earliest_start / beats_per_bar) + 1  # Bars are 1-indexed in Ableton
    length_bars = int((length_beats + beats_per_bar - 1) / beats_per_bar)  # Round up

    return AudioRange(
        start_beats=earliest_start,
        end_beats=latest_end,
        length_beats=length_beats,
        duration_seconds=duration_seconds,
        start_bar=start_bar,
        length_bars=length_bars,
    )


def get_all_tracks(client: AbletonOSCClient, include_clips: bool = False) -> list[TrackInfo]:
    """
    Get information about all tracks.

    Args:
        client: OSC client to use
        include_clips: Whether to include clip count for each track

    Returns:
        List of TrackInfo objects
    """
    count = get_track_count(client)
    tracks = []

    for i in range(count):
        name = get_track_name(client, i)
        is_group = get_track_is_foldable(client, i)
        muted = get_track_muted(client, i)

        clip_count = 0
        if include_clips and not is_group:
            clips = get_arrangement_clips(client, i)
            clip_count = len(clips) if clips else 0

        tracks.append(TrackInfo(
            index=i,
            name=name,
            track_type=TrackType.GROUP if is_group else TrackType.TRACK,
            muted=muted,
            clip_count=clip_count,
        ))

    return tracks


def get_groups(client: AbletonOSCClient) -> list[TrackInfo]:
    """
    Get all group tracks.

    Args:
        client: OSC client to use

    Returns:
        List of TrackInfo for groups only
    """
    all_tracks = get_all_tracks(client)
    return [t for t in all_tracks if t.track_type == TrackType.GROUP]


def get_track_details(client: AbletonOSCClient, track_index: int) -> Optional[TrackInfo]:
    """
    Get detailed information about a specific track.

    Args:
        client: OSC client to use
        track_index: Index of the track

    Returns:
        TrackInfo with full details, or None if invalid index
    """
    count = get_track_count(client)
    if track_index < 0 or track_index >= count:
        return None

    name = get_track_name(client, track_index)
    is_group = get_track_is_foldable(client, track_index)
    muted = get_track_muted(client, track_index)
    clips = get_arrangement_clips(client, track_index)

    audio_start = None
    audio_end = None
    if clips:
        audio_start = clips[0]['start_time']
        audio_end = clips[-1]['start_time'] + clips[-1]['length']

    return TrackInfo(
        index=track_index,
        name=name,
        track_type=TrackType.GROUP if is_group else TrackType.TRACK,
        muted=muted,
        clip_count=len(clips) if clips else 0,
        audio_start=audio_start,
        audio_end=audio_end,
    )


def find_tracks_by_name(client: AbletonOSCClient, search: str) -> list[TrackInfo]:
    """
    Find tracks by name (partial match, case-insensitive).

    Args:
        client: OSC client to use
        search: Text to search for

    Returns:
        List of matching TrackInfo objects
    """
    all_tracks = get_all_tracks(client)
    search_lower = search.lower()
    return [t for t in all_tracks if search_lower in t.name.lower()]


def select_track_by_index(client: AbletonOSCClient, track_index: int) -> tuple[bool, str]:
    """
    Select a track by index.

    Args:
        client: OSC client to use
        track_index: Index of the track to select

    Returns:
        Tuple of (success, message)
    """
    count = get_track_count(client)
    if track_index < 0 or track_index >= count:
        return False, f"Invalid track index. Valid range: 0-{count-1}"

    name = get_track_name(client, track_index)
    select_track(client, track_index)
    return True, f"Selected track {track_index}: {name}"


def set_export_range(client: AbletonOSCClient, start_beats: float, length_beats: float) -> str:
    """
    Set the loop/punch range for export.

    Args:
        client: OSC client to use
        start_beats: Start position in beats
        length_beats: Length in beats

    Returns:
        Confirmation message with time info
    """
    tempo = get_tempo(client)
    set_loop_range(client, start_beats, length_beats)

    duration_sec = (length_beats / tempo) * 60
    end_beats = start_beats + length_beats

    return f"Set export range: {start_beats:.1f} - {end_beats:.1f} beats ({duration_sec:.1f} seconds at {tempo:.0f} BPM)"


def get_track_export_info(client: AbletonOSCClient, track_index: int) -> Optional[ExportInfo]:
    """
    Get all info needed for exporting a track with proper naming.

    Args:
        client: OSC client to use
        track_index: Index of the track

    Returns:
        ExportInfo with suggested filename, or None if invalid index
    """
    count = get_track_count(client)
    if track_index < 0 or track_index >= count:
        return None

    track_name = get_track_name(client, track_index)
    group_name = None
    key = None
    bpm = None

    # Check if track is in a group
    if get_track_is_grouped(client, track_index):
        group_idx = get_track_group_track_index(client, track_index)
        if group_idx is not None:
            group_name = get_track_name(client, group_idx)
            key, bpm = parse_key_and_bpm(group_name)

    # If no key/BPM from group, try from track name
    if not key or not bpm:
        track_key, track_bpm = parse_key_and_bpm(track_name)
        key = key or track_key
        bpm = bpm or track_bpm

    # If still no BPM, get from Live
    if not bpm:
        bpm = int(get_tempo(client))

    # Generate suggested filename
    parts = [sanitize_filename(track_name)]
    if key:
        parts.append(key)
    if bpm:
        parts.append(f"{bpm}bpm")

    suggested_filename = "_".join(parts)

    return ExportInfo(
        track_name=track_name,
        group_name=group_name,
        key=key,
        bpm=bpm,
        suggested_filename=suggested_filename,
    )


def prepare_track_for_export(client: AbletonOSCClient, track_index: int) -> tuple[bool, str]:
    """
    Prepare a track for export by selecting it and setting the loop range.

    Args:
        client: OSC client to use
        track_index: Index of the track to prepare

    Returns:
        Tuple of (success, message)
    """
    count = get_track_count(client)
    if track_index < 0 or track_index >= count:
        return False, f"Invalid track index. Valid range: 0-{count-1}"

    name = get_track_name(client, track_index)
    clips = get_arrangement_clips(client, track_index)

    if not clips:
        return False, f"Track '{name}' has no arrangement clips to export"

    # Calculate range from clips
    start = clips[0]['start_time']
    end = clips[-1]['start_time'] + clips[-1]['length']
    length = end - start

    # Set range and select track
    set_loop_range(client, start, length)
    select_track(client, track_index)

    tempo = get_tempo(client)
    duration_sec = (length / tempo) * 60

    return True, f"Prepared '{name}' for export: {start:.1f} - {end:.1f} beats ({duration_sec:.1f} seconds)"


def export_track(
    client: AbletonOSCClient,
    track_index: Optional[int] = None,
    output_folder: Optional[str] = None,
    custom_filename: Optional[str] = None,
) -> ExportResult:
    """
    Export a track with full safety checks.

    Args:
        client: OSC client to use
        track_index: Track to export (uses current selection if None)
        output_folder: Folder to save to (uses Ableton default if None)
        custom_filename: Override the auto-generated filename

    Returns:
        ExportResult with success status and details
    """
    filename = custom_filename
    track_name = "unknown"

    # If track_index provided, set up the track
    if track_index is not None:
        count = get_track_count(client)
        if track_index < 0 or track_index >= count:
            return ExportResult(
                success=False,
                filename="",
                message=f"Invalid track index. Valid range: 0-{count-1}"
            )

        track_name = get_track_name(client, track_index)

        # Get clips to set loop range
        clips = get_arrangement_clips(client, track_index)
        if clips:
            start = clips[0]['start_time']
            end = clips[-1]['start_time'] + clips[-1]['length']
            length = end - start
            set_loop_range(client, start, length)

        # Get export info for smart filename
        export_info = get_track_export_info(client, track_index)
        if export_info and not filename:
            filename = export_info.suggested_filename

        # Select the track
        select_track(client, track_index)
        time.sleep(0.3)
    else:
        # No track specified
        if not filename:
            tempo = int(get_tempo(client))
            filename = f"export_{tempo}bpm_{int(time.time())}"

    # Perform the safe export with verification at each step
    success, message = safe_export_with_filename(filename, output_folder)

    if success:
        return ExportResult(
            success=True,
            filename=f"{filename}.wav",
            message=f"Exported '{track_name}' as {filename}.wav"
        )
    else:
        return ExportResult(
            success=False,
            filename=filename,
            message=f"Export failed: {message}"
        )


def export_arrangement(
    client: AbletonOSCClient,
    output_folder: Optional[str] = None,
    custom_filename: Optional[str] = None,
    auto_detect_range: bool = True,
) -> ExportResult:
    """
    Export the full arrangement mix with automatic audio range detection.

    This function scans all tracks to find the actual audio content range,
    avoiding trailing silence in the export.

    Args:
        client: OSC client to use
        output_folder: Folder to save to (uses Ableton default if None)
        custom_filename: Override the auto-generated filename
        auto_detect_range: If True, automatically detect audio range (default: True)

    Returns:
        ExportResult with success status and details
    """
    import time as time_module

    # Detect audio range if requested
    audio_range = None
    if auto_detect_range:
        audio_range = get_arrangement_audio_range(client)
        if not audio_range:
            return ExportResult(
                success=False,
                filename="",
                message="No audio clips found in arrangement"
            )

    # Generate filename
    if custom_filename:
        filename = custom_filename
    else:
        tempo = int(get_tempo(client))
        # Try to get key from group names
        key = None
        tracks = get_all_tracks(client)
        for track in tracks:
            if track.track_type == TrackType.GROUP:
                track_key, _ = parse_key_and_bpm(track.name)
                if track_key:
                    key = track_key
                    break

        parts = ["arrangement"]
        if key:
            parts.append(key)
        parts.append(f"{tempo}bpm")
        if audio_range:
            parts.append(f"{audio_range.length_bars}bars")
        filename = "_".join(parts)

    # Activate Ableton
    if not activate_ableton():
        return ExportResult(
            success=False,
            filename=filename,
            message="Could not activate Ableton Live"
        )
    time_module.sleep(0.5)

    # Open export dialog
    if not open_export_dialog():
        return ExportResult(
            success=False,
            filename=filename,
            message="Could not open export dialog"
        )
    time_module.sleep(1.5)

    # Verify we're in the Export dialog
    is_safe, window_name = verify_in_dialog()
    if EXPORT_DIALOG_PREFIX not in window_name:
        close_dialog_with_escape()
        return ExportResult(
            success=False,
            filename=filename,
            message=f"Expected Export dialog, found: {window_name}"
        )

    # Set render range based on detected audio
    if audio_range:
        success, range_msg = set_export_render_range(audio_range.start_bar, audio_range.length_bars)
        if not success:
            close_dialog_with_escape()
            return ExportResult(
                success=False,
                filename=filename,
                message=f"Could not set render range: {range_msg}"
            )

    # Click the Export button (button 10) directly since dialog is already open
    # Note: Button 1-9 are checkboxes, Button 10 = Export, Button 11 = Cancel
    from gui_automation import run_applescript, _handle_export_confirmation_and_wait

    script = '''
    tell application "System Events"
        tell process "Live"
            tell front window
                tell group 1
                    click button 10
                end tell
            end tell
        end tell
    end tell
    '''
    success, _ = run_applescript(script)
    if not success:
        close_dialog_with_escape()
        return ExportResult(
            success=False,
            filename=filename,
            message="Could not click Export button"
        )

    time_module.sleep(1.0)

    # Handle confirmation and wait for completion
    try:
        _handle_export_confirmation_and_wait()
        success = True
        message = f"Export complete: {filename}.wav"
    except Exception as e:
        success = False
        message = str(e)

    if success:
        duration_info = ""
        if audio_range:
            duration_info = f" ({audio_range.duration_seconds:.1f}s, {audio_range.length_bars} bars)"
        return ExportResult(
            success=True,
            filename=f"{filename}.wav",
            message=f"Exported arrangement as {filename}.wav{duration_info}"
        )
    else:
        return ExportResult(
            success=False,
            filename=filename,
            message=f"Export failed: {message}"
        )
