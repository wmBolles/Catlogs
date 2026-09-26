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

"""Keylogger daemon manager for CatLogs.

Handles compilation, daemon lifecycle (start/stop/status),
log file reading, and systemd user service management.
The user must explicitly opt-in before any monitoring begins.
"""

from .crypto import get_encrypted_filename, decrypt_data
import os
import signal
import subprocess
import shutil
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

from .config import CONFIG_DIR


# Paths
KEYLOGGER_DIR = CONFIG_DIR / "keylogger"
KEYLOGGER_BINARY = KEYLOGGER_DIR / "keylogger"
KEYLOGS_FILE = KEYLOGGER_DIR / get_encrypted_filename("keylogs.txt")
PID_FILE = KEYLOGGER_DIR / "keylogger.pid"
SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"
SERVICE_NAME = "catlogs-keylogger"
SERVICE_FILE = SYSTEMD_USER_DIR / f"{SERVICE_NAME}.service"


def _find_source() -> Optional[str]:
    """Locate the keylogger.c source file."""
    import sys

    # Check relative to the package
    base = getattr(sys, '_MEIPASS', os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    source = os.path.join(base, "keylogger", "keylogger.c")
    if os.path.isfile(source):
        return source

    # Check in the config dir
    config_source = str(KEYLOGGER_DIR / "keylogger.c")
    if os.path.isfile(config_source):
        return config_source

    return None


def is_compiled() -> bool:
    """Check if the keylogger binary exists and is executable."""
    return KEYLOGGER_BINARY.is_file() and os.access(str(KEYLOGGER_BINARY), os.X_OK)


def compile_keylogger() -> Dict[str, Any]:
    """Compile the keylogger from source.

    Returns dict with 'success', 'message', and optionally 'error'.
    """
    source = _find_source()
    if not source:
        return {
            "success": False,
            "message": "Source file keylogger.c not found.",
            "error": "Cannot locate keylogger/keylogger.c in the project tree.",
        }

    # Ensure output directory
    KEYLOGGER_DIR.mkdir(parents=True, exist_ok=True)

    # Copy source to config dir for reference
    dest_source = str(KEYLOGGER_DIR / "keylogger.c")
    if os.path.abspath(source) != os.path.abspath(dest_source):
        shutil.copy2(source, dest_source)

    # Check for gcc
    if not shutil.which("gcc"):
        return {
            "success": False,
            "message": "gcc not found. Install build-essential.",
            "error": "gcc compiler is not installed.",
        }

    # Check for X11 dev headers
    try:
        result = subprocess.run(
            ["gcc", "-o", str(KEYLOGGER_BINARY), dest_source, "-lX11"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            os.chmod(str(KEYLOGGER_BINARY), 0o755)
            return {
                "success": True,
                "message": "Compiled successfully.",
            }
        else:
            error_msg = result.stderr.strip()
            if "X11/Xlib.h" in error_msg:
                return {
                    "success": False,
                    "message": "Missing X11 development headers.",
                    "error": f"Install libx11-dev: sudo apt install libx11-dev\n\n{error_msg}",
                }
            return {
                "success": False,
                "message": "Compilation failed.",
                "error": error_msg,
            }
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Compilation timed out.", "error": "gcc took longer than 30 seconds."}
    except Exception as e:
        return {"success": False, "message": f"Compilation error: {e}", "error": str(e)}


def get_daemon_pid() -> Optional[int]:
    """Read and validate the PID from the PID file."""
    if not PID_FILE.is_file():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
        # Check if process is actually running
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError, OSError):
        return None


def is_running() -> bool:
    """Check if the keylogger daemon is running."""
    return get_daemon_pid() is not None


def _systemd_user_available() -> bool:
    """Return True when the current user session supports systemd user services."""
    if shutil.which("systemctl") is None:
        return False
    try:
        result = subprocess.run(
            ["systemctl", "--user", "show-environment"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def start_daemon() -> Dict[str, Any]:
    """Start the keylogger daemon in a way that survives GUI shutdown."""
    if is_running():
        return {"success": False, "message": "Daemon is already running."}

    if not is_compiled():
        result = compile_keylogger()
        if not result["success"]:
            return result

    KEYLOGGER_DIR.mkdir(parents=True, exist_ok=True)

    if _systemd_user_available() and SERVICE_FILE.exists():
        try:
            env = os.environ.copy()
            if not env.get("DISPLAY"):
                env["DISPLAY"] = os.environ.get("DISPLAY", ":0")
            if not env.get("XAUTHORITY") and os.path.exists(os.path.expanduser("~/.Xauthority")):
                env["XAUTHORITY"] = os.path.expanduser("~/.Xauthority")
            result = subprocess.run(
                ["systemctl", "--user", "start", SERVICE_NAME],
                capture_output=True,
                text=True,
                env=env,
                timeout=15,
            )
            if result.returncode == 0:
                time.sleep(0.6)
                if is_running():
                    pid = get_daemon_pid()
                    return {"success": True, "message": f"Daemon started as a persistent systemd service (PID {pid})."}
                return {"success": True, "message": "Systemd user service started; daemon should remain active after CatLogs closes."}
        except Exception:
            pass

    try:
        subprocess.Popen(
            [str(KEYLOGGER_BINARY), str(KEYLOGS_FILE), "--daemon"],
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        time.sleep(0.5)

        if is_running():
            pid = get_daemon_pid()
            return {
                "success": True,
                "message": f"Daemon started in detached mode (PID {pid}).",
            }
        else:
            return {
                "success": False,
                "message": "Daemon failed to start. Check if X11 is available.",
                "error": "The daemon process exited immediately. X11 display may not be accessible.",
            }
    except Exception as e:
        return {"success": False, "message": f"Failed to start daemon: {e}", "error": str(e)}


def stop_daemon() -> Dict[str, Any]:
    """Stop the keylogger daemon."""
    pid = get_daemon_pid()
    if pid is None:
        # Clean up stale PID file
        if PID_FILE.is_file():
            PID_FILE.unlink(missing_ok=True)
        return {"success": True, "message": "Daemon is not running."}

    try:
        os.kill(pid, signal.SIGTERM)

        # Wait up to 3 seconds for graceful shutdown
        for _ in range(30):
            time.sleep(0.1)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
        else:
            # Force kill if still running
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        # Clean up PID file
        if PID_FILE.is_file():
            PID_FILE.unlink(missing_ok=True)

        return {"success": True, "message": f"Daemon stopped (was PID {pid})."}
    except ProcessLookupError:
        if PID_FILE.is_file():
            PID_FILE.unlink(missing_ok=True)
        return {"success": True, "message": "Daemon was already stopped."}
    except Exception as e:
        return {"success": False, "message": f"Failed to stop daemon: {e}", "error": str(e)}


def get_status() -> Dict[str, Any]:
    """Get comprehensive daemon status."""
    pid = get_daemon_pid()
    running = pid is not None

    import platform
    status = {
        "running": running,
        "pid": pid,
        "binary_exists": is_compiled(),
        "binary_path": str(KEYLOGGER_BINARY),
        "log_file": str(KEYLOGS_FILE),
        "pid_file": str(PID_FILE),
        "log_exists": KEYLOGS_FILE.is_file(),
        "log_size": None,
        "log_size_str": "0 B",
        "service_installed": SERVICE_FILE.is_file(),
        "platform": f"{platform.system()} {platform.release()}",
    }

    if status["log_exists"]:
        try:
            size = KEYLOGS_FILE.stat().st_size
            status["log_size"] = size
            if size < 1024:
                status["log_size_str"] = f"{size} B"
            elif size < 1024 * 1024:
                status["log_size_str"] = f"{size / 1024:.1f} KB"
            else:
                status["log_size_str"] = f"{size / (1024 * 1024):.1f} MB"
        except OSError:
            pass

    # If running, get process details
    if running and pid:
        try:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o",
                 "pid,lstart,%cpu,%mem,rss", "--no-headers"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                status["process_info"] = result.stdout.strip()
        except Exception:
            pass

    return status


def read_keylogs(max_lines: int = 500, tail: bool = True) -> List[str]:
    if not KEYLOGS_FILE.is_file():
        return []
    try:
        with open(str(KEYLOGS_FILE), "rb") as f:
            data = f.read()
        decrypted = decrypt_data(data).decode('utf-8', errors='replace')
        lines = decrypted.splitlines()
        lines = [l for l in lines if l.strip()]
        if tail and len(lines) > max_lines:
            lines = lines[-max_lines:]
        return lines
    except (PermissionError, OSError):
        return []


def clear_keylogs() -> Dict[str, Any]:
    """Clear the key log file."""
    if not KEYLOGS_FILE.is_file():
        return {"success": True, "message": "Log file does not exist."}

    try:
        # Stop daemon so it resets its global_offset when restarted
        was_running = is_running()
        if was_running:
            stop_daemon()

        with open(str(KEYLOGS_FILE), "w") as f:
            f.truncate(0)

        if was_running:
            start_daemon()

        return {"success": True, "message": "Key logs cleared."}
    except Exception as e:
        return {"success": False, "message": f"Failed to clear logs: {e}"}


def install_systemd_service() -> Dict[str, Any]:
    """Install a systemd user service for auto-start on login."""
    if not is_compiled():
        result = compile_keylogger()
        if not result["success"]:
            return result

    SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)

    service_content = f"""[Unit]
Description=CatLogs Key Logger Daemon
Documentation=https://catlogs.wassim.tech
After=graphical-session.target

[Service]
Type=forking
ExecStart={KEYLOGGER_BINARY} {KEYLOGS_FILE} --daemon
PIDFile={PID_FILE}
Restart=on-failure
RestartSec=5
Environment=DISPLAY=:0
Environment=XAUTHORITY=%h/.Xauthority

[Install]
WantedBy=default.target
"""

    try:
        SERVICE_FILE.write_text(service_content)

        # Reload systemd user daemon
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            capture_output=True, timeout=10,
        )

        # Enable the service
        subprocess.run(
            ["systemctl", "--user", "enable", SERVICE_NAME],
            capture_output=True, timeout=10,
        )

        return {
            "success": True,
            "message": f"Service installed and enabled. It will auto-start on login.",
        }
    except Exception as e:
        return {"success": False, "message": f"Failed to install service: {e}", "error": str(e)}


def uninstall_systemd_service() -> Dict[str, Any]:
    """Remove the systemd user service."""
    try:
        # Stop and disable
        subprocess.run(
            ["systemctl", "--user", "stop", SERVICE_NAME],
            capture_output=True, timeout=10,
        )
        subprocess.run(
            ["systemctl", "--user", "disable", SERVICE_NAME],
            capture_output=True, timeout=10,
        )

        # Remove service file
        if SERVICE_FILE.is_file():
            SERVICE_FILE.unlink()

        # Reload
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            capture_output=True, timeout=10,
        )

        return {"success": True, "message": "Service uninstalled."}
    except Exception as e:
        return {"success": False, "message": f"Failed to uninstall service: {e}", "error": str(e)}
