#!/usr/bin/env bash
# ClaudeDev Installation Script
# Installs all dependencies and configures the system

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check prerequisites
check_prereqs() {
    log_info "Checking prerequisites..."

    # Check macOS
    [[ "$(uname)" == "Darwin" ]] || { log_error "macOS required"; exit 1; }

    # Check Homebrew
    command -v brew >/dev/null 2>&1 || { log_error "Homebrew not found. Install from https://brew.sh"; exit 1; }
    log_success "Homebrew found"

    # Check Python 3.13+
    if command -v python3 >/dev/null 2>&1; then
        PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        if [[ "$(echo "$PY_VERSION >= 3.13" | bc)" == "1" ]]; then
            log_success "Python $PY_VERSION found"
        else
            log_warn "Python $PY_VERSION found, 3.13+ recommended"
        fi
    else
        log_error "Python 3 not found"
        exit 1
    fi

    # Check Poetry
    if ! command -v poetry >/dev/null 2>&1; then
        log_info "Installing Poetry..."
        curl -sSL https://install.python-poetry.org | python3 -
        log_success "Poetry installed"
    else
        log_success "Poetry found: $(poetry --version)"
    fi

    # Check Claude Code
    if command -v claude >/dev/null 2>&1; then
        log_success "Claude Code found: $(claude --version 2>/dev/null || echo 'installed')"
    else
        log_warn "Claude Code not found. Install from https://claude.ai/code"
        log_warn "ClaudeDev will require ANTHROPIC_API_KEY without Claude Code CLI"
    fi

    # Check gh CLI
    if command -v gh >/dev/null 2>&1; then
        log_success "GitHub CLI found: $(gh --version | head -1)"
        if gh auth status >/dev/null 2>&1; then
            log_success "GitHub CLI authenticated"
        else
            log_warn "GitHub CLI not authenticated. Run: gh auth login"
        fi
    else
        log_info "Installing GitHub CLI..."
        brew install gh
        log_success "GitHub CLI installed. Run: gh auth login"
    fi

    # Check cloudflared
    if command -v cloudflared >/dev/null 2>&1; then
        log_success "Cloudflared found"
    else
        log_info "Installing cloudflared..."
        brew install cloudflared
        log_success "Cloudflared installed"
    fi

    # Check iTerm2
    if [[ -d "/Applications/iTerm.app" ]]; then
        log_success "iTerm2 found"
    else
        log_warn "iTerm2 not found. Install from https://iterm2.com for visual features"
    fi
}

# Create directory structure
setup_directories() {
    log_info "Creating ClaudeDev directories..."
    mkdir -p ~/.claudedev/{logs,projects,tunnel}
    log_success "Directories created at ~/.claudedev/"
}

# Install Python dependencies
install_deps() {
    log_info "Installing Python dependencies with Poetry..."
    cd "$(dirname "$0")/.."
    poetry install
    log_success "Dependencies installed"
}

# Copy example config
setup_config() {
    if [[ ! -f ~/.claudedev/config.toml ]]; then
        log_info "Creating default config..."
        local example_config
        example_config="$(dirname "$0")/../config/settings.example.toml"
        if [[ -f "$example_config" ]]; then
            cp "$example_config" ~/.claudedev/config.toml
            log_success "Config created at ~/.claudedev/config.toml"
        else
            log_warn "Example config not found at $example_config, creating minimal config"
            cat > ~/.claudedev/config.toml << 'TOML'
# ClaudeDev Configuration
# See documentation for all available options

webhook_port = 8787
webhook_host = "0.0.0.0"
tunnel_enabled = true
log_level = "INFO"
max_budget_per_issue = 5.0
max_budget_per_project_daily = 50.0
auto_enhance_issues = true
auto_implement = false
review_on_pr = true
TOML
            log_success "Minimal config created at ~/.claudedev/config.toml"
        fi
    else
        log_warn "Config already exists at ~/.claudedev/config.toml (skipping)"
    fi
}

# Setup LaunchAgent
setup_launchagent() {
    log_info "Setting up LaunchAgent for auto-start..."

    local plist_src
    plist_src="$(dirname "$0")/../config/com.claudedev.daemon.plist"
    local plist_dst="$HOME/Library/LaunchAgents/com.claudedev.daemon.plist"

    if [[ -f "$plist_src" ]]; then
        mkdir -p "$HOME/Library/LaunchAgents"
        # Replace $HOME in plist with actual home directory
        sed "s|\$HOME|$HOME|g" "$plist_src" > "$plist_dst"

        # Also update the claudedev path to use Poetry's path
        local claudedev_path
        claudedev_path=$(poetry env info -e 2>/dev/null || echo "$HOME/.local/bin/claudedev")
        sed -i '' "s|\$HOME/.local/bin/claudedev|$claudedev_path/claudedev|g" "$plist_dst" 2>/dev/null || true

        log_success "LaunchAgent installed at $plist_dst"
        log_info "To enable auto-start: launchctl load $plist_dst"
    else
        log_warn "LaunchAgent plist not found at $plist_src (skipping)"
    fi

    log_info "To start now: claudedev daemon start"
}

# Initialize database
init_db() {
    log_info "Initializing database..."
    cd "$(dirname "$0")/.."
    poetry run python -c "
import asyncio
from claudedev.core.state import init_db
asyncio.run(init_db('sqlite+aiosqlite:///$HOME/.claudedev/claudedev.db'))
"
    log_success "Database initialized at ~/.claudedev/claudedev.db"
}

# Main
main() {
    echo ""
    echo "======================================================"
    echo "         ClaudeDev Installer v0.1.0"
    echo "    Autonomous Development Orchestrator"
    echo "======================================================"
    echo ""

    check_prereqs
    echo ""
    setup_directories
    install_deps
    setup_config
    setup_launchagent
    init_db

    echo ""
    log_success "Installation complete!"
    echo ""
    echo "Next steps:"
    echo "  1. Configure: edit ~/.claudedev/config.toml"
    echo "  2. Start daemon: claudedev daemon start"
    echo "  3. Add a project: claudedev project add"
    echo "  4. Open dashboard: claudedev dashboard"
    echo ""
    echo "For auto-start on login:"
    echo "  launchctl load ~/Library/LaunchAgents/com.claudedev.daemon.plist"
    echo ""
}

main "$@"
