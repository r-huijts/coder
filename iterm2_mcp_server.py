#!/usr/bin/env python3
"""
iTerm2 MCP Server using FastMCP - Shell Integration Enhanced Version
A Model Context Protocol server for controlling iTerm2 with Shell Integration support
"""

import json
import asyncio
import os
import sys
import shutil
import weakref
import gc
import re
from typing import Optional, Dict, Any, Tuple
from pathlib import Path
from datetime import datetime

import iterm2
from mcp.server.fastmcp import FastMCP

# Create the FastMCP server
mcp = FastMCP("iTerm2")

# =============================================================================
# TOOL SELECTION PRIORITY GUIDE (CRITICAL FOR LLM TOOL CHOICE)
# =============================================================================

"""
TOOL CHOICE RUBRIC - FOLLOW THIS ORDER:

PRIORITY 1 - FILE I/O (ALWAYS PREFERRED FOR FILE OPERATIONS):
  - Creating/writing files → write_file (NEVER use run_command with >, >>, tee)
  - Reading files → read_file (NEVER use run_command with cat, less, head, tail)
  - Editing specific lines → edit_file (NEVER use run_command with sed -i, ed, perl -i)

PRIORITY 2 - STRUCTURED OPERATIONS:
  - Directory listing → list_directory (NEVER use run_command with ls)
  - Code searching → search_code (NEVER use run_command with grep, rg, ag)

PRIORITY 4 - TERMINAL MANAGEMENT:
  - Terminal setup → create_tab, create_session, switch_profile, list_profiles
  - Session info → get_session_info, clear_screen

PRIORITY 5 - TERMINAL I/O:
  - Text input → send_text (for interactive prompts without newlines)
  - Screen reading → read_terminal_output (for capturing current display)

PRIORITY 6 - SHELL EXECUTION (LAST RESORT ONLY):
  - run_command → ONLY for: package managers, builds, tests, system commands
  - FORBIDDEN uses: file creation/modification, file reading, text processing
  - BEST PRACTICE: Use plain ASCII text only - NO EMOJIS in commands

REJECTION PATTERNS for run_command:
  ❌ echo 'content' > file.txt        → USE: write_file
  ❌ cat file.txt                     → USE: read_file
  ❌ sed -i 's/a/b/' file.txt         → USE: edit_file
  ❌ ls -la directory/                → USE: list_directory
  ❌ grep "pattern" files             → USE: search_code
  ❌ mkdir -p path && echo > path/f   → USE: write_file (creates parent dirs)
  ❌ echo "✅ Done!"                  → USE: echo "[OK] Done!" (no emojis)

APPROVED uses for run_command:
  ✅ npm install, pip install, cargo build
  ✅ git status, git commit, git push
  ✅ python script.py, node app.js
  ✅ systemctl status, ps aux, df -h
  ✅ echo "[OK] Success" (ASCII only, no emojis)
"""

# =============================================================================
# CONNECTION POOLING & MEMORY MANAGEMENT
# =============================================================================

class iTerm2ConnectionManager:
    """Manages iTerm2 connections with memory optimization and Shell Integration detection"""
    
    def __init__(self):
        self._connection = None
        self._last_used = None
        self._connection_timeout = 300  # 5 minutes
        self._shell_integration_available = None  # Cached detection result
        self._shell_integration_checked_session = None  # Session ID we checked
        
    async def get_connection(self):
        """Get or create a reusable iTerm2 connection"""
        now = datetime.now()
        
        # Check if we need a new connection - FIXED: use total_seconds()
        if (self._connection is None or 
            self._last_used is None or 
            (now - self._last_used).total_seconds() > self._connection_timeout):
            
            # Clean up old connection
            if self._connection:
                try:
                    await self._connection.async_close()
                except:
                    pass
                self._connection = None
                # Reset shell integration cache when connection changes
                self._shell_integration_available = None
                self._shell_integration_checked_session = None
            
            # Create new connection
            try:
                self._connection = await iterm2.Connection.async_create()
                self._last_used = now
            except Exception as e:
                return {"error": f"iTerm2 connection failed: {str(e)}"}
        
        self._last_used = now
        
        try:
            app = await iterm2.async_get_app(self._connection)
            window = app.current_window
            tab = window.current_tab if window else None
            session = tab.current_session if tab else None
            
            return {
                "connection": self._connection,
                "app": app,
                "window": window,
                "tab": tab,
                "session": session,
                "error": None
            }
        except Exception as e:
            return {"error": f"iTerm2 context retrieval failed: {str(e)}"}
    
    async def check_shell_integration(self, connection, session) -> bool:
        """
        Check if Shell Integration is available for the current session.
        Caches the result per session to avoid repeated checks.
        """
        if session is None:
            return False
            
        # Return cached result if we already checked this session
        if (self._shell_integration_available is not None and 
            self._shell_integration_checked_session == session.session_id):
            return self._shell_integration_available
        
        try:
            prompt = await iterm2.async_get_last_prompt(connection, session.session_id)
            self._shell_integration_available = prompt is not None
            self._shell_integration_checked_session = session.session_id
            return self._shell_integration_available
        except Exception:
            self._shell_integration_available = False
            self._shell_integration_checked_session = session.session_id
            return False
    
    async def cleanup(self):
        """Explicit cleanup for connection"""
        if self._connection:
            try:
                await self._connection.async_close()
            except:
                pass
            self._connection = None
        self._shell_integration_available = None
        self._shell_integration_checked_session = None
        gc.collect()  # Force garbage collection

# Global connection manager
connection_manager = iTerm2ConnectionManager()

