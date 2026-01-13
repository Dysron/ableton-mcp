"""
AbletonOSC client wrapper for communicating with Ableton Live.
"""

import threading
from dataclasses import dataclass
from typing import Any, Optional
from pythonosc import udp_client, dispatcher, osc_server


@dataclass
class Clip:
    """Information about an arrangement clip."""
    name: str
    start_time: float
    length: float


class AbletonOSCClient:
    """
    Client for communicating with Ableton Live via AbletonOSC.

    AbletonOSC listens on port 11000 and replies on port 11001.
    """

    def __init__(self, host: str = "127.0.0.1", send_port: int = 11000, receive_port: int = 11001):
        self.host = host
        self.send_port = send_port
        self.receive_port = receive_port

        # OSC client for sending
        self.client = udp_client.SimpleUDPClient(host, send_port)

        # Response handling
        self._responses: dict[str, Any] = {}
        self._response_events: dict[str, threading.Event] = {}
        self._dispatcher = dispatcher.Dispatcher()
        self._dispatcher.set_default_handler(self._handle_response)

        # Start receiver server
        self._server: Optional[osc_server.ThreadingOSCUDPServer] = None
        self._server_thread: Optional[threading.Thread] = None
        self._start_receiver()

    def _start_receiver(self):
        """Start the OSC server to receive responses."""
        self._server = osc_server.ThreadingOSCUDPServer(
            (self.host, self.receive_port), self._dispatcher
        )
        self._server_thread = threading.Thread(target=self._server.serve_forever)
        self._server_thread.daemon = True
        self._server_thread.start()

    def _handle_response(self, address: str, *args):
        """Handle incoming OSC response."""
        self._responses[address] = args
        if address in self._response_events:
            self._response_events[address].set()

    def send(self, address: str, *args) -> None:
        """Send an OSC message without waiting for response."""
        self.client.send_message(address, list(args))

    def query(self, address: str, *args, timeout: float = 2.0) -> Optional[tuple]:
        """
        Send an OSC message and wait for response.

        Args:
            address: OSC address to send to
            *args: Arguments for the message
            timeout: How long to wait for response (seconds)

        Returns:
            Response tuple or None if timeout
        """
        # Set up response event
        event = threading.Event()
        self._response_events[address] = event
        self._responses.pop(address, None)

        # Send message
        self.client.send_message(address, list(args))

        # Wait for response
        if event.wait(timeout):
            return self._responses.get(address)
        return None

    def test_connection(self) -> bool:
        """Test if AbletonOSC is responding."""
        response = self.query("/live/test")
        return response is not None

    def close(self):
        """Shutdown the OSC server."""
        if self._server:
            self._server.shutdown()


# Convenience functions
def get_track_count(client: AbletonOSCClient) -> int:
    """Get the number of tracks in the Live set."""
    response = client.query("/live/song/get/num_tracks")
    return response[0] if response else 0


def get_track_name(client: AbletonOSCClient, track_index: int) -> str:
    """Get the name of a track. Response is (track_index, name)."""
    response = client.query("/live/track/get/name", track_index)
    return response[1] if response and len(response) > 1 else ""


def get_track_muted(client: AbletonOSCClient, track_index: int) -> bool:
    """Check if a track is muted. Response is (track_index, muted)."""
    response = client.query("/live/track/get/mute", track_index)
    return bool(response[1]) if response and len(response) > 1 else False


def get_track_is_grouped(client: AbletonOSCClient, track_index: int) -> bool:
    """Check if a track is inside a group. Response is (track_index, is_grouped)."""
    response = client.query("/live/track/get/is_grouped", track_index)
    return bool(response[1]) if response and len(response) > 1 else False


def get_track_group_track_index(client: AbletonOSCClient, track_index: int) -> Optional[int]:
    """Get the index of the group track that contains this track."""
    response = client.query("/live/track/get/group_track", track_index)
    if response and len(response) > 1:
        return response[1] if response[1] >= 0 else None
    return None


def get_track_is_foldable(client: AbletonOSCClient, track_index: int) -> bool:
    """Check if a track is a group (foldable). Response is (track_index, is_foldable)."""
    response = client.query("/live/track/get/is_foldable", track_index)
    return bool(response[1]) if response and len(response) > 1 else False


def get_arrangement_clips(client: AbletonOSCClient, track_index: int) -> list[Clip]:
    """
    Get all arrangement clips for a track.

    Returns list of Clip dataclass instances with: name, start_time, length

    Note: Response format is (track_index, clip1_value, clip2_value, ...)
    So actual clip data starts at index 1.
    """
    names = client.query("/live/track/get/arrangement_clips/name", track_index)
    starts = client.query("/live/track/get/arrangement_clips/start_time", track_index)
    lengths = client.query("/live/track/get/arrangement_clips/length", track_index)

    if not names or not starts or not lengths:
        return []

    # Skip index 0 which is the track_index, clip data starts at index 1
    clips = []
    for i in range(1, len(names)):
        clips.append(Clip(
            name=names[i] if i < len(names) else "",
            start_time=starts[i] if i < len(starts) else 0.0,
            length=lengths[i] if i < len(lengths) else 0.0,
        ))
    return clips


def get_session_clips(client: AbletonOSCClient, track_index: int) -> list[dict]:
    """
    Get all session clips for a track.

    Returns list of dicts with: slot_index, name, length
    """
    # Query how many clip slots
    response = client.query("/live/track/get/num_clip_slots", track_index)
    num_slots = response[0] if response else 0

    clips = []
    for slot_idx in range(num_slots):
        # Check if slot has clip
        has_clip = client.query("/live/clip_slot/get/has_clip", track_index, slot_idx)
        if has_clip and has_clip[0]:
            name = client.query("/live/clip/get/name", track_index, slot_idx)
            length = client.query("/live/clip/get/length", track_index, slot_idx)
            clips.append({
                "slot_index": slot_idx,
                "name": name[0] if name else "",
                "length": length[0] if length else 0,
            })
    return clips


def select_track(client: AbletonOSCClient, track_index: int) -> None:
    """Select a track in the Live UI."""
    client.send("/live/view/set/selected_track", track_index)


def set_loop_range(client: AbletonOSCClient, start_beats: float, length_beats: float) -> None:
    """Set the loop/punch range for export."""
    client.send("/live/song/set/loop_start", start_beats)
    client.send("/live/song/set/loop_length", length_beats)


def get_tempo(client: AbletonOSCClient) -> float:
    """Get the current tempo."""
    response = client.query("/live/song/get/tempo")
    return response[0] if response else 120.0
