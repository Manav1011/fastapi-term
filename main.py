import asyncio
import subprocess
import json
import os
import pty
import select
import termios
import fcntl
import struct
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import Dict, Any, Optional
import shlex
import signal

app = FastAPI(title="FastAPI Terminal", description="Web-based terminal interface")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

class TerminalSession:
    def __init__(self):
        self.current_directory = os.getcwd()
        self.environment = os.environ.copy()
        self.shell_process = None
        self.master_fd = None
        self.websocket = None
        self.input_task = None
        self.output_task = None
        self.interactive_mode = False
    
    async def start_interactive_shell(self, websocket: WebSocket):
        """Start an interactive shell session using pty"""
        self.websocket = websocket
        
        try:
            # Create a pseudo-terminal
            self.master_fd, slave_fd = pty.openpty()
            
            # Set terminal size
            self._set_terminal_size(80, 24)
            
            # Set up a clean environment for the shell
            clean_env = self.environment.copy()
            clean_env['PS1'] = r'\u@\h:\w\$ '  # Simple, clean prompt
            clean_env['TERM'] = 'dumb'  # Disable fancy terminal features
            clean_env['COLUMNS'] = '80'
            clean_env['LINES'] = '24'
            
            # Start shell process with clean settings
            self.shell_process = await asyncio.create_subprocess_exec(
                '/bin/bash',
                '--noprofile',  # Don't load profile
                '--norc',       # Don't load bashrc
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=self.current_directory,
                env=clean_env,
                preexec_fn=os.setsid
            )
            
            # Close slave fd in parent process
            os.close(slave_fd)
            
            # Make master_fd non-blocking
            fcntl.fcntl(self.master_fd, fcntl.F_SETFL, os.O_NONBLOCK)
            
            self.interactive_mode = True
            
            # Send initial setup commands to clean up the shell
            await asyncio.sleep(0.1)  # Let shell initialize
            
            # Disable command history and other features that create noise
            setup_commands = [
                'unset HISTFILE',
                'set +H',  # Disable history expansion
                'export PS1="\\u@\\h:\\w\\$ "',
                'clear'
            ]
            
            for cmd in setup_commands:
                os.write(self.master_fd, (cmd + '\n').encode('utf-8'))
                await asyncio.sleep(0.05)
            
            # Start output reading task
            self.output_task = asyncio.create_task(self._read_shell_output())
            
            return True
            
        except Exception as e:
            print(f"Failed to start interactive shell: {e}")
            if self.master_fd:
                os.close(self.master_fd)
            return False
    
    def _set_terminal_size(self, cols: int, rows: int):
        """Set terminal size"""
        if self.master_fd:
            try:
                # Set window size
                winsize = struct.pack('HHHH', rows, cols, 0, 0)
                fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
            except:
                pass
    
    async def _read_shell_output(self):
        """Read output from shell and send to websocket"""
        buffer = ""
        last_send_time = asyncio.get_event_loop().time()
        
        while self.interactive_mode and self.master_fd and self.websocket:
            try:
                # Use select to check if data is available
                ready, _, _ = select.select([self.master_fd], [], [], 0.1)
                current_time = asyncio.get_event_loop().time()
                
                if ready:
                    try:
                        data = os.read(self.master_fd, 1024)
                        if data:
                            # Decode and add to buffer
                            chunk = data.decode('utf-8', errors='replace')
                            buffer += chunk
                            
                            # Send buffered output if we have complete lines or after a delay
                            if ('\n' in buffer or 
                                len(buffer) > 50 or 
                                current_time - last_send_time > 0.2):
                                
                                if buffer.strip():  # Only send non-empty content
                                    await self.websocket.send_text(json.dumps({
                                        "type": "shell_output",
                                        "output": buffer,
                                        "interactive": True
                                    }))
                                
                                buffer = ""
                                last_send_time = current_time
                        else:
                            # Shell process ended
                            if buffer.strip():
                                await self.websocket.send_text(json.dumps({
                                    "type": "shell_output",
                                    "output": buffer,
                                    "interactive": True
                                }))
                            break
                    except BlockingIOError:
                        # No data available, send any buffered data if timeout
                        if buffer.strip() and current_time - last_send_time > 0.3:
                            await self.websocket.send_text(json.dumps({
                                "type": "shell_output",
                                "output": buffer,
                                "interactive": True
                            }))
                            buffer = ""
                            last_send_time = current_time
                    except OSError:
                        # Shell process ended
                        break
                
                # Small delay to allow buffering
                await asyncio.sleep(0.02)
                
            except Exception as e:
                print(f"Error reading shell output: {e}")
                break
        
        # Send any remaining buffer
        if buffer.strip():
            try:
                await self.websocket.send_text(json.dumps({
                    "type": "shell_output",
                    "output": buffer,
                    "interactive": True
                }))
            except:
                pass
        
        self.interactive_mode = False
    
    async def send_input_to_shell(self, data: str):
        """Send input to the interactive shell"""
        if self.master_fd and self.interactive_mode:
            try:
                os.write(self.master_fd, data.encode('utf-8'))
                return True
            except Exception as e:
                print(f"Error sending input to shell: {e}")
                return False
        return False
    
    async def stop_interactive_shell(self):
        """Stop the interactive shell session"""
        self.interactive_mode = False
        
        if self.output_task:
            self.output_task.cancel()
            try:
                await self.output_task
            except asyncio.CancelledError:
                pass
        
        if self.shell_process:
            try:
                # Send SIGTERM to process group
                os.killpg(os.getpgid(self.shell_process.pid), signal.SIGTERM)
                await asyncio.wait_for(self.shell_process.wait(), timeout=2.0)
            except (ProcessLookupError, asyncio.TimeoutError):
                # Force kill if needed
                try:
                    os.killpg(os.getpgid(self.shell_process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
        
        if self.master_fd:
            try:
                os.close(self.master_fd)
            except:
                pass
            self.master_fd = None
        
        self.shell_process = None
    
    async def execute_command(self, command: str) -> Dict[str, Any]:
        """Execute a command and return the result"""
        try:
            # Handle clear command specially
            if command.strip() == 'clear':
                return await self._handle_clear_command()
            
            # Check if command typically requires interactive input
            interactive_commands = ['sudo', 'su', 'ssh', 'mysql', 'psql', 'passwd', 'python3', 'python', 'node', 'npm login', 'git push', 'docker login']
            command_parts = command.strip().split()
            
            if (command_parts and any(cmd in command_parts[0] for cmd in interactive_commands) 
                and not self.interactive_mode):
                return {
                    "success": False,
                    "output": f"⚠️  Command '{command_parts[0]}' typically requires user input.\n" +
                             "Switch to interactive mode first by typing: interactive\n" +
                             "Then run your command again.",
                    "exit_code": 1,
                    "suggest_interactive": True
                }
            
            # Handle cd command specially (for non-interactive mode)
            if command.strip().startswith('cd ') and not self.interactive_mode:
                return await self._handle_cd_command(command)
            
            # If in interactive mode, send to shell
            if self.interactive_mode:
                await self.send_input_to_shell(command + '\n')
                return {
                    "success": True,
                    "output": "",
                    "interactive": True,
                    "exit_code": 0
                }
            
            # Handle other commands in non-interactive mode
            return await self._execute_system_command(command)
            
        except Exception as e:
            return {
                "success": False,
                "output": f"Error: {str(e)}",
                "error": str(e),
                "exit_code": 1
            }
    
    async def _handle_clear_command(self) -> Dict[str, Any]:
        """Handle clear command to clear the terminal screen"""
        return {
            "success": True,
            "output": "",
            "exit_code": 0,
            "clear_screen": True,
            "cwd": self.current_directory
        }
    
    async def _handle_cd_command(self, command: str) -> Dict[str, Any]:
        """Handle directory change commands"""
        try:
            # Parse the cd command
            parts = shlex.split(command.strip())
            if len(parts) == 1:
                # cd with no arguments - go to home directory
                target_dir = os.path.expanduser("~")
            else:
                target_dir = parts[1]
            
            # Resolve relative paths
            if not os.path.isabs(target_dir):
                target_dir = os.path.join(self.current_directory, target_dir)
            
            # Normalize the path
            target_dir = os.path.normpath(target_dir)
            
            # Check if directory exists
            if os.path.isdir(target_dir):
                self.current_directory = target_dir
                return {
                    "success": True,
                    "output": f"Changed directory to: {self.current_directory}",
                    "exit_code": 0,
                    "cwd": self.current_directory
                }
            else:
                return {
                    "success": False,
                    "output": f"cd: no such file or directory: {target_dir}",
                    "exit_code": 1
                }
        except Exception as e:
            return {
                "success": False,
                "output": f"cd: {str(e)}",
                "exit_code": 1
            }
    
    async def _execute_system_command(self, command: str) -> Dict[str, Any]:
        """Execute a system command"""
        try:
            # Create the process
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=self.current_directory,
                env=self.environment
            )
            
            # Wait for completion and get output
            stdout, _ = await process.communicate()
            
            output = stdout.decode('utf-8', errors='replace') if stdout else ""
            
            return {
                "success": process.returncode == 0,
                "output": output,
                "exit_code": process.returncode,
                "cwd": self.current_directory
            }
            
        except Exception as e:
            return {
                "success": False,
                "output": f"Command execution failed: {str(e)}",
                "error": str(e),
                "exit_code": 1
            }

# Store terminal sessions for each WebSocket connection
sessions: Dict[str, TerminalSession] = {}

@app.get("/")
async def get_terminal():
    """Serve the terminal interface"""
    return FileResponse("static/index.html")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Create a unique session for this connection
    session_id = id(websocket)
    sessions[session_id] = TerminalSession()
    
    try:
        # Send initial prompt
        await websocket.send_text(json.dumps({
            "type": "prompt",
            "cwd": sessions[session_id].current_directory,
            "message": f"FastAPI Terminal - Current directory: {sessions[session_id].current_directory}\nType 'interactive' to start interactive shell mode."
        }))
        
        while True:
            # Receive command from client
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message["type"] == "command":
                command = message["command"].strip()
                
                if not command:
                    continue
                
                # Handle special commands
                if command == "interactive":
                    # Start interactive shell
                    success = await sessions[session_id].start_interactive_shell(websocket)
                    if success:
                        await websocket.send_text(json.dumps({
                            "type": "output",
                            "command": command,
                            "success": True,
                            "output": "Interactive shell started. You can now run commands that require input.\nType 'exit' to return to normal mode.",
                            "interactive": True,
                            "exit_code": 0
                        }))
                    else:
                        await websocket.send_text(json.dumps({
                            "type": "output",
                            "command": command,
                            "success": False,
                            "output": "Failed to start interactive shell",
                            "exit_code": 1
                        }))
                    continue
                
                elif command == "exit" and sessions[session_id].interactive_mode:
                    # Exit interactive mode
                    await sessions[session_id].stop_interactive_shell()
                    await websocket.send_text(json.dumps({
                        "type": "output",
                        "command": command,
                        "success": True,
                        "output": "Exited interactive shell mode",
                        "interactive": False,
                        "exit_code": 0,
                        "cwd": sessions[session_id].current_directory
                    }))
                    continue
                
                # Execute the command
                result = await sessions[session_id].execute_command(command)
                
                # Send result back to client (only if not interactive)
                if not result.get("interactive", False):
                    await websocket.send_text(json.dumps({
                        "type": "output",
                        "command": command,
                        "success": result["success"],
                        "output": result["output"],
                        "exit_code": result.get("exit_code", 0),
                        "cwd": result.get("cwd", sessions[session_id].current_directory),
                        "clear_screen": result.get("clear_screen", False)
                    }))
            
            elif message["type"] == "input":
                # Send input to interactive shell
                if sessions[session_id].interactive_mode:
                    await sessions[session_id].send_input_to_shell(message["data"])
            
            elif message["type"] == "resize":
                # Handle terminal resize
                if sessions[session_id].interactive_mode:
                    cols = message.get("cols", 80)
                    rows = message.get("rows", 24)
                    sessions[session_id]._set_terminal_size(cols, rows)
                
    except WebSocketDisconnect:
        # Clean up session when client disconnects
        if session_id in sessions:
            await sessions[session_id].stop_interactive_shell()
            del sessions[session_id]
    except Exception as e:
        print(f"WebSocket error: {e}")
        if session_id in sessions:
            await sessions[session_id].stop_interactive_shell()
            del sessions[session_id]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
