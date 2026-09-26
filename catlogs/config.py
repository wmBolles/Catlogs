# CatLogs
# A local system logging and diagnostic tool.
# Copyright (C) 2026 Wassim Bolles
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Configuration management for CatLogs application."""

import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

_xdg_config = os.environ.get("XDG_CONFIG_HOME")
CONFIG_DIR = (Path(_xdg_config)
              if _xdg_config else Path.home() / ".config") / "catlogs"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_LOG_PATHS: List[Dict[str, Any]] = [
    # System & Kernel Logs
    {"path": "/var/log/syslog", "name": "Syslog",
        "type": "syslog", "enabled": True},
    {"path": "/var/log/syslog.1",
        "name": "Syslog (prev)", "type": "syslog", "enabled": True},
    {"path": "/var/log/messages", "name": "Messages",
        "type": "syslog", "enabled": True},
    {"path": "/var/log/messages.1",
        "name": "Messages (prev)", "type": "syslog", "enabled": True},
    {"path": "/var/log/kern.log", "name": "Kernel Log",
        "type": "kernel", "enabled": True},
    {"path": "/var/log/kern.log.1",
        "name": "Kernel Log (prev)", "type": "kernel", "enabled": True},

    # Auth & Security Logs
    {"path": "/var/log/auth.log", "name": "Auth Log",
        "type": "auth", "enabled": True},
    {"path": "/var/log/auth.log.1",
        "name": "Auth Log (prev)", "type": "auth", "enabled": True},
    {"path": "/var/log/secure", "name": "Secure Log",
        "type": "auth", "enabled": True},
    {"path": "/var/log/secure.1",
        "name": "Secure Log (prev)", "type": "auth", "enabled": True},

    # Package Manager Logs
    {"path": "/var/log/dpkg.log", "name": "DPKG Log",
        "type": "dpkg", "enabled": True},
    {"path": "/var/log/dpkg.log.1",
        "name": "DPKG Log (prev)", "type": "dpkg", "enabled": True},
    {"path": "/var/log/apt/history.log", "name": "APT History",
        "type": "apt_history", "enabled": True},
    {"path": "/var/log/apt/term.log", "name": "APT Terminal",
        "type": "apt_term", "enabled": True},
    {"path": "/var/log/alternatives.log", "name": "Alternatives Log",
        "type": "alternatives", "enabled": True},

    # Service & Daemon Logs
    {"path": "/var/log/cron.log", "name": "Cron Log",
        "type": "cron", "enabled": True},
    {"path": "/var/log/cron", "name": "Cron", "type": "cron", "enabled": True},
    {"path": "/var/log/boot.log", "name": "Boot Log",
        "type": "boot", "enabled": True},
    {"path": "/var/log/daemon.log", "name": "Daemon Log",
        "type": "daemon", "enabled": True},
    {"path": "/var/log/daemon.log.1",
        "name": "Daemon Log (prev)", "type": "daemon", "enabled": True},
    {"path": "/var/log/Xorg.0.log", "name": "Xorg Display Log",
        "type": "xorg", "enabled": True},
    {"path": "/var/log/Xorg.1.log", "name": "Xorg Display Log 1",
        "type": "xorg", "enabled": True},

    # User Shell History
    {"path": "~/.bash_history", "name": "Bash History",
        "type": "shell_history", "enabled": True},
    {"path": "~/.zsh_history", "name": "Zsh History",
        "type": "shell_history", "enabled": True},
    {"path": "~/.histfile", "name": "Histfile",
        "type": "shell_history", "enabled": True},
    {"path": "~/.sh_history", "name": "Sh History",
        "type": "shell_history", "enabled": True},
    {"path": "~/.ksh_history", "name": "Ksh History",
        "type": "shell_history", "enabled": True},
    {"path": "~/.history", "name": "Generic History",
        "type": "shell_history", "enabled": True},
    {"path": "~/.local/share/fish/fish_history", "name": "Fish Shell History",
        "type": "fish_history", "enabled": True},
]

DEFAULT_CONFIG: Dict[str, Any] = {
    "theme": "dark",
    "first_run": True,
    "window_feature_shown": False,
    "last_update_check": 0,
    "protection_mode": True,
    "screen_lock_history": False,
    "log_paths": [dict(p) for p in DEFAULT_LOG_PATHS],
    "enabled_features": {
        "processes": True,
        "scanner": True,
        "history": True,
        "read_errors": True,
        "keylogger": True,
        "help": True,
    },
}


def load_config() -> Dict[str, Any]:
    """Load configuration from the user's home directory."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                user_config = json.load(f)
                config = DEFAULT_CONFIG.copy()
                config.update(user_config)
                if "log_paths" not in config or not config["log_paths"]:
                    config["log_paths"] = get_default_log_paths()
                if "enabled_features" not in config:
                    config["enabled_features"] = DEFAULT_CONFIG["enabled_features"].copy()
                return config
        except Exception:
            pass
    return {**DEFAULT_CONFIG, "log_paths": get_default_log_paths(), "enabled_features": DEFAULT_CONFIG["enabled_features"].copy()}


