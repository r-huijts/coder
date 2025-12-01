# iTerm2 MCP Server AI Coding Agent 🐒

A Model Context Protocol (MCP) server that transforms iTerm2 into a powerful AI coding agent. It provides a structured toolkit for agents to interact with the terminal, manipulate the filesystem, and search code with precision.

This server is designed to be the bridge between a large language model's reasoning capabilities and the practical, hands-on tasks of software development.

## Core Capabilities

-   🧠 **Code Intelligence:** Perform structured, gitignore-aware code searches using `ripgrep`. Instead of parsing `grep` output, the agent receives clean JSON with file paths, line numbers, and matching content.
-   📂 **Precise Filesystem I/O:** Read, write, and perform surgical line-based edits on files. This avoids the ambiguity of `sed` or `echo` and allows the agent to safely manipulate code.
-   🖥️ **Full Terminal Control:** Create tabs, split panes, run commands, and read screen output. The agent has a visible, interactive workspace within iTerm2.
-   🤖 **Structured JSON API:** All tools return predictable JSON objects, making it easy for an agent to parse success/failure states and data without guessing.
-   🛡️ **Safety Features:** Automatic detection and handling of complex quoting, heredoc prevention, and unicode/emoji handling to prevent terminal state corruption.

## Installation

A complete step-by-step guide is available in [`INSTALL.md`](./INSTALL.md). The user-focused setup is:

1.  **Install Prerequisites:**
    You will need [Homebrew](https://brew.sh/) to install `ripgrep`.
    ```bash
    # Install ripgrep for the search_code tool
    brew install ripgrep
    ```

2.  **Download the Server:**
    Download or clone this repository to a permanent location on your computer.

3.  **Configure iTerm2:**
    - Open iTerm2.
    - Go to `Scripts > Manage > Install Python Runtime`.
    - Go to `Scripts > Manage > AutoLaunch` and ensure "Allow all apps to connect to iTerm2" is enabled.

## Usage

This server is designed to be run automatically by an MCP client, such as the Claude Desktop app.

Add the following configuration to your client's settings. **You must replace `/path/to/your/coder/iterm2_mcp_server.py` with the actual, absolute path** to the file you downloaded.

```json
"iterm2": {
  "command": "uvx",
  "args": [
    "--with", "mcp",
    "--with", "iterm2", 
    "python",
    "/path/to/your/coder/iterm2_mcp_server.py"
  ]
}
```

That's it. The MCP client will now handle starting the server for you.

## Safety Features

The server uses **Bracketed Paste Mode** for robust command execution:

### Bracketed Paste Mode
- All commands sent via `run_command` and `send_text` (by default) are wrapped in ANSI escape sequences (`\x1b[200~` and `\x1b[201~`)
- This tells the shell to treat the entire command as a single atomic paste operation
- **Zero shell interpretation** until the paste is complete - no premature execution, no buffer overflows
- Supports **heredocs, emojis, complex quoting, and long commands** without any special handling

### What This Means for Agents
- ✅ **Heredocs are fully supported**: Use them freely for multi-line file creation or scripts
- ✅ **Emojis are fully supported**: Unicode characters in commands work reliably
- ✅ **No length limits**: Long commands don't cause buffer issues
- ✅ **Complex quoting works**: Single quotes, double quotes, backticks - all safe
- ✅ **Readable execution**: Commands appear in the terminal exactly as written

### Best Practices
- **Still prefer specialized tools**: `write_file`, `read_file`, `edit_file` are safer and more reliable for file operations
- **Use heredocs wisely**: While supported, `write_file` is clearer for creating files

## Tool Reference

The following tools are available through the MCP server.

### Terminal Control

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `run_command` | `command: str`, `wait_for_output: bool = True`, `timeout: int = 10`, `require_confirmation: bool = False`, `working_directory: str = None`, `isolate_output: bool = False` | Executes a shell command using bracketed paste mode. **Fully supports heredocs, emojis, and complex quoting**. Long commands are handled safely without buffer issues. |
| `read_terminal_output` | `timeout: int = 5` | Reads the entire visible contents of the active iTerm2 screen. |
| `send_text` | `text: str`, `paste: bool = True` | Sends text to the terminal. By default uses bracketed paste mode for safe, atomic text insertion. Set `paste=False` to simulate individual keystrokes (slower, riskier). |
| `create_tab` | `profile: str = None` | Creates a new tab in the current iTerm2 window. |
| `create_session` | `profile: str = None` | Creates a new session (split pane) in the current tab. |
| `clear_screen` | | Clears the screen of the active session (like `Ctrl+L`). |
| `list_profiles` | | Retrieves a list of all available iTerm2 profiles. |
| `switch_profile` | `profile: str` | Switches the profile of the current iTerm2 session. |
| `get_session_info` | | Gets information about the current window, tab, and session IDs. |

### Filesystem I/O

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `read_file` | `file_path: str`, `start_line: int = None`, `end_line: int = None` | Reads a file, with options to specify a range of line numbers. |
| `write_file` | `file_path: str`, `content: str` | Writes content to a file, overwriting it if it exists or creating it if it doesn't. |
| `edit_file` | `file_path: str`, `start_line: int`, `end_line: int`, `new_content: str` | Replaces a specific block of lines in a file with new content. |
| `list_directory` | `path: str`, `recursive: bool = False` | Lists the contents of a directory, returning a structured list of files and subdirectories. |

### Code Intelligence

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `search_code` | `query: str`, `path: str = "."`, `case_sensitive: bool = True` | Searches for a string/regex in files using `ripgrep` and returns structured results (file, line number, content). |

---

*Made with 🐒 by your favorite coding monkey assistant* 
