#!/usr/bin/env bash
# ClaudeDev Uninstall Script
# Removes ClaudeDev configuration, data, and LaunchAgent

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

CLAUDEDEV_DIR="$HOME/.claudedev"
PLIST_PATH="$HOME/Library/LaunchAgents/com.claudedev.daemon.plist"

confirm() {
    local prompt="$1"
    local response
    echo -en "${YELLOW}$prompt [y/N]: ${NC}"
    read -r response
    [[ "$response" =~ ^[Yy]$ ]]
}

# Stop the daemon if running
stop_daemon() {
    log_info "Stopping ClaudeDev daemon..."

    # Unload LaunchAgent if loaded
    if [[ -f "$PLIST_PATH" ]]; then
        launchctl unload "$PLIST_PATH" 2>/dev/null || true
        log_success "LaunchAgent unloaded"
    fi

    # Kill any running daemon process
    local pid_file="$CLAUDEDEV_DIR/daemon.pid"
    if [[ -f "$pid_file" ]]; then
        local pid
        pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            log_success "Daemon process $pid stopped"
        fi
        rm -f "$pid_file"
    fi

    # Also kill any remaining processes
    pkill -f "claudedev daemon" 2>/dev/null || true
}

# Remove LaunchAgent
remove_launchagent() {
    if [[ -f "$PLIST_PATH" ]]; then
        rm -f "$PLIST_PATH"
        log_success "LaunchAgent removed: $PLIST_PATH"
    else
        log_info "No LaunchAgent found (skipping)"
    fi
}

# Remove configuration and data
remove_data() {
    if [[ -d "$CLAUDEDEV_DIR" ]]; then
        if confirm "Remove all ClaudeDev data at $CLAUDEDEV_DIR? This includes config, database, and logs."; then
            rm -rf "$CLAUDEDEV_DIR"
            log_success "ClaudeDev data removed: $CLAUDEDEV_DIR"
        else
            log_warn "Skipping data removal. Files remain at $CLAUDEDEV_DIR"
        fi
    else
        log_info "No ClaudeDev data directory found (skipping)"
    fi
}

# Remove Poetry virtual environment
remove_venv() {
    local project_dir
    project_dir="$(dirname "$0")/.."

    if [[ -f "$project_dir/pyproject.toml" ]]; then
        if confirm "Remove Poetry virtual environment for ClaudeDev?"; then
            cd "$project_dir"
            poetry env remove --all 2>/dev/null || true
            log_success "Poetry virtual environment removed"
        else
            log_warn "Skipping virtual environment removal"
        fi
    fi
}

# Main
main() {
    echo ""
    echo "======================================================"
    echo "         ClaudeDev Uninstaller v0.1.0"
    echo "======================================================"
    echo ""

    if ! confirm "Are you sure you want to uninstall ClaudeDev?"; then
        log_info "Uninstall cancelled."
        exit 0
    fi

    echo ""
    stop_daemon
    remove_launchagent
    remove_data
    remove_venv

    echo ""
    log_success "ClaudeDev uninstall complete."
    echo ""
    echo "Note: The following were NOT removed (remove manually if desired):"
    echo "  - GitHub CLI (gh): brew uninstall gh"
    echo "  - Cloudflared: brew uninstall cloudflared"
    echo "  - Poetry: pipx uninstall poetry"
    echo "  - The ClaudeDev source directory itself"
    echo ""
}

main "$@"