def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to the user's home directory."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Failed to save config: {e}")


def get_default_log_paths() -> List[Dict[str, Any]]:
    """Return a fresh copy of the default log paths list."""
    return [dict(p) for p in DEFAULT_LOG_PATHS]


def load_log_paths() -> List[Dict[str, Any]]:
    """Get the currently configured log file paths."""
    config = load_config()
    paths = config.get("log_paths")
    if not paths:
        paths = get_default_log_paths()
    return paths


def save_log_paths(paths: List[Dict[str, Any]]) -> None:
    """Save updated log paths to config."""
    config = load_config()
    config["log_paths"] = paths
    save_config(config)


def add_log_path(path: str, name: str = "", log_type: str = "auto", enabled: bool = True) -> bool:
    """Add a new log path to configuration. Returns True if added, False if duplicate."""
    path = path.strip()
    if not path:
        return False

    paths = load_log_paths()

    # Normalize path for comparison
    norm_new = os.path.expanduser(path)
    for p in paths:
        if os.path.expanduser(p.get("path", "")) == norm_new:
            return False

    if not name:
        name = Path(path).name or path

    paths.append({
        "path": path,
        "name": name,
        "type": log_type,
        "enabled": enabled,
    })
    save_log_paths(paths)
    return True


def remove_log_path(path: str) -> bool:
    """Remove a log path from configuration. Returns True if removed."""
    path = path.strip()
    paths = load_log_paths()
    norm_target = os.path.expanduser(path)

    new_paths = [p for p in paths if os.path.expanduser(
        p.get("path", "")) != norm_target and p.get("path") != path]
    if len(new_paths) != len(paths):
        save_log_paths(new_paths)
        return True
    return False


def reset_log_paths() -> List[Dict[str, Any]]:
    """Reset log paths to default configuration."""
    defaults = get_default_log_paths()
    save_log_paths(defaults)
    return defaults


def format_size(size_bytes: int) -> str:
    """Format file size in human-readable units."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def check_path_status(path: str) -> Dict[str, Any]:
    """Check existence, readability, and size of a log path."""
    expanded = os.path.expanduser(os.path.expandvars(path.strip()))

    if not os.path.exists(expanded):
        return {
            "status_code": "not_found",
            "status_text": "⚠ Not Found",
            "size_str": "-",
            "size_bytes": None,
            "resolved_path": expanded,
            "exists": False,
            "readable": False,
        }

    if not os.path.isfile(expanded):
        return {
            "status_code": "not_a_file",
            "status_text": "📁 Directory",
            "size_str": "-",
            "size_bytes": None,
            "resolved_path": expanded,
            "exists": True,
            "readable": False,
        }

    if not os.access(expanded, os.R_OK):
        return {
            "status_code": "permission_denied",
            "status_text": "⛔ Permission Denied",
            "size_str": "-",
            "size_bytes": None,
            "resolved_path": expanded,
            "exists": True,
            "readable": False,
        }

    try:
        size = os.path.getsize(expanded)
        size_str = format_size(size)
        return {
            "status_code": "active",
            "status_text": f"✔ Active ({size_str})",
            "size_str": size_str,
            "size_bytes": size,
            "resolved_path": expanded,
            "exists": True,
            "readable": True,
        }
    except OSError:
        return {
            "status_code": "active",
            "status_text": "✔ Active",
            "size_str": "-",
            "size_bytes": None,
            "resolved_path": expanded,
            "exists": True,
            "readable": True,
        }
