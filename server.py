"""
Ableton MCP Server - Control Ableton Live via Model Context Protocol.

macOS only - uses AppleScript for GUI automation.
"""

import platform
import sys
from typing import Optional
from mcp.server.fastmcp import FastMCP

from core import (
    get_osc_client,
    check_connection as core_check_connection,
    get_all_tracks,
    get_groups,
    get_track_details,
    find_tracks_by_name,
    select_track_by_index,
    set_export_range,
    prepare_track_for_export,
    export_track,
    get_track_export_info,
    TrackType,
)

# Check platform
if platform.system() != "Darwin":
    print("Warning: Export features only work on macOS", file=sys.stderr)

# Initialize MCP server
mcp = FastMCP(
    "Ableton Live Controller",
    dependencies=["python-osc", "pyobjc"],
)


# ===== QUERY TOOLS =====

@mcp.tool()
async def check_connection() -> str:
    """Test if Ableton Live is running and AbletonOSC is enabled."""
    client = get_osc_client()
    status = core_check_connection(client)
    return status.message


@mcp.tool()
async def list_tracks(include_clips: bool = False) -> str:
    """
    List all tracks in the current Ableton Live session.

    Args:
        include_clips: If True, include clip count for each track

    Returns:
        Formatted list of tracks with their properties
    """
    client = get_osc_client()
    status = core_check_connection(client)

    if not status.connected:
        return status.message

    tracks = get_all_tracks(client, include_clips=include_clips)

    if not tracks:
        return "No tracks found. Is a Live Set open?"

    lines = [f"Found {len(tracks)} tracks:\n"]

    for track in tracks:
        prefix = "GROUP" if track.track_type == TrackType.GROUP else "     "
        muted = " [MUTED]" if track.muted else ""
        clips = f" ({track.clip_count} clips)" if include_clips and track.clip_count > 0 else ""
        lines.append(f"[{track.index:3d}] {prefix} {track.name}{muted}{clips}")

    return "\n".join(lines)


@mcp.tool()
async def list_groups() -> str:
    """List all group tracks (folders) in the current Live session."""
    client = get_osc_client()
    status = core_check_connection(client)

    if not status.connected:
        return status.message

    groups = get_groups(client)

    if not groups:
        return "No groups found in this Live Set."

    lines = [f"Found {len(groups)} groups:"]
    for group in groups:
        lines.append(f"[{group.index:3d}] {group.name}")

    return "\n".join(lines)


@mcp.tool()
async def get_track_info(track_index: int) -> str:
    """
    Get detailed information about a specific track.

    Args:
        track_index: The index of the track (0-based)

    Returns:
        Track details including name, type, mute status, and clips
    """
    client = get_osc_client()
    status = core_check_connection(client)

    if not status.connected:
        return status.message

    track = get_track_details(client, track_index)

    if track is None:
        return f"Invalid track index {track_index}"

    lines = [
        f"Track {track.index}: {track.name}",
        f"Type: {track.track_type.value.capitalize()}",
        f"Muted: {track.muted}",
        f"Arrangement clips: {track.clip_count}",
    ]

    if track.audio_start is not None and track.audio_end is not None:
        lines.append(f"Audio range: {track.audio_start:.1f} - {track.audio_end:.1f} beats")

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
    client = get_osc_client()
    status = core_check_connection(client)

    if not status.connected:
        return status.message

    matches = find_tracks_by_name(client, name)

    if not matches:
        return f"No tracks found matching '{name}'"

    lines = [f"Found {len(matches)} matches:"]
    for track in matches:
        prefix = "GROUP" if track.track_type == TrackType.GROUP else "track"
        lines.append(f"[{track.index:3d}] {prefix}: {track.name}")

    return "\n".join(lines)


# ===== CONTROL TOOLS =====

@mcp.tool()
async def select_track(track_index: int) -> str:
    """
    Select a track in Ableton Live.

    Args:
        track_index: The index of the track to select (0-based)

    Returns:
        Confirmation message
    """
    client = get_osc_client()
    status = core_check_connection(client)

    if not status.connected:
        return status.message

    success, message = select_track_by_index(client, track_index)
    return message


@mcp.tool()
async def set_loop_range(start_beats: float, length_beats: float) -> str:
    """
    Set the loop/punch range for export.

    Args:
        start_beats: Start position in beats
        length_beats: Length in beats

    Returns:
        Confirmation with time info
    """
    client = get_osc_client()
    status = core_check_connection(client)

    if not status.connected:
        return status.message

    return set_export_range(client, start_beats, length_beats)


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

    client = get_osc_client()
    status = core_check_connection(client)

    if not status.connected:
        return status.message

    result = export_track(
        client,
        track_index=track_index,
        custom_filename=custom_filename,
    )

    if result.success:
        return f"✓ {result.message}"
    else:
        return f"✗ {result.message}"


@mcp.tool()
async def prepare_for_export(track_index: int) -> str:
    """
    Prepare a track for export by selecting it and setting the loop range
    based on its audio clips.

    Args:
        track_index: The index of the track to prepare

    Returns:
        Status with range info, ready for export_selected_track
    """
    client = get_osc_client()
    status = core_check_connection(client)

    if not status.connected:
        return status.message

    success, message = prepare_track_for_export(client, track_index)

    if success:
        return f"{message}\n\nRun export_selected_track() to export."
    else:
        return message


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

    client = get_osc_client()
    status = core_check_connection(client)

    if not status.connected:
        return status.message

    result = export_track(
        client,
        track_index=track_index,
        output_folder=output_folder,
        custom_filename=custom_filename,
    )

    if result.success:
        return f"✓ {result.message}"
    else:
        return f"✗ {result.message}"


if __name__ == "__main__":
    mcp.run()
