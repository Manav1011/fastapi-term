# FastAPI Terminal

A web-based terminal interface built with FastAPI that allows you to execute system commands through a browser.

## Features

- **Real-time terminal interface**: Execute commands and see output in real-time
- **WebSocket communication**: Fast, bidirectional communication between client and server
- **Command history**: Navigate through previous commands with arrow keys
- **Directory tracking**: Maintains current working directory across commands
- **Responsive design**: Works on desktop and mobile devices
- **Security considerations**: Basic command validation and error handling

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python main.py
```

3. Open your browser and navigate to:
```
http://localhost:8000
```

## Usage

- Type commands in the terminal interface and press Enter to execute
- Use arrow keys (↑/↓) to navigate command history
- The `cd` command is handled specially to maintain directory state
- Click "Clear" to clear the terminal output
- Click "Disconnect" to close the WebSocket connection

## Security Warning

⚠️ **Important**: This application executes system commands with the same privileges as the Python process. In a production environment, you should:

- Implement proper authentication and authorization
- Restrict allowed commands or use a sandboxed environment
- Run with limited user privileges
- Add input validation and sanitization
- Consider using Docker containers for isolation

## File Structure

```
fastapi-termina/
├── main.py              # FastAPI application and WebSocket handler
├── requirements.txt     # Python dependencies
├── static/
│   ├── index.html      # Terminal UI
│   ├── style.css       # Terminal styling
│   └── script.js       # Client-side logic
└── README.md           # This file
```

## Technical Details

### Backend (main.py)
- FastAPI application with WebSocket support
- `TerminalSession` class manages command execution and directory state
- Special handling for `cd` commands to maintain working directory
- Asynchronous command execution using `asyncio.create_subprocess_shell`

### Frontend
- HTML5 with responsive CSS design
- JavaScript WebSocket client for real-time communication
- Command history navigation
- Terminal-like styling with proper fonts and colors

### Communication Protocol
WebSocket messages use JSON format:

**Client to Server:**
```json
{
  "type": "command",
  "command": "ls -la"
}
```

**Server to Client:**
```json
{
  "type": "output",
  "command": "ls -la",
  "success": true,
  "output": "...",
  "exit_code": 0,
  "cwd": "/current/directory"
}
```

## Development

To extend this application:

1. **Add authentication**: Implement user login and session management
2. **Command restrictions**: Create allow/deny lists for commands
3. **File upload/download**: Add file transfer capabilities
4. **Multiple sessions**: Support multiple terminal sessions per user
5. **Syntax highlighting**: Add command syntax highlighting
6. **Tab completion**: Implement command and path completion

## License

This project is open source and available under the MIT License.
# fastapi-term
