#!/usr/bin/env python3
"""
Ableton Live CLI - Command line interface for controlling Ableton Live.

Usage:
    ableton-cli status              Check connection to Ableton Live
    ableton-cli tracks              List all tracks
    ableton-cli groups              List all group tracks
    ableton-cli info <index>        Get info about a specific track
    ableton-cli find <name>         Find tracks by name
    ableton-cli select <index>      Select a track
    ableton-cli range <start> <len> Set export range in beats
    ableton-cli prepare <index>     Prepare track for export
    ableton-cli export [options]    Export a track

macOS only - uses AppleScript for GUI automation.
"""

import argparse
import platform
import sys
from typing import Optional

from core import (
    get_osc_client,
    check_connection,
    get_all_tracks,
    get_groups,
    get_track_details,
    find_tracks_by_name,
    select_track_by_index,
    set_export_range,
    prepare_track_for_export,
    export_track,
    TrackType,
)


# Exit codes
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_CONNECTION_FAILED = 2


def cmd_status(args: argparse.Namespace) -> int:
    """Check connection to Ableton Live."""
    client = get_osc_client()
    status = check_connection(client)

    print(status.message)
    return EXIT_SUCCESS if status.connected else EXIT_CONNECTION_FAILED


def cmd_tracks(args: argparse.Namespace) -> int:
    """List all tracks."""
    client = get_osc_client()
    status = check_connection(client)

    if not status.connected:
        print(f"Error: {status.message}", file=sys.stderr)
        return EXIT_CONNECTION_FAILED

    tracks = get_all_tracks(client, include_clips=args.clips)

    if not tracks:
        print("No tracks found. Is a Live Set open?")
        return EXIT_SUCCESS

    print(f"Found {len(tracks)} tracks:\n")
    for track in tracks:
        prefix = "GROUP" if track.track_type == TrackType.GROUP else "     "
        muted = " [MUTED]" if track.muted else ""
        clips = f" ({track.clip_count} clips)" if args.clips and track.clip_count > 0 else ""
        print(f"[{track.index:3d}] {prefix} {track.name}{muted}{clips}")

    return EXIT_SUCCESS


def cmd_groups(args: argparse.Namespace) -> int:
    """List all group tracks."""
    client = get_osc_client()
    status = check_connection(client)

    if not status.connected:
        print(f"Error: {status.message}", file=sys.stderr)
        return EXIT_CONNECTION_FAILED

    groups = get_groups(client)

    if not groups:
        print("No groups found in this Live Set.")
        return EXIT_SUCCESS

    print(f"Found {len(groups)} groups:\n")
    for group in groups:
        print(f"[{group.index:3d}] {group.name}")

    return EXIT_SUCCESS


def cmd_info(args: argparse.Namespace) -> int:
    """Get info about a specific track."""
    client = get_osc_client()
    status = check_connection(client)

    if not status.connected:
        print(f"Error: {status.message}", file=sys.stderr)
        return EXIT_CONNECTION_FAILED

    track = get_track_details(client, args.index)

    if track is None:
        print(f"Error: Invalid track index {args.index}", file=sys.stderr)
        return EXIT_ERROR

    print(f"Track {track.index}: {track.name}")
    print(f"Type: {track.track_type.value.capitalize()}")
    print(f"Muted: {track.muted}")
    print(f"Arrangement clips: {track.clip_count}")

    if track.audio_start is not None and track.audio_end is not None:
        print(f"Audio range: {track.audio_start:.1f} - {track.audio_end:.1f} beats")

    return EXIT_SUCCESS


def cmd_find(args: argparse.Namespace) -> int:
    """Find tracks by name."""
    client = get_osc_client()
    status = check_connection(client)

    if not status.connected:
        print(f"Error: {status.message}", file=sys.stderr)
        return EXIT_CONNECTION_FAILED

    matches = find_tracks_by_name(client, args.name)

    if not matches:
        print(f"No tracks found matching '{args.name}'")
        return EXIT_SUCCESS

    print(f"Found {len(matches)} matches:\n")
    for track in matches:
        prefix = "GROUP" if track.track_type == TrackType.GROUP else "track"
        print(f"[{track.index:3d}] {prefix}: {track.name}")

    return EXIT_SUCCESS


