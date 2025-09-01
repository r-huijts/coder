#!/usr/bin/env python3
"""
iTerm2 MCP Server using FastMCP
A Model Context Protocol server for controlling iTerm2
"""

import json
import asyncio
import os
import subprocess
import sys
import functools
import shutil
from typing import Optional

import iterm2
from mcp.server.fastmcp import FastMCP


# Create the FastMCP server
mcp = FastMCP("iTerm2")


async def connect_to_iterm2():
    """
    Creates an iTerm2 connection and returns a context dictionary.
    """
    try:
        connection = await iterm2.Connection.async_create()
        app = await iterm2.async_get_app(connection)
        window = app.current_window
        tab = window.current_tab if window else None
        session = tab.current_session if tab else None
        
        return {
            "connection": connection,
            "app": app,
            "window": window,
            "tab": tab,
            "session": session,
            "error": None
        }
    except Exception as e:
        return {"error": f"iTerm2 connection failed: {str(e)}"}


@mcp.tool()
async def create_tab(profile: Optional[str] = None) -> str:
    """
    Creates a new tab in the current iTerm2 window.

    Args:
        profile (Optional[str]): The name of the profile to use for the new tab. 
                                 If not provided, the default profile is used.

    Returns:
        str: A JSON string containing the new window, tab, and session IDs.
    """
    ctx = await connect_to_iterm2()
    if ctx["error"]:
        return json.dumps({"success": False, "error": ctx["error"]}, indent=2)

    connection = ctx["connection"]
    if profile:
        profile_obj = await iterm2.Profile.async_get(connection, [profile])
        if profile_obj:
            window = await iterm2.Window.async_create(connection, profile=profile_obj[0])
        else:
            window = await iterm2.Window.async_create(connection)
    else:
        window = await iterm2.Window.async_create(connection)
    
    tab = window.current_tab
    session = tab.current_session
    
    result = {
        "success": True,
        "window_id": window.window_id,
        "tab_id": tab.tab_id,
        "session_id": session.session_id,
        "message": f"Created new tab with session {session.session_id}"
    }
    
    return json.dumps(result, indent=2)


@mcp.tool()
async def create_session(profile: Optional[str] = None) -> str:
    """
    Creates a new session (split pane) in the current iTerm2 tab.

    Args:
        profile (Optional[str]): The name of the profile to use for the new session.
                                 If not provided, the default profile is used.

    Returns:
        str: A JSON string containing the new session ID.
    """
    ctx = await connect_to_iterm2()
    if ctx["error"]:
        return json.dumps({"success": False, "error": ctx["error"]}, indent=2)

    connection, tab = ctx["connection"], ctx["tab"]
    if not tab:
        return json.dumps({"success": False, "error": "No active iTerm2 tab found."}, indent=2)

    if profile:
        profile_obj = await iterm2.Profile.async_get(connection, [profile])
        if profile_obj:
            session = await tab.async_create_session(profile=profile_obj[0])
        else:
            session = await tab.async_create_session()
    else:
        session = await tab.async_create_session()
    
    result = {
        "success": True,
        "session_id": session.session_id,
        "message": f"Created new session {session.session_id}"
    }
    
    return json.dumps(result, indent=2)


