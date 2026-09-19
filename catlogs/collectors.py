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

import os
import re
import glob
import socket
import subprocess
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from .models import CommandEntry
from .read_errors import log_read_error

logger = logging.getLogger(__name__)


def _run_command(cmd: List[str], timeout: int = 15) -> Optional[str]:
    """Run a shell command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "LC_ALL": "C"},
        )
        if result.returncode == 0:
            return result.stdout
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError, OSError) as e:
        logger.debug(f"Command {cmd} failed: {e}")
        if isinstance(e, PermissionError):
            log_read_error(str(cmd), str(e), "collectors._run_command")
        return None


def _get_hostname() -> str:
    """Get the system hostname."""
    try:
        return socket.gethostname()
    except Exception:
        return "localhost"


def _parse_bash_history(filepath: str, username: str) -> List[CommandEntry]:
    """Parse a bash history file. Handles optional timestamps (#<epoch>)."""
    entries = []
    hostname = _get_hostname()

    try:
        with open(filepath, "r", errors="replace") as f:
            lines = f.readlines()
    except (PermissionError, OSError) as e:
        logger.debug(f"Cannot read {filepath}: {e}")
        log_read_error(filepath, str(e), "collectors._parse_bash_history")
        return entries

    current_timestamp = None
    for line in lines:
        line = line.rstrip("\n")
        if not line:
            continue

        if line.startswith("#") and len(line) > 1:
            try:
                ts_val = int(line[1:])
                if 946684800 <= ts_val <= 4102444800:
                    current_timestamp = datetime.fromtimestamp(ts_val)
                    continue
            except (ValueError, OSError, OverflowError):
                pass

        cmd = line.strip()
        if not cmd:
            continue

        entries.append(
            CommandEntry(
                timestamp=current_timestamp,
                user=username,
                command=cmd,
                shell="bash",
                source="history",
                hostname=hostname,
                extra={"history_file": filepath},
            )
        )
        current_timestamp = None

    return entries


def _parse_zsh_history(filepath: str, username: str) -> List[CommandEntry]:
    """Parse a zsh history file. Handles EXTENDED_HISTORY format.

    Extended format: `: <epoch>:<duration>;<command>`
    Plain format: just the command text.
    """
    entries = []
    hostname = _get_hostname()

    try:
        with open(filepath, "r", errors="replace") as f:
            lines = f.readlines()
    except (PermissionError, OSError) as e:
        logger.debug(f"Cannot read {filepath}: {e}")
        log_read_error(filepath, str(e), "collectors._parse_zsh_history")
        return entries

    ext_pattern = re.compile(r"^:\s*(\d+):\d+;(.+)$")

    for line in lines:
        line = line.rstrip("\n")
        if not line:
            continue

        timestamp = None
        cmd = line

        match = ext_pattern.match(line)
        if match:
            try:
                epoch = int(match.group(1))
                timestamp = datetime.fromtimestamp(epoch)
            except (OSError, OverflowError, ValueError):
                pass
            cmd = match.group(2)

        cmd = cmd.strip()
        if not cmd:
            continue

        entries.append(
            CommandEntry(
                timestamp=timestamp,
                user=username,
                command=cmd,
                shell="zsh",
                source="history",
                hostname=hostname,
                extra={"history_file": filepath},
            )
        )

    return entries


def _parse_generic_history(filepath: str, username: str, shell: str) -> List[CommandEntry]:
    """Parse a generic history file (sh, ksh, etc.) — one command per line."""
    entries = []
    hostname = _get_hostname()

    try:
        with open(filepath, "r", errors="replace") as f:
            lines = f.readlines()
    except (PermissionError, OSError) as e:
        logger.debug(f"Cannot read {filepath}: {e}")
        log_read_error(filepath, str(e), "collectors._parse_generic_history")
        return entries

    for line in lines:
        cmd = line.strip()
        if not cmd:
            continue

        entries.append(
            CommandEntry(
                timestamp=None,
                user=username,
                command=cmd,
                shell=shell,
                source="history",
                hostname=hostname,
                extra={"history_file": filepath},
            )
        )

    return entries


def _parse_fish_history(filepath: str, username: str) -> List[CommandEntry]:
    """Parse a fish shell history file.

    Fish history format:
        - cmd: <command>
          when: <epoch>
    """
    entries = []
    hostname = _get_hostname()

    try:
        with open(filepath, "r", errors="replace") as f:
            lines = f.readlines()
    except (PermissionError, OSError) as e:
        logger.debug(f"Cannot read {filepath}: {e}")
        log_read_error(filepath, str(e), "collectors._parse_fish_history")
        return entries

    current_cmd = None
    current_ts = None

    for line in lines:
        line = line.rstrip("\n")
        if line.startswith("- cmd: "):
            if current_cmd:
                entries.append(
                    CommandEntry(
                        timestamp=current_ts,
                        user=username,
                        command=current_cmd,
                        shell="fish",
                        source="history",
                        hostname=hostname,
                        extra={"history_file": filepath},
                    )
                )
            current_cmd = line[7:].strip()
            current_ts = None
        elif line.strip().startswith("when: "):
            try:
                epoch = int(line.strip().split(":", 1)[1].strip())
                current_ts = datetime.fromtimestamp(epoch)
            except (ValueError, OSError, OverflowError):
                pass

    if current_cmd:
        entries.append(
            CommandEntry(
                timestamp=current_ts,
                user=username,
                command=current_cmd,
                shell="fish",
                source="history",
                hostname=hostname,
                extra={"history_file": filepath},
            )
        )

    return entries


def collect_shell_history(paths: Optional[List[str]] = None) -> List[CommandEntry]:
    """Collect commands from shell history files for all accessible users."""
    entries = []
    current_user = os.environ.get("USER", os.environ.get("LOGNAME", "unknown"))

    history_map = {
        ".bash_history": ("bash", _parse_bash_history),
        ".zsh_history": ("zsh", _parse_zsh_history),
        ".histfile": ("zsh", _parse_zsh_history),
        ".sh_history": ("sh", lambda fp, u: _parse_generic_history(fp, u, "sh")),
        ".ksh_history": ("ksh", lambda fp, u: _parse_generic_history(fp, u, "ksh")),
        ".history": ("sh", lambda fp, u: _parse_generic_history(fp, u, "sh")),
    }

    if paths is not None:
        for raw_path in paths:
            filepath = os.path.expanduser(os.path.expandvars(raw_path))
            if not os.path.isfile(filepath) or not os.access(filepath, os.R_OK):
                continue
            filename = os.path.basename(filepath).lower()
            try:
                if "fish" in filename or "fish" in filepath:
                    file_entries = _parse_fish_history(filepath, current_user)
                elif "zsh" in filename or "histfile" in filename:
                    file_entries = _parse_zsh_history(filepath, current_user)
                elif "bash" in filename:
                    file_entries = _parse_bash_history(filepath, current_user)
                else:
                    file_entries = _parse_generic_history(
                        filepath, current_user, "sh")
                entries.extend(file_entries)
                logger.info(
                    f"Collected {len(file_entries)} entries from {filepath}")
            except Exception as e:
                logger.debug(f"Error parsing {filepath}: {e}")
        return entries

    home_dirs = {}
    current_home = os.path.expanduser("~")
    home_dirs[current_user] = current_home
    try:
        with open("/etc/passwd", "r") as f:
            for line in f:
                parts = line.strip().split(":")
                if len(parts) >= 6:
                    username = parts[0]
                    uid = int(parts[2]) if parts[2].isdigit() else -1
                    home = parts[5]
                    shell = parts[6] if len(parts) > 6 else ""
                    if (uid >= 1000 or uid == 0) and os.path.isdir(home):
                        if "nologin" not in shell and "false" not in shell:
                            home_dirs[username] = home
    except (PermissionError, OSError):
        pass

    for username, home in home_dirs.items():
        for hist_name, (shell, parser) in history_map.items():
            filepath = os.path.join(home, hist_name)
            if os.path.isfile(filepath) and os.access(filepath, os.R_OK):
                try:
                    file_entries = parser(filepath, username)
                    entries.extend(file_entries)
                    logger.info(
                        f"Collected {len(file_entries)} entries from {filepath}")
                except Exception as e:
                    logger.debug(f"Error parsing {filepath}: {e}")

    for username, home in home_dirs.items():
        fish_hist = os.path.join(
            home, ".local", "share", "fish", "fish_history")
        if os.path.isfile(fish_hist) and os.access(fish_hist, os.R_OK):
            try:
                file_entries = _parse_fish_history(fish_hist, username)
                entries.extend(file_entries)
                logger.info(
                    f"Collected {len(file_entries)} entries from {fish_hist}")
            except Exception as e:
                logger.debug(f"Error parsing {fish_hist}: {e}")

    return entries


def collect_running_processes() -> List[CommandEntry]:
    """Collect currently running processes using `ps`."""
    entries = []
    hostname = _get_hostname()

    output = _run_command([
        "ps", "axo", "user,pid,pcpu,pmem,tty,stat,lstart,args",
        "--no-headers", "--sort=-pcpu"
    ])

    if not output:
        return entries

    lstart_pattern = re.compile(
        r"^(\S+)\s+"       # USER
        r"(\d+)\s+"        # PID
        r"([\d.]+)\s+"     # %CPU
        r"([\d.]+)\s+"     # %MEM
        r"(\S+)\s+"        # TTY
        r"(\S+)\s+"        # STAT
        r"(\w{3}\s+\w{3}\s+\d+\s+[\d:]+\s+\d{4})\s+"  # LSTART
        r"(.+)$"           # COMMAND
    )

    for line in output.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        match = lstart_pattern.match(line)
        if not match:
            continue

        user = match.group(1)
        pid = int(match.group(2))
        cpu = match.group(3)
        mem = match.group(4)
        tty = match.group(5)
        stat = match.group(6)
        lstart_str = match.group(7)
        command = match.group(8)

        timestamp = None
        try:
            timestamp = datetime.strptime(lstart_str, "%a %b %d %H:%M:%S %Y")
        except ValueError:
            try:
                timestamp = datetime.strptime(
                    lstart_str, "%a %b  %d %H:%M:%S %Y")
            except ValueError:
                pass

        shell = "process"
        cmd_base = os.path.basename(command.split()[0]) if command else ""
        if cmd_base in ("bash", "zsh", "sh", "ksh", "csh", "tcsh", "fish", "dash"):
            shell = cmd_base

        if tty == "?":
            tty = "none"

        entries.append(
            CommandEntry(
                timestamp=timestamp,
                user=user,
                command=command,
                shell=shell,
                source="process",
                pid=pid,
                tty=tty,
                hostname=hostname,
                cpu_percent=cpu,
                mem_percent=mem,
                status=stat,
            )
        )

    return entries


def collect_auth_log(paths: Optional[List[str]] = None) -> List[CommandEntry]:
    """Collect sudo/su commands from auth log files."""
    from .log_parsers import read_log_file_lines
    from .config import load_log_paths

    entries = []
    hostname = _get_hostname()

    if paths is not None:
        auth_paths = paths
    else:
        configured = [p["path"] for p in load_log_paths() if p.get(
            "type") == "auth" and p.get("enabled", True)]
        auth_paths = configured if configured else [
            "/var/log/auth.log",
            "/var/log/auth.log.1",
            "/var/log/secure",
            "/var/log/secure.1",
        ]

    # Example: Sep  6 09:40:00 hostname sudo: username : TTY=pts/0 ; PWD=/home/user ; USER=root ; COMMAND=/usr/bin/apt update
    sudo_pattern = re.compile(
        r"^(\w{3}\s+\d+\s+[\d:]+)\s+"  # timestamp
        r"(\S+)\s+"                       # hostname
        r"sudo(?:\[\d+\])?:\s+"          # sudo[pid]:
        r"(\S+)\s+:\s+"                  # username :
        r"(.+)$"                          # rest
    )

    command_pattern = re.compile(r"COMMAND=(.+)$")
    tty_pattern = re.compile(r"TTY=(\S+)")
    pwd_pattern = re.compile(r"PWD=(\S+)")
    runas_pattern = re.compile(r"USER=(\S+)")

    current_year = datetime.now().year

    for raw_path in auth_paths:
        auth_path = os.path.expanduser(os.path.expandvars(raw_path))
        lines = read_log_file_lines(auth_path)
        if not lines:
            continue

        for line in lines:
            match = sudo_pattern.match(line.strip())
            if not match:
                continue

            ts_str = match.group(1)
            user = match.group(3)
            rest = match.group(4)

            # Extract COMMAND
            cmd_match = command_pattern.search(rest)
            if not cmd_match:
                continue
            command = cmd_match.group(1).strip()

            # Parse timestamp (syslog format doesn't include year)
            timestamp = None
            try:
                timestamp = datetime.strptime(
                    f"{current_year} {ts_str}", "%Y %b %d %H:%M:%S"
                )
                # Handle year rollover
                if timestamp > datetime.now():
                    timestamp = timestamp.replace(year=current_year - 1)
            except ValueError:
                # Try alternate format with leading space day
                try:
                    timestamp = datetime.strptime(
                        f"{current_year} {ts_str}", "%Y %b  %d %H:%M:%S"
                    )
                except ValueError:
                    pass

            # Extract optional fields
            tty = None
            tty_match = tty_pattern.search(rest)
            if tty_match:
                tty = tty_match.group(1)

            pwd = None
            pwd_match = pwd_pattern.search(rest)
            if pwd_match:
                pwd = pwd_match.group(1)

            runas = None
            runas_match = runas_pattern.search(rest)
            if runas_match:
                runas = runas_match.group(1)

            extra = {}
            if runas:
                extra["run_as_user"] = runas

            entries.append(
                CommandEntry(
                    timestamp=timestamp,
                    user=user,
                    command=f"sudo {command}",
                    shell="sudo",
                    source=os.path.basename(auth_path),
                    tty=tty,
                    working_dir=pwd,
                    hostname=hostname,
                    extra=extra,
                )
            )

    return entries


def collect_journal() -> List[CommandEntry]:
    """Collect command executions from the systemd journal."""
    entries = []
    hostname = _get_hostname()

    output = _run_command([
        "journalctl", "--no-pager", "-n", "2000", "--output=short-iso",
        "_COMM=sudo", "--quiet",
    ], timeout=20)

    if not output:
        # Try without filtering
        output = _run_command([
            "journalctl", "--no-pager", "-n", "500", "--output=short-iso",
            "-t", "sudo", "--quiet",
        ], timeout=20)

    if not output:
        return entries

    journal_pattern = re.compile(
        r"^([\d\-T:+]+)\s+"   # ISO timestamp
        r"(\S+)\s+"             # hostname
        r"sudo\[\d+\]:\s+"    # sudo[pid]:
        r"(\S+)\s*:\s*"       # username :
        r"(.+)$"               # rest
    )

    command_pattern = re.compile(r"COMMAND=(.+)$")
    tty_pattern = re.compile(r"TTY=(\S+)")
    pwd_pattern = re.compile(r"PWD=(\S+)")

    for line in output.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        match = journal_pattern.match(line)
        if not match:
            continue

        ts_str = match.group(1)
        user = match.group(3)
        rest = match.group(4)

        cmd_match = command_pattern.search(rest)
        if not cmd_match:
            continue
        command = cmd_match.group(1).strip()

        timestamp = None
        try:
            # Handle various ISO timestamp formats from journalctl
            timestamp = datetime.fromisoformat(ts_str)
            timestamp = timestamp.astimezone().replace(
                tzinfo=None)  # normalize to naive local time
        except ValueError:
            try:
                timestamp = datetime.strptime(ts_str[:19], "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                pass

        tty = None
        tty_match = tty_pattern.search(rest)
        if tty_match:
            tty = tty_match.group(1)

        pwd = None
        pwd_match = pwd_pattern.search(rest)
        if pwd_match:
            pwd = pwd_match.group(1)

        entries.append(
            CommandEntry(
                timestamp=timestamp,
                user=user,
                command=f"sudo {command}",
                shell="sudo",
                source="journal",
                tty=tty,
                working_dir=pwd,
                hostname=hostname,
            )
        )

    return entries


def collect_accounting() -> List[CommandEntry]:
    """Collect command executions from process accounting (lastcomm)."""
    entries = []
    hostname = _get_hostname()

    output = _run_command(["lastcomm", "--forwards"], timeout=10)
    if not output:
        return entries

    # lastcomm format varies, typical:
    # command  flags  user  tty  timestamp
    # e.g.: ls  S  root  pts/0  Sat Sep  6 09:40
    current_year = datetime.now().year

    for line in output.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        parts = line.split()
        if len(parts) < 4:
            continue

        command = parts[0]
        # Flags can be multiple characters
        # Find user (first part that looks like a username after flags)
        # lastcomm output: command flags user tty time...
        # But flags can contain S, F, X, etc.

        # Try to parse — the format is quite variable
        try:
            # Typical: command  flags  user  tty  day_of_week month day time
            cmd_name = parts[0]
            # Skip flags (single character fields)
            idx = 1
            while idx < len(parts) and len(parts[idx]) <= 2 and parts[idx].isalpha():
                idx += 1

            if idx >= len(parts) - 3:
                continue

            user = parts[idx]
            tty = parts[idx + 1] if idx + 1 < len(parts) else None
            # Remaining parts are the timestamp
            ts_parts = parts[idx + 2:]
            if ts_parts:
                ts_str = " ".join(ts_parts)
                try:
                    timestamp = datetime.strptime(
                        f"{current_year} {ts_str}", "%Y %a %b %d %H:%M"
                    )
                except ValueError:
                    timestamp = None
            else:
                timestamp = None

            entries.append(
                CommandEntry(
                    timestamp=timestamp,
                    user=user,
                    command=cmd_name,
                    shell="acct",
                    source="accounting",
                    tty=tty if tty and tty != "__" else None,
                    hostname=hostname,
                )
            )
        except (IndexError, ValueError):
            continue

    return entries


def collect_last_logins() -> List[CommandEntry]:
    """Collect login sessions from `last` command."""
    entries = []
    hostname = _get_hostname()

    output = _run_command(["last", "-Faw", "-n", "200"], timeout=10)
    if not output:
        output = _run_command(["last", "-n", "200"], timeout=10)
    if not output:
        return entries

    current_year = datetime.now().year

    for line in output.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("wtmp") or line.startswith("btmp"):
            continue
        if "reboot" in line or "shutdown" in line:
            continue
        if line.startswith("BEGIN"):
            continue

        parts = line.split()
        if len(parts) < 4:
            continue

        user = parts[0]
        tty = parts[1]

        # Try to extract timestamp — format varies by `last` version
        # With -F: user tty host Day Mon DD HH:MM:SS YYYY - Day Mon DD HH:MM:SS YYYY
        timestamp = None
        rest = " ".join(parts[2:])

        # Try full timestamp format first
        ts_match = re.search(
            r"(\w{3}\s+\w{3}\s+\d+\s+[\d:]+\s+\d{4})", rest
        )
        if ts_match:
            try:
                timestamp = datetime.strptime(
                    ts_match.group(1), "%a %b %d %H:%M:%S %Y")
            except ValueError:
                pass

        if not timestamp:
            # Try shorter format
            ts_match = re.search(r"(\w{3}\s+\w{3}\s+\d+\s+[\d:]+)", rest)
            if ts_match:
                try:
                    timestamp = datetime.strptime(
                        f"{current_year} {ts_match.group(1)}", "%Y %a %b %d %H:%M"
                    )
                except ValueError:
                    pass

        login_host = ""
        for part in parts[2:]:
            if re.match(r"[\d.]+|[\w.-]+\.\w+", part) and ":" not in part:
                login_host = part
                break

        extra = {}
        if "still logged in" in line.lower():
            extra["session_status"] = "still logged in"
        elif "gone" in line.lower():
            extra["session_status"] = "gone - no logout"

        if login_host and login_host not in ("in", "still", "logged", "gone"):
            extra["remote_host"] = login_host

        entries.append(
            CommandEntry(
                timestamp=timestamp,
                user=user,
                command=f"login session on {tty}",
                shell="login",
                source="last",
                tty=tty,
                hostname=hostname,
                extra=extra,
            )
        )

    return entries


def _parse_syslog_file(filepath: str, shell_name: str, source_name: str) -> List[CommandEntry]:
    from .log_parsers import read_log_file_lines
    entries = []
    hostname = _get_hostname()
    current_year = datetime.now().year

    # syslog format: Sep  6 10:30:00 hostname process[pid]: message
    syslog_pattern = re.compile(
        r"^(\w{3}\s+\d+\s+[\d:]+)\s+"  # timestamp
        r"(\S+)\s+"                       # hostname
        r"([^:]+):\s+"                  # process (and optional pid)
        r"(.+)$"                          # message
    )

    expanded = os.path.expanduser(os.path.expandvars(filepath))
    lines = read_log_file_lines(expanded)
    if not lines:
        return entries

    for line in lines:
        match = syslog_pattern.match(line.strip())
        if not match:
            continue

        ts_str, h, proc, msg = match.groups()
        timestamp = None
        try:
            timestamp = datetime.strptime(
                f"{current_year} {ts_str}", "%Y %b %d %H:%M:%S")
            if timestamp > datetime.now():
                timestamp = timestamp.replace(year=current_year - 1)
        except ValueError:
            try:
                timestamp = datetime.strptime(
                    f"{current_year} {ts_str}", "%Y %b  %d %H:%M:%S")
            except ValueError:
                pass

        entries.append(
            CommandEntry(
                timestamp=timestamp,
                user="root",
                command=f"{proc}: {msg}",
                shell=shell_name,
                source=source_name,
                hostname=h,
            )
        )

    return entries


def collect_syslog(paths: Optional[List[str]] = None) -> List[CommandEntry]:
    entries = []
    if paths is None:
        from .config import load_log_paths
        configured = [p["path"] for p in load_log_paths() if p.get(
            "type") in ("syslog", "syslog_iso") and p.get("enabled", True)]
        paths = configured if configured else [
            "/var/log/syslog", "/var/log/syslog.1", "/var/log/messages", "/var/log/messages.1"]
    for path in paths:
        entries.extend(_parse_syslog_file(
            path, "syslog", os.path.basename(path)))
    return entries


def collect_kernel_log(paths: Optional[List[str]] = None) -> List[CommandEntry]:
    entries = []
    if paths is None:
        from .config import load_log_paths
        configured = [p["path"] for p in load_log_paths() if p.get(
            "type") == "kernel" and p.get("enabled", True)]
        paths = configured if configured else [
            "/var/log/kern.log", "/var/log/kern.log.1"]
    for path in paths:
        entries.extend(_parse_syslog_file(
            path, "kernel", os.path.basename(path)))
    return entries


def collect_dpkg_log(paths: Optional[List[str]] = None) -> List[CommandEntry]:
    from .log_parsers import read_log_file_lines
    entries = []
    if paths is None:
        from .config import load_log_paths
        configured = [p["path"] for p in load_log_paths() if p.get(
            "type") == "dpkg" and p.get("enabled", True)]
        paths = configured if configured else [
            "/var/log/dpkg.log", "/var/log/dpkg.log.1"]
    hostname = _get_hostname()

    for raw_path in paths:
        filepath = os.path.expanduser(os.path.expandvars(raw_path))
        lines = read_log_file_lines(filepath)
        for line in lines:
            line = line.strip()
            if not line:
                continue

            parts = line.split(" ", 2)
            timestamp = None
            if len(parts) >= 3:
                try:
                    timestamp = datetime.strptime(
                        f"{parts[0]} {parts[1]}", "%Y-%m-%d %H:%M:%S")
                    msg = parts[2]
                except ValueError:
                    msg = line
            else:
                msg = line

            entries.append(
                CommandEntry(
                    timestamp=timestamp,
                    user="root",
                    command=msg,
                    shell="dpkg",
                    source=os.path.basename(filepath),
                    hostname=hostname,
                )
            )

    return entries


def collect_apt_log(paths: Optional[List[str]] = None) -> List[CommandEntry]:
    from .log_parsers import parse_log_file, read_log_file_lines
    entries = []
    if paths is None:
        from .config import load_log_paths
        configured = [p["path"] for p in load_log_paths() if p.get("type") in (
            "apt", "apt_history", "apt_term") and p.get("enabled", True)]
        paths = configured if configured else [
            "/var/log/apt/history.log", "/var/log/apt/term.log"]
    hostname = _get_hostname()

    for raw_path in paths:
        filepath = os.path.expanduser(os.path.expandvars(raw_path))
        if "history" in filepath.lower():
            file_entries = parse_log_file(
                filepath, log_type="apt_history", source_name=os.path.basename(filepath))
            entries.extend(file_entries)
        else:
            lines = read_log_file_lines(filepath)
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                entries.append(
                    CommandEntry(
                        timestamp=None,
                        user="root",
                        command=line,
                        shell="apt",
                        source=os.path.basename(filepath),
                        hostname=hostname,
                    )
                )

    return entries


def collect_cron_log(paths: Optional[List[str]] = None) -> List[CommandEntry]:
    entries = []
    if paths is None:
        from .config import load_log_paths
        configured = [p["path"] for p in load_log_paths() if p.get(
            "type") == "cron" and p.get("enabled", True)]
        paths = configured if configured else [
            "/var/log/cron.log", "/var/log/cron"]
    for path in paths:
        entries.extend(_parse_syslog_file(
            path, "cron", os.path.basename(path)))
    return entries


def collect_power_events() -> List[CommandEntry]:
    """Collect power-on/power-off transitions and reboot records."""
    entries: List[CommandEntry] = []
    hostname = _get_hostname()
    sources = [
        "last -Faw -n 200",
        "journalctl --no-pager -b -n 200 --output=short-iso",
        "/var/log/syslog",
        "/var/log/messages",
        "/var/log/auth.log",
    ]

    for source in sources:
        if source.startswith("last "):
            result = _run_command(["last", "-Faw", "-n", "200"], timeout=10)
            if not result:
                continue
            for line in result.strip().splitlines():
                line = line.strip()
                if not line or line.startswith("wtmp") or line.startswith("btmp"):
                    continue
                if "reboot" not in line.lower() and "shutdown" not in line.lower() and "power" not in line.lower():
                    continue
                try:
                    timestamp = None
                    match = re.search(r"(\w{3}\s+\w{3}\s+\d+\s+[\d:]+\s+\d{4})", line)
                    if match:
                        try:
                            timestamp = datetime.strptime(match.group(1), "%a %b %d %H:%M:%S %Y")
                        except ValueError:
                            pass
                    if not timestamp:
                        match = re.search(r"(\w{3}\s+\w{3}\s+\d+\s+[\d:]+)", line)
                        if match:
                            try:
                                timestamp = datetime.strptime(f"{datetime.now().year} {match.group(1)}", "%Y %a %b %d %H:%M")
                            except ValueError:
                                pass
                    entries.append(CommandEntry(
                        timestamp=timestamp,
                        user="root",
                        command=line,
                        shell="power",
                        source="power",
                        hostname=hostname,
                    ))
                except Exception:
                    continue
        elif source.startswith("journalctl "):
            result = _run_command([
                "journalctl", "--no-pager", "-b", "-n", "200", "--output=short-iso"
            ], timeout=15)
            if not result:
                continue
            for line in result.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                lowered = line.lower()
                if "reboot" not in lowered and "shutdown" not in lowered and "power" not in lowered:
                    continue
                timestamp = None
                try:
                    timestamp = datetime.fromisoformat(line.split()[0])
                except Exception:
                    pass
                entries.append(CommandEntry(
                    timestamp=timestamp,
                    user="root",
                    command=line,
                    shell="power",
                    source="power",
                    hostname=hostname,
                ))
        else:
            expanded = os.path.expanduser(os.path.expandvars(source))
            if not os.path.isfile(expanded) or not os.access(expanded, os.R_OK):
                continue
            with open(expanded, "r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    lowered = line.lower()
                    if "reboot" not in lowered and "shutdown" not in lowered and "power" not in lowered:
                        continue
                    timestamp = None
                    match = re.search(r"^(\w{3}\s+\d+\s+[\d:]+)", line)
                    if match:
                        try:
                            timestamp = datetime.strptime(f"{datetime.now().year} {match.group(1)}", "%Y %b %d %H:%M:%S")
                        except ValueError:
                            pass
                    entries.append(CommandEntry(
                        timestamp=timestamp,
                        user="root",
                        command=line,
                        shell="power",
                        source="power",
                        hostname=hostname,
                    ))

    deduped: List[CommandEntry] = []
    seen = set()
    for entry in entries:
        normalized = " ".join(entry.command.strip().split()).lower()
        key = (normalized, entry.shell.lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)

    return deduped


def collect_session_lifecycle_events() -> List[CommandEntry]:
    """Collect screen lock/unlock, login, and logout events from logind/systemd."""
    entries: List[CommandEntry] = []
    hostname = _get_hostname()
    output = _run_command([
        "journalctl", "--no-pager", "-n", "500", "--output=short-iso",
        "-g", "session.*(logged out|locked|unlocked|login|log in|log out|New session)",
        "--quiet",
    ], timeout=20)

    if not output:
        output = _run_command([
            "journalctl", "--no-pager", "-n", "500", "--output=short-iso",
            "-t", "systemd-logind", "--quiet",
        ], timeout=20)

    if not output:
        return entries

    for line in output.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        lower = line.lower()
        if "session" not in lower and "lock" not in lower and "unlock" not in lower:
            continue

        match = re.match(r"^([\d\-T:+]+)\s+(\S+)\s+(.*)$", line)
        if not match:
            continue

        ts_str, host, message = match.groups()
        timestamp = None
        try:
            timestamp = datetime.fromisoformat(ts_str)
            timestamp = timestamp.astimezone().replace(tzinfo=None)
        except ValueError:
            try:
                timestamp = datetime.strptime(ts_str[:19], "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                timestamp = None

        lower_msg = message.lower()
        if "unlocked" in lower_msg:
            command = "Screen unlock event"
            shell = "screenlock"
        elif "locked" in lower_msg:
            command = "Screen lock event"
            shell = "screenlock"
        elif "logged out" in lower_msg or "log out" in lower_msg:
            command = "User logout event"
            shell = "login"
        elif "new session" in lower_msg or ("session" in lower_msg and "user" in lower_msg):
            command = "User login event"
            shell = "login"
        elif "session" in lower_msg:
            command = message.strip()
            shell = "login"
        else:
            command = message.strip()
            shell = "screenlock"

        entries.append(CommandEntry(
            timestamp=timestamp,
            user="root",
            command=command,
            shell=shell,
            source="logind",
            hostname=host or hostname,
            extra={"raw_message": message.strip()},
        ))

    return entries


def collect_boot_log(paths: Optional[List[str]] = None) -> List[CommandEntry]:
    from .log_parsers import read_log_file_lines
    entries = []
    if paths is None:
        from .config import load_log_paths
        configured = [p["path"] for p in load_log_paths() if p.get(
            "type") == "boot" and p.get("enabled", True)]
        paths = configured if configured else ["/var/log/boot.log"]
    hostname = _get_hostname()
    for raw_path in paths:
        filepath = os.path.expanduser(os.path.expandvars(raw_path))
        lines = read_log_file_lines(filepath)
        for line in lines:
            line = line.strip()
            if not line:
                continue
            entries.append(
                CommandEntry(
                    timestamp=None,
                    user="root",
                    command=line,
                    shell="boot",
                    source=os.path.basename(filepath),
                    hostname=hostname,
                )
            )
    return entries


def collect_daemon_log(paths: Optional[List[str]] = None) -> List[CommandEntry]:
    entries = []
    if paths is None:
        from .config import load_log_paths
        configured = [p["path"] for p in load_log_paths() if p.get(
            "type") == "daemon" and p.get("enabled", True)]
        paths = configured if configured else [
            "/var/log/daemon.log", "/var/log/daemon.log.1"]
    for path in paths:
        entries.extend(_parse_syslog_file(
            path, "daemon", os.path.basename(path)))
    return entries


def collect_xorg_log(paths: Optional[List[str]] = None) -> List[CommandEntry]:
    from .log_parsers import read_log_file_lines
    entries = []
    if paths is None:
        from .config import load_log_paths
        configured = [p["path"] for p in load_log_paths() if p.get(
            "type") == "xorg" and p.get("enabled", True)]
        paths = configured if configured else [
            "/var/log/Xorg.0.log", "/var/log/Xorg.1.log"]
    hostname = _get_hostname()
    for raw_path in paths:
        filepath = os.path.expanduser(os.path.expandvars(raw_path))
        lines = read_log_file_lines(filepath)
        for line in lines:
            line = line.strip()
            if not line:
                continue
            entries.append(
                CommandEntry(
                    timestamp=None,
                    user="root",
                    command=line,
                    shell="xorg",
                    source=os.path.basename(filepath),
                    hostname=hostname,
                )
            )
    return entries


def collect_custom_logs(custom_paths: Optional[List[Dict[str, Any]]] = None) -> List[CommandEntry]:
    """Collect commands and events from custom or user-added log files."""
    from .log_parsers import parse_log_file
    from .config import load_log_paths

    entries = []
    if custom_paths is None:
        configured = load_log_paths()
        standard_types = {
            "syslog", "syslog_iso", "auth", "kernel", "dpkg",
            "apt", "apt_history", "apt_term", "cron", "boot",
            "daemon", "xorg", "shell_history", "fish_history"
        }
        custom_paths = [
            p for p in configured
            if p.get("enabled", True) and p.get("type", "auto") not in standard_types
        ]

    for item in custom_paths:
        if isinstance(item, dict) and not item.get("enabled", True):
            continue
        path = item.get("path") if isinstance(item, dict) else str(item)
        log_type = item.get("type", "auto") if isinstance(
            item, dict) else "auto"
        source_name = item.get("name", "") if isinstance(item, dict) else ""
        if not path:
            continue
        try:
            file_entries = parse_log_file(
                path, log_type=log_type, source_name=source_name)
            entries.extend(file_entries)
            logger.info(
                f"Custom log collector: {len(file_entries)} entries from {path}")
        except Exception as e:
            logger.warning(f"Failed parsing custom log {path}: {e}")

    return entries


def collect_dmesg() -> List[CommandEntry]:
    entries = []
    hostname = _get_hostname()
    output = _run_command(["dmesg", "-T"], timeout=10)
    if not output:
        return entries

    for line in output.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        timestamp = None
        cmd = line

        # [Sat Sep  6 09:40:00 2026] msg
        if line.startswith("[") and "]" in line:
            ts_str, msg = line[1:].split("]", 1)
            msg = msg.strip()
            try:
                timestamp = datetime.strptime(
                    ts_str.strip(), "%a %b %d %H:%M:%S %Y")
                cmd = msg
            except ValueError:
                try:
                    timestamp = datetime.strptime(
                        ts_str.strip(), "%a %b  %d %H:%M:%S %Y")
                    cmd = msg
                except ValueError:
                    pass

        entries.append(
            CommandEntry(
                timestamp=timestamp,
                user="root",
                command=cmd,
                shell="dmesg",
                source="dmesg",
                hostname=hostname,
            )
        )
    return entries


def collect_failed_logins() -> List[CommandEntry]:
    entries = []
    hostname = _get_hostname()
    output = _run_command(["lastb", "-Faw", "-n", "200"], timeout=10)
    if not output:
        output = _run_command(["lastb", "-n", "200"], timeout=10)
    if not output:
        return entries

    current_year = datetime.now().year

    for line in output.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("btmp"):
            continue
        if "reboot" in line or "shutdown" in line:
            continue
        if line.startswith("BEGIN"):
            continue

        parts = line.split()
        if len(parts) < 4:
            continue

        user = parts[0]
        tty = parts[1]

        timestamp = None
        rest = " ".join(parts[2:])

        ts_match = re.search(
            r"(\w{3}\s+\w{3}\s+\d+\s+[\d:]+\s+\d{4})", rest
        )
        if ts_match:
            try:
                timestamp = datetime.strptime(
                    ts_match.group(1), "%a %b %d %H:%M:%S %Y")
            except ValueError:
                pass

        if not timestamp:
            ts_match = re.search(r"(\w{3}\s+\w{3}\s+\d+\s+[\d:]+)", rest)
            if ts_match:
                try:
                    timestamp = datetime.strptime(
                        f"{current_year} {ts_match.group(1)}", "%Y %a %b %d %H:%M"
                    )
                except ValueError:
                    pass

        entries.append(
            CommandEntry(
                timestamp=timestamp,
                user=user,
                command=f"failed login on {tty}",
                shell="login",
                source="lastb",
                tty=tty,
                hostname=hostname,
            )
        )
    return entries


def collect_systemd_services() -> List[CommandEntry]:
    entries = []
    hostname = _get_hostname()
    output = _run_command([
        "journalctl", "--no-pager", "-n", "500", "--output=short-iso", "-p", "err..emerg"
    ], timeout=20)

    if not output:
        return entries

    journal_pattern = re.compile(
        r"^([\d\-T:+]+)\s+"
        r"(\S+)\s+"
        r"([^:]+):\s*"
        r"(.+)$"
    )

    for line in output.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        match = journal_pattern.match(line)
        if not match:
            continue

        ts_str = match.group(1)
        host = match.group(2)
        proc = match.group(3)
        msg = match.group(4)

        timestamp = None
        try:
            timestamp = datetime.fromisoformat(ts_str)
            timestamp = timestamp.astimezone().replace(
                tzinfo=None)  # normalize to naive local time
        except ValueError:
            try:
                timestamp = datetime.strptime(ts_str[:19], "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                pass

        entries.append(
            CommandEntry(
                timestamp=timestamp,
                user="root",
                command=f"{proc}: {msg}",
                shell="systemd",
                source="journal-errors",
                hostname=hostname,
            )
        )
    return entries


def collect_all(
    include_history: bool = True,
    include_processes: bool = True,
    include_auth: bool = True,
    include_journal: bool = True,
    include_accounting: bool = True,
    include_logins: bool = True,
    include_session_lifecycle: bool = True,
    include_syslog: bool = True,
    include_kernel: bool = True,
    include_dpkg: bool = True,
    include_apt: bool = True,
    include_cron: bool = True,
    include_boot: bool = True,
    include_power: bool = True,
    include_daemon: bool = True,
    include_xorg: bool = True,
    include_dmesg: bool = True,
    include_failed_logins: bool = True,
    include_systemd_services: bool = True,
    include_custom: bool = True,
    log_paths: Optional[List[Dict[str, Any]]] = None,
    progress_callback=None,
) -> List[CommandEntry]:
    """Run all enabled collectors and return a combined list of CommandEntry objects.

    Args:
        include_*: Toggle individual collectors on/off.
        log_paths: Optional list of configured log path dictionaries from config.
        progress_callback: Optional callable(message: str, percent: int)
                          to report progress during collection.

    Returns:
        Combined and sorted list of CommandEntry objects.
    """
    from .config import load_log_paths

    all_entries = []

    if log_paths is None:
        log_paths = load_log_paths()

    enabled_paths = [p for p in log_paths if p.get("enabled", True)]

    def get_paths_for(types: List[str]) -> List[str]:
        return [p["path"] for p in enabled_paths if p.get("type") in types]

    syslog_paths = get_paths_for(["syslog", "syslog_iso"])
    auth_paths = get_paths_for(["auth"])
    kernel_paths = get_paths_for(["kernel"])
    dpkg_paths = get_paths_for(["dpkg"])
    apt_paths = get_paths_for(["apt", "apt_history", "apt_term"])
    cron_paths = get_paths_for(["cron"])
    boot_paths = get_paths_for(["boot"])
    daemon_paths = get_paths_for(["daemon"])
    xorg_paths = get_paths_for(["xorg"])
    history_paths = get_paths_for(["shell_history", "fish_history"])

    standard_handled = {
        "syslog", "syslog_iso", "auth", "kernel", "dpkg",
        "apt", "apt_history", "apt_term", "cron", "boot",
        "daemon", "xorg", "shell_history", "fish_history"
    }
    custom_items = [p for p in enabled_paths if p.get(
        "type", "auto") not in standard_handled]

    collectors = []
    if include_history:
        collectors.append(
            ("Shell History", lambda: collect_shell_history(paths=history_paths)))
    if include_processes:
        collectors.append(("Running Processes", collect_running_processes))
    if include_auth:
        collectors.append(
            ("Auth/Sudo Logs", lambda: collect_auth_log(paths=auth_paths)))
    if include_journal:
        collectors.append(("Systemd Journal", collect_journal))
    if include_accounting:
        collectors.append(("Process Accounting", collect_accounting))
    if include_logins:
        collectors.append(("Login Sessions", collect_last_logins))
    if include_session_lifecycle:
        collectors.append(("Session Lifecycle", collect_session_lifecycle_events))
    if include_syslog:
        collectors.append(
            ("Syslog", lambda: collect_syslog(paths=syslog_paths)))
    if include_kernel:
        collectors.append(
            ("Kernel Log", lambda: collect_kernel_log(paths=kernel_paths)))
    if include_dpkg:
        collectors.append(
            ("Dpkg Log", lambda: collect_dpkg_log(paths=dpkg_paths)))
    if include_apt:
        collectors.append(
            ("Apt Log", lambda: collect_apt_log(paths=apt_paths)))
    if include_cron:
        collectors.append(
            ("Cron Log", lambda: collect_cron_log(paths=cron_paths)))
    if include_boot:
        collectors.append(
            ("Boot Log", lambda: collect_boot_log(paths=boot_paths)))
    if include_power:
        collectors.append(
            ("Power Events", collect_power_events))
    if include_daemon:
        collectors.append(
            ("Daemon Log", lambda: collect_daemon_log(paths=daemon_paths)))
    if include_xorg:
        collectors.append(
            ("Xorg Log", lambda: collect_xorg_log(paths=xorg_paths)))
    if include_dmesg:
        collectors.append(("Dmesg", collect_dmesg))
    if include_failed_logins:
        collectors.append(("Failed Logins", collect_failed_logins))
    if include_systemd_services:
        collectors.append(("Systemd Services", collect_systemd_services))
    if include_custom and custom_items:
        collectors.append(
            ("Custom Log Files", lambda: collect_custom_logs(custom_paths=custom_items)))

    total = len(collectors)
    for idx, (name, collector_fn) in enumerate(collectors):
        if progress_callback:
            pct = int((idx / total) * 100)
            progress_callback(f"Collecting: {name}...", pct)

        try:
            result = collector_fn()
            all_entries.extend(result)
            logger.info(f"{name}: collected {len(result)} entries")
        except Exception as e:
            logger.warning(f"{name} collector failed: {e}")

    if progress_callback:
        progress_callback("Sorting results...", 95)

    all_entries.sort(
        key=lambda e: (e.timestamp is not None, e.timestamp or datetime.min),
        reverse=True,
    )

    if progress_callback:
        progress_callback(
            f"Done — {len(all_entries)} commands collected.", 100)

    return all_entries
