# Installation Guide 🐒

## Prerequisites

1. **macOS** - iTerm2 is macOS-only (sorry Windows friends!)
2. **iTerm2** - Download from [iterm2.com](https://iterm2.com/)
3. **Python 3.8+** - Because we're not savages
4. **iTerm2 Python API** - Enable this in iTerm2

## Step 1: Enable iTerm2 Python API

1. Open iTerm2
2. Go to **Scripts** → **Manage** → **Install Python Runtime**
3. Click **Install** if not already installed
4. Go to **Scripts** → **Manage** → **AutoLaunch**
5. Enable **Allow all apps to connect to iTerm2**

## Step 2: Install Dependencies

```bash
# Install the required packages
pip install -r requirements.txt

# Or install in development mode
pip install -e .
```

## Step 3: Test the Installation

```bash
# Run the test script
python test_iterm2_mcp.py
```

## Step 4: Configure Your MCP Client

Add this to your MCP client configuration (e.g., for Claude Desktop):

```json
{
  "mcpServers": {
    "iterm2": {
      "command": "python",
      "args": ["/full/path/to/iterm2_mcp_server.py"]
    }
  }
}
```

## Troubleshooting

### "Failed to connect to iTerm2"

- Make sure iTerm2 is running
- Verify Python API is enabled in iTerm2
- Check that "Allow all apps to connect to iTerm2" is enabled

### Import Errors

- Make sure all dependencies are installed: `pip install -r requirements.txt`
- Check your Python version: `python --version`

### Permission Errors

- Make sure the script is executable: `chmod +x iterm2_mcp_server.py`

## Quick Start

1. Start iTerm2
2. Run the server: `python iterm2_mcp_server.py`
3. In another terminal, test it: `python test_iterm2_mcp.py`

## Available Commands

Once connected, you can use these tools:

- `create_tab` - Create a new tab
- `create_session` - Create a new session
- `run_command` - Execute a command
- `send_text` - Send text to terminal
- `clear_screen` - Clear the screen
- `list_profiles` - List available profiles
- `switch_profile` - Change profile
- `get_session_info` - Get current session info

---

*Need help? Check the README.md or open an issue! 🐒* 