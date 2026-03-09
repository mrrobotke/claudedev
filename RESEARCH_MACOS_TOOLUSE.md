# ClaudeDev macOS Tool Use Research
## Comprehensive Guide to Maximum Autonomous AI Agent Capability on macOS

**System Under Test:** macOS 26.3 (Darwin 25.3.0) | Apple M5 (10 cores: 4P + 6E) | 16 GB RAM | Metal 4 GPU
**Date:** 2026-03-09
**Purpose:** Document every macOS capability an autonomous AI coding agent (ClaudeDev) can leverage for maximum tool use.

---

## Table of Contents

1. [macOS System Capabilities for AI Agents](#1-macos-system-capabilities-for-ai-agents)
2. [macOS Developer Tools Integration](#2-macos-developer-tools-integration)
3. [File System and Project Understanding](#3-file-system-and-project-understanding)
4. [Local AI Inference on macOS](#4-local-ai-inference-on-macos)
5. [Secure and Private Operations](#5-secure-and-private-operations)
6. [Process and Resource Management](#6-process-and-resource-management)
7. [Distribution on macOS](#7-distribution-on-macos)
8. [Claude Code CLI Integration on macOS](#8-claude-code-cli-integration-on-macos)
9. [RECOMMENDED macOS TOOL USE ARCHITECTURE](#9-recommended-macos-tool-use-architecture)

---

## 1. macOS System Capabilities for AI Agents

### 1.1 Terminal / Shell (zsh, bash)

**What's Possible:**
- Full POSIX-compliant shell access via `/bin/zsh` (default) and `/bin/bash`
- Execute any CLI tool, compiler, interpreter, or system utility
- Pipe-based composition of tools (`cmd1 | cmd2 | cmd3`)
- Background process management (`&`, `nohup`, `disown`)
- Shell scripting for complex multi-step workflows
- Process substitution, here-docs, and advanced redirections

**Implementation:**
```python
import subprocess
import shlex

def run_shell(cmd: str, cwd: str = None, timeout: int = 120) -> tuple[str, str, int]:
    """Execute a shell command and return (stdout, stderr, returncode)."""
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout,
        env={**os.environ}  # Inherit environment
    )
    return result.stdout, result.stderr, result.returncode
```

**Python Libraries:**
- `subprocess` (stdlib) -- primary interface
- `shlex` (stdlib) -- safe command parsing
- `pexpect` -- interactive process control (for tools requiring input)
- `asyncio.create_subprocess_exec` -- async subprocess management

**Performance on Apple Silicon:** Native. Shell execution is extremely fast. The 4 performance cores handle burst workloads; 6 efficiency cores handle sustained background operations.

**Security:** Commands run with the user's permissions. Sandboxing via `sandbox-exec` is available but rarely used. The agent should maintain an allowlist of safe commands and never execute untrusted input directly.

---

### 1.2 AppleScript / JXA (JavaScript for Automation)

**What's Possible:**
- Script ANY macOS application that exposes an AppleScript dictionary (most do)
- Control Finder, Safari, Chrome, Mail, Calendar, Reminders, Notes, Terminal, Xcode, and more
- Read and manipulate application state (windows, documents, selections)
- Create and send emails, calendar events, reminders
- Control System Preferences/Settings
- Execute UI actions via System Events (click buttons, type text, navigate menus)
- Launch and quit applications
- Interact with Notification Center

**Scriptable Applications Detected on This System:**
Google Chrome, TextEdit, iTerm2, System Settings, Finder, Safari, Docker Desktop, Claude, Sublime Text, Cursor

**Available Scripting Languages:**
- AppleScript (native)
- JavaScript for Automation (JXA) -- modern alternative
- Generic Scripting System

**Implementation (AppleScript via osascript):**
```python
import subprocess

def run_applescript(script: str) -> str:
    """Execute AppleScript and return output."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True
    )
    return result.stdout.strip()

def run_jxa(script: str) -> str:
    """Execute JavaScript for Automation."""
    result = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", script],
        capture_output=True, text=True
    )
    return result.stdout.strip()

# Examples:
# Get frontmost app name
run_applescript('tell application "System Events" to get name of first application process whose frontmost is true')

# List all open windows
run_jxa('Application("System Events").processes().filter(p => !p.backgroundOnly()).map(p => p.name())')

# Send notification
run_applescript('display notification "Build complete!" with title "ClaudeDev" sound name "Glass"')

# Open URL in default browser
run_applescript('open location "https://github.com"')

# Get Chrome tab URLs
run_jxa('''
  var chrome = Application("Google Chrome");
  chrome.windows().flatMap(w => w.tabs().map(t => t.url()));
''')
```

**Implementation (JXA for complex operations):**
```python
# Control Xcode
run_jxa('''
  var xcode = Application("Xcode");
  xcode.activate();
  var workspace = xcode.workspaceDocuments[0];
  workspace.build();
''')

# Manipulate Finder
run_jxa('''
  var finder = Application("Finder");
  var desktop = finder.desktop;
  desktop.files().map(f => f.name());
''')
```

**Python Libraries:**
- `subprocess` + `osascript` -- simplest approach
- `pyobjc-framework-ScriptingBridge` -- native Cocoa scripting bridge
- `appscript` (deprecated but functional) -- Pythonic AppleScript wrapper

**Performance:** AppleScript execution is fast (< 100ms for simple commands). JXA is slightly faster. Main overhead is IPC to target applications.

**Security:** Requires user approval for controlling other applications (Accessibility permission). System Events access requires explicit TCC grant.

---

### 1.3 Accessibility API

**What's Possible:**
- Read the full UI element hierarchy of ANY running application
- Get text content, button labels, menu items, form values from any app
- Programmatically click buttons, type text, select menu items
- Monitor UI changes in real-time (observers)
- Extract accessibility trees for AI understanding of app state
- Automate applications that have no scripting dictionary

**Implementation (via PyObjC):**
```python
import AppKit
import ApplicationServices

def get_frontmost_app_elements():
    """Get accessibility tree of the frontmost application."""
    app = ApplicationServices.AXUIElementCreateSystemWide()
    # Get focused application
    err, focused_app = ApplicationServices.AXUIElementCopyAttributeValue(
        app, "AXFocusedApplication", None
    )
    if err == 0:
        # Get all windows
        err, windows = ApplicationServices.AXUIElementCopyAttributeValue(
            focused_app, "AXWindows", None
        )
        return windows
    return None

def click_element(element):
    """Perform a click action on an AX element."""
    ApplicationServices.AXUIElementPerformAction(element, "AXPress")
```

**Python Libraries:**
- `pyobjc-framework-Accessibility` (v12.1 available) -- direct API bindings
- `pyobjc-framework-ApplicationServices` -- AX functions
- `atomacos` -- high-level GUI testing framework for macOS
- `pyatomac` -- another high-level wrapper
- `macapptree` -- extracts accessibility trees as JSON with bounding boxes

**macapptree for AI Agents:**
```python
# macapptree extracts accessibility trees in JSON format
# Ideal for feeding to LLMs for understanding app state
import macapptree
tree = macapptree.get_tree(app_name="Xcode")
# Returns structured JSON with element roles, labels, values, positions
```

**Performance:** Accessibility API calls are synchronous and typically complete in 1-10ms per element. Full tree traversal of a complex app might take 50-200ms.

**Security:** Requires the calling application to have "Accessibility" permission in System Settings > Privacy & Security > Accessibility. This is a one-time user grant. The agent MUST request this permission explicitly during setup.

---

### 1.4 Shortcuts.app

**What's Possible:**
- Execute pre-built or custom Shortcuts from the CLI
- Chain complex multi-app workflows
- Access system capabilities (location, network, files, clipboard)
- Run Shortcuts with input data and capture output
- Integrate with HomeKit, Siri, and system automation

**Shortcuts Available on This System (sample):**
Antony, Order, Babe, I Miss Her, Take a Break, Text Last Image, Shazam shortcut, Make GIF, Choose from Menu

**Implementation:**
```bash
# List all shortcuts
shortcuts list

# Run a shortcut
shortcuts run "My Shortcut"

# Run with input from stdin
echo "input data" | shortcuts run "My Shortcut" --input-path -

# Run and capture output
shortcuts run "My Shortcut" --output-path /tmp/output.txt --output-type public.plain-text
```

```python
def run_shortcut(name: str, input_data: str = None) -> str:
    """Execute a macOS Shortcut and return output."""
    cmd = ["shortcuts", "run", name]
    if input_data:
        cmd.extend(["--input-path", "-"])
    result = subprocess.run(
        cmd,
        input=input_data,
        capture_output=True, text=True
    )
    return result.stdout
```

**Performance:** Shortcut execution adds ~200-500ms overhead for framework initialization, but individual actions run quickly.

**Security:** Some actions require user confirmation. The Shortcuts runtime has its own sandboxing model.

---

### 1.5 Automator (Legacy)

**What's Possible:**
- Run existing Automator workflows from CLI
- Service workflows for contextual actions
- Folder actions for automatic file processing
- Calendar-triggered automations
- Print plugin workflows

**Implementation:**
```bash
# Run an Automator workflow
automator /path/to/workflow.workflow

# Run from Python
subprocess.run(["automator", workflow_path])
```

**Note:** Automator is considered legacy. Apple is migrating to Shortcuts. However, Automator workflows remain functional and some capabilities (folder actions, print plugins) are not yet fully replicated in Shortcuts.

---

### 1.6 XPC Services (Inter-Process Communication)

**What's Possible:**
- Create lightweight services that run in separate processes
- Communicate between ClaudeDev components securely
- Build a microservice architecture on the local machine
- Leverage macOS kernel-level IPC for low-latency messaging

**Implementation (via PyObjC):**
```python
import objc
from Foundation import NSXPCConnection, NSXPCInterface

# PyObjC can create XPC connections to system services
# and custom XPC services

# For most agent needs, simpler IPC (Unix sockets, named pipes) is preferred
import socket, json

def create_ipc_server(socket_path: str):
    """Create a Unix domain socket server for inter-component IPC."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(socket_path)
    sock.listen(5)
    return sock
```

**Python Libraries:**
- `pyobjc-framework-Cocoa` -- XPC bindings
- `multiprocessing.connection` (stdlib) -- simpler IPC
- Unix domain sockets via `socket` (stdlib) -- fastest IPC option

**Performance:** XPC is kernel-optimized for low latency. Unix sockets add ~0.01ms per message.

**Recommendation for ClaudeDev:** Use Unix domain sockets for component IPC. Reserve XPC for integrating with macOS system services.

---

### 1.7 FSEvents (File System Monitoring)

**What's Possible:**
- Monitor any directory tree for file changes in real-time
- Detect file creation, modification, deletion, renaming
- Low CPU overhead even for thousands of files
- Kernel-level notification (no polling)
- Critical for: auto-indexing, hot-reload, build triggers, test watchers

**Implementation:**
```python
from watchfiles import watch, Change

# watchfiles uses Rust's notify crate which wraps FSEvents on macOS
def watch_directory(path: str, callback):
    """Watch a directory for changes using FSEvents."""
    for changes in watch(path):
        for change_type, file_path in changes:
            if change_type == Change.modified:
                callback("modified", file_path)
            elif change_type == Change.added:
                callback("added", file_path)
            elif change_type == Change.deleted:
                callback("deleted", file_path)

# Async version
import asyncio
from watchfiles import awatch

async def async_watch_directory(path: str):
    async for changes in awatch(path):
        for change_type, file_path in changes:
            yield change_type, file_path
```

**Python Libraries:**
- `watchfiles` (v1.1.1 installed) -- Rust-backed, fastest option
- `watchdog` -- pure Python, broader feature set
- `pyobjc-framework-CoreServices` -- direct FSEvents bindings

**Performance on Apple Silicon:** FSEvents is a kernel subsystem with near-zero overhead. `watchfiles` (Rust) processes 10,000+ file events/sec with minimal CPU usage. APFS copy-on-write makes metadata operations extremely fast.

---

### 1.8 launchd (Daemon/Agent Management)

**What's Possible:**
- Run ClaudeDev components as persistent background services
- Auto-start on login, restart on crash
- Schedule recurring tasks (cron replacement)
- Resource limits and process management
- Integration with macOS power management

**Existing Launch Agents on This System:**
- `com.clawdbot.gateway.plist` (custom bot gateway)
- `homebrew.mxcl.postgresql@15.plist` (PostgreSQL)
- Various Google/system agents

**Implementation:**
```xml
<!-- ~/Library/LaunchAgents/com.claudedev.agent.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claudedev.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/iworldafric/.local/bin/claudedev</string>
        <string>daemon</string>
        <string>--mode</string>
        <string>background</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/claudedev.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/claudedev.stderr.log</string>
    <key>ProcessType</key>
    <string>Background</string>
    <key>LowPriorityBackgroundIO</key>
    <true/>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

```python
import subprocess
import plistlib

def install_launch_agent(plist_path: str, label: str):
    """Install and load a launchd agent."""
    subprocess.run(["launchctl", "load", plist_path])

def uninstall_launch_agent(plist_path: str, label: str):
    """Unload and remove a launchd agent."""
    subprocess.run(["launchctl", "unload", plist_path])

def check_agent_status(label: str) -> dict:
    """Check if a launchd agent is running."""
    result = subprocess.run(
        ["launchctl", "print", f"gui/{os.getuid()}/{label}"],
        capture_output=True, text=True
    )
    return {"running": result.returncode == 0, "output": result.stdout}
```

**Key Configuration Options:**
| Key | Purpose |
|-----|---------|
| `RunAtLoad` | Start when plist is loaded (login) |
| `KeepAlive` | Restart if process exits |
| `StartInterval` | Run every N seconds |
| `StartCalendarInterval` | Cron-like scheduling |
| `WatchPaths` | Run when specified files change |
| `ProcessType` | `Background`, `Standard`, `Interactive`, `Adaptive` |
| `LowPriorityBackgroundIO` | Reduce I/O priority for battery life |
| `ThrottleInterval` | Minimum seconds between launches |

**Performance:** launchd is the most efficient process manager on macOS. Zero overhead when services are idle. Automatic CPU/memory throttling for background processes.

**Security:** User-level agents run with user permissions. System daemons require root. No additional security permissions needed for user agents.

---

### 1.9 Spotlight / mdfind (System-Wide Search)

**What's Possible:**
- Search the entire filesystem by filename, content, or metadata
- Query by file type, creation date, modification date, author, etc.
- Real-time index maintained by the system (always current)
- Structured queries using Spotlight metadata attributes
- Live queries that update as files change

**Implementation:**
```python
def spotlight_search(query: str, directory: str = None) -> list[str]:
    """Search using Spotlight/mdfind."""
    cmd = ["mdfind"]
    if directory:
        cmd.extend(["-onlyin", directory])
    cmd.append(query)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip().split("\n") if result.stdout.strip() else []

# Find Python files in a project
spotlight_search('kMDItemContentType == "public.python-script"', "/Users/iworldafric/claudedev")

# Find files modified today
spotlight_search('kMDItemFSContentChangeDate >= $time.today')

# Find files by name
spotlight_search('-name "*.py"')

# Find files containing text
spotlight_search('kMDItemTextContent == "def main"')

# Complex metadata query
spotlight_search('kMDItemContentType == "public.python-script" && kMDItemFSSize > 10000')
```

**Key Spotlight Metadata Attributes:**
| Attribute | Description |
|-----------|-------------|
| `kMDItemContentType` | UTI file type |
| `kMDItemFSName` | File name |
| `kMDItemFSSize` | File size |
| `kMDItemFSContentChangeDate` | Last modified |
| `kMDItemTextContent` | Full text content |
| `kMDItemContentCreationDate` | Creation date |
| `kMDItemDisplayName` | Display name |

**Performance:** Spotlight's index is maintained by the system and is extremely fast (< 100ms for most queries). For code projects, it provides instant file discovery.

**Limitation:** Spotlight does not index inside `.git` directories or other hidden directories by default. Custom Spotlight importers can be written but are complex.

---

### 1.10 Hammerspoon (Advanced Desktop Automation)

**Status:** Installed on this system at `/Applications/Hammerspoon.app`

**What's Possible:**
- Bridge between Lua scripting and ALL macOS system APIs
- Window management (move, resize, tile windows programmatically)
- Keyboard/mouse event capture and simulation
- Application lifecycle management
- WiFi, battery, screen, audio monitoring
- Clipboard management
- URL event handling (custom URL schemes)
- File system watchers
- HTTP server for receiving commands
- Spoons (plugin ecosystem) for pre-built functionality

**Implementation (Controlling Hammerspoon from Python):**
```lua
-- ~/.hammerspoon/init.lua
-- HTTP server for ClaudeDev to send commands
local server = hs.httpserver.new(false, false)
server:setPort(41234)
server:setCallback(function(method, path, headers, body)
    local cmd = hs.json.decode(body)
    if cmd.action == "focus_app" then
        hs.application.launchOrFocus(cmd.app)
        return hs.json.encode({status = "ok"}), 200, {}
    elseif cmd.action == "move_window" then
        local win = hs.window.focusedWindow()
        win:move(hs.geometry.rect(cmd.x, cmd.y, cmd.w, cmd.h))
        return hs.json.encode({status = "ok"}), 200, {}
    elseif cmd.action == "get_windows" then
        local wins = {}
        for _, w in ipairs(hs.window.allWindows()) do
            table.insert(wins, {
                title = w:title(),
                app = w:application():name(),
                frame = w:frame()
            })
        end
        return hs.json.encode(wins), 200, {}
    end
end)
server:start()
```

```python
import requests

def hammerspoon_cmd(action: str, **kwargs) -> dict:
    """Send a command to Hammerspoon's HTTP server."""
    payload = {"action": action, **kwargs}
    resp = requests.post("http://localhost:41234", json=payload)
    return resp.json()

# Focus an application
hammerspoon_cmd("focus_app", app="Xcode")

# Get all windows
windows = hammerspoon_cmd("get_windows")

# Move a window
hammerspoon_cmd("move_window", x=0, y=0, w=1920, h=1080)
```

**Performance:** Hammerspoon runs as a lightweight always-on process. API calls via HTTP take < 5ms.

**Security:** Hammerspoon requires Accessibility permission. The HTTP server should be bound to localhost only.

---

### 1.11 Additional macOS System Capabilities

**Clipboard (pbcopy/pbpaste):**
```python
def get_clipboard() -> str:
    return subprocess.run(["pbpaste"], capture_output=True, text=True).stdout

def set_clipboard(text: str):
    subprocess.run(["pbcopy"], input=text, text=True)
```

**Text-to-Speech (say):**
```python
def speak(text: str, voice: str = "Samantha"):
    subprocess.run(["say", "-v", voice, text])
```

**System Notifications:**
```python
def notify(title: str, message: str, sound: str = "Glass"):
    subprocess.run([
        "osascript", "-e",
        f'display notification "{message}" with title "{title}" sound name "{sound}"'
    ])
```

**Open files/URLs:**
```python
def open_file(path: str):
    subprocess.run(["open", path])

def open_url(url: str):
    subprocess.run(["open", url])

def open_in_app(path: str, app: str):
    subprocess.run(["open", "-a", app, path])
```

---

## 2. macOS Developer Tools Integration

### 2.1 Xcode

**Available:** Yes (`/Applications/Xcode.app/Contents/Developer`)

**What's Possible:**
- Build iOS/macOS/watchOS/tvOS projects from CLI
- Run unit and UI tests
- Code signing and provisioning
- Interface Builder file manipulation
- Simulator management
- Performance profiling with Instruments

**Implementation:**
```bash
# Build a project
xcodebuild -project MyApp.xcodeproj -scheme MyApp -configuration Debug build

# Run tests
xcodebuild test -project MyApp.xcodeproj -scheme MyApp -destination 'platform=iOS Simulator,name=iPhone 16'

# List simulators
xcrun simctl list devices

# Boot simulator
xcrun simctl boot "iPhone 16"

# Install app on simulator
xcrun simctl install booted /path/to/app.app

# Clean build
xcodebuild clean -project MyApp.xcodeproj -scheme MyApp
```

**Python Integration:**
```python
def xcode_build(project: str, scheme: str, config: str = "Debug") -> tuple[bool, str]:
    """Build an Xcode project."""
    result = subprocess.run(
        ["xcodebuild", "-project", project, "-scheme", scheme,
         "-configuration", config, "build"],
        capture_output=True, text=True
    )
    return result.returncode == 0, result.stdout + result.stderr
```

---

### 2.2 Git (Advanced Features)

**Version:** git 2.50.1 (Apple Git-155)

**Advanced Features for AI Agents:**

```bash
# Worktrees -- parallel checkouts of the same repo
git worktree add ../feature-branch feature-branch
git worktree list
git worktree remove ../feature-branch

# Sparse checkout -- only check out needed files (for monorepos)
git sparse-checkout init --cone
git sparse-checkout set src/core src/api
git sparse-checkout disable

# Diff stat for quick change summary
git diff --stat HEAD~5..HEAD

# Log with file changes
git log --oneline --name-status -10

# Blame with line range
git blame -L 10,20 src/main.py

# Search commit messages
git log --grep="fix" --oneline

# Search code across history
git log -S "function_name" --oneline

# Stash with message
git stash push -m "WIP: feature X"

# Interactive rebase (for agent: use --exec for automated operations)
git rebase HEAD~3 --exec "python -m pytest"
```

**Python Libraries:**
- `gitpython` -- full Git wrapper
- `pygit2` -- libgit2 bindings (faster, lower-level)
- subprocess calls to `git` (simplest, most reliable)

---

### 2.3 Homebrew

**Version:** Homebrew 5.0.16

**What's Possible:**
- Install/upgrade/remove any of 10,000+ packages
- Manage GUI applications via casks
- Tap third-party repositories
- Create custom formulae for ClaudeDev distribution

**Key Commands for AI Agents:**
```bash
# Search for a package
brew search tree-sitter

# Install a package
brew install tree-sitter

# Install a GUI app
brew install --cask visual-studio-code

# List installed packages
brew list

# Check outdated packages
brew outdated

# Get package info
brew info mlx
```

**Available ML/AI Packages:**
- `mlx`, `mlx-c`, `mlx-lm` -- Apple ML framework
- `llama.cpp` -- Local LLM inference
- `ollama` -- LLM runner with API server

---

### 2.4 Docker Desktop for Mac

**Version:** Docker 29.1.2

**What's Possible:**
- Run containerized development environments
- Build and test in isolated environments
- Multi-architecture builds (ARM64 + x86_64)
- Docker Compose for multi-service stacks
- Volume mounts for live code editing

**Performance Note:** Docker on Apple Silicon runs Linux ARM64 containers natively. x86_64 containers use Rosetta 2 emulation (slower but functional).

```python
def docker_run(image: str, cmd: str, volumes: dict = None) -> str:
    """Run a Docker container."""
    args = ["docker", "run", "--rm"]
    if volumes:
        for host, container in volumes.items():
            args.extend(["-v", f"{host}:{container}"])
    args.extend([image, "sh", "-c", cmd])
    result = subprocess.run(args, capture_output=True, text=True)
    return result.stdout
```

---

### 2.5 Terminal Emulators

**iTerm2:** Installed. Supports tmux integration, split panes, scripting API, Python runtime.

**tmux:** Version 3.6a installed. Essential for:
- Session persistence (survives terminal close)
- Multiple panes for parallel operations
- Scriptable window management
- Remote session management

```python
def tmux_create_session(name: str, cmd: str = None):
    """Create a new tmux session."""
    args = ["tmux", "new-session", "-d", "-s", name]
    if cmd:
        args.append(cmd)
    subprocess.run(args)

def tmux_send_keys(session: str, keys: str):
    """Send keys to a tmux session."""
    subprocess.run(["tmux", "send-keys", "-t", session, keys, "Enter"])

def tmux_capture_pane(session: str) -> str:
    """Capture the current output of a tmux pane."""
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", session, "-p"],
        capture_output=True, text=True
    )
    return result.stdout
```

---

### 2.6 IDE Integration

**Cursor:** Installed at `/Applications/Cursor.app`

**VS Code CLI:** Not installed (can be added via `code` command)

```bash
# Open file in Cursor
open -a Cursor /path/to/file.py

# Cursor CLI (if available)
cursor /path/to/project
```

---

## 3. File System and Project Understanding

### 3.1 Fast Codebase Indexing

**Strategy: Hybrid Approach**

1. **Spotlight (mdfind)** for initial file discovery -- instant, system-maintained index
2. **Tree-sitter** for structural code understanding -- AST-level analysis
3. **FSEvents (watchfiles)** for real-time index updates -- kernel-efficient
4. **Vector embeddings** for semantic search -- requires local ML inference

**Spotlight for Initial Scan:**
```python
def discover_project_files(project_root: str) -> dict[str, list[str]]:
    """Use Spotlight to rapidly discover project files by type."""
    type_map = {
        "python": 'kMDItemContentType == "public.python-script"',
        "javascript": 'kMDItemContentType == "com.netscape.javascript-source"',
        "typescript": 'kMDItemFSName == "*.ts" || kMDItemFSName == "*.tsx"',
        "json": 'kMDItemContentType == "public.json"',
        "yaml": 'kMDItemFSName == "*.yml" || kMDItemFSName == "*.yaml"',
    }
    files = {}
    for lang, query in type_map.items():
        result = subprocess.run(
            ["mdfind", "-onlyin", project_root, query],
            capture_output=True, text=True
        )
        files[lang] = [f for f in result.stdout.strip().split("\n") if f]
    return files
```

---

### 3.2 Tree-sitter for Code Understanding

**What's Possible:**
- Parse source code into concrete syntax trees (CSTs)
- Extract functions, classes, methods, imports, variables
- Navigate code structurally (parent, children, siblings)
- Incremental parsing (only re-parse changed regions)
- Support for 160+ programming languages
- Language-agnostic queries via S-expression patterns

**Installation:**
```bash
pip install tree-sitter tree-sitter-language-pack
```

**Implementation:**
```python
import tree_sitter_language_pack as tslp

def parse_python_file(filepath: str) -> dict:
    """Parse a Python file and extract structural elements."""
    parser = tslp.get_parser("python")

    with open(filepath, "rb") as f:
        source = f.read()

    tree = parser.parse(source)
    root = tree.root_node

    symbols = {
        "functions": [],
        "classes": [],
        "imports": [],
    }

    def visit(node):
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            symbols["functions"].append({
                "name": name_node.text.decode() if name_node else "unknown",
                "start_line": node.start_point[0],
                "end_line": node.end_point[0],
                "params": _extract_params(node),
            })
        elif node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            symbols["classes"].append({
                "name": name_node.text.decode() if name_node else "unknown",
                "start_line": node.start_point[0],
                "end_line": node.end_point[0],
            })
        elif node.type in ("import_statement", "import_from_statement"):
            symbols["imports"].append(node.text.decode())

        for child in node.children:
            visit(child)

    visit(root)
    return symbols

def incremental_reparse(parser, old_tree, source: bytes, edit) -> object:
    """Incrementally re-parse after an edit (extremely fast)."""
    old_tree.edit(
        start_byte=edit["start_byte"],
        old_end_byte=edit["old_end_byte"],
        new_end_byte=edit["new_end_byte"],
        start_point=edit["start_point"],
        old_end_point=edit["old_end_point"],
        new_end_point=edit["new_end_point"],
    )
    return parser.parse(source, old_tree)
```

**Tree-sitter Query Language:**
```python
# Find all function definitions with decorators
QUERY = """
(decorated_definition
  (decorator) @decorator
  (function_definition
    name: (identifier) @func_name
    parameters: (parameters) @params
  )
) @definition
"""

def query_code(filepath: str, query_str: str):
    """Run a tree-sitter query against source code."""
    language = tslp.get_language("python")
    query = language.query(query_str)
    parser = tslp.get_parser("python")

    with open(filepath, "rb") as f:
        tree = parser.parse(f.read())

    return query.captures(tree.root_node)
```

**Performance on Apple Silicon:** Tree-sitter parsing is extremely fast -- typically < 1ms per file for Python, < 5ms for large files. Incremental re-parsing after edits is sub-millisecond. The Rust-based `tree-sitter-language-pack` is compiled natively for ARM64.

---

### 3.3 Real-Time File Watching with FSEvents

```python
import asyncio
from watchfiles import awatch, Change
from pathlib import Path

class ProjectWatcher:
    """Watch a project directory and maintain a live index."""

    def __init__(self, project_root: str):
        self.root = project_root
        self.index = {}  # filepath -> parsed symbols
        self._ignore_patterns = {".git", "node_modules", "__pycache__", ".venv", "dist"}

    async def start(self):
        """Start watching the project directory."""
        # Initial scan
        await self._full_scan()

        # Watch for changes
        async for changes in awatch(self.root):
            for change_type, filepath in changes:
                if self._should_ignore(filepath):
                    continue
                if change_type in (Change.added, Change.modified):
                    await self._index_file(filepath)
                elif change_type == Change.deleted:
                    self.index.pop(filepath, None)

    def _should_ignore(self, filepath: str) -> bool:
        parts = Path(filepath).parts
        return any(p in self._ignore_patterns for p in parts)

    async def _full_scan(self):
        """Scan all files in the project."""
        for path in Path(self.root).rglob("*.py"):
            if not self._should_ignore(str(path)):
                await self._index_file(str(path))

    async def _index_file(self, filepath: str):
        """Parse and index a single file."""
        try:
            symbols = parse_python_file(filepath)
            self.index[filepath] = symbols
        except Exception:
            pass  # Skip unparseable files
```

---

### 3.4 Smart File Caching

**Strategy:** Use memory-mapped files for large indexes to avoid loading everything into RAM.

```python
import mmap
import json
from pathlib import Path

class MmapCache:
    """Memory-mapped file cache for project indexes."""

    CACHE_DIR = Path.home() / ".claudedev" / "cache"

    def __init__(self, project_id: str):
        self.cache_file = self.CACHE_DIR / f"{project_id}.cache"
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def write_index(self, index: dict):
        """Write index to disk as memory-mappable file."""
        data = json.dumps(index).encode()
        with open(self.cache_file, "wb") as f:
            f.write(data)

    def read_index(self) -> dict:
        """Memory-map the index file for fast access."""
        if not self.cache_file.exists():
            return {}
        with open(self.cache_file, "rb") as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            data = mm.read()
            mm.close()
        return json.loads(data)
```

---

### 3.5 Dealing with Large Monorepos

**Strategies:**
1. **Git Sparse Checkout:** Only check out directories the agent needs
2. **Spotlight Queries:** Use `mdfind -onlyin` to search within subdirectories
3. **Incremental Indexing:** Only re-index changed files via FSEvents
4. **Tiered Caching:**
   - L1: In-memory LRU cache for recently accessed files
   - L2: Memory-mapped disk cache for the full project index
   - L3: Spotlight/mdfind for system-wide searches

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_file_symbols(filepath: str, mtime: float) -> dict:
    """Cache parsed symbols, invalidated by modification time."""
    return parse_python_file(filepath)

def get_symbols_cached(filepath: str) -> dict:
    """Get symbols with automatic cache invalidation."""
    mtime = os.path.getmtime(filepath)
    return get_file_symbols(filepath, mtime)
```

---

## 4. Local AI Inference on macOS

### 4.1 Apple Silicon GPU Capabilities

**This System:** Apple M5, Metal 4 GPU, 10 cores (4P + 6E), 16 GB unified memory

**Key Specifications:**
- **Memory Bandwidth:** ~153 GB/s (M5), significantly higher than M4's 120 GB/s
- **Unified Memory:** GPU and CPU share the same 16 GB -- no data copying overhead
- **Neural Engine:** Dedicated ML accelerator (16-core on M5)
- **Metal 4:** Latest GPU compute API with enhanced ML capabilities
- **MLX Advantage:** M5 GPU neural accelerators yield up to 4x speedup vs M4 for time-to-first-token

**What This Means for ClaudeDev:**
- Embedding models run natively on GPU with zero-copy from CPU memory
- Small classification models (< 2B params) fit entirely in memory
- Embedding generation is fast enough for real-time use during code editing

---

### 4.2 MLX Framework (Apple's ML Framework)

**Status:** Available via Homebrew (`brew install mlx mlx-lm`)

**What's Possible:**
- Run transformer models natively on Apple Silicon
- Lazy evaluation for memory efficiency
- Automatic Metal GPU acceleration
- NumPy-compatible API
- Training and inference

**Installation:**
```bash
# Install MLX
pip install mlx mlx-lm

# Or via Homebrew
brew install mlx mlx-lm
```

**Implementation for Embeddings:**
```python
import mlx.core as mx
import mlx.nn as nn

# Load a pre-trained embedding model
from mlx_lm import load, generate

# For embeddings specifically:
# Use sentence-transformers models converted to MLX format
def generate_embedding_mlx(text: str, model, tokenizer) -> list[float]:
    """Generate text embeddings using MLX."""
    tokens = tokenizer.encode(text, return_tensors="mlx")
    with mx.no_grad():
        output = model(tokens)
    # Mean pooling over token embeddings
    embedding = mx.mean(output.last_hidden_state, axis=1)
    return embedding.tolist()[0]
```

**Performance Benchmarks (M5):**
- FLUX-dev-4bit (12B params) image generation: 3.8x faster than M4
- General LLM inference: 19-27% faster than M4
- Embedding generation (nomic-embed-text): ~50-100 embeddings/sec for short texts

---

### 4.3 Ollama for Local LLM Inference

**Available via:** `brew install ollama`

**What's Possible:**
- Run embedding models locally with a REST API
- Run small classification/extraction models
- Compatible with OpenAI API format
- Manages model downloads and caching

**Implementation:**
```python
import httpx

OLLAMA_BASE = "http://localhost:11434"

async def ollama_embed(text: str, model: str = "nomic-embed-text") -> list[float]:
    """Generate embeddings via Ollama."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{OLLAMA_BASE}/api/embeddings", json={
            "model": model,
            "prompt": text
        })
        return resp.json()["embedding"]

async def ollama_generate(prompt: str, model: str = "qwen2.5:3b") -> str:
    """Generate text via Ollama for local classification tasks."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{OLLAMA_BASE}/api/generate", json={
            "model": model,
            "prompt": prompt,
            "stream": False
        })
        return resp.json()["response"]
```

**Recommended Models for ClaudeDev:**
| Model | Size | Purpose | Speed (M5) |
|-------|------|---------|------------|
| `nomic-embed-text` | 274MB | Code/text embeddings | ~100 embed/sec |
| `all-minilm` | 46MB | Fast sentence embeddings | ~500 embed/sec |
| `qwen2.5:3b` | 2GB | Code understanding/classification | ~30 tok/sec |
| `codellama:7b` | 4GB | Code-specific tasks | ~15 tok/sec |

---

### 4.4 llama.cpp for GGUF Models

**Available via:** `brew install llama.cpp`

**What's Possible:**
- Run GGUF-quantized models directly on Apple Silicon
- Metal GPU acceleration out of the box
- Extremely memory efficient (4-bit quantization)
- C/C++ performance with Python bindings

**Implementation:**
```bash
# Install
brew install llama.cpp

# Run a model
llama-cli -m /path/to/model.gguf -p "Classify this code change:" --n-gpu-layers 99
```

```python
# Python bindings
# pip install llama-cpp-python
from llama_cpp import Llama

llm = Llama(
    model_path="/path/to/model.gguf",
    n_gpu_layers=-1,  # Use all GPU layers
    n_ctx=4096,
    embedding=True,  # Enable embedding mode
)

# Generate embeddings
embedding = llm.create_embedding("def hello_world():\n    print('hello')")

# Text generation
output = llm("Summarize this code change:", max_tokens=256)
```

---

### 4.5 Vector Databases for macOS

**Recommended: LanceDB (Embedded, Rust-based)**

```python
# pip install lancedb
import lancedb

db = lancedb.connect("/Users/iworldafric/.claudedev/vectordb")

# Create a table for code embeddings
table = db.create_table("code_chunks", data=[
    {"filepath": "src/main.py", "chunk": "def main():", "vector": [0.1] * 384},
])

# Search
results = table.search([0.1] * 384).limit(10).to_list()
```

**Comparison for macOS:**
| Database | Storage | Speed | Memory | Install |
|----------|---------|-------|--------|---------|
| LanceDB | ~0.5MB/1k docs | 100x faster than Parquet | Minimal (embedded) | `pip install lancedb` |
| ChromaDB | ~1MB/1k docs | Fast (SQLite-backed) | Moderate | `pip install chromadb` |
| Qdrant | ~0.8MB/1k docs | Fast (Rust server) | Higher (server mode) | `brew install qdrant` |
| FAISS | Custom | Fastest search | RAM-intensive | `pip install faiss-cpu` |

**Recommendation:** LanceDB for ClaudeDev because:
- Embedded (no server process needed)
- Rust-based (native ARM64 performance)
- Smallest storage footprint
- Columnar format enables efficient queries
- Supports on-disk storage (important for large codebases)

---

### 4.6 Optimal Embedding Pipeline for ClaudeDev

```python
"""
Recommended: Ollama + nomic-embed-text + LanceDB
This provides the best balance of quality, speed, and simplicity.
"""

import asyncio
import hashlib
import lancedb
import httpx

class CodeEmbeddingPipeline:
    """Generate and store code embeddings locally on macOS."""

    def __init__(self, db_path: str = "~/.claudedev/vectordb"):
        self.db = lancedb.connect(db_path)
        self.model = "nomic-embed-text"
        self._client = httpx.AsyncClient(base_url="http://localhost:11434")

    async def embed_text(self, text: str) -> list[float]:
        """Generate embedding via Ollama."""
        resp = await self._client.post("/api/embeddings", json={
            "model": self.model,
            "prompt": f"search_document: {text}"
        })
        return resp.json()["embedding"]

    async def index_file(self, filepath: str, chunks: list[str]):
        """Index code chunks from a file."""
        embeddings = await asyncio.gather(
            *[self.embed_text(chunk) for chunk in chunks]
        )
        data = [{
            "filepath": filepath,
            "chunk": chunk,
            "chunk_hash": hashlib.md5(chunk.encode()).hexdigest(),
            "vector": emb
        } for chunk, emb in zip(chunks, embeddings)]

        table_name = "code_embeddings"
        if table_name in self.db.table_names():
            table = self.db.open_table(table_name)
            table.add(data)
        else:
            self.db.create_table(table_name, data)

    async def search(self, query: str, limit: int = 10) -> list[dict]:
        """Semantic search across indexed code."""
        query_emb = await self.embed_text(f"search_query: {query}")
        table = self.db.open_table("code_embeddings")
        results = table.search(query_emb).limit(limit).to_list()
        return results
```

---

## 5. Secure and Private Operations

### 5.1 Keychain API

**Available Keychains:**
- `/Users/iworldafric/Library/Keychains/login.keychain-db` (user)
- `/Library/Keychains/System.keychain` (system)

**What's Possible:**
- Store API keys, tokens, and credentials securely
- Hardware-encrypted storage on Apple Silicon (Secure Enclave)
- Access control per-application
- Password generation

**Implementation:**
```python
import subprocess
import json

class KeychainManager:
    """Manage secrets in macOS Keychain."""

    SERVICE = "com.claudedev"

    def store_secret(self, key: str, value: str):
        """Store a secret in the Keychain."""
        subprocess.run([
            "security", "add-generic-password",
            "-s", self.SERVICE,
            "-a", key,
            "-w", value,
            "-U",  # Update if exists
        ], check=True)

    def get_secret(self, key: str) -> str:
        """Retrieve a secret from the Keychain."""
        result = subprocess.run([
            "security", "find-generic-password",
            "-s", self.SERVICE,
            "-a", key,
            "-w",  # Output password only
        ], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
        raise KeyError(f"Secret '{key}' not found in Keychain")

    def delete_secret(self, key: str):
        """Delete a secret from the Keychain."""
        subprocess.run([
            "security", "delete-generic-password",
            "-s", self.SERVICE,
            "-a", key,
        ])

    def list_secrets(self) -> list[str]:
        """List all ClaudeDev secrets."""
        result = subprocess.run([
            "security", "dump-keychain", "-d",
        ], capture_output=True, text=True)
        # Parse output for our service entries
        # (simplified -- real implementation would parse the plist output)
        return [line for line in result.stdout.split("\n")
                if self.SERVICE in line]
```

**Python Libraries:**
- `subprocess` + `security` CLI (simplest)
- `keyring` -- cross-platform Python keyring access (uses macOS Keychain on macOS)
- `pyobjc-framework-Security` -- direct Keychain API bindings

---

### 5.2 macOS Privacy Permissions (TCC)

**Permissions ClaudeDev May Need:**

| Permission | Purpose | How to Request |
|------------|---------|----------------|
| Accessibility | Control other apps, read UI elements | System Settings > Privacy > Accessibility |
| Full Disk Access | Read files in protected locations | System Settings > Privacy > Full Disk Access |
| Automation | Control apps via AppleScript | Prompted on first use |
| Developer Tools | Attach debugger to processes | System Settings > Privacy > Developer Tools |
| Input Monitoring | Capture keyboard events | System Settings > Privacy > Input Monitoring |
| Screen Recording | Capture screen content | System Settings > Privacy > Screen Recording |

**Implementation (Permission Check):**
```python
def check_accessibility_permission() -> bool:
    """Check if the application has Accessibility permission."""
    try:
        import ApplicationServices
        return ApplicationServices.AXIsProcessTrusted()
    except ImportError:
        # Fallback: try to use System Events
        result = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get name of first process'],
            capture_output=True, text=True
        )
        return result.returncode == 0

def request_accessibility_permission():
    """Prompt the user to grant Accessibility permission."""
    subprocess.run([
        "osascript", "-e",
        '''tell application "System Settings"
            activate
            reveal anchor "Privacy_Accessibility" of pane id "com.apple.preference.security"
        end tell'''
    ])
```

---

### 5.3 Code Signing and Notarization

**Tools Available:**
- `codesign` -- sign code and applications
- `xcrun notarytool` -- submit for Apple notarization
- `pkgbuild` / `productbuild` -- create installer packages

**Implementation:**
```bash
# Sign a binary
codesign --sign "Developer ID Application: Your Name" --options runtime /path/to/binary

# Create a DMG
hdiutil create -volname "ClaudeDev" -srcfolder /path/to/app -ov ClaudeDev.dmg

# Notarize
xcrun notarytool submit ClaudeDev.dmg --apple-id "dev@example.com" --team-id "TEAMID" --password "@keychain:AC_PASSWORD"

# Staple the ticket
xcrun stapler staple ClaudeDev.dmg
```

---

### 5.4 Secure Enclave

**What's Possible on Apple Silicon:**
- Generate and store cryptographic keys in hardware
- Keys never leave the Secure Enclave
- Biometric authentication (Touch ID) for key access
- Available via CryptoKit framework

**Implementation (via PyObjC / Swift bridge):**
```python
# Secure Enclave operations are best done via a small Swift helper
# that ClaudeDev calls as a subprocess

# swift_helper.swift:
# import CryptoKit
# let privateKey = try SecureEnclave.P256.Signing.PrivateKey()
# let publicKey = privateKey.publicKey
```

**Recommendation:** Use Keychain for most secrets. Reserve Secure Enclave for the highest-sensitivity operations (e.g., signing agent-to-agent messages).

---

## 6. Process and Resource Management

### 6.1 CPU/Memory Management

**Tools:**
- `top` -- real-time process monitoring
- `vm_stat` -- virtual memory statistics
- `iostat` -- I/O statistics
- `sysctl` -- system information and tuning

**Implementation:**
```python
import os
import resource
import psutil  # pip install psutil

class ResourceManager:
    """Manage system resources for background AI operations."""

    @staticmethod
    def get_system_stats() -> dict:
        """Get current system resource usage."""
        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=1, percpu=True)
        return {
            "memory_total_gb": mem.total / (1024**3),
            "memory_available_gb": mem.available / (1024**3),
            "memory_percent": mem.percent,
            "cpu_percent_per_core": cpu,
            "cpu_percent_avg": sum(cpu) / len(cpu),
        }

    @staticmethod
    def set_process_priority(nice_value: int = 10):
        """Lower process priority to be a good citizen."""
        os.nice(nice_value)

    @staticmethod
    def set_memory_limit(max_gb: float):
        """Set memory limit for the current process."""
        max_bytes = int(max_gb * 1024**3)
        resource.setrlimit(resource.RLIMIT_RSS, (max_bytes, max_bytes))

    @staticmethod
    def should_throttle() -> bool:
        """Check if we should reduce resource usage."""
        mem = psutil.virtual_memory()
        # Throttle if memory usage > 80% or on battery
        battery = psutil.sensors_battery()
        on_battery = battery and not battery.power_plugged if battery else False
        return mem.percent > 80 or on_battery
```

---

### 6.2 Energy Efficiency

**Critical for Laptops:**

```python
def get_power_state() -> dict:
    """Get current power state."""
    result = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True)
    on_battery = "Battery Power" in result.stdout
    # Parse battery percentage
    import re
    match = re.search(r"(\d+)%", result.stdout)
    percent = int(match.group(1)) if match else 100
    return {"on_battery": on_battery, "battery_percent": percent}

def prevent_sleep_during_task():
    """Prevent system sleep while a task is running."""
    # caffeinate prevents sleep; -i prevents idle sleep
    return subprocess.Popen(["caffeinate", "-i"])

class EnergyAwareAgent:
    """Adjust agent behavior based on power state."""

    def get_operation_mode(self) -> str:
        power = get_power_state()
        if not power["on_battery"]:
            return "full"  # Full performance
        elif power["battery_percent"] > 50:
            return "balanced"  # Reduce background tasks
        elif power["battery_percent"] > 20:
            return "efficient"  # Minimal background operations
        else:
            return "minimal"  # Critical operations only

    def adjust_concurrency(self) -> int:
        mode = self.get_operation_mode()
        return {"full": 8, "balanced": 4, "efficient": 2, "minimal": 1}[mode]
```

---

### 6.3 Sleep/Wake Handling

```python
import signal

class SleepWakeHandler:
    """Handle macOS sleep/wake events gracefully."""

    def __init__(self):
        # Register for power notifications via IOKit
        # Simplified: use a launchd WatchPath on power assertion file
        self._paused_tasks = []

    def on_sleep(self):
        """Called before system sleeps."""
        # Pause all background operations
        # Save state to disk
        # Close network connections
        pass

    def on_wake(self):
        """Called after system wakes."""
        # Reconnect network
        # Resume background operations
        # Check for file system changes that occurred during sleep
        pass
```

---

### 6.4 launchd Process Types

Use the `ProcessType` key in launchd plists to inform the system about the nature of each process:

| ProcessType | CPU Priority | I/O Priority | Use Case |
|-------------|-------------|-------------|----------|
| `Interactive` | High | High | User-facing UI operations |
| `Standard` | Normal | Normal | Default for most operations |
| `Background` | Low | Low | Indexing, embedding generation |
| `Adaptive` | Dynamic | Dynamic | Adjusts based on system load |

**Recommendation for ClaudeDev:**
- Main agent process: `Standard`
- File watcher / indexer: `Background`
- Embedding generator: `Background`
- Active task execution: `Adaptive`

---

## 7. Distribution on macOS

### 7.1 Homebrew Formula

**Recommended Primary Distribution:**
```ruby
# Formula/claudedev.rb
class Claudedev < Formula
  include Language::Python::Virtualenv

  desc "Autonomous AI coding platform powered by Claude"
  homepage "https://github.com/yourorg/claudedev"
  url "https://github.com/yourorg/claudedev/archive/refs/tags/v1.0.0.tar.gz"
  sha256 "abc123..."
  license "MIT"

  depends_on "python@3.13"
  depends_on "ollama" => :recommended  # For local embeddings

  def install
    virtualenv_install_with_resources
  end

  service do
    run [opt_bin/"claudedev", "daemon"]
    keep_alive true
    working_dir var/"claudedev"
    log_path var/"log/claudedev.log"
    error_log_path var/"log/claudedev.error.log"
  end

  test do
    system "#{bin}/claudedev", "--version"
  end
end
```

**Distribution via Custom Tap:**
```bash
# Create tap
brew tap yourorg/tools
brew install yourorg/tools/claudedev

# Or with cask for GUI version
brew install --cask claudedev
```

---

### 7.2 pip / pipx Installation

```bash
# Standard pip install
pip install claudedev

# Recommended: pipx for isolated install
pipx install claudedev

# With optional dependencies
pipx install "claudedev[ml,embedding]"
```

**pyproject.toml extras:**
```toml
[project.optional-dependencies]
ml = ["mlx", "mlx-lm"]
embedding = ["lancedb", "nomic"]
full = ["mlx", "mlx-lm", "lancedb", "nomic", "tree-sitter-language-pack"]
```

---

### 7.3 DMG / PKG Installer

For a GUI or all-in-one distribution:

```bash
# Create signed DMG
#!/bin/bash
APP_NAME="ClaudeDev"
VERSION="1.0.0"

# Build the app
python setup.py py2app

# Create DMG
hdiutil create -volname "$APP_NAME $VERSION" \
    -srcfolder "dist/$APP_NAME.app" \
    -ov "$APP_NAME-$VERSION.dmg"

# Sign
codesign --deep --force --sign "Developer ID Application: Your Name" \
    "$APP_NAME-$VERSION.dmg"

# Notarize
xcrun notarytool submit "$APP_NAME-$VERSION.dmg" \
    --keychain-profile "notarize"
xcrun stapler staple "$APP_NAME-$VERSION.dmg"
```

---

### 7.4 Auto-Update Mechanism

```python
import httpx
from packaging import version

class AutoUpdater:
    """Check for and install updates."""

    RELEASES_URL = "https://api.github.com/repos/yourorg/claudedev/releases/latest"

    async def check_for_updates(self) -> dict | None:
        """Check if a newer version is available."""
        current = self._get_current_version()
        async with httpx.AsyncClient() as client:
            resp = await client.get(self.RELEASES_URL)
            latest = resp.json()

        if version.parse(latest["tag_name"].lstrip("v")) > version.parse(current):
            return {
                "current": current,
                "latest": latest["tag_name"],
                "url": latest["html_url"],
                "notes": latest["body"],
            }
        return None

    def _get_current_version(self) -> str:
        result = subprocess.run(
            ["claudedev", "--version"],
            capture_output=True, text=True
        )
        return result.stdout.strip()
```

---

## 8. Claude Code CLI Integration on macOS

### 8.1 Claude Code Installation and Data

**Binary Location:** `/Users/iworldafric/.local/bin/claude`
**Version:** 2.1.71 (Claude Code)
**Data Directory:** `~/.claude/`

**Data Directory Structure:**
```
~/.claude/
  CLAUDE.md              # Global instructions
  settings.json          # Global settings
  settings.local.json    # Local settings override
  .credentials.json      # API credentials
  history.jsonl          # Conversation history
  agents/                # Agent configurations
  cache/                 # Temporary cache
  debug/                 # Debug logs
  hooks/                 # Hook scripts
  ide/                   # IDE integration
  logs/                  # Application logs
  plans/                 # Planning documents
  plugins/               # Plugin configurations (Serena, etc.)
  projects/              # Per-project settings
  session-env/           # Session environment snapshots
  skills/                # Skill definitions
  tasks/                 # Task tracking
  teams/                 # Team management
  todos/                 # Todo lists
```

---

### 8.2 Programmatic Invocation

**Method 1: Claude Agent SDK (Python) -- Recommended**

```python
# pip install claude-agent-sdk
from claude_agent_sdk import AgentSession, PermissionMode

async def run_claude_task(prompt: str, project_dir: str) -> str:
    """Run a Claude Code task programmatically."""
    session = AgentSession(
        model="claude-opus-4-6",
        permission_mode=PermissionMode.ACCEPT_EDITS,
        allowed_tools=["Bash(git:*)", "Edit", "Read", "Glob", "Grep"],
        cwd=project_dir,
    )

    result = await session.query(prompt)
    return result.text

# With custom tools
from claude_agent_sdk import AgentDefinition, Tool

agent = AgentDefinition(
    name="code-reviewer",
    description="Reviews code for quality issues",
    tools=[
        Tool(name="read_file", function=read_file_fn),
        Tool(name="search_code", function=search_code_fn),
    ],
    model="claude-sonnet-4-6",
)
```

**Method 2: Direct CLI Subprocess**

```python
import subprocess
import json

def claude_print(prompt: str, cwd: str = None, model: str = None) -> str:
    """Run Claude Code in non-interactive print mode."""
    cmd = [
        "claude",
        "--print",
        "--output-format", "json",
    ]
    if model:
        cmd.extend(["--model", model])
    cmd.append(prompt)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=300,  # 5 minute timeout
    )

    if result.returncode == 0:
        return json.loads(result.stdout)
    raise RuntimeError(f"Claude Code failed: {result.stderr}")

def claude_stream(prompt: str, cwd: str = None):
    """Run Claude Code with streaming JSON output."""
    cmd = [
        "claude",
        "--print",
        "--output-format", "stream-json",
        prompt
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
    )

    for line in proc.stdout:
        if line.strip():
            yield json.loads(line)

    proc.wait()
```

**Method 3: Session Management**

```python
def claude_continue(session_id: str = None) -> str:
    """Continue the most recent or specified conversation."""
    cmd = ["claude", "--continue", "--print", "--output-format", "json"]
    if session_id:
        cmd = ["claude", "--resume", session_id, "--print", "--output-format", "json"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def claude_resume(session_id: str, prompt: str) -> str:
    """Resume a specific session with a new prompt."""
    cmd = [
        "claude",
        "--resume", session_id,
        "--print",
        "--output-format", "json",
        prompt
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout
```

---

### 8.3 Key CLI Flags for Automation

| Flag | Purpose | Example |
|------|---------|---------|
| `-p, --print` | Non-interactive mode, print and exit | `claude -p "explain this code"` |
| `--output-format json` | Structured JSON output | `claude -p --output-format json "..."` |
| `--output-format stream-json` | Real-time streaming JSON | `claude -p --output-format stream-json "..."` |
| `--model <model>` | Select model | `claude --model claude-sonnet-4-6 -p "..."` |
| `--allowedTools` | Pre-approve tools | `claude --allowedTools "Bash(git:*) Edit Read"` |
| `--dangerously-skip-permissions` | Skip all permission prompts | For sandboxed environments only |
| `--permission-mode` | Set permission mode | `bypassPermissions`, `acceptEdits`, `plan` |
| `-c, --continue` | Continue last conversation | `claude --continue -p "now fix the tests"` |
| `-r, --resume <id>` | Resume specific session | `claude --resume abc123 -p "..."` |
| `--system-prompt` | Override system prompt | `claude --system-prompt "You are a reviewer"` |
| `--append-system-prompt` | Add to system prompt | `claude --append-system-prompt "Focus on security"` |
| `--max-budget-usd` | Limit API spend | `claude --max-budget-usd 5.00 -p "..."` |
| `--add-dir` | Allow access to additional directories | `claude --add-dir /other/project -p "..."` |
| `--agents` | Define custom agents as JSON | `claude --agents '{"reviewer": {...}}'` |
| `--mcp-config` | Load MCP server configs | `claude --mcp-config servers.json` |
| `-w, --worktree` | Create git worktree for isolation | `claude --worktree feature-x` |
| `--tmux` | Create tmux session for worktree | `claude --worktree --tmux` |
| `--effort` | Set effort level | `claude --effort high -p "..."` |
| `--fallback-model` | Fallback if primary overloaded | `claude --fallback-model claude-sonnet-4-6 -p "..."` |
| `--json-schema` | Enforce structured output schema | `claude --json-schema '{"type":"object",...}'` |
| `--tools` | Limit available built-in tools | `claude --tools "Bash,Edit,Read"` |
| `--no-session-persistence` | Don't save session to disk | For ephemeral tasks |
| `--fork-session` | Fork when resuming (don't modify original) | `claude --resume id --fork-session` |

---

### 8.4 Environment Variables

```bash
# Authentication
ANTHROPIC_API_KEY=sk-ant-...       # API key for direct API access

# Experimental features
CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1  # Enable agent teams (set on this system)

# Model configuration
CLAUDE_MODEL=claude-opus-4-6       # Default model

# Output control
CLAUDE_CODE_MAX_OUTPUT_TOKENS=16384  # Max output tokens
```

---

### 8.5 Hooks System

Claude Code supports hooks that execute at various lifecycle points:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/hook-script.sh"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/after-tool.sh"
          }
        ]
      }
    ]
  }
}
```

**Hook Points:**
- `UserPromptSubmit` -- Before processing user input
- `PostToolUse` -- After a tool is executed
- (Additional hooks may exist in newer versions)

---

### 8.6 MCP Server Integration

Claude Code supports Model Context Protocol (MCP) servers for extending capabilities:

```json
{
  "mcpServers": {
    "serena": {
      "command": "python",
      "args": ["-m", "serena.mcp_server"],
      "env": {}
    },
    "playwright": {
      "command": "npx",
      "args": ["@anthropic/mcp-server-playwright"]
    }
  }
}
```

**Available MCP Servers on This System:**
- Serena (code intelligence)
- Playwright (browser automation)
- Claude in Chrome (browser control)
- Claude Preview (dev server preview)
- Scheduled Tasks
- MCP Registry (connector discovery)

---

## 9. RECOMMENDED macOS TOOL USE ARCHITECTURE

### 9.1 Architecture Overview

```
+------------------------------------------------------------------+
|                        ClaudeDev Core                              |
|                  (Python 3.13, async-first)                       |
+------------------------------------------------------------------+
|                                                                    |
|  +------------------+  +------------------+  +------------------+ |
|  | Claude Agent SDK |  | Tool Registry    |  | Task Scheduler   | |
|  | (Primary Brain)  |  | (macOS Tools)    |  | (launchd-based)  | |
|  +------------------+  +------------------+  +------------------+ |
|                                                                    |
|  +------------------+  +------------------+  +------------------+ |
|  | Code Intelligence|  | System Control   |  | Security Layer   | |
|  | (tree-sitter +   |  | (AppleScript +   |  | (Keychain +      | |
|  |  Serena + LSP)   |  |  Accessibility)  |  |  TCC + Sandbox)  | |
|  +------------------+  +------------------+  +------------------+ |
|                                                                    |
|  +------------------+  +------------------+  +------------------+ |
|  | Local AI Engine  |  | File Watcher     |  | IPC Bus          | |
|  | (MLX + Ollama +  |  | (FSEvents via    |  | (Unix Sockets)   | |
|  |  LanceDB)        |  |  watchfiles)     |  |                  | |
|  +------------------+  +------------------+  +------------------+ |
|                                                                    |
+------------------------------------------------------------------+
|                     macOS System Layer                             |
|  [Metal 4 GPU] [Keychain] [launchd] [FSEvents] [Spotlight]       |
|  [Accessibility API] [AppleScript/JXA] [XPC] [Notifications]     |
+------------------------------------------------------------------+
```

---

### 9.2 Component Design

#### A. Primary Brain (Claude Agent SDK)

The core decision-making engine uses Claude Code programmatically:

```python
class ClaudeDevBrain:
    """Primary AI brain using Claude Agent SDK."""

    def __init__(self):
        self.session = AgentSession(
            model="claude-opus-4-6",
            permission_mode=PermissionMode.ACCEPT_EDITS,
            allowed_tools=self._get_allowed_tools(),
        )
        self.fallback_session = AgentSession(
            model="claude-sonnet-4-6",  # Faster, cheaper fallback
        )

    async def execute_task(self, task: str, context: dict) -> str:
        """Execute a coding task with full context."""
        prompt = self._build_prompt(task, context)
        try:
            return await self.session.query(prompt)
        except RateLimitError:
            return await self.fallback_session.query(prompt)

    def _build_prompt(self, task: str, context: dict) -> str:
        """Build a rich prompt with project context."""
        return f"""
Project: {context['project_name']}
Files changed recently: {context['recent_changes']}
Relevant code symbols: {context['symbols']}
Related test files: {context['test_files']}

Task: {task}
"""
```

#### B. Tool Registry (macOS-Native Tools)

Register all available macOS tools for the agent to use:

```python
from enum import Enum
from dataclasses import dataclass
from typing import Callable, Any

class ToolCategory(Enum):
    SHELL = "shell"
    FILESYSTEM = "filesystem"
    CODE_ANALYSIS = "code_analysis"
    APP_CONTROL = "app_control"
    SYSTEM = "system"
    AI_LOCAL = "ai_local"
    SECURITY = "security"
    SEARCH = "search"

@dataclass
class MacOSTool:
    name: str
    category: ToolCategory
    description: str
    function: Callable
    requires_permission: str | None = None

class ToolRegistry:
    """Registry of all available macOS tools."""

    def __init__(self):
        self.tools: dict[str, MacOSTool] = {}
        self._register_all()

    def _register_all(self):
        # Shell tools
        self.register(MacOSTool(
            name="shell_execute",
            category=ToolCategory.SHELL,
            description="Execute a shell command",
            function=run_shell,
        ))

        # Filesystem tools
        self.register(MacOSTool(
            name="spotlight_search",
            category=ToolCategory.SEARCH,
            description="Search files using Spotlight/mdfind",
            function=spotlight_search,
        ))

        # Code analysis tools
        self.register(MacOSTool(
            name="parse_code",
            category=ToolCategory.CODE_ANALYSIS,
            description="Parse source code with tree-sitter",
            function=parse_python_file,
        ))

        # App control tools
        self.register(MacOSTool(
            name="applescript",
            category=ToolCategory.APP_CONTROL,
            description="Execute AppleScript",
            function=run_applescript,
            requires_permission="Automation",
        ))
        self.register(MacOSTool(
            name="hammerspoon",
            category=ToolCategory.APP_CONTROL,
            description="Control apps via Hammerspoon",
            function=hammerspoon_cmd,
            requires_permission="Accessibility",
        ))

        # AI tools
        self.register(MacOSTool(
            name="local_embed",
            category=ToolCategory.AI_LOCAL,
            description="Generate embeddings locally",
            function=ollama_embed,
        ))
        self.register(MacOSTool(
            name="semantic_search",
            category=ToolCategory.AI_LOCAL,
            description="Semantic code search",
            function=vector_search,
        ))

        # Security tools
        self.register(MacOSTool(
            name="keychain_get",
            category=ToolCategory.SECURITY,
            description="Retrieve secret from Keychain",
            function=keychain_manager.get_secret,
        ))

    def register(self, tool: MacOSTool):
        self.tools[tool.name] = tool

    def get_available_tools(self) -> list[MacOSTool]:
        """Return tools available based on current permissions."""
        return [t for t in self.tools.values()
                if t.requires_permission is None or self._has_permission(t)]
```

#### C. Code Intelligence Engine

Combines tree-sitter, Serena LSP, and vector search:

```python
class CodeIntelligenceEngine:
    """Multi-layered code understanding."""

    def __init__(self, project_root: str):
        self.root = project_root
        self.parser_cache = {}
        self.embedding_pipeline = CodeEmbeddingPipeline()
        self.watcher = ProjectWatcher(project_root)

    async def understand_file(self, filepath: str) -> dict:
        """Get comprehensive understanding of a file."""
        # Layer 1: Structural analysis (tree-sitter)
        symbols = parse_python_file(filepath)

        # Layer 2: Semantic relationships (LSP via Serena)
        references = await self._get_references(filepath)

        # Layer 3: Similar code (vector search)
        similar = await self.embedding_pipeline.search(
            open(filepath).read()[:500],  # First 500 chars as query
            limit=5
        )

        return {
            "symbols": symbols,
            "references": references,
            "similar_files": similar,
        }

    async def find_relevant_context(self, query: str) -> dict:
        """Find all relevant code for a given task description."""
        # Semantic search
        semantic_results = await self.embedding_pipeline.search(query, limit=20)

        # Structural search (find related symbols)
        keywords = self._extract_keywords(query)
        structural_results = []
        for kw in keywords:
            files = spotlight_search(f'-name "*{kw}*"', self.root)
            structural_results.extend(files)

        return {
            "semantic": semantic_results,
            "structural": structural_results,
        }
```

#### D. Background Services (launchd)

Three persistent services:

1. **File Watcher Service** (`com.claudedev.watcher`)
   - Monitors project directories via FSEvents
   - Triggers re-indexing on file changes
   - Updates vector embeddings incrementally

2. **Embedding Service** (`com.claudedev.embedder`)
   - Runs Ollama with nomic-embed-text
   - Processes embedding queue
   - Maintains LanceDB vector index

3. **Agent Daemon** (`com.claudedev.agent`)
   - Listens for task requests via Unix socket
   - Manages Claude Code sessions
   - Handles scheduling and orchestration

---

### 9.3 Data Flow

```
User Request
    |
    v
[ClaudeDev Brain]
    |
    +---> [Code Intelligence] ---> tree-sitter parse
    |         |                     Spotlight search
    |         |                     LSP symbols
    |         +---> [Vector DB] --> semantic search results
    |
    +---> [Tool Registry] -------> select appropriate tools
    |
    +---> [Claude Agent SDK] ----> plan execution
    |         |
    |         +---> [Shell] ------> git, build, test commands
    |         +---> [Edit] -------> file modifications
    |         +---> [AppleScript] -> app automation
    |         +---> [Accessibility]-> UI interaction
    |
    +---> [Security Layer] ------> Keychain for secrets
    |                               TCC permission checks
    |
    v
[Results + Side Effects]
    |
    +---> [Notification] ---------> macOS notification to user
    +---> [FSEvents] -------------> triggers re-indexing
    +---> [Vector DB] ------------> update embeddings
```

---

### 9.4 Recommended Technology Stack

| Layer | Technology | Reason |
|-------|-----------|--------|
| **Primary AI** | Claude Agent SDK + Claude Opus 4.6 | Best reasoning, native tool use |
| **Fast AI** | Claude Sonnet 4.6 via SDK | Faster, cheaper for simple tasks |
| **Local AI** | Ollama + nomic-embed-text | Zero-latency embeddings, offline capable |
| **Local LLM** | MLX + Qwen2.5 3B (optional) | Classification without API calls |
| **Code Parsing** | tree-sitter-language-pack | 160+ languages, incremental, fast |
| **Vector DB** | LanceDB | Embedded, Rust-fast, tiny footprint |
| **File Watching** | watchfiles (Rust/FSEvents) | Kernel-efficient, async |
| **IPC** | Unix domain sockets | Lowest latency, no overhead |
| **Process Mgmt** | launchd | Native, energy-aware, auto-restart |
| **App Automation** | AppleScript/JXA + Hammerspoon | Full macOS control |
| **UI Automation** | PyObjC + Accessibility API | Read/control any application |
| **Secrets** | macOS Keychain via `security` CLI | Hardware-encrypted, OS-managed |
| **Search** | Spotlight (mdfind) + ripgrep | System index + content search |
| **Shell** | zsh via subprocess | Native, full POSIX |
| **Package Mgmt** | Homebrew | Standard macOS ecosystem |
| **Distribution** | Homebrew formula + pip | Maximum reach |
| **Sessions** | tmux | Persistent, scriptable |
| **Notifications** | osascript display notification | Native, zero-dependency |

---

### 9.5 Permission Requirements Summary

| Permission | Required For | How to Request | Priority |
|-----------|-------------|----------------|----------|
| **None** | Shell, Git, Homebrew, mdfind, tree-sitter, LanceDB, Ollama | N/A | Baseline |
| **Accessibility** | UI automation, Hammerspoon, screen readers | System Settings prompt | High |
| **Automation** | AppleScript app control | First-use prompt | High |
| **Full Disk Access** | Read protected files (optional) | System Settings | Low |
| **Developer Tools** | Debugging, profiling | System Settings | Low |
| **Notifications** | Display alerts to user | First-use prompt | Medium |

**Principle of Least Privilege:** ClaudeDev should work with NO special permissions for core functionality (code editing, git, building, testing). Permissions should only be requested for specific advanced features and only when the user explicitly enables them.

---

### 9.6 Performance Budget (Apple M5, 16 GB)

| Operation | Target Latency | Memory |
|-----------|---------------|--------|
| File parse (tree-sitter) | < 5ms per file | < 10MB |
| Spotlight search | < 100ms | System-managed |
| Embedding generation (single) | < 20ms | ~500MB (Ollama model) |
| Vector search (10k docs) | < 10ms | ~50MB (LanceDB) |
| Claude Code API call | 2-30s (network) | < 100MB (subprocess) |
| FSEvents notification | < 1ms | < 1MB |
| AppleScript execution | < 100ms | < 5MB |
| Shell command | < 10ms overhead | Variable |
| **Total idle footprint** | -- | **< 200MB** |
| **Total active footprint** | -- | **< 1.5GB** |

---

### 9.7 Startup Sequence

```python
async def startup():
    """ClaudeDev startup sequence on macOS."""

    # 1. Check system requirements
    assert sys.platform == "darwin"
    assert platform.machine() == "arm64"  # Apple Silicon

    # 2. Load credentials from Keychain
    api_key = keychain.get_secret("anthropic_api_key")

    # 3. Start background services
    ensure_launchd_agent("com.claudedev.watcher")
    ensure_launchd_agent("com.claudedev.embedder")

    # 4. Initialize Ollama (if not running)
    if not is_ollama_running():
        subprocess.Popen(["ollama", "serve"])
        await wait_for_ollama()

    # 5. Pull required models
    await ensure_model("nomic-embed-text")

    # 6. Initialize vector database
    db = lancedb.connect("~/.claudedev/vectordb")

    # 7. Initialize code intelligence
    intelligence = CodeIntelligenceEngine(project_root)

    # 8. Initialize Claude Agent SDK session
    brain = ClaudeDevBrain(api_key=api_key)

    # 9. Start file watcher
    asyncio.create_task(intelligence.watcher.start())

    # 10. Ready
    notify("ClaudeDev", "Ready for autonomous coding")
```

---

### 9.8 Key Design Principles

1. **Offline-First:** Core functionality (parsing, searching, editing) works without internet. API calls are for reasoning only.

2. **Energy-Aware:** Automatically throttle background operations on battery. Use `ProcessType: Background` for indexing.

3. **Permission-Minimal:** Request only what's needed, when it's needed. Core workflow needs zero special permissions.

4. **Native-First:** Use macOS APIs (FSEvents, Spotlight, Keychain, launchd) instead of cross-platform alternatives. They are always faster and more efficient on macOS.

5. **Async-Everything:** Use `asyncio` throughout. Never block the main thread. File watching, embedding generation, and API calls all run concurrently.

6. **Graceful Degradation:** If Ollama is unavailable, skip local embeddings. If Accessibility permission is missing, skip UI automation. Never crash on missing optional capabilities.

7. **Security-by-Default:** All secrets in Keychain. No plaintext credentials. Sandbox untrusted operations. Validate all inputs from external sources.

8. **Incremental Processing:** Never re-process everything. Use FSEvents to detect changes, tree-sitter for incremental parsing, and content hashes to skip unchanged embeddings.

---

## Appendix: Quick Reference Commands

```bash
# System info
sw_vers                          # macOS version
sysctl -n machdep.cpu.brand_string  # CPU model
system_profiler SPHardwareDataType   # Full hardware info

# Process management
launchctl list | grep claudedev  # Check our services
launchctl load ~/Library/LaunchAgents/com.claudedev.*.plist
caffeinate -i command            # Prevent sleep during command

# File search
mdfind -onlyin /path 'query'    # Spotlight search
mdfind -name "*.py"             # Find by name

# App control
osascript -e 'tell application "App" to activate'
osascript -l JavaScript -e 'Application("App").windows()'

# Security
security add-generic-password -s "com.claudedev" -a "key" -w "value"
security find-generic-password -s "com.claudedev" -a "key" -w

# Clipboard
pbcopy < file.txt               # Copy to clipboard
pbpaste > file.txt              # Paste from clipboard

# Notifications
osascript -e 'display notification "msg" with title "title"'

# Claude Code
claude -p "prompt"              # Non-interactive
claude -p --output-format json "prompt"  # JSON output
claude --continue -p "prompt"   # Continue last session
claude --resume ID -p "prompt"  # Resume specific session
```

---

## Sources

- [MLX Framework Documentation](https://ml-explore.github.io/mlx/)
- [MLX on Apple M5 GPU Research](https://machinelearning.apple.com/research/exploring-llms-mlx-m5)
- [MLX Benchmarks on Apple Silicon](https://arxiv.org/html/2510.18921v1)
- [Claude Code Headless Mode](https://code.claude.com/docs/en/headless)
- [Claude Agent SDK Python](https://github.com/anthropics/claude-agent-sdk-python)
- [Claude Agent SDK Reference](https://platform.claude.com/docs/en/agent-sdk/python)
- [PyObjC Accessibility Framework](https://pyobjc.readthedocs.io/en/latest/apinotes/Accessibility.html)
- [macapptree Accessibility Parser](https://github.com/MacPaw/macapptree)
- [Tree-sitter Language Pack](https://pypi.org/project/tree-sitter-language-pack/)
- [LanceDB Vector Database](https://lancedb.com/)
- [Nomic Embed Local Inference](https://www.nomic.ai/blog/posts/local-nomic-embed)
- [Hammerspoon Desktop Automation](https://www.hammerspoon.org/)
- [Apple launchd Documentation](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)
- [WWDC 2025 MLX Session](https://developer.apple.com/videos/play/wwdc2025/315/)
- [Production-Grade Local LLM Study](https://arxiv.org/abs/2511.05502)
