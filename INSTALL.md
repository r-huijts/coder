# Installation Guide 🐒

## Prerequisites

1.  **macOS** - iTerm2 is macOS-only.
2.  **Homebrew** - The easiest way to install system dependencies. Install from [brew.sh](https://brew.sh/).
3.  **iTerm2** - Download from [iterm2.com](https://iterm2.com/).
4.  **Python 3.8+** - Check with `python3 --version`.
5.  **ripgrep** - A system dependency for the `search_code` tool. Install with `brew install ripgrep`.
6.  **iTerm2 Python API** - Must be enabled within iTerm2.

## Step 1: Install System Dependencies

Open your terminal and run the following command:
```bash
brew install ripgrep
```

## Step 2: Enable iTerm2 Python API

1. Open iTerm2
2. Go to **Scripts** → **Manage** → **Install Python Runtime**
3. Click **Install** if the runtime is not already installed.
4. Go to **Scripts** → **Manage** → **AutoLaunch** (or similar, depending on iTerm version)
5. Ensure **Allow all apps to connect to iTerm2** is checked.

## Step 3: Setup Project and Install Dependencies
```bash
# Clone the repository (if you haven't already)
# git clone ...
# cd iterm2-mcp-server

# Create a Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install the required Python packages
pip install -r requirements.txt
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
- `search_code` tool fails with a "'rg' command not found" error:
  - Make sure you have installed `ripgrep` via Homebrew: `brew install ripgrep`.

## Quick Start (Manual)

1. Start iTerm2.
2. Activate your virtual environment: `source venv/bin/activate`.
3. Run the server: `python iterm2_mcp_server.py`.

## Available Commands

Once connected via an MCP client, you can use these tools:

- `run_command`
- `read_terminal_output`
- `send_text`
- `create_tab`
- `create_session`
- `clear_screen`
- `list_profiles`
- `switch_profile`
- `get_session_info`
- `read_file`
- `write_file`
- `edit_file`
- `list_directory`
- `search_code`

---

*Need help? Check the README.md or open an issue! 🐒* 