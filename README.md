# Ableton MCP

MCP (Model Context Protocol) server for controlling Ableton Live. Query tracks, analyze sessions, and export stems via AI assistants like Claude.

**macOS only** - Uses AppleScript for GUI automation.

## Features

### Query Tools
- `test_connection` - Verify Ableton Live and AbletonOSC are running
- `list_tracks` - List all tracks with optional clip counts
- `list_groups` - List all group/folder tracks
- `get_track_info` - Get detailed info about a specific track
- `find_track` - Search tracks by name

### Control Tools
- `select_track_by_index` - Select a track in Live
- `set_export_range` - Set the loop/punch range for export

### Export Tools (macOS only)
- `prepare_track_for_export` - Select track and set range from clips
- `export_selected_track` - Trigger export via GUI automation

## Requirements

- macOS (for export features)
- Python 3.10+
- Ableton Live 11+ with [AbletonOSC](https://github.com/ideoforms/AbletonOSC) installed
- Accessibility permissions for Terminal/Python (for export)

## Installation

### 1. Install AbletonOSC

```bash
cd ~/Downloads
git clone https://github.com/ideoforms/AbletonOSC.git
cp -r AbletonOSC ~/Music/Ableton/User\ Library/Remote\ Scripts/
```

Then in Ableton Live:
1. Preferences > Link/Tempo/MIDI
2. Control Surface > Select "AbletonOSC"

### 2. Install ableton-mcp

```bash
cd ~/mcps/src/ableton-mcp
pip install -e .
```

### 3. Configure Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ableton": {
      "command": "python",
      "args": ["-m", "server"],
      "cwd": "/path/to/ableton-mcp"
    }
  }
}
```

### 4. Grant Accessibility Permissions (for export)

System Preferences > Privacy & Security > Accessibility > Add Terminal (or your Python environment)

## Usage Examples

```
"List all tracks in my Ableton session"
"Find tracks containing 'bass'"
"Prepare track 57 for export"
"Export the selected track"
```

## Architecture

```
┌─────────────┐       OSC        ┌─────────────┐
│  MCP Server │ ───────────────▶ │  Ableton    │
│  (FastMCP)  │ ◀─────────────── │  Live       │
└─────────────┘    port 11000    └─────────────┘
       │
       │ AppleScript (export only)
       ▼
┌─────────────┐
│  GUI Auto   │
│  (macOS)    │
└─────────────┘
```

## Limitations

- **Export is macOS only** - Uses AppleScript for GUI automation
- Export requires Accessibility permissions
- AbletonOSC must be enabled each time Live starts

## Credits

- Uses [AbletonOSC](https://github.com/ideoforms/AbletonOSC) for Live communication
- Built with [FastMCP](https://github.com/jlowin/fastmcp)

## License

MIT
