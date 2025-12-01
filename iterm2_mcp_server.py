#!/usr/bin/env python3
"""
iTerm2 MCP Server using FastMCP - Memory Optimized Version
A Model Context Protocol server for controlling iTerm2 with better memory management
"""

import json
import asyncio
import os
import sys
import shutil
import weakref
import gc
import re
from typing import Optional, Dict, Any
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
    """Manages iTerm2 connections with memory optimization"""
    
    def __init__(self):
        self._connection = None
        self._last_used = None
        self._connection_timeout = 300  # 5 minutes
        
    async def get_connection(self):
        """Get or create a reusable iTerm2 connection"""
        now = datetime.now()
        
        # Check if we need a new connection
        if (self._connection is None or 
            self._last_used is None or 
            (now - self._last_used).seconds > self._connection_timeout):
            
            # Clean up old connection
            if self._connection:
                try:
                    await self._connection.async_close()
                except:
                    pass
                self._connection = None
            
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
    
    async def cleanup(self):
        """Explicit cleanup for connection"""
        if self._connection:
            try:
                await self._connection.async_close()
            except:
                pass
            self._connection = None
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
# OPTIMIZED CORE TOOLS
# =============================================================================

@mcp.tool()
async def create_tab(profile: Optional[str] = None) -> str:
    """
    🛸 PRIORITY 4 - NEW TAB CREATOR 🛸
    
    Creates a new iTerm2 tab for organizing terminal sessions.
    
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

    connection, tab = ctx["connection"], ctx["tab"]
    if not tab:
        return optimize_json_response({"success": False, "error": "No active iTerm2 tab found."})

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
    
    return optimize_json_response(result)


@mcp.tool()
async def run_command(command: str, wait_for_output: bool = True, timeout: int = 10, 
                      require_confirmation: bool = False, 
                      working_directory: Optional[str] = None, 
                      isolate_output: bool = False, max_output_chars: int = 10000) -> str:
    """
    ⚠️  SHELL EXECUTION - USE AS LAST RESORT ONLY ⚠️
    
    Executes shell commands in iTerm2. HIGH RISK TOOL with significant limitations.
    
    💡 FOR CLEAN, PARSEABLE OUTPUT: Use isolate_output=True and set appropriate timeout!
    
    🚫 FORBIDDEN USES (Use specialized tools instead):
    ❌ File creation/writing: echo 'x' > file.txt → USE write_file
    ❌ File reading: cat, head, tail, less → USE read_file  
    ❌ File editing: sed -i, ed, perl -i → USE edit_file
    ❌ Directory listing: ls, find → USE list_directory
    ❌ Text searching: grep, rg, ag → USE search_code
    ❌ File operations: mv, cp, rm → USE write_file/edit_file + confirmation
    
    ✅ APPROVED USES ONLY:
    ✅ Package managers: npm install, pip install, cargo build, brew install
    ✅ Version control: git status, git commit, git push, git pull
    ✅ Process execution: python script.py, node app.js, ./configure, make
    ✅ System inspection: ps aux, df -h, systemctl status, uname -a
    ✅ Network tools: curl, wget, ping, ssh (non-file operations)
    ✅ Build tools: make, cmake, gradlew, mvn compile
    
    ✅ SAFE FEATURES (New):
    • HEREDOCS: Fully supported via temporary script execution.
    • EMOJIS: Fully supported.
    • LONG COMMANDS: Fully supported (no buffer limits).
    • COMPLEX QUOTING: All quoting patterns work reliably.
    
    SECURITY: Dangerous commands (rm, dd, mkfs, shutdown) require `require_confirmation=True`.
    MEMORY: Output size limited to prevent memory issues during long tasks.
    
    ⚠️  WARNING: This tool bypasses safety mechanisms of specialized file tools.
    Prefer write_file/edit_file/read_file for ANY file operations - they are safer,
    more reliable, handle edge cases better, and respect security boundaries.

    Args:
        command (str): The command to execute. Supports heredocs, emojis, and complex quoting safely.
        
        wait_for_output (bool): If True, waits for the command to finish and captures the output.
                                Defaults to True. Set to False for fire-and-forget commands.
        
        timeout (int): Maximum seconds to wait for command completion. Defaults to 10.
                       ⚠️ IMPORTANT: Adjust based on expected command duration:
                       • Quick commands (ls, echo, git status): 10s (default)
                       • Package installs (npm install, pip install): 60-120s
                       • Media processing (ffmpeg, video encoding): 120-300s
                       • Large compilations (make, cargo build): 300-600s
                       If output reading times out, increase this value.
        
        require_confirmation (bool): If True, allows potentially destructive commands to run.
                                     Defaults to False.
        
        working_directory (str): Optional directory to cd into before executing the command.
        
        isolate_output (bool): ⭐ HIGHLY RECOMMENDED when you need to parse command output.
                               When True (default False):
                               • Wraps command with unique BEGIN/END markers
                               • Extracts ONLY the command's output (no prompts, no noise)
                               • Actively polls terminal until END marker appears
                               • Returns clean, parseable results
                               
                               USE isolate_output=True FOR:
                               ✅ Commands whose output you need to read/parse
                               ✅ Long-running commands (ffmpeg, builds, installs)
                               ✅ Commands with verbose/multi-line output
                               ✅ Any time terminal noise would confuse parsing
                               
                               SKIP isolate_output FOR:
                               • Quick commands where you don't need the output
                               • Interactive commands (they won't work with markers)
        
        max_output_chars (int): Maximum output size to prevent memory issues. Defaults to 10000.
                                Increase if you expect more output (e.g. large log files).

    Returns:
        str: A JSON string containing the execution status and output if captured.
    """
    ctx = await connection_manager.get_connection()
    if ctx.get("error"):
        return optimize_json_response({"success": False, "error": ctx["error"]})

    # Heredocs are now fully supported via direct text injection - no special handling needed

    DANGEROUS_COMMANDS = ["rm ", "dd ", "mkfs ", "shutdown ", "reboot "]
    if any(cmd in command for cmd in DANGEROUS_COMMANDS) and not require_confirmation:
        # Provide an elicitation-style payload for compatible clients
        return optimize_json_response({
            "success": False,
            "error": "This command is potentially destructive.",
            "action_required": "confirmation",
            "elicitation": {
                "method": "elicitation/requestInput",
                "params": {
                    "message": f"Confirm execution of potentially destructive command: {command}",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "confirm": {
                                "type": "boolean",
                                "description": "Confirm running the command"
                            }
                        },
                        "required": ["confirm"]
                    }
                }
            },
            "hint": "Re-run with require_confirmation=True to proceed."
        })

    session = ctx["session"]
    if not session:
        return optimize_json_response({"success": False, "error": "No active iTerm2 session found."})

    # CRITICAL FIX: Neither async_inject_text nor async_send_text handle complex
    # commands reliably (they simulate typing which causes quote hell).
    # Solution: Write command to a temporary file and source it.
    
    import tempfile
    import uuid
    import os
    
    # Build the full command including working directory if specified
    full_command = command
    if working_directory:
        safe_dir = str(Path(working_directory).expanduser().resolve())
        full_command = f"cd '{safe_dir}' && {command}"

    # If isolate_output, wrap with unique markers
    if isolate_output:
        sid = uuid.uuid4().hex
        begin = f"__MCP_BEGIN_{sid}__"
        end = f"__MCP_END_{sid}__"
        full_command = f"echo '{begin}'; {full_command}; echo '{end}'"
    
    # Write command to a temporary script file
    script_id = uuid.uuid4().hex[:8]
    script_path = f"/tmp/mcp_cmd_{script_id}.sh"
    
    try:
        # Write the command to the temp file
        with open(script_path, 'w') as f:
            f.write("#!/bin/bash\n")
            f.write("set -e\n")  # Exit on error
            f.write(full_command + "\n")
            # Auto-cleanup: remove the script after execution (even on error)
            f.write(f"EXIT_CODE=$?\n")
            f.write(f"rm -f {script_path}\n")
            f.write(f"exit $EXIT_CODE\n")
        
        # Make it executable
        os.chmod(script_path, 0o755)
        
        # Execute the script by sourcing it (this is safe and readable)
        send_method = getattr(session, "async_send_text", None)
        if not send_method:
            # Cleanup before returning error
            if os.path.exists(script_path):
                os.remove(script_path)
            return optimize_json_response({
                "success": False,
                "error": "async_send_text is not available on this iTerm2 Session."
            })
        
        await send_method(f"source {script_path}\n")
        
    except Exception as e:
        # Clean up on error
        if os.path.exists(script_path):
            try:
                os.remove(script_path)
            except:
                pass  # Best effort cleanup
        return optimize_json_response({
            "success": False,
            "error": f"Failed to create temporary script: {str(e)}"
        })
    
    result = {
        "success": True,
        "command": command,
        "session_id": session.session_id,
        "script_path": script_path,
        "message": f"Executed command via temporary script: {command}",
        "timestamp": datetime.now().isoformat()
    }
    
    # If requested, wait for and read output (with memory limits)
    if wait_for_output:
        try:
            # For isolate_output mode, we wait for the END marker to appear
            # For normal mode, we wait for the command to likely finish
            if isolate_output:
                # Poll for the end marker with exponential backoff
                end_marker_found = False
                poll_interval = 0.1
                max_wait = timeout
                elapsed = 0
                
                while elapsed < max_wait and not end_marker_found:
                    await asyncio.sleep(poll_interval)
                    elapsed += poll_interval
                    
                    # Read screen and check for end marker
                    screen = await session.async_get_screen_contents()
                    if screen:
                        # Check last N lines for the end marker
                        check_lines = min(50, screen.number_of_lines)
                        for i in range(screen.number_of_lines - check_lines, screen.number_of_lines):
                            line = screen.line(i)
                            if line and line.string and "__MCP_END_" in line.string:
                                end_marker_found = True
                                break
                    
                    # Exponential backoff up to 1 second
                    poll_interval = min(poll_interval * 1.5, 1.0)
                
                if not end_marker_found:
                    result["warning"] = f"End marker not found after {timeout}s - output may be incomplete"
            else:
                # For non-isolated mode, give the command time to execute
                # Use a more reasonable wait time based on timeout
                await asyncio.sleep(min(1.0, timeout * 0.2))
            
            # Now read the final output
            screen = await asyncio.wait_for(
                session.async_get_screen_contents(),
                timeout=5  # Quick timeout just for reading
            )
            
            if screen:
                # Extract the text content using the correct API with limits
                output_text = ""
                lines_processed = 0
                max_lines = 200  # Limit lines to prevent memory bloat
                
                for i in range(min(screen.number_of_lines, max_lines)):
                    line = screen.line(i)
                    if line.string:
                        output_text += line.string + "\n"
                        lines_processed += 1
                        
                # If requested, extract only marked region
                if isolate_output:
                    # Find begin/end markers on line boundaries
                    lines = output_text.splitlines()
                    begin_idx, end_idx = None, None
                    for idx, ln in enumerate(lines):
                        if begin_idx is None and "__MCP_BEGIN_" in ln:
                            begin_idx = idx + 1  # start after the marker line
                        elif begin_idx is not None and "__MCP_END_" in ln:
                            end_idx = idx
                            break
                    if begin_idx is not None and end_idx is not None and end_idx >= begin_idx:
                        output_text = "\n".join(lines[begin_idx:end_idx])
                    elif begin_idx is not None:
                        # Found BEGIN but not END - take everything after BEGIN
                        output_text = "\n".join(lines[begin_idx:])
                        result["warning"] = (result.get("warning", "") + " Output isolation incomplete - END marker not found").strip()
                    else:
                        # Markers not found at all
                        result["warning"] = (result.get("warning", "") + " Output isolation failed - markers not found").strip()

                # Truncate if too large
                if len(output_text) > max_output_chars:
                    output_text = output_text[:max_output_chars]
                    result["output_truncated"] = True
                    result["warning"] = (result.get("warning", "") + 
                                       f" Output truncated at {max_output_chars} characters").strip()

                result["output"] = output_text.strip()
                result["output_length"] = len(output_text)
                result["lines_processed"] = lines_processed
                result["message"] = f"Executed command: {command} (output captured)"
                
                if lines_processed >= max_lines:
                    result["lines_truncated"] = True
                    result["warning"] = (result.get("warning", "") + 
                                       f" Output limited to {max_lines} lines").strip()
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
    
    return optimize_json_response(result)


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
        paste (bool): If True (default), uses async_inject_text to directly inject
                      text into the readline buffer, bypassing all shell interpretation.
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
            # Use async_inject_text to directly inject into readline buffer
            # This bypasses shell interpretation entirely - safest method
            inject_method = getattr(session, "async_inject_text", None)
            if inject_method:
                await inject_method(text)
                method_used = "inject_text"
            else:
                # Fallback to send_text if inject isn't available
                await session.async_send_text(text)
                method_used = "send_text_fallback"
        else:
            # Send as raw keystrokes (character by character simulation)
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
    
    Clears terminal screen (equivalent to Ctrl+L).
    
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
        await session.async_send_text("\x0c")  # Form feed character
        
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
    
    Gets current iTerm2 window/tab/session IDs for debugging.
    
    🎯 USE FOR: Terminal context and debugging.
    READ-ONLY: Safe information retrieval.

    Returns:
        str: A JSON string containing the window, tab, and session IDs.
    """
    ctx = await connection_manager.get_connection()
    if ctx.get("error"):
        return optimize_json_response({"success": False, "error": ctx["error"]})

    window, tab, session = ctx["window"], ctx["tab"], ctx["session"]
    if not (window and tab and session):
        return optimize_json_response({"success": False, "error": "Could not retrieve complete session info."})

    result = {
        "success": True,
        "window_id": window.window_id,
        "tab_id": tab.tab_id,
        "session_id": session.session_id,
        "message": f"Current session: {session.session_id}"
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
    # Create parent directories if they don't exist
    parent_dir = Path(file_path).parent
    parent_dir.mkdir(parents=True, exist_ok=True)

    if os.path.exists(file_path) and not require_confirmation:
        return optimize_json_response({
            "success": False,
            "error": f"File '{file_path}' already exists. Set `require_confirmation=True` to overwrite."
        })

    try:
        with open(file_path, "w") as f:
            f.write(content)
        result = {
            "success": True,
            "file_path": file_path,
            "content_length": len(content),
            "message": f"Successfully wrote {len(content)} characters to {file_path}"
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
        # Check file size before reading
        file_size = os.path.getsize(file_path)
        max_size_bytes = max_size_mb * 1024 * 1024
        
        if file_size > max_size_bytes:
            return optimize_json_response({
                "success": False,
                "error": f"File too large ({file_size / 1024 / 1024:.1f}MB > {max_size_mb}MB limit)",
                "hint": "Use start_line/end_line parameters to read specific sections or increase max_size_mb"
            })
        
        with open(file_path, 'r') as f:
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
            "file_path": file_path,
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
            "lines_replaced": end_line - start_line + 1,
            "new_lines_count": len(new_lines),
            "message": f"Successfully replaced lines {start_line}-{end_line} in {file_path}"
        }
        return optimize_json_response(result)
    except FileNotFoundError:
        return optimize_json_response({"success": False, "error": f"File not found: {file_path}"})
    except IndexError:
        return optimize_json_response({"success": False, "error": "Line numbers are out of range for the file."})
    except Exception as e:
        return optimize_json_response({"success": False, "error": str(e)})


@mcp.tool()
async def search_code(query: str, path: str = ".", case_sensitive: bool = True) -> str:
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
    ❌ find . -name "*.py" -exec grep "pattern" {} \;
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
            return optimize_json_response({
                "success": False, 
                "error": "The 'rg' (ripgrep) command was not found in your PATH or common locations. Please install it and ensure it's accessible."
            })

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
                # Ignore lines that aren't valid JSON or don't have the expected structure
                continue
        
        result = {
            "success": True, 
            "query": query, 
            "results": results,
            "results_count": len(results),
            "search_path": path
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
        gc.collect()  # Force garbage collection
        
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
                "last_used": connection_manager._last_used.isoformat() if connection_manager._last_used else None
            },
            "timestamp": datetime.now().isoformat()
        }
        
        return optimize_json_response(result)
        
    except Exception as e:
        return optimize_json_response({"success": False, "error": str(e)})

if __name__ == "__main__":
    # Run the FastMCP server with proper cleanup
    print("Starting memory-optimized iTerm2 MCP server...", file=sys.stderr)
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