@mcp.tool()
async def run_command(command: str, wait_for_output: bool = True, timeout: int = 10, require_confirmation: bool = False) -> str:
    """
    Runs a command in the active iTerm2 session.

    Note: For writing content to files, please use the `write_file` tool instead of shell
    commands like `echo`, `cat`, or `heredoc`. The `write_file` tool is more reliable
    and the preferred method for file creation.

    Pro-tip: For safer file modifications, use `git` commands to stage and commit
    changes, creating a safety net for your work.

    Args:
        command (str): The command to execute.
        wait_for_output (bool): If True, waits for the command to finish and captures the output.
                                Defaults to True.
        timeout (int): The maximum time in seconds to wait for output. Defaults to 10.
        require_confirmation (bool): If True, allows potentially destructive commands to run.
                                     Defaults to False.

    Returns:
        str: A JSON string containing the execution status and output if captured.
    """
    ctx = await connect_to_iterm2()
    if ctx["error"]:
        return json.dumps({"success": False, "error": ctx["error"]}, indent=2)

    DANGEROUS_COMMANDS = ["rm ", "dd ", "mkfs ", "shutdown ", "reboot "]
    if any(cmd in command for cmd in DANGEROUS_COMMANDS) and not require_confirmation:
        return json.dumps({
            "success": False,
            "error": "This command is potentially destructive. Set `require_confirmation=True` to proceed."
        }, indent=2)

    session = ctx["session"]
    if not session:
        return json.dumps({"success": False, "error": "No active iTerm2 session found."}, indent=2)

    # Encode the command in base64 to prevent shell interpretation issues
    import base64
    encoded_command = base64.b64encode(command.encode('utf-8')).decode('utf-8')
    
    # Send the command to be decoded and executed by the shell
    await session.async_send_text(f"echo '{encoded_command}' | base64 --decode | /bin/zsh\n")
    
    result = {
        "success": True,
        "command": command,
        "session_id": session.session_id,
        "message": f"Executed command: {command}"
    }
    
    # If requested, wait for and read output
    if wait_for_output:
        try:
            # Wait a bit for the command to start
            await asyncio.sleep(0.5)
            
            # Read the output with timeout
            output = await asyncio.wait_for(
                session.async_get_screen_contents(),
                timeout=timeout
            )
            
            # Get the current screen contents
            screen = await session.async_get_screen_contents()
            if screen:
                # Extract the text content using the correct API
                output_text = ""
                for i in range(screen.number_of_lines):
                    line = screen.line(i)
                    if line.string:
                        output_text += line.string + "\n"
                
                result["output"] = output_text.strip()
                result["output_length"] = len(output_text)
                result["message"] = f"Executed command: {command} (output captured)"
            else:
                result["output"] = ""
                result["message"] = f"Executed command: {command} (no output captured)"
                
        except asyncio.TimeoutError:
            result["output"] = ""
            result["error"] = f"Timeout waiting for command output after {timeout} seconds"
            result["message"] = f"Executed command: {command} (timeout waiting for output)"
        except Exception as e:
            result["output"] = ""
            result["error"] = f"Failed to read output: {str(e)}"
            result["message"] = f"Executed command: {command} (failed to read output)"
    
    return json.dumps(result, indent=2)


@mcp.tool()
async def send_text(text: str) -> str:
    """
    Sends a string of text to the active iTerm2 session without adding a newline.

    Args:
        text (str): The text to send to the terminal.

    Returns:
        str: A JSON string confirming the text was sent.
    """
    ctx = await connect_to_iterm2()
    if ctx["error"]:
        return json.dumps({"success": False, "error": ctx["error"]}, indent=2)

    session = ctx["session"]
    if not session:
        return json.dumps({"success": False, "error": "No active iTerm2 session found."}, indent=2)

    await session.async_send_text(text)
    
    result = {
        "success": True,
        "text": text,
        "session_id": session.session_id,
        "message": f"Sent text: {text}"
    }
    
    return json.dumps(result, indent=2)


@mcp.tool()
async def read_terminal_output(timeout: int = 5) -> str:
    """
    Reads the entire visible contents of the active iTerm2 session's screen.

    Args:
        timeout (int): The maximum time in seconds to wait for the screen contents. Defaults to 5.

    Returns:
        str: A JSON string containing the captured terminal output.
    """
    ctx = await connect_to_iterm2()
    if ctx["error"]:
        return json.dumps({"success": False, "error": ctx["error"]}, indent=2)

    session = ctx["session"]
    if not session:
        return json.dumps({"success": False, "error": "No active iTerm2 session found."}, indent=2)

    try:
        # Get the current screen contents
        screen = await asyncio.wait_for(
            session.async_get_screen_contents(),
            timeout=timeout
        )
        
        if screen:
            # Extract the text content using the correct API
            output_text = ""
            for i in range(screen.number_of_lines):
                line = screen.line(i)
                if line.string:
                    output_text += line.string + "\n"
            
            result = {
                "success": True,
                "output": output_text.strip(),
                "output_length": len(output_text),
                "session_id": session.session_id,
                "message": f"Read terminal output ({len(output_text)} characters)"
            }
        else:
            result = {
                "success": True,
                "output": "",
                "output_length": 0,
                "session_id": session.session_id,
                "message": "No terminal output available"
            }
        
        return json.dumps(result, indent=2)
    except asyncio.TimeoutError:
        return json.dumps({
            "success": False,
            "error": f"Timeout reading terminal output after {timeout} seconds"
        }, indent=2)


@mcp.tool()
async def clear_screen() -> str:
    """
    Clears the screen of the active iTerm2 session.
    
    This is equivalent to pressing Ctrl+L.

    Returns:
        str: A JSON string confirming the screen was cleared.
    """
    ctx = await connect_to_iterm2()
    if ctx["error"]:
        return json.dumps({"success": False, "error": ctx["error"]}, indent=2)

    session = ctx["session"]
    if not session:
        return json.dumps({"success": False, "error": "No active iTerm2 session found."}, indent=2)

    await session.async_send_text("\x0c")  # Form feed character
    
    result = {
        "success": True,
        "session_id": session.session_id,
        "message": "Screen cleared"
    }
    
    return json.dumps(result, indent=2)


