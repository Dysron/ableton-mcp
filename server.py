"""
Ableton MCP Server - Control Ableton Live via Model Context Protocol.

macOS only - uses AppleScript for GUI automation.
"""

import re
import sys
import platform
import time
from typing import Optional
from mcp.server.fastmcp import FastMCP

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
    activate_ableton,
    open_export_dialog,
    press_enter,
    close_dialog_with_escape,
    type_text,
    verify_in_dialog,
    safe_export_with_filename,
)

# Check platform
if platform.system() != "Darwin":
    print("Warning: Export features only work on macOS", file=sys.stderr)

# Initialize MCP server
mcp = FastMCP(
    "Ableton Live Controller",
    dependencies=["python-osc", "pyobjc"],
)

# Global OSC client (lazy initialized)
_osc_client: Optional[AbletonOSCClient] = None


def get_client() -> AbletonOSCClient:
    """Get or create the OSC client."""
    global _osc_client
    if _osc_client is None:
        _osc_client = AbletonOSCClient()
    return _osc_client


def parse_key_and_bpm(name: str) -> tuple[Optional[str], Optional[int]]:
    """
    Parse musical key and BPM from a track/group name.

    Common patterns:
    - "Amin - 143bpm" -> ("Amin", 143)
    - "Song_Cmaj_120" -> ("Cmaj", 120)
    - "Track 140bpm Fmin" -> ("Fmin", 140)
    """
    key = None
    bpm = None

    # Pattern for BPM: number followed by optional "bpm"
    bpm_match = re.search(r'(\d{2,3})\s*(?:bpm)?', name, re.IGNORECASE)
    if bpm_match:
        bpm_val = int(bpm_match.group(1))
        if 60 <= bpm_val <= 200:  # Reasonable BPM range
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
    """Sanitize a string for use as filename."""
    invalid_chars = '<>:"/\\|?*'
    result = name
    for char in invalid_chars:
        result = result.replace(char, "_")
    return result.strip()


def get_track_export_info(client: AbletonOSCClient, track_index: int) -> dict:
    """
    Get all info needed for exporting a track with proper naming.

    Returns dict with: track_name, group_name, key, bpm, suggested_filename
    """
    track_name = get_track_name(client, track_index)
    group_name = None
    key = None
    bpm = None

    # Check if track is in a group
    if get_track_is_grouped(client, track_index):
        group_idx = get_track_group_track_index(client, track_index)
        if group_idx is not None:
            group_name = get_track_name(client, group_idx)
            # Parse key/BPM from group name
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

    return {
        "track_name": track_name,
        "group_name": group_name,
        "key": key,
        "bpm": bpm,
        "suggested_filename": suggested_filename,
    }


# ===== QUERY TOOLS =====

@mcp.tool()
async def test_connection() -> str:
    """Test if Ableton Live is running and AbletonOSC is enabled."""
    client = get_client()
    if client.test_connection():
        tempo = get_tempo(client)
        count = get_track_count(client)
        return f"Connected to Ableton Live! Tempo: {tempo} BPM, Tracks: {count}"
    else:
        return "Could not connect. Make sure Ableton Live is running with AbletonOSC enabled in Preferences > Link/Tempo/MIDI > Control Surface."


@mcp.tool()
async def list_tracks(include_clips: bool = False) -> str:
    """
    List all tracks in the current Ableton Live session.

    Args:
        include_clips: If True, include clip count for each track

    Returns:
        Formatted list of tracks with their properties
    """
    client = get_client()
    count = get_track_count(client)

    if count == 0:
        return "No tracks found. Is a Live Set open?"

    lines = [f"Found {count} tracks:\n"]

    for i in range(count):
        name = get_track_name(client, i)
        is_group = get_track_is_foldable(client, i)
        muted = get_track_muted(client, i)

        prefix = "GROUP" if is_group else "     "
        status = " [MUTED]" if muted else ""

        line = f"[{i:3d}] {prefix} {name}{status}"

        if include_clips and not is_group:
            clips = get_arrangement_clips(client, i)
            if clips:
                line += f" ({len(clips)} clips)"

        lines.append(line)

    return "\n".join(lines)


@mcp.tool()
async def list_groups() -> str:
    """List all group tracks (folders) in the current Live session."""
    client = get_client()
    count = get_track_count(client)

    groups = []
    for i in range(count):
        if get_track_is_foldable(client, i):
            name = get_track_name(client, i)
            groups.append(f"[{i:3d}] {name}")

    if not groups:
        return "No groups found in this Live Set."

    return f"Found {len(groups)} groups:\n" + "\n".join(groups)


@mcp.tool()
async def get_track_info(track_index: int) -> str:
    """
    Get detailed information about a specific track.

    Args:
        track_index: The index of the track (0-based)

    Returns:
        Track details including name, type, mute status, and clips
    """
    client = get_client()
    count = get_track_count(client)

    if track_index < 0 or track_index >= count:
        return f"Invalid track index. Valid range: 0-{count-1}"

    name = get_track_name(client, track_index)
    is_group = get_track_is_foldable(client, track_index)
    muted = get_track_muted(client, track_index)
    clips = get_arrangement_clips(client, track_index)

    lines = [
        f"Track {track_index}: {name}",
        f"Type: {'Group' if is_group else 'Track'}",
        f"Muted: {muted}",
        f"Arrangement clips: {len(clips)}",
    ]

    if clips:
        first = clips[0]
        last = clips[-1]
        start = first['start_time']
        end = last['start_time'] + last['length']
        lines.append(f"Audio range: {start:.1f} - {end:.1f} beats")

    return "\n".join(lines)