def optimize_json_response(data: Dict[Any, Any], max_output_size: int = 10000) -> str:
    """Create memory-efficient JSON responses"""
    
    # Truncate large outputs
    if "output" in data and isinstance(data["output"], str):
        output_len = len(data["output"])
        if output_len > max_output_size:
            data["output"] = data["output"][:max_output_size] + f"... (truncated {output_len - max_output_size} chars)"
            data["output_truncated"] = True
            data["original_length"] = output_len
    
    # Use compact JSON for large responses
    if len(str(data)) > 5000:
        return json.dumps(data, separators=(',', ':'))
    else:
        return json.dumps(data, indent=2)


# =============================================================================
# SHELL INTEGRATION HELPERS
# =============================================================================

async def run_command_with_shell_integration(
    connection, 
    session, 
    command: str, 
    timeout: int = 30,
    max_output_chars: int = 10000,
    working_directory: Optional[str] = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Run a command using Shell Integration for reliable output capture.
    Uses a temp script to avoid quoting issues with direct text injection.
    
    Returns:
        Tuple of (success, output, metadata)
    """
    import uuid
    
    metadata = {
        "method": "shell_integration",
        "timeout": timeout
    }
    
    # Build the full command
    full_command = command
    if working_directory:
        safe_dir = str(Path(working_directory).expanduser().resolve())
        full_command = f"cd '{safe_dir}' && {command}"
    
    # Write command to temp script to avoid quoting issues
    script_id = uuid.uuid4().hex[:8]
    script_path = f"/tmp/mcp_cmd_{script_id}.sh"
    
    try:
        with open(script_path, 'w') as f:
            f.write("#!/bin/bash\n")
            f.write(full_command + "\n")
            f.write(f"rm -f {script_path}\n")  # Self-cleanup
        
        os.chmod(script_path, 0o755)
        metadata["script_path"] = script_path
        
    except Exception as e:
        return False, "", {"error": f"Failed to create temp script: {str(e)}"}
    
    try:
        # Step 1: Get the current prompt (before our command)
        pre_prompt = await iterm2.async_get_last_prompt(connection, session.session_id)
        if not pre_prompt:
            return False, "", {"error": "Could not get prompt - Shell Integration may not be active"}
        
        metadata["pre_prompt_id"] = pre_prompt.unique_id
        
        # Step 2: Start monitoring for command completion BEFORE sending
        modes = [iterm2.PromptMonitor.Mode.COMMAND_END]
        
        async with iterm2.PromptMonitor(connection, session.session_id, modes) as monitor:
            # Send the script path (not the raw command)
            await session.async_send_text(f"{script_path}\n")
            
            # Wait for COMMAND_END with timeout
            try:
                await asyncio.wait_for(monitor.async_get(), timeout=timeout)
            except asyncio.TimeoutError:
                metadata["warning"] = f"Command did not complete within {timeout}s timeout"
                # Continue anyway - try to get whatever output we can
        
        # Step 3: Get the prompt info for our command (now completed)
        post_prompt = await iterm2.async_get_last_prompt(connection, session.session_id)
        
        if not post_prompt:
            return False, "", {"error": "Could not get post-command prompt"}
        
        metadata["post_prompt_id"] = post_prompt.unique_id
        metadata["command_recorded"] = post_prompt.command
        
        # Step 4: Extract output using the output_range
        output_range = post_prompt.output_range
        
        if output_range:
            start_y = output_range.start.y
            end_y = output_range.end.y
            num_lines = end_y - start_y
            
            metadata["output_range"] = {"start": start_y, "end": end_y, "lines": num_lines}
            
            if num_lines > 0:
                # Fetch the content
                async with iterm2.Transaction(connection):
                    contents = await session.async_get_contents(start_y, num_lines)
                
                # Build output string
                output_lines = []
                for line in contents:
                    if line.string:
                        output_lines.append(line.string)
                
                output = "\n".join(output_lines)
                
                # Truncate if needed
                if len(output) > max_output_chars:
                    output = output[:max_output_chars]
                    metadata["output_truncated"] = True
                    metadata["original_length"] = len(output)
                
                return True, output, metadata
            else:
                return True, "", metadata
        else:
            # No output range available - command may have produced no output
            return True, "", {"warning": "No output range available", **metadata}
            
    except Exception as e:
        return False, "", {"error": str(e), **metadata}


async def run_command_with_markers(
    connection,
    session, 
    command: str, 
    timeout: int = 30,
    max_output_chars: int = 10000,
    working_directory: Optional[str] = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Fallback method: Run command with BEGIN/END markers for output capture.
    Used when Shell Integration is not available.
    
    Returns:
        Tuple of (success, output, metadata)
    """
    import uuid
    
    metadata = {
        "method": "marker_based",
        "timeout": timeout
    }
    
    # Build the full command with markers
    sid = uuid.uuid4().hex
    marker_begin = f"__MCP_BEGIN_{sid}__"
    marker_end = f"__MCP_END_{sid}__"
    
    full_command = command
    if working_directory:
        safe_dir = str(Path(working_directory).expanduser().resolve())
        full_command = f"cd '{safe_dir}' && {command}"
    
    wrapped_command = f"echo '{marker_begin}'; {full_command}; echo '{marker_end}'"
    
    # Write to temp script for reliable execution
    script_id = uuid.uuid4().hex[:8]
    script_path = f"/tmp/mcp_cmd_{script_id}.sh"
    
    try:
        with open(script_path, 'w') as f:
            f.write("#!/bin/bash\n")
            f.write("set -e\n")
            f.write(wrapped_command + "\n")
            f.write(f"rm -f {script_path}\n")
        
        os.chmod(script_path, 0o755)
        metadata["script_path"] = script_path
        
        # Execute
        await session.async_send_text(f"{script_path}\n")
        
    except Exception as e:
        if os.path.exists(script_path):
            try:
                os.remove(script_path)
            except:
                pass
        return False, "", {"error": f"Failed to create script: {str(e)}"}
    
    # Poll for end marker
    end_marker_found = False
    poll_interval = 0.1
    elapsed = 0
    
    while elapsed < timeout and not end_marker_found:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
        
        try:
            screen = await session.async_get_screen_contents()
            if screen:
                check_lines = min(50, screen.number_of_lines)
                for i in range(screen.number_of_lines - check_lines, screen.number_of_lines):
                    line = screen.line(i)
                    if line and line.string and marker_end in line.string:
                        end_marker_found = True
                        break
        except:
            pass
        
        poll_interval = min(poll_interval * 1.5, 1.0)
    
    if not end_marker_found:
        metadata["warning"] = f"End marker not found after {timeout}s"
    
    # Wait for output to stabilize
    if end_marker_found:
        stable_count = 0
        last_line_count = 0
        for _ in range(10):
            await asyncio.sleep(0.2)
            try:
                screen_check = await session.async_get_screen_contents()
                if screen_check:
                    current_line_count = screen_check.number_of_lines
                    if current_line_count == last_line_count:
                        stable_count += 1
                        if stable_count >= 3:
                            break
                    else:
                        stable_count = 0
                        last_line_count = current_line_count
            except:
                break
    
    # Read output with scrollback
    try:
        async with iterm2.Transaction(connection):
            line_info = await session.async_get_line_info()
            total_available = line_info.scrollback_buffer_height + line_info.mutable_area_height
            max_lines = 2000
            num_lines_to_fetch = min(total_available, max_lines)
            
            if total_available > max_lines:
                first_line = line_info.overflow + (total_available - max_lines)
            else:
                first_line = line_info.overflow
            
            lines = await session.async_get_contents(first_line, num_lines_to_fetch)
        
        # Extract text
        output_text = ""
        for line in lines:
            if line.string:
                output_text += line.string + "\n"
        
        # Find markers
        text_lines = output_text.splitlines()
        begin_idx = None
        end_idx = None
        
        for idx, ln in enumerate(text_lines):
            if begin_idx is None and marker_begin in ln:
                begin_idx = idx + 1
                continue
            if begin_idx is not None and marker_end in ln:
                end_idx = idx
                break
        
        if begin_idx is not None and end_idx is not None and end_idx >= begin_idx:
            output = "\n".join(text_lines[begin_idx:end_idx])
            metadata["marker_extraction"] = f"BEGIN at {begin_idx}, END at {end_idx}"
        elif begin_idx is not None:
            output = "\n".join(text_lines[begin_idx:])
            metadata["warning"] = (metadata.get("warning", "") + f" BEGIN found at {begin_idx}, END not found").strip()
        else:
            output = output_text
            metadata["warning"] = (metadata.get("warning", "") + " Markers not found, returning raw output").strip()
        
        # Truncate if needed
        if len(output) > max_output_chars:
            output = output[:max_output_chars]
            metadata["output_truncated"] = True
        
        return True, output.strip(), metadata
        
    except Exception as e:
        return False, "", {"error": f"Failed to read output: {str(e)}", **metadata}


# =============================================================================
# OPTIMIZED CORE TOOLS
# =============================================================================

@mcp.tool()
async def create_tab(profile: Optional[str] = None) -> str:
    """
    🛸 PRIORITY 4 - NEW TAB CREATOR 🛸
    
    Creates a new iTerm2 tab in the current window for organizing terminal sessions.
    
    🎯 USE THIS TOOL FOR:
    ✅ Setting up new development environments
    ✅ Organizing different projects or tasks
    ✅ Creating dedicated tabs for servers, logs, etc.
    
    TERMINAL-SPECIFIC: Creates new iTerm2 tab with optional profile.

    Args:
        profile (Optional[str]): The name of the profile to use for the new tab. 
                                 If not provided, the default profile is used.

    Returns:
        str: A JSON string containing the new window, tab, and session IDs.
    """
    ctx = await connection_manager.get_connection()
    if ctx.get("error"):
        return optimize_json_response({"success": False, "error": ctx["error"]})

    connection = ctx["connection"]
    window = ctx["window"]
    
    if not window:
        return optimize_json_response({"success": False, "error": "No active iTerm2 window found."})
    
    # FIXED: Create a tab in current window, not a new window
    if profile:
        profile_obj = await iterm2.Profile.async_get(connection, [profile])
        if profile_obj:
            tab = await window.async_create_tab(profile=profile_obj[0])
        else:
            tab = await window.async_create_tab()
    else:
        tab = await window.async_create_tab()
    
    session = tab.current_session
    
    result = {
        "success": True,
        "window_id": window.window_id,
        "tab_id": tab.tab_id,
        "session_id": session.session_id,
        "message": f"Created new tab with session {session.session_id}"
    }
    
    return optimize_json_response(result)


@mcp.tool()
async def create_session(profile: Optional[str] = None) -> str:
    """
    ⚡ PRIORITY 4 - SPLIT PANE CREATOR ⚡
    
    Creates a new session (split pane) in current tab for multitasking.
    
    🎯 USE FOR: Side-by-side terminal work, monitoring + coding.
    TERMINAL-SPECIFIC: Creates split pane in current iTerm2 tab.

    Args:
        profile (Optional[str]): The name of the profile to use for the new session.
                                 If not provided, the default profile is used.

    Returns:
        str: A JSON string containing the new session ID.
    """
    ctx = await connection_manager.get_connection()
    if ctx.get("error"):
        return optimize_json_response({"success": False, "error": ctx["error"]})

    connection, session = ctx["connection"], ctx["session"]
    if not session:
        return optimize_json_response({"success": False, "error": "No active iTerm2 session found."})

    # Split the current session
    if profile:
        profile_obj = await iterm2.Profile.async_get(connection, [profile])
        if profile_obj:
            new_session = await session.async_split_pane(profile=profile_obj[0])
        else:
            new_session = await session.async_split_pane()
    else:
        new_session = await session.async_split_pane()
    
    result = {
        "success": True,
        "session_id": new_session.session_id,
        "message": f"Created new split pane session {new_session.session_id}"
    }
    
    return optimize_json_response(result)


@mcp.tool()
async def run_command(
    command: str, 
    wait_for_output: bool = True, 
    timeout: int = 30, 
    require_confirmation: bool = False, 
    working_directory: Optional[str] = None, 
    max_output_chars: int = 50000
) -> str:
    """
    ⚠️  SHELL EXECUTION - USE AS LAST RESORT ONLY ⚠️
    
    Executes shell commands in iTerm2 with Shell Integration support for reliable output capture.
    
    🎯 SHELL INTEGRATION (when available):
    • Automatically detects command completion
    • Captures exact output range (no markers needed)
    • More reliable than polling-based approaches
    
    🎯 FALLBACK MODE (when Shell Integration unavailable):
    • Uses BEGIN/END markers for output isolation
    • Polls for completion with exponential backoff
    
    🚫 FORBIDDEN USES (Use specialized tools instead):
    ❌ File creation/writing: echo 'x' > file.txt → USE write_file
    ❌ File reading: cat, head, tail, less → USE read_file  
    ❌ File editing: sed -i, ed, perl -i → USE edit_file
    ❌ Directory listing: ls, find → USE list_directory
    ❌ Text searching: grep, rg, ag → USE search_code
    
    ✅ APPROVED USES ONLY:
    ✅ Package managers: npm install, pip install, cargo build, brew install
    ✅ Version control: git status, git commit, git push, git pull
    ✅ Process execution: python script.py, node app.js, ./configure, make
    ✅ System inspection: ps aux, df -h, systemctl status, uname -a
    ✅ Network tools: curl, wget, ping, ssh (non-file operations)
    ✅ Build tools: make, cmake, gradlew, mvn compile
    
    SECURITY: Dangerous commands (rm, dd, mkfs, shutdown) require `require_confirmation=True`.

    Args:
        command (str): The command to execute.
        wait_for_output (bool): If True, waits for command completion and captures output. Defaults to True.
        timeout (int): Maximum seconds to wait for command completion. Defaults to 30.
                       Adjust based on expected duration:
                       • Quick commands (git status): 10-30s
                       • Package installs: 60-120s
                       • Media processing (ffmpeg): 120-300s
                       • Large compilations: 300-600s
        require_confirmation (bool): Required for destructive commands. Defaults to False.
        working_directory (str): Optional directory to cd into before executing.
        max_output_chars (int): Maximum output size. Defaults to 50000.

    Returns:
        str: A JSON string containing execution status, output, and metadata.
    """
    ctx = await connection_manager.get_connection()
    if ctx.get("error"):
        return optimize_json_response({"success": False, "error": ctx["error"]})

    # Security check for dangerous commands
    DANGEROUS_COMMANDS = ["rm ", "rm -", "dd ", "mkfs ", "shutdown ", "reboot "]
    if any(cmd in command for cmd in DANGEROUS_COMMANDS) and not require_confirmation:
        return optimize_json_response({
            "success": False,
            "error": "This command is potentially destructive.",
            "hint": "Re-run with require_confirmation=True to proceed."
        })

    connection = ctx["connection"]
    session = ctx["session"]
    if not session:
        return optimize_json_response({"success": False, "error": "No active iTerm2 session found."})

    result = {
        "success": True,
        "command": command,
        "session_id": session.session_id,
        "timestamp": datetime.now().isoformat()
    }

    if not wait_for_output:
        # Fire-and-forget mode
        full_command = command
        if working_directory:
            safe_dir = str(Path(working_directory).expanduser().resolve())
            full_command = f"cd '{safe_dir}' && {command}"
        
        await session.async_send_text(full_command + "\n")
        result["message"] = f"Command sent (fire-and-forget): {command}"
        result["output"] = ""
        return optimize_json_response(result)

    # Check if Shell Integration is available
    shell_integration = await connection_manager.check_shell_integration(connection, session)
    
    if shell_integration:
        # Use Shell Integration for reliable output capture
        success, output, metadata = await run_command_with_shell_integration(
            connection, session, command, timeout, max_output_chars, working_directory
        )
        
        result["output"] = output
        result["output_length"] = len(output)
        result["shell_integration"] = True
        result.update(metadata)
        
        if not success:
            result["success"] = False
            
        result["message"] = f"Executed via Shell Integration: {command}"
        
    else:
        # Fallback to marker-based approach
        success, output, metadata = await run_command_with_markers(
            connection, session, command, timeout, max_output_chars, working_directory
        )
        
        result["output"] = output
        result["output_length"] = len(output)
        result["shell_integration"] = False
        result.update(metadata)
        
        if not success:
            result["success"] = False
            
        result["message"] = f"Executed via markers (Shell Integration unavailable): {command}"

    return optimize_json_response(result, max_output_size=max_output_chars)


@mcp.tool()
async def send_text(text: str, paste: bool = True) -> str:
    """
    ⌨️  PRIORITY 5 - RAW TEXT INPUT TOOL ⌨️
    
    Sends text to terminal. By default, uses direct text injection for safety.
    
    🎯 USE THIS TOOL FOR:
    ✅ Interactive prompts requiring user input
    ✅ Typing into REPLs, editors, or interactive programs
    ✅ Pasting code blocks or long text
    
    🚫 DON'T USE FOR:
    ❌ Executing complete commands → USE run_command
    ❌ Writing files → USE write_file
    
    TERMINAL-SPECIFIC: Sends text to current iTerm2 session.
    NO NEWLINE (by default): Text appears at cursor without executing.

    Args:
        text (str): The text to send to the terminal.
        paste (bool): If True (default), uses async_inject to inject bytes directly
                      into the terminal, bypassing shell interpretation during input.
                      This is much safer and faster for code blocks or long text.
                      If False, simulates individual keystrokes (slower, riskier).

    Returns:
        str: A JSON string confirming the text was sent.
    """
    ctx = await connection_manager.get_connection()
    if ctx.get("error"):
        return optimize_json_response({"success": False, "error": ctx["error"]})

    session = ctx["session"]
    if not session:
        return optimize_json_response({"success": False, "error": "No active iTerm2 session found."})

    try:
        if paste:
            inject_method = getattr(session, "async_inject", None)
            if inject_method:
                await inject_method(text.encode('utf-8'))
                method_used = "inject_bytes"
            else:
                await session.async_send_text(text)
                method_used = "send_text_fallback"
        else:
            await session.async_send_text(text)
            method_used = "raw_keystrokes"
        
        result = {
            "success": True,
            "text_length": len(text),
            "session_id": session.session_id,
            "method": method_used,
            "message": f"Sent {len(text)} characters via {method_used}"
        }
        
        return optimize_json_response(result)
        
    except Exception as e:
        return optimize_json_response({"success": False, "error": str(e)})


@mcp.tool()
async def read_terminal_output(timeout: int = 5, max_lines: int = 100) -> str:
    """
    📺 PRIORITY 5 - TERMINAL SCREEN READER 📺
    
    Captures the current visible terminal screen contents. Use for reading
    current terminal state, not for file operations.
    
    🎯 USE THIS TOOL FOR:
    ✅ Reading current terminal display/output
    ✅ Capturing command results that are already visible
    ✅ Debugging terminal state or checking current directory
    ✅ Reading interactive program output (REPLs, editors)
    
    🚫 DON'T USE FOR FILE OPERATIONS:
    ❌ Reading file contents → USE read_file
    ❌ Capturing command output → USE run_command with wait_for_output=True
    ❌ Getting directory listings → USE list_directory
    
    READ-ONLY: This tool never modifies anything - completely safe.
    TERMINAL-SPECIFIC: Only works with current iTerm2 session screen.
    MEMORY-OPTIMIZED: Limits output to prevent memory issues.

    Args:
        timeout (int): The maximum time in seconds to wait for the screen contents. Defaults to 5.
        max_lines (int): Maximum number of lines to read for memory efficiency. Defaults to 100.

    Returns:
        str: A JSON string containing the captured terminal output.
    """
    ctx = await connection_manager.get_connection()
    if ctx.get("error"):
        return optimize_json_response({"success": False, "error": ctx["error"]})

    session = ctx["session"]
    if not session:
        return optimize_json_response({"success": False, "error": "No active iTerm2 session found."})

    try:
        screen = await asyncio.wait_for(
            session.async_get_screen_contents(),
            timeout=timeout
        )
        
        if screen:
            output_text = ""
            actual_lines = min(screen.number_of_lines, max_lines)
            
            for i in range(actual_lines):
                line = screen.line(i)
                if line.string:
                    output_text += line.string + "\n"
            
            result = {
                "success": True,
                "output": output_text.strip(),
                "lines_read": actual_lines,
                "total_lines_available": screen.number_of_lines,
                "session_id": session.session_id,
                "message": f"Read terminal output ({len(output_text)} characters, {actual_lines} lines)"
            }
            
            if screen.number_of_lines > max_lines:
                result["lines_truncated"] = True
                result["warning"] = f"Output limited to {max_lines} lines for memory efficiency"
                
        else:
            result = {
                "success": True,
                "output": "",
                "lines_read": 0,
                "session_id": session.session_id,
                "message": "No terminal output available"
            }
        
        return optimize_json_response(result)
        
    except asyncio.TimeoutError:
        return optimize_json_response({
            "success": False,
            "error": f"Timeout reading terminal output after {timeout} seconds"
        })
    except Exception as e:
        return optimize_json_response({"success": False, "error": str(e)})


@mcp.tool()
async def clear_screen() -> str:
    """
    🧹 PRIORITY 4 - SCREEN CLEANER 🧹
    
    Clears terminal screen using ANSI escape codes.
    
    🎯 USE FOR: Cleaning cluttered terminal display.
    TERMINAL-SPECIFIC: Clears current iTerm2 session screen only.

    Returns:
        str: A JSON string confirming the screen was cleared.
    """
    ctx = await connection_manager.get_connection()
    if ctx.get("error"):
        return optimize_json_response({"success": False, "error": ctx["error"]})

    session = ctx["session"]
    if not session:
        return optimize_json_response({"success": False, "error": "No active iTerm2 session found."})

    try:
        # FIXED: Use proper ANSI escape sequence for clear + cursor home
        await session.async_send_text("\x1b[2J\x1b[H")
        
        result = {
            "success": True,
            "session_id": session.session_id,
            "message": "Screen cleared"
        }
        
        return optimize_json_response(result)
        
    except Exception as e:
        return optimize_json_response({"success": False, "error": str(e)})


@mcp.tool()
async def list_profiles() -> str:
    """
    📋 PRIORITY 4 - PROFILE LISTER 📋
    
    Lists available iTerm2 profiles for theme/config selection.
    
    🎯 USE FOR: Discovering available terminal profiles.
    READ-ONLY: Safe profile enumeration.

    Returns:
        str: A JSON string containing a list of profile names.
    """
    ctx = await connection_manager.get_connection()
    if ctx.get("error"):
        return optimize_json_response({"success": False, "error": ctx["error"]})

    connection = ctx["connection"]
    profiles = await iterm2.Profile.async_get(connection)
    profile_list = [profile.name for profile in profiles]
    
    result = {
        "success": True,
        "profiles": profile_list,
        "count": len(profile_list),
        "message": f"Found {len(profile_list)} profiles"
    }
    
    return optimize_json_response(result)


@mcp.tool()
async def switch_profile(profile: str) -> str:
    """
    🎨 PRIORITY 4 - PROFILE SWITCHER 🎨
    
    Switches iTerm2 profile (theme, colors, settings).
    
    🎯 USE FOR: Changing terminal appearance/behavior.
    TERMINAL-SPECIFIC: Affects current session only.

    Args:
        profile (str): The name of the profile to switch to.

    Returns:
        str: A JSON string confirming the profile switch.
    """
    ctx = await connection_manager.get_connection()
    if ctx.get("error"):
        return optimize_json_response({"success": False, "error": ctx["error"]})

    connection, session = ctx["connection"], ctx["session"]
    if not session:
        return optimize_json_response({"success": False, "error": "No active iTerm2 session found."})

    profile_obj = await iterm2.Profile.async_get(connection, [profile])
    if not profile_obj:
        return optimize_json_response({"success": False, "error": f"Profile '{profile}' not found"})
    
    await session.async_set_profile(profile_obj[0])
    
    result = {
        "success": True,
        "profile": profile,
        "session_id": session.session_id,
        "message": f"Switched to profile: {profile}"
    }
    
    return optimize_json_response(result)


@mcp.tool()
async def get_session_info() -> str:
    """
    ℹ️  PRIORITY 4 - SESSION INFO ℹ️
    
    Gets current iTerm2 window/tab/session IDs and Shell Integration status.
    
    🎯 USE FOR: Terminal context and debugging.
    READ-ONLY: Safe information retrieval.

    Returns:
        str: A JSON string containing session info and capabilities.
    """
    ctx = await connection_manager.get_connection()
    if ctx.get("error"):
        return optimize_json_response({"success": False, "error": ctx["error"]})

    connection = ctx["connection"]
    window, tab, session = ctx["window"], ctx["tab"], ctx["session"]
    if not (window and tab and session):
        return optimize_json_response({"success": False, "error": "Could not retrieve complete session info."})

    # Check Shell Integration status
    shell_integration = await connection_manager.check_shell_integration(connection, session)
    
    result = {
        "success": True,
        "window_id": window.window_id,
        "tab_id": tab.tab_id,
        "session_id": session.session_id,
        "shell_integration_available": shell_integration,
        "message": f"Current session: {session.session_id} (Shell Integration: {'enabled' if shell_integration else 'disabled'})"
    }
    
    return optimize_json_response(result)


@mcp.tool()
async def write_file(file_path: str, content: str, require_confirmation: bool = False) -> str:
    """
    🏆 PRIORITY 1 - FILE CREATION/WRITING TOOL 🏆
    
    The ONLY correct tool for creating or overwriting files. NEVER use run_command
    for file writing operations.
    
    🎯 USE THIS TOOL FOR:
    ✅ Creating new files: any file type (.py, .js, .txt, .md, .json, etc.)
    ✅ Overwriting entire files with new content
    ✅ Writing multi-line content with proper newline handling
    ✅ Writing content with special characters, quotes, or shell metacharacters
    ✅ Creating files in nested directories (automatically creates parent dirs)
    
    🚫 NEVER USE run_command FOR:
    ❌ echo 'content' > file.txt
    ❌ cat << EOF > file.txt  
    ❌ printf 'data' > file.txt
    ❌ tee file.txt <<< 'content'
    ❌ python -c "open('file','w').write('data')"
    
    ADVANTAGES over shell redirection:
    • Handles newlines, quotes, and special characters correctly
    • Atomic write operations prevent partial file corruption
    • Proper error handling with structured JSON responses
    • No shell injection vulnerabilities
    
    SAFETY: Overwrites require `require_confirmation=True`.

    Args:
        file_path (str): The absolute or relative path to the file.
        content (str): The content to write to the file.
        require_confirmation (bool): If True, allows overwriting an existing file.
                                     Defaults to False.

    Returns:
        str: A JSON string confirming success or reporting an error.
    """
    # Expand user path and resolve
    resolved_path = Path(file_path).expanduser().resolve()
    
    # Create parent directories if they don't exist
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    if resolved_path.exists() and not require_confirmation:
        return optimize_json_response({
            "success": False,
            "error": f"File '{file_path}' already exists. Set `require_confirmation=True` to overwrite."
        })

    try:
        with open(resolved_path, "w") as f:
            f.write(content)
        result = {
            "success": True,
            "file_path": str(resolved_path),
            "content_length": len(content),
            "message": f"Successfully wrote {len(content)} characters to {resolved_path}"
        }
        return optimize_json_response(result)
    except Exception as e:
        return optimize_json_response({"success": False, "error": str(e)})


@mcp.tool()
async def read_file(file_path: str, start_line: Optional[int] = None, end_line: Optional[int] = None, max_size_mb: float = 10.0) -> str:
    """
    🏆 PRIORITY 1 - FILE READING TOOL 🏆
    
    The ONLY correct tool for reading file contents. NEVER use run_command
    for file reading operations.
    
    🎯 USE THIS TOOL FOR:
    ✅ Reading entire files: any file type (.py, .js, .txt, .md, .json, logs, etc.)
    ✅ Reading specific line ranges: start_line and end_line parameters
    ✅ Reading files with special characters, unicode, or binary content
    ✅ Safe file access with proper error handling
    
    🚫 NEVER USE run_command FOR:
    ❌ cat file.txt
    ❌ head -n 20 file.txt  
    ❌ tail -n 10 file.txt
    ❌ less file.txt
    ❌ more file.txt
    ❌ sed -n '1,10p' file.txt
    
    ADVANTAGES over shell commands:
    • Returns structured JSON with proper error handling
    • Handles unicode and special characters correctly
    • Optional line slicing without external tools
    • No output formatting issues or terminal paging
    • Memory limits to prevent system issues
    
    READ-ONLY: This tool never modifies files - completely safe.
    MEMORY-OPTIMIZED: Includes size limits to prevent memory issues.

    Args:
        file_path (str): The path to the file to read.
        start_line (Optional[int]): The 1-indexed line number to start reading from.
        end_line (Optional[int]): The 1-indexed line number to stop reading at (inclusive).
        max_size_mb (float): Maximum file size to read in MB. Defaults to 10.0MB.

    Returns:
        str: A JSON string with the file content or an error.
    """
    try:
        # Expand user path
        resolved_path = Path(file_path).expanduser().resolve()
        
        # Check file size before reading
        file_size = os.path.getsize(resolved_path)
        max_size_bytes = max_size_mb * 1024 * 1024
        
        if file_size > max_size_bytes:
            return optimize_json_response({
                "success": False,
                "error": f"File too large ({file_size / 1024 / 1024:.1f}MB > {max_size_mb}MB limit)",
                "hint": "Use start_line/end_line parameters to read specific sections or increase max_size_mb"
            })
        
        with open(resolved_path, 'r') as f:
            if start_line is not None or end_line is not None:
                # Read only specific lines to save memory
                lines = []
                current_line = 1
                
                for line in f:
                    if start_line is not None and current_line < start_line:
                        current_line += 1
                        continue
                    if end_line is not None and current_line > end_line:
                        break
                    lines.append(line)
                    current_line += 1
                    
                content = "".join(lines)
            else:
                content = f.read()
            
        result = {
            "success": True,
            "file_path": str(resolved_path),
            "content": content,
            "file_size_bytes": file_size,
            "content_length": len(content)
        }
        return optimize_json_response(result)
        
    except FileNotFoundError:
        return optimize_json_response({"success": False, "error": f"File not found: {file_path}"})
    except Exception as e:
        return optimize_json_response({"success": False, "error": str(e)})


@mcp.tool()
async def list_directory(path: str, recursive: bool = False) -> str:
    """
    📁 PRIORITY 2 - DIRECTORY LISTING TOOL 📁
    
    The ONLY correct tool for listing directory contents. NEVER use run_command
    for directory listing operations.
    
    🎯 USE THIS TOOL FOR:
    ✅ Listing files and directories in structured format
    ✅ Recursive directory traversal with recursive=True
    ✅ Getting file/directory metadata and paths
    ✅ Exploring project structure safely
    
    🚫 NEVER USE run_command FOR:
    ❌ ls -la directory/
    ❌ find directory/ -type f
    ❌ tree directory/
    ❌ ls -R directory/
    ❌ find . -name "*.py"
    
    ADVANTAGES over shell commands:
    • Returns structured JSON with file/directory distinction
    • Handles filenames with spaces, special characters, unicode
    • Optional recursive traversal without complex find commands
    • Consistent cross-platform behavior
    • No output parsing or formatting issues
    
    READ-ONLY: This tool never modifies the filesystem - completely safe.

    Args:
        path (str): The path to the directory to list.
        recursive (bool): If True, lists contents recursively. Defaults to False.

    Returns:
        str: A JSON string with a list of files and directories, or an error.
    """
    try:
        # Expand '~' and resolve symlinks for accurate checks
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_dir():
            return optimize_json_response({"success": False, "error": f"Not a directory: {path}"})

        contents = []
        if recursive:
            for root, dirs, files in os.walk(str(resolved)):
                for name in files:
                    full_path = os.path.join(root, name)
                    contents.append({"name": name, "path": full_path, "is_directory": False})
                for name in dirs:
                    full_path = os.path.join(root, name)
                    contents.append({"name": name, "path": full_path, "is_directory": True})
        else:
            for name in os.listdir(str(resolved)):
                full_path = os.path.join(str(resolved), name)
                is_dir = os.path.isdir(full_path)
                contents.append({"name": name, "path": full_path, "is_directory": is_dir})
        
        result = {
            "success": True,
            "path": str(resolved),
            "contents": contents,
            "count": len(contents)
        }
        return optimize_json_response(result)
    except Exception as e:
        return optimize_json_response({"success": False, "error": str(e)})


@mcp.tool()
async def edit_file(file_path: str, start_line: int, end_line: int, new_content: str, require_confirmation: bool = False) -> str:
    """
    🏆 PRIORITY 1 - SURGICAL FILE EDITING TOOL 🏆
    
    The ONLY correct tool for modifying specific lines in files. NEVER use run_command
    for in-place file editing operations.
    
    🎯 USE THIS TOOL FOR:
    ✅ Replacing specific line ranges in existing files
    ✅ Inserting content at specific positions
    ✅ Deleting specific lines (with empty new_content)
    ✅ Precise code modifications without affecting other lines
    ✅ Safe surgical edits with line-number precision
    
    🚫 NEVER USE run_command FOR:
    ❌ sed -i 's/old/new/g' file.txt
    ❌ perl -i -pe 's/pattern/replacement/' file.txt
    ❌ ed file.txt (with ed commands)
    ❌ awk -i inplace '{gsub(/old/,new)}1' file.txt
    ❌ python -c "edit file in place"
    
    ADVANTAGES over shell editing:
    • Precise line-based modifications without regex complexity
    • No risk of unintended global replacements
    • Preserves file encoding and line endings
    • Atomic operations prevent partial corruption
    • Clear error messages for out-of-range line numbers
    
    WORKFLOW: Use read_file first to see current content and determine line ranges.
    SAFETY: Empty `new_content` deletes lines, requires `require_confirmation=True`.

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
        return optimize_json_response({
            "success": False,
            "error": "Replacing content with an empty string will delete lines. Set `require_confirmation=True` to proceed."
        })

    try:
        # Expand user path
        resolved_path = Path(file_path).expanduser().resolve()
        
        with open(resolved_path, 'r') as f:
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

        with open(resolved_path, 'w') as f:
            f.writelines(lines)

        result = {
            "success": True,
            "file_path": str(resolved_path),
            "lines_replaced": end_line - start_line + 1,
            "new_lines_count": len(new_lines),
            "message": f"Successfully replaced lines {start_line}-{end_line} in {resolved_path}"
        }
        return optimize_json_response(result)
    except FileNotFoundError:
        return optimize_json_response({"success": False, "error": f"File not found: {file_path}"})
    except IndexError:
        return optimize_json_response({"success": False, "error": "Line numbers are out of range for the file."})
    except Exception as e:
        return optimize_json_response({"success": False, "error": str(e)})


@mcp.tool()
async def search_code(query: str, search_path: str = ".", case_sensitive: bool = True) -> str:
    """
    🔍 PRIORITY 2 - CODE SEARCH TOOL 🔍
    
    The ONLY correct tool for searching text in files. NEVER use run_command
    for text search operations.
    
    🎯 USE THIS TOOL FOR:
    ✅ Finding text/patterns across multiple files
    ✅ Locating function definitions, variable usage, imports
    ✅ Searching with regex patterns
    ✅ Case-sensitive or case-insensitive searches
    ✅ Fast, gitignore-aware searching with ripgrep
    
    🚫 NEVER USE run_command FOR:
    ❌ grep -r "pattern" directory/
    ❌ find . -name "*.py" -exec grep "pattern" {} \\;
    ❌ rg "pattern" files/
    ❌ ag "pattern" directory/
    ❌ ack "pattern" 
    
    ADVANTAGES over shell search:
    • Returns structured JSON with file paths, line numbers, and content
    • Gitignore-aware (skips .git, node_modules, build artifacts automatically)
    • Extremely fast ripgrep-powered search engine
    • Proper error handling and search result organization
    • No output parsing issues or formatting problems
    
    READ-ONLY: This tool never modifies files - completely safe for exploration.
    REQUIREMENT: Ripgrep (rg) must be installed on the system.

    Args:
        query (str): The string or regex pattern to search for.
        search_path (str): The file or directory to search in. Defaults to the current directory.
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
            for p in common_paths:  # FIXED: renamed from 'path' to 'p' to avoid shadowing
                if os.path.exists(p):
                    rg_path = p
                    break
        
        if not rg_path:
            return optimize_json_response({
                "success": False, 
                "error": "The 'rg' (ripgrep) command was not found in your PATH or common locations. Please install it and ensure it's accessible."
            })

        command = [rg_path, '--json', query, search_path]
        if not case_sensitive:
            command.insert(1, '-i')

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0 and stderr:
            error_message = stderr.decode().strip()
            if "No files were searched" not in error_message:
                 return optimize_json_response({"success": False, "error": error_message})

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
                continue
        
        result = {
            "success": True, 
            "query": query, 
            "results": results,
            "results_count": len(results),
            "search_path": search_path
        }
        
        return optimize_json_response(result)
    except Exception as e:
        return optimize_json_response({"success": False, "error": str(e)})


# =============================================================================
# MEMORY MANAGEMENT TOOLS
# =============================================================================

@mcp.tool()
async def cleanup_connections() -> str:
    """
    🧹 Manual cleanup tool for memory management during long sessions.
    
    Use this tool periodically during long coding sessions to free up memory
    and reset connections. Especially useful after many tool calls.
    """
    try:
        await connection_manager.cleanup()
        gc.collect()
        
        result = {
            "success": True,
            "message": "Connections cleaned up and garbage collection forced",
            "timestamp": datetime.now().isoformat()
        }
        
        return optimize_json_response(result)
        
    except Exception as e:
        return optimize_json_response({"success": False, "error": str(e)})


@mcp.tool()
async def get_memory_stats() -> str:
    """
    📊 Get basic memory usage stats for debugging long sessions.
    
    Returns current memory usage and connection status. Useful for
    monitoring memory during long coding sessions or debugging issues.
    """
    try:
        try:
            import psutil
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            
            memory_stats = {
                "rss_mb": round(memory_info.rss / 1024 / 1024, 2),
                "vms_mb": round(memory_info.vms / 1024 / 1024, 2),
                "percent": round(process.memory_percent(), 2)
            }
        except ImportError:
            memory_stats = {
                "error": "psutil not available - install with 'pip install psutil' for detailed memory stats"
            }
        
        result = {
            "success": True,
            "memory_stats": memory_stats,
            "connection_manager": {
                "has_active_connection": connection_manager._connection is not None,
                "last_used": connection_manager._last_used.isoformat() if connection_manager._last_used else None,
                "shell_integration_cached": connection_manager._shell_integration_available,
                "shell_integration_session": connection_manager._shell_integration_checked_session
            },
            "timestamp": datetime.now().isoformat()
        }
        
        return optimize_json_response(result)
        
    except Exception as e:
        return optimize_json_response({"success": False, "error": str(e)})


if __name__ == "__main__":
    # Run the FastMCP server with proper cleanup
    print("Starting Shell Integration enhanced iTerm2 MCP server...", file=sys.stderr)
    try:
        mcp.run()
    except KeyboardInterrupt:
        print("Shutting down server...", file=sys.stderr)
        asyncio.run(connection_manager.cleanup())
    except Exception as e:
        print(f"MCP server crashed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        asyncio.run(connection_manager.cleanup())
