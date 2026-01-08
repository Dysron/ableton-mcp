"""
Ableton MCP Server - Control Ableton Live via Model Context Protocol.

macOS only - uses AppleScript for GUI automation.
"""

import sys
import platform
from typing import Optional
from mcp.server.fastmcp import FastMCP

from osc_client import (
    AbletonOSCClient,
    get_track_count,
    get_track_name,
    get_track_muted,
    get_track_is_foldable,
    get_track_is_grouped,
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
async def export_selected_track(output_folder: str = "~/Desktop/ableton-exports") -> str:
    """
    Export the currently selected track using GUI automation.

    IMPORTANT: Requires Accessibility permissions for Terminal/Python.
    macOS only.

    Args:
        output_folder: Where to save the exported file

    Returns:
        Status message
    """
    if platform.system() != "Darwin":
        return "Export is only supported on macOS"

    # Activate Ableton
    if not activate_ableton():
        return "Could not activate Ableton Live. Is it running?"

    # Open export dialog (Cmd+Shift+R)
    if not open_export_dialog():
        return "Could not open export dialog. Check Accessibility permissions in System Preferences > Privacy & Security > Accessibility"

    # Press Enter to start export with current settings
    import time
    time.sleep(1.5)
    press_enter()

    return f"Export triggered. Check {output_folder} for the output file. Note: You may need to manually set the output location in the save dialog."


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


if __name__ == "__main__":
    mcp.run()
