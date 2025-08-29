# iTerm2 MCP Server 🐒

A Model Context Protocol (MCP) server that lets you control iTerm2 through Python scripts. Because sometimes you need a little monkey magic to make your terminal dance!

## Features

- 🎭 **Create and manage tabs** - Because one tab is never enough
- 🎪 **Run commands** - Execute shell commands in any session
- 🎨 **Session management** - Split, resize, and organize your terminal like a pro
- 🎯 **Profile switching** - Change themes faster than a chameleon on a disco floor
- 📝 **Text manipulation** - Send text, clear screens, and more

## Installation

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Enable iTerm2 Python API:**
   - Open iTerm2
   - Go to Scripts → Manage → Install Python Runtime
   - Enable "Allow all apps to connect to iTerm2"

## Usage

### Running the Server

```bash
python iterm2_mcp_server.py
```

### Connecting from an MCP Client

Add this to your MCP client configuration:

```json
{
  "mcpServers": {
    "iterm2": {
      "command": "python",
      "args": ["path/to/iterm2_mcp_server.py"]
    }
  }
}
```

## Available Tools

- `create_tab` - Create a new tab with optional profile
- `create_session` - Create a new session in current tab
- `run_command` - Execute a command in the active session
- `send_text` - Send text to the active session
- `clear_screen` - Clear the current screen
- `list_profiles` - Get available iTerm2 profiles
- `switch_profile` - Change the profile of current session
- `get_session_info` - Get information about current session

## Example Usage

```python
# Create a new tab with a dark theme
await session.call_tool("create_tab", {"profile": "Dark"})

# Run a command
await session.call_tool("run_command", {"command": "ls -la"})

# Send some text
await session.call_tool("send_text", {"text": "echo 'Hello from MCP!'"})
```

## Requirements

- macOS (iTerm2 is macOS-only, sorry Windows friends!)
- iTerm2 with Python API enabled
- Python 3.8+

## License

MIT - Because sharing is caring! 🐒

---

*Made with 🐒 by your favorite coding monkey assistant* 