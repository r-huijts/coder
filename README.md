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

The server includes several safety mechanisms to prevent terminal state corruption:

### Heredoc Prevention
- **Heredoc operators (`<<`) are explicitly rejected** in `run_command` to prevent the terminal from getting stuck waiting for delimiters
- Commands containing `<<` will return an error directing the agent to use `write_file` instead for file creation

### Automatic Quote Handling
- Commands with complex quoting patterns (unmatched quotes, mixed quote types with special characters) are automatically detected
- These commands are safely wrapped using `bash -c $'...'` syntax which properly handles unicode, emojis, and special characters
- Commands remain **human-readable** in the terminal while being safe to execute

### Best Practices for Agents
- **Avoid emojis in commands**: Use plain ASCII text instead (e.g., `[OK]` instead of `✅`)
- **Use `write_file` for file creation**: Never use heredocs or `cat > file <<EOF` patterns
- **Prefer specialized tools**: Use `write_file`, `read_file`, `edit_file` instead of shell redirection

## Tool Reference

The following tools are available through the MCP server.

### Terminal Control

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `run_command` | `command: str`, `wait_for_output: bool = True`, `timeout: int = 10`, `use_base64: bool = False`, `require_confirmation: bool = False` | Executes a shell command in the active iTerm2 session. Automatically handles complex quoting safely. **Heredocs (`<<`) are rejected** - use `write_file` for file creation. Avoid emojis - use ASCII text like `[OK]` instead. |
| `read_terminal_output` | `timeout: int = 5` | Reads the entire visible contents of the active iTerm2 screen. |
| `send_text` | `text: str`, `force: bool = False` | Sends a string of text to the active session without adding a newline. Validates for heredoc patterns to prevent terminal state corruption. Use `force=True` to bypass validation if needed. |
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