@mcp.tool()
async def find_track(name: str) -> str:
    """
    Find tracks by name (partial match).

    Args:
        name: Text to search for in track names

    Returns:
        List of matching tracks
    """
    client = get_client()
    count = get_track_count(client)
    search = name.lower()

    matches = []
    for i in range(count):
        track_name = get_track_name(client, i)
        if search in track_name.lower():
            is_group = get_track_is_foldable(client, i)
            prefix = "GROUP" if is_group else "track"
            matches.append(f"[{i:3d}] {prefix}: {track_name}")

    if not matches:
        return f"No tracks found matching '{name}'"

    return f"Found {len(matches)} matches:\n" + "\n".join(matches)


# ===== CONTROL TOOLS =====

@mcp.tool()
async def select_track_by_index(track_index: int) -> str:
    """
    Select a track in Ableton Live.

    Args:
        track_index: The index of the track to select (0-based)

    Returns:
        Confirmation message
    """
    client = get_client()
    count = get_track_count(client)

    if track_index < 0 or track_index >= count:
        return f"Invalid track index. Valid range: 0-{count-1}"

    name = get_track_name(client, track_index)
    select_track(client, track_index)
    return f"Selected track {track_index}: {name}"


@mcp.tool()
async def set_export_range(start_beats: float, length_beats: float) -> str:
    """
    Set the loop/punch range for export.

    Args:
        start_beats: Start position in beats
        length_beats: Length in beats

    Returns:
        Confirmation with time info
    """
    client = get_client()
    tempo = get_tempo(client)

    set_loop_range(client, start_beats, length_beats)

    duration_sec = (length_beats / tempo) * 60
    end_beats = start_beats + length_beats

    return f"Set export range: {start_beats:.1f} - {end_beats:.1f} beats ({duration_sec:.1f} seconds at {tempo:.0f} BPM)"


# ===== EXPORT TOOLS (macOS only) =====

@mcp.tool()
async def export_selected_track(
    track_index: Optional[int] = None,
    custom_filename: Optional[str] = None,
) -> str:
    """
    Export a track using GUI automation with smart filename generation.

    Automatically generates filename from track name + key + BPM (parsed from group name).
    Example: "flute_Amin_143bpm.wav"

    IMPORTANT: Requires Accessibility permissions for Terminal/Python.
    macOS only.

    Args:
        track_index: Track to export (if None, exports currently selected track)
        custom_filename: Override the auto-generated filename

    Returns:
        Status message with filename used
    """
    if platform.system() != "Darwin":
        return "Export is only supported on macOS"

    client = get_client()

    # If track_index provided, get export info and select the track
    filename = custom_filename
    if track_index is not None:
        count = get_track_count(client)
        if track_index < 0 or track_index >= count:
            return f"Invalid track index. Valid range: 0-{count-1}"

        export_info = get_track_export_info(client, track_index)
        if not filename:
            filename = export_info["suggested_filename"]

        # Select the track
        select_track(client, track_index)
        time.sleep(0.3)
    else:
        # No track specified, use generic name
        if not filename:
            filename = f"export_{int(time.time())}"

    # Use the safe export function with full verification at each step
    success, message = safe_export_with_filename(filename)

    if not success:
        return f"Export failed: {message}"

    return message


@mcp.tool()
async def prepare_track_for_export(track_index: int) -> str:
    """
    Prepare a track for export by selecting it and setting the loop range
    based on its audio clips.

    Args:
        track_index: The index of the track to prepare

    Returns:
        Status with range info, ready for export_selected_track
    """
    client = get_client()
    count = get_track_count(client)

    if track_index < 0 or track_index >= count:
        return f"Invalid track index. Valid range: 0-{count-1}"

    name = get_track_name(client, track_index)
    clips = get_arrangement_clips(client, track_index)

    if not clips:
        return f"Track '{name}' has no arrangement clips to export"

    # Calculate range from clips
    start = clips[0]['start_time']
    end = clips[-1]['start_time'] + clips[-1]['length']
    length = end - start

    # Set range and select track
    set_loop_range(client, start, length)
    select_track(client, track_index)

    tempo = get_tempo(client)
    duration_sec = (length / tempo) * 60

    return f"Prepared '{name}' for export:\n- Range: {start:.1f} - {end:.1f} beats\n- Duration: {duration_sec:.1f} seconds\n- Track selected\n\nRun export_selected_track() to export."


@mcp.tool()
async def full_export(
    track_index: Optional[int] = None,
    output_folder: Optional[str] = None,
    custom_filename: Optional[str] = None,
) -> str:
    """
    Complete export workflow with full safety checks.

    This is the recommended way to export - it:
    1. Selects the track (if specified)
    2. Sets the loop range based on track clips
    3. Generates a smart filename (track_key_bpm)
    4. Verifies each step before proceeding
    5. Aborts safely if anything unexpected happens

    Args:
        track_index: Track to export (uses current selection if None)
        output_folder: Folder to save to (uses Ableton default if None)
        custom_filename: Override the auto-generated filename

    Returns:
        Status message with export result
    """
    if platform.system() != "Darwin":
        return "Export is only supported on macOS"

    client = get_client()
    filename = custom_filename
    track_name = "unknown"

    # If track_index provided, set up the track
    if track_index is not None:
        count = get_track_count(client)
        if track_index < 0 or track_index >= count:
            return f"Invalid track index. Valid range: 0-{count-1}"

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
        if not filename:
            filename = export_info["suggested_filename"]

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
        return f"✓ Exported '{track_name}' as {filename}.wav"
    else:
        return f"✗ Export failed: {message}"


if __name__ == "__main__":
    mcp.run()