@mcp.tool()
async def list_profiles() -> str:
    """
    Retrieves a list of all available iTerm2 profiles.

    Returns:
        str: A JSON string containing a list of profile names.
    """
    ctx = await connect_to_iterm2()
    if ctx["error"]:
        return json.dumps({"success": False, "error": ctx["error"]}, indent=2)

    connection = ctx["connection"]
    profiles = await iterm2.Profile.async_get(connection)
    profile_list = [profile.name for profile in profiles]
    
    result = {
        "success": True,
        "profiles": profile_list,
        "count": len(profile_list),
        "message": f"Found {len(profile_list)} profiles"
    }
    
    return json.dumps(result, indent=2)


@mcp.tool()
async def switch_profile(profile: str) -> str:
    """
    Switches the profile of the current iTerm2 session.

    Args:
        profile (str): The name of the profile to switch to.

    Returns:
        str: A JSON string confirming the profile switch.
    """
    ctx = await connect_to_iterm2()
    if ctx["error"]:
        return json.dumps({"success": False, "error": ctx["error"]}, indent=2)

    connection, session = ctx["connection"], ctx["session"]
    if not session:
        return json.dumps({"success": False, "error": "No active iTerm2 session found."}, indent=2)

    profile_obj = await iterm2.Profile.async_get(connection, [profile])
    if not profile_obj:
        return json.dumps({"success": False, "error": f"Profile '{profile}' not found"}, indent=2)
    
    await session.async_set_profile(profile_obj[0])
    
    result = {
        "success": True,
        "profile": profile,
        "session_id": session.session_id,
        "message": f"Switched to profile: {profile}"
    }
    
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_session_info() -> str:
    """
    Gets information about the current iTerm2 window, tab, and session.

    Returns:
        str: A JSON string containing the window, tab, and session IDs.
    """
    ctx = await connect_to_iterm2()
    if ctx["error"]:
        return json.dumps({"success": False, "error": ctx["error"]}, indent=2)

    window, tab, session = ctx["window"], ctx["tab"], ctx["session"]
    if not (window and tab and session):
        return json.dumps({"success": False, "error": "Could not retrieve complete session info."}, indent=2)

    result = {
        "success": True,
        "window_id": window.window_id,
        "tab_id": tab.tab_id,
        "session_id": session.session_id,
        "message": f"Current session: {session.session_id}"
    }
    
    return json.dumps(result, indent=2)


@mcp.tool()
async def write_file(file_path: str, content: str, require_confirmation: bool = False) -> str:
    """
    Writes content to a specified file on the local filesystem.

    This is the **preferred** and most reliable method for creating or overwriting files.
    It uses standard Python file I/O and should be used instead of shell
    commands like 'echo' or 'heredoc' via the `run_command` tool.

    Pro-tip: For safer file modifications, use `git` commands to stage and commit
    changes, creating a safety net for your work.

    Args:
        file_path (str): The absolute or relative path to the file.
        content (str): The content to write to the file.
        require_confirmation (bool): If True, allows overwriting an existing file.
                                     Defaults to False.

    Returns:
        str: A JSON string confirming success or reporting an error.
    """
    if os.path.exists(file_path) and not require_confirmation:
        return json.dumps({
            "success": False,
            "error": f"File '{file_path}' already exists. Set `require_confirmation=True` to overwrite."
        }, indent=2)

    try:
        with open(file_path, "w") as f:
            f.write(content)
        result = {
            "success": True,
            "file_path": file_path,
            "content_length": len(content),
            "message": f"Successfully wrote {len(content)} characters to {file_path}"
        }
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


