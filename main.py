#!/usr/bin/env python3
"""
Ableton Export Tool - CLI entry point.

Automates exporting individual tracks from Ableton Live sets.
"""

import argparse
import sys
from pathlib import Path

from track_analyzer import ViewType
from exporter import AbletonExporter


def main():
    parser = argparse.ArgumentParser(
        description="Export tracks from Ableton Live",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export all enabled tracks from a group
  python main.py --group "134 - Fmaj" --output ~/Desktop/stems/

  # Export from session view instead of arrangement
  python main.py --group "My Group" --view session --output ~/Desktop/stems/

  # Export a specific track
  python main.py --track "Bass" --output ~/Desktop/stems/

  # List all groups in the Live set
  python main.py --list-groups

  # List all tracks with structure
  python main.py --list-tracks

Prerequisites:
  1. Ableton Live running with AbletonOSC enabled
  2. macOS with Accessibility permissions for Terminal/Python
        """,
    )

    # Mode selection (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--group",
        type=str,
        help="Name of the group to export tracks from",
    )
    mode_group.add_argument(
        "--track",
        type=str,
        help="Name of a specific track to export",
    )
    mode_group.add_argument(
        "--list-groups",
        action="store_true",
        help="List all groups in the Live set",
    )
    mode_group.add_argument(
        "--list-tracks",
        action="store_true",
        help="List all tracks with structure",
    )

    # Export options
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="~/Desktop/ableton-exports",
        help="Output folder for exported files (default: ~/Desktop/ableton-exports)",
    )
    parser.add_argument(
        "--view",
        type=str,
        choices=["arrangement", "session"],
        default="arrangement",
        help="Which view to export from (default: arrangement)",
    )
    parser.add_argument(
        "--no-auto-range",
        action="store_true",
        help="Don't auto-detect time range from clips",
    )
    parser.add_argument(
        "--start",
        type=float,
        help="Start position in beats (requires --no-auto-range)",
    )
    parser.add_argument(
        "--length",
        type=float,
        help="Length in beats (requires --no-auto-range)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay between exports in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="AbletonOSC host (default: 127.0.0.1)",
    )

    args = parser.parse_args()

    # Validate arguments
    if args.no_auto_range and (args.start is None or args.length is None):
        parser.error("--no-auto-range requires --start and --length")

    # Determine view type
    view = ViewType.ARRANGEMENT if args.view == "arrangement" else ViewType.SESSION

    # Expand output path
    output_path = Path(args.output).expanduser()

    try:
        # Initialize exporter
        exporter = AbletonExporter(
            output_folder=output_path,
            view=view,
            osc_host=args.host,
        )

        # Execute requested mode
        if args.list_groups:
            exporter.list_groups()

        elif args.list_tracks:
            exporter.list_tracks()

        elif args.group:
            results = exporter.export_group(
                group_name=args.group,
                auto_range=not args.no_auto_range,
                start_beats=args.start,
                length_beats=args.length,
                delay_between_exports=args.delay,
            )

            # Exit with error if any exports failed
            if any(not r.success for r in results):
                sys.exit(1)

        elif args.track:
            result = exporter.export_track(
                track_name=args.track,
                auto_range=not args.no_auto_range,
                start_beats=args.start,
                length_beats=args.length,
            )

            if not result.success:
                print(f"ERROR: {result.error}")
                sys.exit(1)

        else:
            parser.print_help()
            print("\nPlease specify --group, --track, --list-groups, or --list-tracks")
            sys.exit(1)

        exporter.close()

    except ConnectionError as e:
        print(f"ERROR: {e}")
        print("\nMake sure:")
        print("  1. Ableton Live is running")
        print("  2. AbletonOSC is enabled in Preferences > Link/Tempo/MIDI")
        sys.exit(1)

    except KeyboardInterrupt:
        print("\nExport cancelled by user")
        sys.exit(130)

    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
