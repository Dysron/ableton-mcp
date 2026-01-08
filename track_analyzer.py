"""
Track analyzer for querying Ableton Live session structure.
"""

from dataclasses import dataclass
from typing import Optional
from enum import Enum

from osc_client import (
    AbletonOSCClient,
    get_track_count,
    get_track_name,
    get_track_muted,
    get_track_is_grouped,
    get_track_group_track_index,
    get_track_is_foldable,
    get_arrangement_clips,
    get_session_clips,
)


class ViewType(Enum):
    ARRANGEMENT = "arrangement"
    SESSION = "session"


@dataclass
class Clip:
    """Represents an audio/MIDI clip."""
    name: str
    start_time: float  # In beats
    length: float  # In beats
    slot_index: Optional[int] = None  # For session view


@dataclass
class Track:
    """Represents a track in the Live set."""
    index: int
    name: str
    is_muted: bool
    is_group: bool
    is_grouped: bool
    group_track_index: Optional[int]
    clips: list[Clip]

    @property
    def is_enabled(self) -> bool:
        """Track is enabled if not muted."""
        return not self.is_muted

    @property
    def has_audio(self) -> bool:
        """Track has audio if it has clips."""
        return len(self.clips) > 0

    @property
    def audio_start(self) -> Optional[float]:
        """Earliest clip start time in beats."""
        if not self.clips:
            return None
        return min(clip.start_time for clip in self.clips)

    @property
    def audio_end(self) -> Optional[float]:
        """Latest clip end time in beats."""
        if not self.clips:
            return None
        return max(clip.start_time + clip.length for clip in self.clips)


@dataclass
class Group:
    """Represents a group track and its contents."""
    track: Track
    child_tracks: list[Track]

    @property
    def audio_start(self) -> Optional[float]:
        """Earliest audio start across all child tracks."""
        starts = [t.audio_start for t in self.child_tracks if t.audio_start is not None]
        return min(starts) if starts else None

    @property
    def audio_end(self) -> Optional[float]:
        """Latest audio end across all child tracks."""
        ends = [t.audio_end for t in self.child_tracks if t.audio_end is not None]
        return max(ends) if ends else None

    @property
    def enabled_tracks_with_audio(self) -> list[Track]:
        """Get all enabled child tracks that have audio."""
        return [t for t in self.child_tracks if t.is_enabled and t.has_audio]


class TrackAnalyzer:
    """Analyzes the track structure of an Ableton Live set."""

    def __init__(self, client: AbletonOSCClient, view: ViewType = ViewType.ARRANGEMENT):
        self.client = client
        self.view = view
        self._tracks: list[Track] = []
        self._groups: list[Group] = []

    def refresh(self) -> None:
        """Refresh the track list from Live."""
        self._tracks = []
        self._groups = []

        num_tracks = get_track_count(self.client)
        print(f"Found {num_tracks} tracks")

        # First pass: build all tracks
        for i in range(num_tracks):
            track = self._build_track(i)
            self._tracks.append(track)

        # Second pass: build groups
        for track in self._tracks:
            if track.is_group:
                children = [t for t in self._tracks if t.group_track_index == track.index]
                self._groups.append(Group(track=track, child_tracks=children))

    def _build_track(self, index: int) -> Track:
        """Build a Track object from Live data."""
        name = get_track_name(self.client, index)
        is_muted = get_track_muted(self.client, index)
        is_grouped = get_track_is_grouped(self.client, index)
        group_track_index = get_track_group_track_index(self.client, index)
        is_group = get_track_is_foldable(self.client, index)

        # Get clips based on view
        if self.view == ViewType.ARRANGEMENT:
            clip_data = get_arrangement_clips(self.client, index)
            clips = [
                Clip(
                    name=c["name"],
                    start_time=c["start_time"],
                    length=c["length"],
                )
                for c in clip_data
            ]
        else:
            clip_data = get_session_clips(self.client, index)
            clips = [
                Clip(
                    name=c["name"],
                    start_time=0,  # Session clips don't have arrangement position
                    length=c["length"],
                    slot_index=c["slot_index"],
                )
                for c in clip_data
            ]

        return Track(
            index=index,
            name=name,
            is_muted=is_muted,
            is_group=is_group,
            is_grouped=is_grouped,
            group_track_index=group_track_index,
            clips=clips,
        )

    @property
    def tracks(self) -> list[Track]:
        """Get all tracks."""
        return self._tracks

    @property
    def groups(self) -> list[Group]:
        """Get all groups."""
        return self._groups

    def find_group_by_name(self, name: str) -> Optional[Group]:
        """Find a group by name (case-insensitive partial match)."""
        name_lower = name.lower()
        for group in self._groups:
            if name_lower in group.track.name.lower():
                return group
        return None

    def find_track_by_name(self, name: str) -> Optional[Track]:
        """Find a track by name (case-insensitive partial match)."""
        name_lower = name.lower()
        for track in self._tracks:
            if name_lower in track.name.lower():
                return track
        return None

    def print_structure(self) -> None:
        """Print the track structure for debugging."""
        print("\n=== Track Structure ===\n")

        for track in self._tracks:
            indent = "  " if track.is_grouped else ""
            group_marker = "[GROUP]" if track.is_group else ""
            muted_marker = "[MUTED]" if track.is_muted else ""
            clip_info = f"({len(track.clips)} clips)" if track.clips else "(no clips)"

            print(f"{indent}{track.index}: {track.name} {group_marker} {muted_marker} {clip_info}")

            if track.clips and not track.is_group:
                for clip in track.clips:
                    print(f"{indent}    - {clip.name}: {clip.start_time:.1f} - {clip.start_time + clip.length:.1f} beats")

        print("\n=== Groups ===\n")
        for group in self._groups:
            enabled_with_audio = group.enabled_tracks_with_audio
            print(f"{group.track.name}:")
            print(f"  Children: {len(group.child_tracks)}")
            print(f"  Enabled with audio: {len(enabled_with_audio)}")
            if group.audio_start is not None:
                print(f"  Audio range: {group.audio_start:.1f} - {group.audio_end:.1f} beats")
            print()
