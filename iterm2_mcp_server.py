#!/usr/bin/env python3
"""
iTerm2 MCP Server using FastMCP
A Model Context Protocol server for controlling iTerm2
"""

import json
import asyncio
import os
from typing import Optional

import iterm2
from mcp.server.fastmcp import FastMCP


# Create the FastMCP server
mcp = FastMCP("iTerm2")


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
    try:
        connection = await iterm2.Connection.async_create()
        
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
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


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
    try:
        connection = await iterm2.Connection.async_create()
        app = await iterm2.async_get_app(connection)
        
        current_window = app.current_window
        current_tab = current_window.current_tab
        
        if profile:
            profile_obj = await iterm2.Profile.async_get(connection, [profile])
            if profile_obj:
                session = await current_tab.async_create_session(profile=profile_obj[0])
            else:
                session = await current_tab.async_create_session()
        else:
            session = await current_tab.async_create_session()
        
        result = {
            "success": True,
            "session_id": session.session_id,
            "message": f"Created new session {session.session_id}"
        }
        
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


@mcp.tool()
async def run_command(command: str, wait_for_output: bool = True, timeout: int = 10) -> str:
    """
    Runs a command in the active iTerm2 session.

    Args:
        command (str): The command to execute.
        wait_for_output (bool): If True, waits for the command to finish and captures the output.
                                Defaults to True.
        timeout (int): The maximum time in seconds to wait for output. Defaults to 10.

    Returns:
        str: A JSON string containing the execution status and output if captured.
    """
    try:
        connection = await iterm2.Connection.async_create()
        app = await iterm2.async_get_app(connection)
        
        current_window = app.current_window
        current_tab = current_window.current_tab
        session = current_tab.current_session
        
        # Send the command
        await session.async_send_text(f"{command}\n")
        
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
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


@mcp.tool()
async def send_text(text: str) -> str:
    """
    Sends a string of text to the active iTerm2 session without adding a newline.

    Args:
        text (str): The text to send to the terminal.

    Returns:
        str: A JSON string confirming the text was sent.
    """
    try:
        connection = await iterm2.Connection.async_create()
        app = await iterm2.async_get_app(connection)
        
        current_window = app.current_window
        current_tab = current_window.current_tab
        session = current_tab.current_session
        
        await session.async_send_text(text)
        
        result = {
            "success": True,
            "text": text,
            "session_id": session.session_id,
            "message": f"Sent text: {text}"
        }
        
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


@mcp.tool()
async def read_terminal_output(timeout: int = 5) -> str:
    """
    Reads the entire visible contents of the active iTerm2 session's screen.

    Args:
        timeout (int): The maximum time in seconds to wait for the screen contents. Defaults to 5.

    Returns:
        str: A JSON string containing the captured terminal output.
    """
    try:
        connection = await iterm2.Connection.async_create()
        app = await iterm2.async_get_app(connection)
        
        current_window = app.current_window
        current_tab = current_window.current_tab
        session = current_tab.current_session
        
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
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


@mcp.tool()
async def clear_screen() -> str:
    """
    Clears the screen of the active iTerm2 session.
    
    This is equivalent to pressing Ctrl+L.

    Returns:
        str: A JSON string confirming the screen was cleared.
    """
    try:
        connection = await iterm2.Connection.async_create()
        app = await iterm2.async_get_app(connection)
        
        current_window = app.current_window
        current_tab = current_window.current_tab
        session = current_tab.current_session
        
        await session.async_send_text("\x0c")  # Form feed character
        
        result = {
            "success": True,
            "session_id": session.session_id,
            "message": "Screen cleared"
        }
        
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


@mcp.tool()
async def list_profiles() -> str:
    """
    Retrieves a list of all available iTerm2 profiles.

    Returns:
        str: A JSON string containing a list of profile names.
    """
    try:
        connection = await iterm2.Connection.async_create()
        profiles = await iterm2.Profile.async_get(connection)
        profile_list = [profile.name for profile in profiles]
        
        result = {
            "success": True,
            "profiles": profile_list,
            "count": len(profile_list),
            "message": f"Found {len(profile_list)} profiles"
        }
        
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


@mcp.tool()
async def switch_profile(profile: str) -> str:
    """
    Switches the profile of the current iTerm2 session.

    Args:
        profile (str): The name of the profile to switch to.

    Returns:
        str: A JSON string confirming the profile switch.
    """
    try:
        connection = await iterm2.Connection.async_create()
        app = await iterm2.async_get_app(connection)
        
        profile_obj = await iterm2.Profile.async_get(connection, [profile])
        if not profile_obj:
            return json.dumps({"success": False, "error": f"Profile '{profile}' not found"}, indent=2)
        
        current_window = app.current_window
        current_tab = current_window.current_tab
        session = current_tab.current_session
        
        await session.async_set_profile(profile_obj[0])
        
        result = {
            "success": True,
            "profile": profile,
            "session_id": session.session_id,
            "message": f"Switched to profile: {profile}"
        }
        
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


@mcp.tool()
async def get_session_info() -> str:
    """
    Gets information about the current iTerm2 window, tab, and session.

    Returns:
        str: A JSON string containing the window, tab, and session IDs.
    """
    try:
        connection = await iterm2.Connection.async_create()
        app = await iterm2.async_get_app(connection)
        
        current_window = app.current_window
        current_tab = current_window.current_tab
        session = current_tab.current_session
        
        result = {
            "success": True,
            "window_id": current_window.window_id,
            "tab_id": current_tab.tab_id,
            "session_id": session.session_id,
            "message": f"Current session: {session.session_id}"
        }
        
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


@mcp.tool()
async def write_file(file_path: str, content: str) -> str:
    """
    Writes content to a specified file on the local filesystem.

    This tool uses standard Python file I/O and is more reliable for file creation
    and modification than using shell commands like 'echo' or 'heredoc'.

    Args:
        file_path (str): The absolute or relative path to the file.
        content (str): The content to write to the file.

    Returns:
        str: A JSON string confirming success or reporting an error.
    """
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
async def edit_file(file_path: str, start_line: int, end_line: int, new_content: str) -> str:
    """
    Replaces a specific block of lines in a file with new content.

    Args:
        file_path (str): The file to modify.
        start_line (int): The 1-indexed first line of the block to replace.
        end_line (int): The 1-indexed last line of the block to replace (inclusive).
        new_content (str): The new text to insert.

    Returns:
        str: A JSON string confirming success or reporting an error.
    """
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


if __name__ == "__main__":
    # Run the FastMCP server
    mcp.run() 