@mcp.tool()
async def read_file(file_path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
    """
    Reads the contents of a file, optionally slicing by line numbers.

    Args:
        file_path (str): The path to the file to read.
        start_line (Optional[int]): The 1-indexed line number to start reading from.
        end_line (Optional[int]): The 1-indexed line number to stop reading at (inclusive).

    Returns:
        str: A JSON string with the file content or an error.
    """
    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()
        
        if start_line is not None and end_line is not None:
            # Adjust for 0-based indexing and slice
            content = "".join(lines[start_line - 1:end_line])
        elif start_line is not None:
            content = "".join(lines[start_line - 1:])
        else:
            content = "".join(lines)
            
        result = {
            "success": True,
            "file_path": file_path,
            "content": content
        }
        return json.dumps(result, indent=2)
    except FileNotFoundError:
        return json.dumps({"success": False, "error": f"File not found: {file_path}"}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


@mcp.tool()
async def list_directory(path: str, recursive: bool = False) -> str:
    """
    Lists the contents of a directory in a structured format.

    Args:
        path (str): The path to the directory to list.
        recursive (bool): If True, lists contents recursively. Defaults to False.

    Returns:
        str: A JSON string with a list of files and directories, or an error.
    """
    try:
        if not os.path.isdir(path):
            return json.dumps({"success": False, "error": f"Not a directory: {path}"}, indent=2)

        contents = []
        if recursive:
            for root, dirs, files in os.walk(path):
                for name in files:
                    full_path = os.path.join(root, name)
                    contents.append({"name": name, "path": full_path, "is_directory": False})
                for name in dirs:
                    full_path = os.path.join(root, name)
                    contents.append({"name": name, "path": full_path, "is_directory": True})
        else:
            for name in os.listdir(path):
                full_path = os.path.join(path, name)
                is_dir = os.path.isdir(full_path)
                contents.append({"name": name, "path": full_path, "is_directory": is_dir})
        
        result = {
            "success": True,
            "path": path,
            "contents": contents
        }
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


@mcp.tool()
async def edit_file(file_path: str, start_line: int, end_line: int, new_content: str, require_confirmation: bool = False) -> str:
    """
    Replaces a specific block of lines in a file with new content.

    Use this tool for targeted modifications of existing files. For creating new files
    or completely overwriting existing files, use the `write_file` tool.

    Pro-tip: For safer file modifications, use `git` commands to stage and commit
    changes, creating a safety net for your work.

    Args:
        file_path (str): The file to modify.
        start_line (int): The 1-indexed first line of the block to replace.
        end_line (int): The 1-indexed last line of the block to replace (inclusive).
        new_content (str): The new text to insert.
        require_confirmation (bool): If True, allows deleting content by providing empty `new_content`.
                                     Defaults to False.

    Returns:
        str: A JSON string confirming success or reporting an error.
    """
    if not new_content and not require_confirmation:
        return json.dumps({
            "success": False,
            "error": "Replacing content with an empty string will delete lines. Set `require_confirmation=True` to proceed."
        }, indent=2)

    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()

        # Adjust for 0-based indexing
        start_index = start_line - 1
        end_index = end_line

        # Ensure new_content ends with a newline if it's not empty
        if new_content and not new_content.endswith('\n'):
            new_content += '\n'
            
        new_lines = new_content.splitlines(True) if new_content else []

        # Replace the specified lines
        lines[start_index:end_index] = new_lines

        with open(file_path, 'w') as f:
            f.writelines(lines)

        result = {
            "success": True,
            "file_path": file_path,
            "message": f"Successfully replaced lines {start_line}-{end_line} in {file_path}"
        }
        return json.dumps(result, indent=2)
    except FileNotFoundError:
        return json.dumps({"success": False, "error": f"File not found: {file_path}"}, indent=2)
    except IndexError:
        return json.dumps({"success": False, "error": "Line numbers are out of range for the file."}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


@mcp.tool()
async def search_code(query: str, path: str = ".", case_sensitive: bool = True) -> str:
    """
    Searches for a string in files using ripgrep and returns structured results.

    This tool leverages ripgrep (rg) for high-speed, gitignore-aware code searching.
    Ripgrep must be installed on the system for this tool to function.

    Args:
        query (str): The string or regex pattern to search for.
        path (str): The file or directory to search in. Defaults to the current directory.
        case_sensitive (bool): Whether the search should be case-sensitive. Defaults to True.

    Returns:
        str: A JSON string containing a list of search results or an error.
    """
    try:
        # Find the ripgrep executable in a robust way
        rg_path = shutil.which("rg")
        if not rg_path:
            # Fallback to common hardcoded paths if not in PATH
            common_paths = ["/opt/homebrew/bin/rg", "/usr/local/bin/rg"]
            for path in common_paths:
                if os.path.exists(path):
                    rg_path = path
                    break
        
        if not rg_path:
            return json.dumps({
                "success": False, 
                "error": "The 'rg' (ripgrep) command was not found in your PATH or common locations. Please install it and ensure it's accessible."
            }, indent=2)

        command = [rg_path, '--json', query, path]
        if not case_sensitive:
            command.insert(1, '-i')

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0 and stderr:
            # Ripgrep exits with 1 if no matches are found, which is not an error for us.
            # A real error will have content in stderr.
            error_message = stderr.decode().strip()
            if "No files were searched" not in error_message:
                 return json.dumps({"success": False, "error": error_message}, indent=2)

        results = []
        for line in stdout.decode().splitlines():
            try:
                message = json.loads(line)
                if message['type'] == 'match':
                    data = message['data']
                    results.append({
                        "file_path": data['path']['text'],
                        "line_number": data['line_number'],
                        "line_content": data['lines']['text'].strip()
                    })
            except (json.JSONDecodeError, KeyError):
                # Ignore lines that aren't valid JSON or don't have the expected structure
                continue
        
        return json.dumps({"success": True, "query": query, "results": results}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


if __name__ == "__main__":
    # Run the FastMCP server
    print("Starting MCP server...", file=sys.stderr)
    try:
        mcp.run()
    except Exception as e:
        print(f"MCP server crashed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr) 