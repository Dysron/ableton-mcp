"""
Export orchestrator - ties together OSC and GUI automation.
"""

import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from osc_client import AbletonOSCClient, select_track, set_loop_range, get_tempo
from track_analyzer import TrackAnalyzer, Group, Track, ViewType
from gui_automation import AbletonExportAutomation, activate_ableton


@dataclass
class ExportResult:
    """Result of an export operation."""
    track_name: str
    success: bool
    output_path: Optional[Path] = None
    error: Optional[str] = None


class AbletonExporter:
    """
    Orchestrates the export of tracks from Ableton Live.
    """

    def __init__(
        self,
        output_folder: Path,
        view: ViewType = ViewType.ARRANGEMENT,
        osc_host: str = "127.0.0.1",
    ):
        self.output_folder = Path(output_folder)
        self.view = view

        # Initialize OSC client
        print("Connecting to AbletonOSC...")
        self.osc_client = AbletonOSCClient(host=osc_host)

        if not self.osc_client.test_connection():
            raise ConnectionError(
                "Could not connect to AbletonOSC. "
                "Make sure Ableton Live is running with AbletonOSC enabled."
            )

        print("Connected to Ableton Live!")

        # Initialize track analyzer
        self.analyzer = TrackAnalyzer(self.osc_client, view=view)

        # Initialize GUI automation
        self.automation = AbletonExportAutomation(output_folder)

    def refresh(self) -> None:
        """Refresh track data from Live."""
        print("Analyzing track structure...")
        self.analyzer.refresh()

    def export_group(
        self,
        group_name: str,
        auto_range: bool = True,
        start_beats: Optional[float] = None,
        length_beats: Optional[float] = None,
        delay_between_exports: float = 2.0,
    ) -> list[ExportResult]:
        """
        Export all enabled tracks with audio from a group.

        Args:
            group_name: Name of the group to export from
            auto_range: Automatically determine time range from clips
            start_beats: Manual start position (if not auto_range)
            length_beats: Manual length (if not auto_range)
            delay_between_exports: Seconds to wait between track exports

        Returns:
            List of export results
        """
        self.refresh()

        # Find the group
        group = self.analyzer.find_group_by_name(group_name)
        if not group:
            print(f"ERROR: Could not find group '{group_name}'")
            print("Available groups:")
            for g in self.analyzer.groups:
                print(f"  - {g.track.name}")
            return []

        print(f"\nFound group: {group.track.name}")

        # Get enabled tracks with audio
        tracks_to_export = group.enabled_tracks_with_audio
        if not tracks_to_export:
            print("No enabled tracks with audio found in group")
            return []

        print(f"Tracks to export: {len(tracks_to_export)}")
        for track in tracks_to_export:
            print(f"  - {track.name}")

        # Determine time range
        if auto_range:
            start_beats = group.audio_start
            end_beats = group.audio_end
            if start_beats is None or end_beats is None:
                print("ERROR: Could not determine audio range")
                return []
            length_beats = end_beats - start_beats
        else:
            if start_beats is None or length_beats is None:
                print("ERROR: Must specify start_beats and length_beats when auto_range is False")
                return []

        tempo = get_tempo(self.osc_client)
        duration_seconds = (length_beats / tempo) * 60

        print(f"\nExport range: {start_beats:.1f} - {start_beats + length_beats:.1f} beats")
        print(f"Duration: {duration_seconds:.1f} seconds (at {tempo:.1f} BPM)")

        # Set the loop range for export
        print("Setting export range...")
        set_loop_range(self.osc_client, start_beats, length_beats)
        time.sleep(0.5)

        # Bring Ableton to foreground
        activate_ableton()
        time.sleep(0.5)

        # Export each track
        results = []
        for i, track in enumerate(tracks_to_export):
            print(f"\n[{i + 1}/{len(tracks_to_export)}] Exporting: {track.name}")

            # Select the track via OSC
            select_track(self.osc_client, track.index)
            time.sleep(0.3)

            # Trigger export via GUI automation
            success = self.automation.export_track(
                track_name=track.name,
                wait_for_completion=True,
                export_timeout=duration_seconds + 10,
            )

            results.append(ExportResult(
                track_name=track.name,
                success=success,
                output_path=self.output_folder / f"{track.name}.wav" if success else None,
            ))

            # Wait between exports
            if i < len(tracks_to_export) - 1:
                print(f"  Waiting {delay_between_exports}s before next export...")
                time.sleep(delay_between_exports)

        # Print summary
        print("\n" + "=" * 50)
        print("EXPORT SUMMARY")
        print("=" * 50)
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        print(f"Successful: {len(successful)}")
        print(f"Failed: {len(failed)}")

        if failed:
            print("\nFailed tracks:")
            for r in failed:
                print(f"  - {r.track_name}: {r.error or 'Unknown error'}")

        return results

    def export_track(
        self,
        track_name: str,
        auto_range: bool = True,
        start_beats: Optional[float] = None,
        length_beats: Optional[float] = None,
    ) -> ExportResult:
        """Export a single track by name."""
        self.refresh()

        track = self.analyzer.find_track_by_name(track_name)
        if not track:
            return ExportResult(
                track_name=track_name,
                success=False,
                error=f"Track '{track_name}' not found",
            )

        # Determine time range
        if auto_range:
            if track.audio_start is None or track.audio_end is None:
                return ExportResult(
                    track_name=track_name,
                    success=False,
                    error="Track has no audio clips",
                )
            start_beats = track.audio_start
            length_beats = track.audio_end - track.audio_start

        if start_beats is None or length_beats is None:
            return ExportResult(
                track_name=track_name,
                success=False,
                error="Could not determine export range",
            )

        # Set range and select track
        set_loop_range(self.osc_client, start_beats, length_beats)
        select_track(self.osc_client, track.index)
        time.sleep(0.5)

        # Export
        tempo = get_tempo(self.osc_client)
        duration_seconds = (length_beats / tempo) * 60

        success = self.automation.export_track(
            track_name=track.name,
            wait_for_completion=True,
            export_timeout=duration_seconds + 10,
        )

        return ExportResult(
            track_name=track.name,
            success=success,
            output_path=self.output_folder / f"{track.name}.wav" if success else None,
        )

    def list_groups(self) -> None:
        """List all groups in the Live set."""
        self.refresh()
        print("\nGroups in Live set:")
        for group in self.analyzer.groups:
            enabled_count = len(group.enabled_tracks_with_audio)
            print(f"  - {group.track.name} ({enabled_count} enabled tracks with audio)")

    def list_tracks(self) -> None:
        """List all tracks in the Live set."""
        self.refresh()
        self.analyzer.print_structure()

    def close(self) -> None:
        """Clean up resources."""
        self.osc_client.close()
