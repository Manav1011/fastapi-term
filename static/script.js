class Terminal {
    constructor() {
        this.socket = null;
        this.output = document.getElementById('output');
        this.input = document.getElementById('command-input');
        this.prompt = document.getElementById('prompt');
        this.statusElement = document.getElementById('connection-status');
        this.directoryElement = document.getElementById('current-directory');
        this.commandHistory = [];
        this.historyIndex = -1;
        this.currentDirectory = '';
        this.interactiveMode = false;
        this.currentLine = '';
        
        this.initializeEventListeners();
        this.connect();
    }
    
    initializeEventListeners() {
        // Handle command input
        this.input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                if (this.interactiveMode) {
                    this.sendInputToShell();
                } else {
                    this.executeCommand();
                }
            } else if (e.key === 'ArrowUp' && !this.interactiveMode) {
                e.preventDefault();
                this.navigateHistory(-1);
            } else if (e.key === 'ArrowDown' && !this.interactiveMode) {
                e.preventDefault();
                this.navigateHistory(1);
            } else if (e.key === 'Tab') {
                e.preventDefault();
                // Could implement tab completion here
            } else if (this.interactiveMode) {
                // In interactive mode, send all key presses immediately for special keys
                if (e.ctrlKey || e.key === 'Backspace' || e.key === 'Delete' || 
                    e.key === 'ArrowUp' || e.key === 'ArrowDown' || 
                    e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
                    // Let these through to be handled by the shell
                }
            }
        });
        
        // Handle real-time input in interactive mode
        this.input.addEventListener('input', (e) => {
            if (this.interactiveMode) {
                // In interactive mode, we could send character by character
                // For now, we'll handle it on Enter
            }
        });
        
        // Handle window resize
        window.addEventListener('resize', () => {
            if (this.interactiveMode) {
                this.sendTerminalResize();
            }
        });
        
        // Keep input focused
        document.addEventListener('click', () => {
            this.input.focus();
        });
        
        // Focus input when page loads
        window.addEventListener('load', () => {
            this.input.focus();
        });
    }
    
    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        this.updateStatus('Connecting...', 'connecting');
        
        this.socket = new WebSocket(wsUrl);
        
        this.socket.onopen = () => {
            this.updateStatus('Connected', 'connected');
            this.addOutput('Connected to FastAPI Terminal', 'success-text');
        };
        
        this.socket.onmessage = (event) => {
            const message = JSON.parse(event.data);
            this.handleMessage(message);
        };
        
        this.socket.onclose = () => {
            this.updateStatus('Disconnected', 'disconnected');
            this.addOutput('Connection closed', 'error-text');
        };
        
        this.socket.onerror = (error) => {
            this.updateStatus('Error', 'disconnected');
            this.addOutput('Connection error occurred', 'error-text');
            console.error('WebSocket error:', error);
        };
    }
    
    disconnect() {
        if (this.socket) {
            this.socket.close();
        }
    }
    
    updateStatus(status, type) {
        this.statusElement.textContent = status;
        this.statusElement.parentElement.className = `status-bar status-${type}`;
    }
    
    executeCommand() {
        const command = this.input.value.trim();
        
        if (!command) {
            return;
        }
        
        // Add to history (only in non-interactive mode)
        if (!this.interactiveMode) {
            this.commandHistory.push(command);
            this.historyIndex = this.commandHistory.length;
            
            // Display the command
            this.addOutput(`${this.getPromptText()}${command}`, 'command-line');
        }
        
        // Send command to server
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify({
                type: 'command',
                command: command
            }));
        } else {
            this.addOutput('Not connected to server', 'error-text');
        }
        
        // Clear input
        this.input.value = '';
    }
    
    sendInputToShell() {
        const input = this.input.value;
        
        // Show what user typed (for interactive commands)
        if (input.trim()) {
            this.addFormattedOutput(input, 'user-input');
        }
        
        // Send input to shell
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify({
                type: 'input',
                data: input + '\n'
            }));
        }
        
        // Clear input
        this.input.value = '';
    }
    
    sendTerminalResize() {
        // Calculate terminal size based on container
        const terminalRect = this.output.getBoundingClientRect();
        const charWidth = 8; // Approximate character width
        const charHeight = 16; // Approximate character height
        
        const cols = Math.floor(terminalRect.width / charWidth);
        const rows = Math.floor(terminalRect.height / charHeight);
        
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify({
                type: 'resize',
                cols: cols,
                rows: rows
            }));
        }
    }
    
    handleMessage(message) {
        switch (message.type) {
            case 'prompt':
                this.currentDirectory = message.cwd;
                this.updatePrompt();
                this.addOutput(message.message, 'success-text');
                break;
                
            case 'output':
                // Handle interactive mode changes
                if (message.hasOwnProperty('interactive')) {
                    this.interactiveMode = message.interactive;
                    this.updatePromptForMode();
                }
                
                if (message.clear_screen) {
                    this.clear();
                    // Don't show the clear command itself
                    if (message.command !== 'clear') {
                        this.addOutput(`${this.getPromptText()}${message.command}`, 'command-line');
                    }
                } else {
                    if (message.output) {
                        let className = message.success ? 'output-text' : 'error-text';
                        
                        // Special styling for interactive command suggestions
                        if (message.suggest_interactive) {
                            className = 'warning-text';
                        }
                        
                        this.addOutput(message.output, className);
                    }
                }
                
                if (message.cwd) {
                    this.currentDirectory = message.cwd;
                    this.updatePrompt();
                }
                break;
                
            case 'shell_output':
                // Real-time output from interactive shell
                if (message.output) {
                    this.addRawOutput(message.output);
                }
                break;
                
            default:
                console.log('Unknown message type:', message);
        }
    }
    
    addRawOutput(text) {
        // Clean and process the raw terminal output
        const cleanText = this.stripAnsiCodes(text);
        
        // Split into lines and process each one
        const lines = cleanText.split('\n');
        
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            
            // Skip empty lines unless they're meaningful
            if (line.trim() === '' && i !== lines.length - 1) {
                this.addFormattedOutput('', 'raw-output');
                continue;
            }
            
            // Process the line content
            this.processTerminalLine(line, i === lines.length - 1 && !text.endsWith('\n'));
        }
    }
    
    processTerminalLine(line, isLastLine) {
        // Clean up the line
        let cleanLine = line.trim();
        
        // Skip if completely empty
        if (!cleanLine && !isLastLine) {
            return;
        }
        
        // Detect and format different types of content
        if (this.isPromptLine(cleanLine)) {
            this.addFormattedOutput(this.formatPrompt(cleanLine), 'shell-prompt');
        } else if (this.isPasswordPrompt(cleanLine)) {
            this.addFormattedOutput(cleanLine, 'password-prompt');
        } else if (cleanLine) {
            this.addFormattedOutput(cleanLine, 'raw-output');
        }
    }
    
    isPromptLine(line) {
        // Detect shell prompts
        return /[@$#]\s*$/.test(line) || 
               /^\w+@\w+.*[$#]\s*$/.test(line) ||
               line.includes('web-h-063@web-h-063');
    }
    
    isPasswordPrompt(line) {
        // Detect password prompts
        return line.toLowerCase().includes('password') || 
               line.includes('[sudo]') ||
               line.includes('Password:');
    }
    
    formatPrompt(line) {
        // Extract just the essential prompt information
        if (line.includes('web-h-063@web-h-063')) {
            // Extract the working directory and prompt symbol
            const match = line.match(/:([^$#]+)[$#]/);
            if (match) {
                const dir = match[1].replace(/~/g, '~');
                const symbol = line.includes('#') ? '#' : '$';
                return `${dir}${symbol}`;
            }
        }
        return line;
    }
    
    stripAnsiCodes(text) {
        // Remove all ANSI escape sequences and control characters
        return text
            // Remove ANSI color codes and cursor movement
            .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')
            // Remove ANSI operating system commands
            .replace(/\x1b\][0-9]*;[^\x07]*\x07/g, '')
            // Remove other ANSI sequences
            .replace(/\x1b[=>]/g, '')
            // Remove backspace sequences
            .replace(/[\x08\x7f]/g, '')
            // Remove carriage returns but keep newlines
            .replace(/\r\n/g, '\n')
            .replace(/\r/g, '')
            // Remove bell characters
            .replace(/\x07/g, '')
            // Remove other control characters except newline and tab
            .replace(/[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]/g, '')
            // Clean up multiple spaces
            .replace(/[ \t]+/g, ' ')
            // Remove trailing whitespace from lines
            .replace(/ +$/gm, '');
    }
    
    addFormattedOutput(text, className = 'output-text') {
        const line = document.createElement('div');
        line.className = `output-line ${className}`;
        
        // Handle different types of content
        if (className === 'raw-output') {
            // For raw shell output, clean it up further
            const cleanText = text.replace(/^\s+|\s+$/g, ''); // trim
            if (cleanText) {
                line.textContent = cleanText;
            } else {
                // Empty line - add minimal spacing
                line.innerHTML = '&nbsp;';
                line.style.height = '0.5em';
            }
        } else if (className === 'shell-prompt') {
            // Format shell prompts nicely
            line.textContent = text;
            line.style.fontWeight = 'bold';
        } else if (className === 'password-prompt') {
            // Highlight password prompts
            line.textContent = text;
        } else {
            line.textContent = text;
        }
        
        this.output.appendChild(line);
        
        // Auto-scroll to bottom
        this.output.scrollTop = this.output.scrollHeight;
    }
    
    updatePromptForMode() {
        const modeIndicator = document.querySelector('.mode-indicator');
        
        if (this.interactiveMode) {
            this.input.placeholder = 'Interactive shell mode - type commands or input...';
            this.prompt.textContent = '>';
            if (modeIndicator) {
                modeIndicator.textContent = 'Interactive Mode | Type "exit" to return to normal mode';
                modeIndicator.style.color = '#4ec9b0';
            }
        } else {
            this.input.placeholder = 'Type commands here...';
            this.updatePrompt();
            if (modeIndicator) {
                modeIndicator.textContent = 'Normal Mode | Type "interactive" for interactive shell';
                modeIndicator.style.color = 'rgba(255,255,255,0.8)';
            }
        }
    }
    
    addOutput(text, className = 'output-text') {
        this.addFormattedOutput(text, className);
    }
    
    updatePrompt() {
        if (!this.interactiveMode) {
            const shortPath = this.getShortPath(this.currentDirectory);
            this.prompt.textContent = `${shortPath}$`;
            this.directoryElement.textContent = this.currentDirectory;
        }
    }
    
    getPromptText() {
        return this.prompt.textContent + ' ';
    }
    
    getShortPath(path) {
        if (!path) return '~';
        
        const home = '/home/' + (process.env.USER || 'user');
        if (path.startsWith(home)) {
            return '~' + path.substring(home.length);
        }
        
        const parts = path.split('/');
        if (parts.length > 3) {
            return '.../' + parts.slice(-2).join('/');
        }
        
        return path;
    }
    
    navigateHistory(direction) {
        if (this.commandHistory.length === 0) return;
        
        this.historyIndex += direction;
        
        if (this.historyIndex < 0) {
            this.historyIndex = 0;
        } else if (this.historyIndex >= this.commandHistory.length) {
            this.historyIndex = this.commandHistory.length;
            this.input.value = '';
            return;
        }
        
        this.input.value = this.commandHistory[this.historyIndex] || '';
    }
    
    clear() {
        this.output.innerHTML = '';
    }
}

// Global functions for UI controls
function clearTerminal() {
    if (window.terminal) {
        window.terminal.clear();
    }
}

function toggleConnection() {
    if (window.terminal) {
        if (window.terminal.socket && window.terminal.socket.readyState === WebSocket.OPEN) {
            window.terminal.disconnect();
        } else {
            window.terminal.connect();
        }
    }
}

// Initialize terminal when page loads
document.addEventListener('DOMContentLoaded', () => {
    window.terminal = new Terminal();
});