def cmd_select(args: argparse.Namespace) -> int:
    """Select a track."""
    client = get_osc_client()
    status = check_connection(client)

    if not status.connected:
        print(f"Error: {status.message}", file=sys.stderr)
        return EXIT_CONNECTION_FAILED

    success, message = select_track_by_index(client, args.index)
    print(message)
    return EXIT_SUCCESS if success else EXIT_ERROR


def cmd_range(args: argparse.Namespace) -> int:
    """Set export range."""
    client = get_osc_client()
    status = check_connection(client)

    if not status.connected:
        print(f"Error: {status.message}", file=sys.stderr)
        return EXIT_CONNECTION_FAILED

    message = set_export_range(client, args.start, args.length)
    print(message)
    return EXIT_SUCCESS


def cmd_prepare(args: argparse.Namespace) -> int:
    """Prepare track for export."""
    client = get_osc_client()
    status = check_connection(client)

    if not status.connected:
        print(f"Error: {status.message}", file=sys.stderr)
        return EXIT_CONNECTION_FAILED

    success, message = prepare_track_for_export(client, args.index)
    print(message)

    if success:
        print("\nRun 'ableton-cli export' to export the prepared track.")

    return EXIT_SUCCESS if success else EXIT_ERROR


def cmd_export(args: argparse.Namespace) -> int:
    """Export a track."""
    if platform.system() != "Darwin":
        print("Error: Export is only supported on macOS", file=sys.stderr)
        return EXIT_ERROR

    client = get_osc_client()
    status = check_connection(client)

    if not status.connected:
        print(f"Error: {status.message}", file=sys.stderr)
        return EXIT_CONNECTION_FAILED

    track_index: Optional[int] = args.track if args.track is not None else None

    result = export_track(
        client,
        track_index=track_index,
        output_folder=args.output,
        custom_filename=args.filename,
    )

    if result.success:
        print(f"✓ {result.message}")
    else:
        print(f"✗ {result.message}", file=sys.stderr)

    return EXIT_SUCCESS if result.success else EXIT_ERROR


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="ableton-cli",
        description="Control Ableton Live from the command line",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ableton-cli status                    Check connection
  ableton-cli tracks --clips            List tracks with clip counts
  ableton-cli find "bass"               Find tracks containing "bass"
  ableton-cli export --track 5          Export track 5 with auto-generated name
  ableton-cli export --track 5 -o ~/exports -f my_bass
                                        Export track 5 to ~/exports/my_bass.wav
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # status
    subparsers.add_parser("status", help="Check connection to Ableton Live")

    # tracks
    tracks_parser = subparsers.add_parser("tracks", help="List all tracks")
    tracks_parser.add_argument(
        "--clips", "-c",
        action="store_true",
        help="Include clip count for each track",
    )

    # groups
    subparsers.add_parser("groups", help="List all group tracks")

    # info
    info_parser = subparsers.add_parser("info", help="Get info about a specific track")
    info_parser.add_argument("index", type=int, help="Track index (0-based)")

    # find
    find_parser = subparsers.add_parser("find", help="Find tracks by name")
    find_parser.add_argument("name", help="Text to search for in track names")

    # select
    select_parser = subparsers.add_parser("select", help="Select a track")
    select_parser.add_argument("index", type=int, help="Track index (0-based)")

    # range
    range_parser = subparsers.add_parser("range", help="Set export range in beats")
    range_parser.add_argument("start", type=float, help="Start position in beats")
    range_parser.add_argument("length", type=float, help="Length in beats")

    # prepare
    prepare_parser = subparsers.add_parser("prepare", help="Prepare track for export")
    prepare_parser.add_argument("index", type=int, help="Track index (0-based)")

    # export
    export_parser = subparsers.add_parser("export", help="Export a track")
    export_parser.add_argument(
        "--track", "-t",
        type=int,
        help="Track index to export (uses current selection if not specified)",
    )
    export_parser.add_argument(
        "--output", "-o",
        help="Output folder (uses Ableton default if not specified)",
    )
    export_parser.add_argument(
        "--filename", "-f",
        help="Custom filename without extension (auto-generated if not specified)",
    )

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return EXIT_SUCCESS

    # Command dispatch
    commands = {
        "status": cmd_status,
        "tracks": cmd_tracks,
        "groups": cmd_groups,
        "info": cmd_info,
        "find": cmd_find,
        "select": cmd_select,
        "range": cmd_range,
        "prepare": cmd_prepare,
        "export": cmd_export,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)
    else:
        parser.print_help()
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
