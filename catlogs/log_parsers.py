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

"""The Universal log file parsers for CatLogs hhhh.

Parses all known and common log file formats into CommandEntry objects:
- Syslog (RFC 3164 BSD syslog, RFC 5424 IETF syslog, ISO 8601 timestamps)
- Auth / Sudo / Security logs (sudo, sshd, su, pam)
- Web Server Access logs (Apache, Nginx, Caddy in CLF / Combined format)
- Web Server Error logs (Nginx, Apache)
- JSON Lines / NDJSON structured logs (Docker, Kubernetes, Python/Node/Go apps)
- Standard Application logs (ISO datetime + log level + message)
- Package Manager logs (DPKG, APT history, APT term, Alternatives, Pacman, Yum/DNF)
- Kernel & Boot logs (dmesg, kern.log, boot.log)
- Cron logs (CRON daemon)
- Daemon & Service logs
- Xorg / Display server logs
- Linux Audit logs (auditd syscall / execve)
- Fail2ban security logs
- Database logs (PostgreSQL, MySQL, MariaDB, Redis)
- Shell history files (Bash, Zsh, Fish, generic sh/ksh)
- Generic text logs (fallback with smart timestamp and level extraction)
- Automatic format detection for arbitrary added files
- Transparent support for .gz compressed logs
"""

import os
import re
import json
import gzip
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .models import CommandEntry
from .read_errors import log_read_error

logger = logging.getLogger(__name__)

# Known log type identifiers and display names
LOG_FORMAT_CHOICES = [
    ("auto", "Auto-detect (Recommended)"),
    ("syslog", "Syslog (RFC 3164 / BSD)"),
    ("syslog_iso", "Syslog ISO (RFC 5424 / Systemd)"),
    ("auth", "Auth / Sudo / SSH Log"),
    ("web_access", "Web Server Access (Nginx / Apache / CLF)"),
    ("web_error", "Web Server Error (Nginx / Apache)"),
    ("json", "JSON Lines (NDJSON / Structured)"),
    ("app", "Application Log (ISO / Timestamped)"),
    ("shell_history", "Shell History (Bash / Zsh / Sh)"),
    ("fish_history", "Fish Shell History"),
    ("dpkg", "DPKG Package Log"),
    ("apt_history", "APT History Log"),
    ("apt_term", "APT Terminal Log"),
    ("alternatives", "Update-Alternatives Log"),
    ("kernel", "Kernel Log (kern.log / dmesg)"),
    ("cron", "Cron Service Log"),
    ("boot", "System Boot Log"),
    ("daemon", "Daemon Service Log"),
    ("xorg", "Xorg Display Server Log"),
    ("audit", "Auditd Log (Linux Audit)"),
    ("fail2ban", "Fail2ban Log"),
    ("database", "Database Log (PostgreSQL / MySQL / Redis)"),
    ("generic", "Generic Text Log"),
]

# Month name lookup for fast syslog date parsing
_MONTH_NAMES = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
}


def read_log_file_lines(filepath: str, max_lines: int = 50000) -> List[str]:
    """Read lines from a log file safely.

    Handles ~ expansion, environment variables, .gz decompression,
    permission errors, and enforces a line limit for performance.
    """
    expanded = os.path.expanduser(os.path.expandvars(filepath))

    if not os.path.exists(expanded):
        return []

    if not os.path.isfile(expanded):
        return []

    try:
        is_gz = expanded.endswith(".gz")
        lines = []

        if is_gz:
            with gzip.open(expanded, "rt", encoding="utf-8", errors="replace") as f:
                for idx, line in enumerate(f):
                    lines.append(line.rstrip("\r\n"))
                    if idx >= max_lines - 1:
                        break
        else:
            file_size = os.path.getsize(expanded)
            if file_size > 15 * 1024 * 1024:
                # Seek near the end to get the most recent lines
                with open(expanded, "r", encoding="utf-8", errors="replace") as f:
                    chunk_size = min(file_size, 10 * 1024 * 1024)
                    f.seek(file_size - chunk_size)
                    f.readline()  # discard partial line
                    for line in f:
                        lines.append(line.rstrip("\r\n"))
                if len(lines) > max_lines:
                    lines = lines[-max_lines:]
            else:
                with open(expanded, "r", encoding="utf-8", errors="replace") as f:
                    for idx, line in enumerate(f):
                        lines.append(line.rstrip("\r\n"))
                        if idx >= max_lines - 1:
                            break

        return lines
    except (PermissionError, OSError) as e:
        logger.debug(f"Cannot read log file {filepath}: {e}")
        log_read_error(filepath, str(e), "log_parsers.read_log_file_lines")
        return []


def parse_any_timestamp(text: str, default_year: Optional[int] = None) -> Optional[datetime]:
    """Try to parse a timestamp from various date string representations."""
    if not text:
        return None

    text = text.strip()
    if default_year is None:
        default_year = datetime.now().year

    iso_match = re.match(
        r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})[T ](\d{1,2}):(\d{2}):(\d{2})(?:[,\.](\d+))?(?:\s*(?:Z|([+-]\d{2}):?(\d{2})?))?", text)
    if iso_match:
        try:
            year, month, day, hour, minute, second = map(
                int, iso_match.group(1, 2, 3, 4, 5, 6))
            microsecond = 0
            if iso_match.group(7):
                ms_str = iso_match.group(7)[:6].ljust(6, '0')
                microsecond = int(ms_str)
            return datetime(year, month, day, hour, minute, second, microsecond)
        except (ValueError, OverflowError):
            pass

    # 2. Syslog BSD: Oct 11 22:14:15 or Oct  1 22:14:15
    syslog_match = re.match(
        r"^([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{2}):(\d{2}):(\d{2})", text)
    if syslog_match:
        m_str, d_str, h_str, min_str, s_str = syslog_match.groups()
        month = _MONTH_NAMES.get(m_str)
        if month:
            try:
                dt = datetime(default_year, month, int(d_str),
                              int(h_str), int(min_str), int(s_str))
                if dt > datetime.now():
                    dt = dt.replace(year=default_year - 1)
                return dt
            except (ValueError, OverflowError):
                pass

    # 3. Web server CLF / Combined: 12/Sep/2026:15:04:05
    clf_match = re.match(
        r"^(\d{1,2})/([A-Z][a-z]{2})/(\d{4}):(\d{2}):(\d{2}):(\d{2})", text)
    if clf_match:
        d_str, m_str, y_str, h_str, min_str, s_str = clf_match.groups()
        month = _MONTH_NAMES.get(m_str)
        if month:
            try:
                return datetime(int(y_str), month, int(d_str), int(h_str), int(min_str), int(s_str))
            except (ValueError, OverflowError):
                pass

    # 4. Unix epoch timestamp: 1726153445 or @1726153445 or 1726153445.123
    epoch_match = re.match(r"^@?(\d{10})(?:\.(\d+))?$", text)
    if epoch_match:
        try:
            ts = float(epoch_match.group(1))
            if 946684800 <= ts <= 4102444800:
                return datetime.fromtimestamp(ts)
        except (ValueError, OSError, OverflowError):
            pass

    # 5. Dmesg human: Sat Sep 12 15:04:05 2026
    dmesg_match = re.match(
        r"^[A-Z][a-z]{2}\s+([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{2}):(\d{2}):(\d{2})\s+(\d{4})", text)
    if dmesg_match:
        m_str, d_str, h_str, min_str, s_str, y_str = dmesg_match.groups()
        month = _MONTH_NAMES.get(m_str)
        if month:
            try:
                return datetime(int(y_str), month, int(d_str), int(h_str), int(min_str), int(s_str))
            except (ValueError, OverflowError):
                pass

    return None


# ---------------------------------------------------------------------------
# Format Auto-Detection
# ---------------------------------------------------------------------------

def detect_log_type(filepath: str, sample_lines: Optional[List[str]] = None) -> str:
    """Analyze the file content and name to determine the best parser type."""
    filepath_lower = filepath.lower()
    filename = os.path.basename(filepath_lower)

    # Direct filename and directory matching
    if "audit" in filename or "/audit/" in filepath_lower:
        return "audit"
    if "fail2ban" in filename:
        return "fail2ban"
    if "dpkg" in filename:
        return "dpkg"
    if "apt" in filename and "history" in filename:
        return "apt_history"
    if "apt" in filename and "term" in filename:
        return "apt_term"
    if "alternatives" in filename:
        return "alternatives"
    if "cron" in filename:
        return "cron"
    if "boot" in filename:
        return "boot"
    if "xorg" in filename:
        return "xorg"
    if "kern" in filename or "dmesg" in filename:
        return "kernel"
    if "daemon" in filename:
        return "daemon"
    if "error" in filename and any(k in filepath_lower for k in ("nginx", "apache", "httpd", "caddy", "lighttpd", "web")):
        return "web_error"
    if "access" in filename or any(k in filename for k in ("nginx", "apache", "httpd", "caddy")):
        if "error" in filename:
            return "web_error"
        return "web_access"
    if "auth" in filename or "secure" in filename:
        return "auth"
    if "fish_history" in filename:
        return "fish_history"
    if "bash_history" in filename or "zsh_history" in filename or "histfile" in filename or "sh_history" in filename:
        return "shell_history"
    if filename.endswith(".json") or filename.endswith(".jsonl") or filename.endswith(".ndjson"):
        return "json"

    # Inspect sample lines
    if sample_lines is None:
        sample_lines = read_log_file_lines(filepath, max_lines=30)

    if not sample_lines:
        return "generic"

    json_count = 0
    web_access_count = 0
    web_error_count = 0
    syslog_bsd_count = 0
    syslog_iso_count = 0
    app_log_count = 0
    audit_count = 0
    sudo_count = 0

    web_access_pattern = re.compile(
        r'^\S+\s+\S+\s+\S+\s+\[[^\]]+\]\s+"[A-Z]+\s+[^"]*"\s+\d{3}')
    web_error_pattern = re.compile(
        r'^\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}\s+\[\w+\]\s+\d+#\d+:')
    syslog_bsd_pattern = re.compile(
        r'^[A-Z][a-z]{2}\s+\d+\s+\d{2}:\d{2}:\d{2}\s+\S+\s+[^:]+:\s+')
    syslog_iso_pattern = re.compile(
        r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})\s+\S+\s+')
    app_log_pattern = re.compile(
        r'^[\[\(]?\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}:\d{2}.*?\b(INFO|DEBUG|WARN|WARNING|ERROR|FATAL|CRITICAL|TRACE|NOTICE)\b', re.IGNORECASE)
    audit_pattern = re.compile(r'^type=\w+\s+msg=audit\(')

    for line in sample_lines[:25]:
        line = line.strip()
        if not line:
            continue

        if line.startswith("{") and line.endswith("}"):
            try:
                json.loads(line)
                json_count += 1
                continue
            except Exception:
                pass

        if web_access_pattern.match(line):
            web_access_count += 1
        elif web_error_pattern.match(line):
            web_error_count += 1
        elif audit_pattern.match(line):
            audit_count += 1
        elif "sudo:" in line and ("COMMAND=" in line or "USER=" in line):
            sudo_count += 1
        elif syslog_iso_pattern.match(line):
            syslog_iso_count += 1
        elif syslog_bsd_pattern.match(line):
            syslog_bsd_count += 1
        elif app_log_pattern.match(line):
            app_log_count += 1

    total_tested = max(1, len([l for l in sample_lines[:25] if l.strip()]))
    threshold = 1 if total_tested <= 3 else 2

    if json_count >= threshold:
        return "json"
    if web_access_count >= threshold:
        return "web_access"
    if web_error_count >= threshold:
        return "web_error"
    if audit_count >= threshold:
        return "audit"
    if sudo_count >= threshold:
        return "auth"
    if syslog_iso_count >= threshold:
        return "syslog_iso"
    if syslog_bsd_count >= threshold:
        return "syslog"
    if app_log_count >= threshold:
        return "app"

    return "generic"


# ---------------------------------------------------------------------------
# Individual Parsers
# ---------------------------------------------------------------------------

def parse_syslog_lines(lines: List[str], source: str, filepath: str) -> List[CommandEntry]:
    """Parse standard BSD Syslog RFC 3164 lines."""
    entries = []
    current_year = datetime.now().year

    pattern = re.compile(
        r"^([A-Z][a-z]{2}\s+\d+\s+\d{2}:\d{2}:\d{2})\s+"  # Timestamp
        r"(\S+)\s+"                                        # Hostname
        r"([^:\[\s]+)(?:\[(\d+)\])?:\s*"                  # Process [PID]:
        r"(.*)$"                                           # Message
    )

    for line in lines:
        match = pattern.match(line)
        if not match:
            continue

        ts_str, host, proc, pid_str, msg = match.groups()
        timestamp = parse_any_timestamp(ts_str, default_year=current_year)
        pid = int(pid_str) if pid_str and pid_str.isdigit() else None

        user = "root"
        if proc == "sudo" and ":" in msg:
            user_part = msg.split(":")[0].strip()
            if user_part:
                user = user_part

        entries.append(
            CommandEntry(
                timestamp=timestamp,
                user=user,
                command=f"{proc}: {msg}",
                shell="syslog",
                source=source,
                pid=pid,
                hostname=host,
                extra={"file": filepath, "process": proc},
            )
        )

    return entries


def parse_syslog_iso_lines(lines: List[str], source: str, filepath: str) -> List[CommandEntry]:
    """Parse modern RFC 5424 / ISO 8601 Syslog lines."""
    entries = []

    pattern = re.compile(
        r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s+"
        r"(\S+)\s+"
        r"([^:\[\s]+)(?:\[(\d+)\])?:\s*"
        r"(.*)$"
    )

    for line in lines:
        match = pattern.match(line)
        if not match:
            continue

        ts_str, host, proc, pid_str, msg = match.groups()
        timestamp = parse_any_timestamp(ts_str)
        pid = int(pid_str) if pid_str and pid_str.isdigit() else None

        entries.append(
            CommandEntry(
                timestamp=timestamp,
                user="root",
                command=f"{proc}: {msg}",
                shell="syslog",
                source=source,
                pid=pid,
                hostname=host,
                extra={"file": filepath, "process": proc},
            )
        )

    return entries


def parse_auth_lines(lines: List[str], source: str, filepath: str) -> List[CommandEntry]:
    """Parse auth / sudo / sshd log lines."""
    entries = []
    current_year = datetime.now().year

    # Sudo pattern
    sudo_pattern = re.compile(
        r"^([A-Z][a-z]{2}\s+\d+\s+[\d:]+|\d{4}-\d{2}-\d{2}T[\d:.]+[\w+-:]*)\s+"
        r"(\S+)\s+"
        r"sudo(?:\[\d+\])?:\s+"
        r"(\S+)\s+:\s+"
        r"(.+)$"
    )
    cmd_pattern = re.compile(r"COMMAND=(.+)$")
    tty_pattern = re.compile(r"TTY=(\S+)")
    pwd_pattern = re.compile(r"PWD=(\S+)")
    runas_pattern = re.compile(r"USER=(\S+)")

    # SSH pattern
    ssh_pattern = re.compile(
        r"^([A-Z][a-z]{2}\s+\d+\s+[\d:]+|\d{4}-\d{2}-\d{2}T[\d:.]+[\w+-:]*)\s+"
        r"(\S+)\s+"
        r"sshd(?:\[(\d+)\])?:\s+"
        r"(Accepted|Failed|Invalid)\s+.*?(?:for\s+(\S+)|user\s+(\S+))?\s+from\s+(\S+)"
    )

    # General syslog fallback for auth
    general_pattern = re.compile(
        r"^([A-Z][a-z]{2}\s+\d+\s+[\d:]+|\d{4}-\d{2}-\d{2}T[\d:.]+[\w+-:]*)\s+"
        r"(\S+)\s+"
        r"([^:\[\s]+)(?:\[(\d+)\])?:\s*"
        r"(.*)$"
    )

    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue

        # Check sudo match first
        sudo_match = sudo_pattern.match(line_str)
        if sudo_match:
            ts_str, host, user, rest = sudo_match.groups()
            timestamp = parse_any_timestamp(ts_str, default_year=current_year)

            cmd_m = cmd_pattern.search(rest)
            command = f"sudo {cmd_m.group(1).strip()}" if cmd_m else f"sudo {rest}"

            tty = (tty_pattern.search(rest) or [None, None])[1]
            pwd = (pwd_pattern.search(rest) or [None, None])[1]
            runas = (runas_pattern.search(rest) or [None, None])[1]

            extra = {"file": filepath}
            if runas:
                extra["run_as_user"] = runas

            entries.append(
                CommandEntry(
                    timestamp=timestamp,
                    user=user,
                    command=command,
                    shell="sudo",
                    source=source,
                    tty=tty,
                    working_dir=pwd,
                    hostname=host,
                    extra=extra,
                )
            )
            continue

        # Check SSH match
        ssh_match = ssh_pattern.match(line_str)
        if ssh_match:
            ts_str, host, pid_str, action, u1, u2, ip = ssh_match.groups()
            timestamp = parse_any_timestamp(ts_str, default_year=current_year)
            user = u1 or u2 or "unknown"
            pid = int(pid_str) if pid_str and pid_str.isdigit() else None

            entries.append(
                CommandEntry(
                    timestamp=timestamp,
                    user=user,
                    command=f"ssh [{action}] from {ip}",
                    shell="sshd",
                    source=source,
                    pid=pid,
                    hostname=host,
                    status=action,
                    extra={"file": filepath, "client_ip": ip},
                )
            )
            continue

        # General auth match (su, pam, systemd-logind, etc.)
        gen_match = general_pattern.match(line_str)
        if gen_match:
            ts_str, host, proc, pid_str, msg = gen_match.groups()
            timestamp = parse_any_timestamp(ts_str, default_year=current_year)
            pid = int(pid_str) if pid_str and pid_str.isdigit() else None

            entries.append(
                CommandEntry(
                    timestamp=timestamp,
                    user="root",
                    command=f"{proc}: {msg}",
                    shell=proc,
                    source=source,
                    pid=pid,
                    hostname=host,
                    extra={"file": filepath, "process": proc},
                )
            )

    return entries


def parse_web_access_lines(lines: List[str], source: str, filepath: str) -> List[CommandEntry]:
    """Parse Apache / Nginx / Caddy HTTP access logs in Combined or Common Log Format."""
    entries = []

    pattern = re.compile(
        r"^(\S+)\s+"                         # Client IP
        r"\S+\s+"                           # Ident
        r"(\S+)\s+"                         # Auth user
        r"\[([^\]]+)\]\s+"                  # [Date/Time]
        r'"([^"]*)"\s+'                     # "Request"
        r"(\d{3}|-)\s+"                     # Status code
        r"(\S+)"                            # Bytes sent
        r'(?:\s+"([^"]*)"\s+"([^"]*)")?'    # Optional "Referer" "User-Agent"
    )

    for line in lines:
        match = pattern.match(line.strip())
        if not match:
            continue

        ip, user_raw, dt_str, req, status_code, bytes_sent, referer, ua = match.groups()
        timestamp = parse_any_timestamp(dt_str)
        user = user_raw if user_raw != "-" else ip
        exit_code = int(
            status_code) if status_code and status_code.isdigit() else None

        extra = {
            "file": filepath,
            "client_ip": ip,
            "bytes_sent": bytes_sent,
        }
        if referer and referer != "-":
            extra["referer"] = referer
        if ua and ua != "-":
            extra["user_agent"] = ua

        shell = "nginx" if "nginx" in filepath.lower() else (
            "apache" if "apache" in filepath.lower() else "web")

        entries.append(
            CommandEntry(
                timestamp=timestamp,
                user=user,
                command=req or "HTTP Request",
                shell=shell,
                source=source,
                exit_code=exit_code,
                status=str(exit_code) if exit_code else None,
                extra=extra,
            )
        )

    return entries


def parse_web_error_lines(lines: List[str], source: str, filepath: str) -> List[CommandEntry]:
    """Parse Nginx and Apache HTTP error logs."""
    entries = []

    nginx_pattern = re.compile(
        r"^(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})\s+"
        r"\[(\w+)\]\s+"
        r"(\d+)(?:#\d+)?:\s*"
        r"(.*)$"
    )

    apache_pattern = re.compile(
        r"^\[([^\]]+)\]\s+"
        r"\[([^\]]+)\]\s+"
        r"(?:\[pid\s+(\d+)\]\s+)?"
        r"(.*)$"
    )

    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue

        n_match = nginx_pattern.match(line_str)
        if n_match:
            ts_str, level, pid_str, msg = n_match.groups()
            timestamp = parse_any_timestamp(ts_str)
            pid = int(pid_str) if pid_str.isdigit() else None

            entries.append(
                CommandEntry(
                    timestamp=timestamp,
                    user="www-data",
                    command=f"[{level}] {msg}",
                    shell="nginx",
                    source=source,
                    pid=pid,
                    status=level.upper(),
                    extra={"file": filepath, "level": level},
                )
            )
            continue

        a_match = apache_pattern.match(line_str)
        if a_match:
            ts_str, mod_level, pid_str, msg = a_match.groups()
            timestamp = parse_any_timestamp(ts_str)
            pid = int(pid_str) if pid_str and pid_str.isdigit() else None

            entries.append(
                CommandEntry(
                    timestamp=timestamp,
                    user="www-data",
                    command=f"[{mod_level}] {msg}",
                    shell="apache",
                    source=source,
                    pid=pid,
                    status=mod_level,
                    extra={"file": filepath, "module": mod_level},
                )
            )

    return entries


def parse_json_lines(lines: List[str], source: str, filepath: str) -> List[CommandEntry]:
    """Parse JSON lines / NDJSON structured logs."""
    entries = []

    ts_keys = ["timestamp", "time", "@timestamp", "ts",
               "datetime", "date", "created_at", "time_local"]
    msg_keys = ["message", "msg", "command", "cmd", "log",
                "event", "action", "request", "text", "description"]
    user_keys = ["user", "username", "actor", "author",
                 "client_ip", "ip", "caller", "identity"]
    level_keys = ["level", "severity", "status",
                  "status_code", "log_level", "type"]
    pid_keys = ["pid", "process_id"]
    service_keys = ["service", "app", "logger",
                    "component", "name", "module", "shell"]

    for line in lines:
        line_str = line.strip()
        if not line_str or not line_str.startswith("{"):
            continue

        try:
            data = json.loads(line_str)
            if not isinstance(data, dict):
                continue
        except Exception:
            continue

        timestamp = None
        for k in ts_keys:
            if k in data:
                val = data[k]
                if isinstance(val, (int, float)):
                    if val > 1e12:
                        val = val / 1000.0
                    try:
                        timestamp = datetime.fromtimestamp(val)
                        break
                    except Exception:
                        pass
                elif isinstance(val, str):
                    timestamp = parse_any_timestamp(val)
                    if timestamp:
                        break

        command = None
        for k in msg_keys:
            if k in data and data[k]:
                command = str(data[k])
                break
        if not command:
            items = [f"{k}={v}" for k, v in list(
                data.items())[:5] if k not in ts_keys]
            command = " ".join(items) if items else line_str[:120]

        user = "unknown"
        for k in user_keys:
            if k in data and data[k]:
                user = str(data[k])
                break

        status = None
        for k in level_keys:
            if k in data and data[k]:
                status = str(data[k])
                break

        pid = None
        for k in pid_keys:
            if k in data:
                try:
                    pid = int(data[k])
                    break
                except (ValueError, TypeError):
                    pass

        shell = "json"
        for k in service_keys:
            if k in data and data[k]:
                shell = str(data[k])
                break

        extra = {"file": filepath}
        for k, v in data.items():
            if k not in (ts_keys + msg_keys + user_keys + level_keys + pid_keys + service_keys):
                extra[k] = str(v)[:200]

        entries.append(
            CommandEntry(
                timestamp=timestamp,
                user=user,
                command=command,
                shell=shell,
                source=source,
                pid=pid,
                status=status,
                extra=extra,
            )
        )

    return entries


def parse_app_lines(lines: List[str], source: str, filepath: str) -> List[CommandEntry]:
    """Parse standard timestamped application logs (e.g. Python, Java, Go, Spring)."""
    entries = []

    pattern = re.compile(
        r"^[\[\(]?(\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[,\.]\d+)?)[\]\)]?\s+"
        r"(?:"
        r"\[?(DEBUG|INFO|WARN|WARNING|ERROR|FATAL|CRITICAL|TRACE|NOTICE)\]?[:\s-]+"
        r"(?:\[([^\]]+)\]\s*|([a-zA-Z0-9_.-]+)(?::\s*|\s+-\s+))?"
        r"|"
        r"\[([^\]]+)\]\s*"
        r"\[?(DEBUG|INFO|WARN|WARNING|ERROR|FATAL|CRITICAL|TRACE|NOTICE)\]?[:\s-]+"
        r"(?:\[([^\]]+)\]\s*|([a-zA-Z0-9_.-]+)(?::\s*|\s+-\s+))?"
        r")?"
        r"(.*)$",
        re.IGNORECASE,
    )

    stem = Path(filepath).stem.replace(".log", "")

    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue

        match = pattern.match(line_str)
        if not match:
            continue

        ts_str, lvl1, c1, c2, c3, lvl2, c4, c5, msg = match.groups()
        timestamp = parse_any_timestamp(ts_str)

        log_level = (lvl1 or lvl2 or "").upper() or None
        component = c1 or c2 or c3 or c4 or c5 or stem

        command = msg.strip() if msg else line_str
        if log_level and not command.startswith(f"[{log_level}]") and not command.startswith(f"{log_level}:"):
            command = f"[{log_level}] {command}"

        entries.append(
            CommandEntry(
                timestamp=timestamp,
                user="system",
                command=command,
                shell=component[:30],
                source=source,
                status=log_level,
                extra={"file": filepath, "level": log_level or ""},
            )
        )

    return entries


def parse_dpkg_lines(lines: List[str], source: str, filepath: str) -> List[CommandEntry]:
    """Parse Debian dpkg.log lines."""
    entries = []

    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue

        parts = line_str.split(" ", 2)
        if len(parts) >= 3:
            timestamp = parse_any_timestamp(f"{parts[0]} {parts[1]}")
            msg = parts[2]
        else:
            timestamp = None
            msg = line_str

        entries.append(
            CommandEntry(
                timestamp=timestamp,
                user="root",
                command=msg,
                shell="dpkg",
                source=source,
                extra={"file": filepath},
            )
        )

    return entries


def parse_apt_history_lines(lines: List[str], source: str, filepath: str) -> List[CommandEntry]:
    """Parse APT /var/log/apt/history.log multi-line blocks."""
    entries = []
    current_block = {}

    def commit_block():
        if not current_block:
            return
        cmd = current_block.get("commandline", "")
        if not cmd:
            install = current_block.get("install", "")
            upgrade = current_block.get("upgrade", "")
            remove = current_block.get("remove", "")
            cmd = install or upgrade or remove or "apt operation"

        ts = current_block.get("timestamp")
        user = current_block.get("user", "root")

        entries.append(
            CommandEntry(
                timestamp=ts,
                user=user,
                command=cmd,
                shell="apt",
                source=source,
                extra={"file": filepath, **{k: v for k, v in current_block.items()
                                            if k not in ("commandline", "timestamp", "user")}},
            )
        )

    for line in lines:
        line = line.strip()
        if not line:
            commit_block()
            current_block = {}
            continue

        if line.startswith("Start-Date:"):
            ts_str = line.replace("Start-Date:", "").strip()
            current_block["timestamp"] = parse_any_timestamp(ts_str)
        elif line.startswith("Commandline:"):
            current_block["commandline"] = line.replace(
                "Commandline:", "").strip()
        elif line.startswith("Requested-By:"):
            m = re.search(r"Requested-By:\s+(\w+)", line)
            if m:
                current_block["user"] = m.group(1)
        elif line.startswith("Install:"):
            current_block["install"] = line
        elif line.startswith("Upgrade:"):
            current_block["upgrade"] = line
        elif line.startswith("Remove:"):
            current_block["remove"] = line
        elif line.startswith("End-Date:"):
            pass

    commit_block()
    return entries


def parse_alternatives_lines(lines: List[str], source: str, filepath: str) -> List[CommandEntry]:
    """Parse /var/log/alternatives.log lines."""
    entries = []
    pattern = re.compile(
        r"^update-alternatives\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}):\s*(.*)$")

    for line in lines:
        match = pattern.match(line.strip())
        if match:
            ts_str, cmd = match.groups()
            timestamp = parse_any_timestamp(ts_str)
            entries.append(
                CommandEntry(
                    timestamp=timestamp,
                    user="root",
                    command=f"update-alternatives {cmd}",
                    shell="alternatives",
                    source=source,
                    extra={"file": filepath},
                )
            )

    return entries


def parse_cron_lines(lines: List[str], source: str, filepath: str) -> List[CommandEntry]:
    """Parse cron.log lines."""
    entries = []
    current_year = datetime.now().year

    pattern = re.compile(
        r"^([A-Z][a-z]{2}\s+\d+\s+[\d:]+|\d{4}-\d{2}-\d{2}T[\d:.]+[\w+-:]*)\s+"
        r"(\S+)\s+"
        r"CRON(?:\[(\d+)\])?:\s+"
        r"(?:\((\w+)\)\s+)?(?:CMD\s+\((.+)\)|(.*))$"
    )

    for line in lines:
        match = pattern.match(line.strip())
        if match:
            ts_str, host, pid_str, user, cmd1, cmd2 = match.groups()
            timestamp = parse_any_timestamp(ts_str, default_year=current_year)
            pid = int(pid_str) if pid_str and pid_str.isdigit() else None
            command = cmd1 or cmd2 or "cron task"

            entries.append(
                CommandEntry(
                    timestamp=timestamp,
                    user=user or "root",
                    command=f"cron: {command}",
                    shell="cron",
                    source=source,
                    pid=pid,
                    hostname=host,
                    extra={"file": filepath},
                )
            )

    return entries


def parse_kernel_lines(lines: List[str], source: str, filepath: str) -> List[CommandEntry]:
    """Parse kernel and dmesg log lines."""
    entries = []
    current_year = datetime.now().year

    bsd_pattern = re.compile(
        r"^([A-Z][a-z]{2}\s+\d+\s+[\d:]+)\s+(\S+)\s+kernel:\s*(.*)$")
    dmesg_pattern = re.compile(
        r"^\[([A-Z][a-z]{2}\s+[A-Z][a-z]{2}\s+\d+\s+[\d:]+\s+\d{4})\]\s*(.*)$")
    uptime_pattern = re.compile(r"^\[\s*(\d+\.\d+)\]\s*(.*)$")

    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue

        m_bsd = bsd_pattern.match(line_str)
        if m_bsd:
            ts_str, host, msg = m_bsd.groups()
            timestamp = parse_any_timestamp(ts_str, default_year=current_year)
            entries.append(
                CommandEntry(
                    timestamp=timestamp,
                    user="root",
                    command=msg,
                    shell="kernel",
                    source=source,
                    hostname=host,
                    extra={"file": filepath},
                )
            )
            continue

        m_dmesg = dmesg_pattern.match(line_str)
        if m_dmesg:
            ts_str, msg = m_dmesg.groups()
            timestamp = parse_any_timestamp(ts_str)
            entries.append(
                CommandEntry(
                    timestamp=timestamp,
                    user="root",
                    command=msg,
                    shell="kernel",
                    source=source,
                    extra={"file": filepath},
                )
            )
            continue

        m_uptime = uptime_pattern.match(line_str)
        if m_uptime:
            uptime, msg = m_uptime.groups()
            entries.append(
                CommandEntry(
                    timestamp=None,
                    user="root",
                    command=msg,
                    shell="kernel",
                    source=source,
                    extra={"file": filepath, "uptime": uptime},
                )
            )

    return entries


def parse_audit_lines(lines: List[str], source: str, filepath: str) -> List[CommandEntry]:
    """Parse Linux Auditd log lines (/var/log/audit/audit.log)."""
    entries = []

    pattern = re.compile(
        r"^type=(\w+)\s+msg=audit\((\d+\.\d+):(\d+)\):\s*(.*)$")
    comm_pattern = re.compile(r'\bcomm="([^"]+)"|\bcomm=(\S+)')
    exe_pattern = re.compile(r'\bexe="([^"]+)"|\bexe=(\S+)')
    auid_pattern = re.compile(r'\bauid=(\d+)')
    uid_pattern = re.compile(r'\buid=(\d+)')
    pid_pattern = re.compile(r'\bpid=(\d+)')
    success_pattern = re.compile(r'\bsuccess=(\w+)')

    for line in lines:
        match = pattern.match(line.strip())
        if not match:
            continue

        audit_type, epoch_str, event_id, rest = match.groups()
        timestamp = None
        try:
            timestamp = datetime.fromtimestamp(float(epoch_str))
        except Exception:
            pass

        comm_m = comm_pattern.search(rest)
        exe_m = exe_pattern.search(rest)
        comm = (comm_m.group(1) or comm_m.group(2)) if comm_m else ""
        exe = (exe_m.group(1) or exe_m.group(2)) if exe_m else ""
        command = exe or comm or f"audit {audit_type}: {rest[:80]}"

        auid_m = auid_pattern.search(rest)
        uid_m = uid_pattern.search(rest)
        uid_val = (auid_m.group(1) if auid_m else (
            uid_m.group(1) if uid_m else "0"))
        user = "root" if uid_val == "0" else f"uid:{uid_val}"

        pid_m = pid_pattern.search(rest)
        pid = int(pid_m.group(1)) if pid_m else None

        succ_m = success_pattern.search(rest)
        status = f"success={succ_m.group(1)}" if succ_m else None

        entries.append(
            CommandEntry(
                timestamp=timestamp,
                user=user,
                command=command,
                shell="audit",
                source=source,
                pid=pid,
                status=status,
                extra={"file": filepath, "audit_type": audit_type,
                       "event_id": event_id},
            )
        )

    return entries


def parse_fail2ban_lines(lines: List[str], source: str, filepath: str) -> List[CommandEntry]:
    """Parse /var/log/fail2ban.log lines."""
    entries = []
    pattern = re.compile(
        r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:,\d+)?)\s+"
        r"(\S+)\s+"
        r"(?:\[(\d+)\])?:\s*"
        r"(\w+)\s+"
        r"(.*)$"
    )

    for line in lines:
        match = pattern.match(line.strip())
        if match:
            ts_str, comp, pid_str, level, msg = match.groups()
            timestamp = parse_any_timestamp(ts_str)
            pid = int(pid_str) if pid_str and pid_str.isdigit() else None

            entries.append(
                CommandEntry(
                    timestamp=timestamp,
                    user="fail2ban",
                    command=f"[{level}] {msg}",
                    shell="fail2ban",
                    source=source,
                    pid=pid,
                    status=level,
                    extra={"file": filepath, "component": comp},
                )
            )

    return entries


def parse_database_lines(lines: List[str], source: str, filepath: str) -> List[CommandEntry]:
    """Parse PostgreSQL, MySQL, and Redis database logs."""
    entries = []

    pg_pattern = re.compile(
        r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+\w+\s+"
        r"(?:\[(\d+)\]\s+)?"
        r"(?:(\S+@\S+)\s+)?"
        r"(\w+):\s*(.*)$"
    )

    my_pattern = re.compile(
        r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)\s+"
        r"(\d+)?\s*"
        r"\[(\w+)\]\s*"
        r"(.*)$"
    )

    redis_pattern = re.compile(
        r"^(\d+):\w\s+"
        r"(\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+"
        r"[*#.-]\s*(.*)$"
    )

    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue

        m_pg = pg_pattern.match(line_str)
        if m_pg:
            ts_str, pid_str, user_db, level, msg = m_pg.groups()
            timestamp = parse_any_timestamp(ts_str)
            pid = int(pid_str) if pid_str and pid_str.isdigit() else None
            user = user_db.split(
                "@")[0] if user_db and "@" in user_db else "postgres"
            entries.append(
                CommandEntry(
                    timestamp=timestamp,
                    user=user,
                    command=f"[{level}] {msg}",
                    shell="postgres",
                    source=source,
                    pid=pid,
                    status=level,
                    extra={"file": filepath},
                )
            )
            continue

        m_my = my_pattern.match(line_str)
        if m_my:
            ts_str, thread_id, level, msg = m_my.groups()
            timestamp = parse_any_timestamp(ts_str)
            entries.append(
                CommandEntry(
                    timestamp=timestamp,
                    user="mysql",
                    command=f"[{level}] {msg}",
                    shell="mysql",
                    source=source,
                    status=level,
                    extra={"file": filepath, "thread_id": thread_id or ""},
                )
            )
            continue

        m_red = redis_pattern.match(line_str)
        if m_red:
            pid_str, ts_str, msg = m_red.groups()
            timestamp = parse_any_timestamp(ts_str)
            pid = int(pid_str) if pid_str.isdigit() else None
            entries.append(
                CommandEntry(
                    timestamp=timestamp,
                    user="redis",
                    command=msg,
                    shell="redis",
                    source=source,
                    pid=pid,
                    extra={"file": filepath},
                )
            )

    return entries


def parse_shell_history_lines(lines: List[str], source: str, filepath: str, shell_type: str = "bash") -> List[CommandEntry]:
    """Parse Bash, Zsh, Sh, Ksh history files."""
    entries = []
    user = os.environ.get("USER", os.environ.get("LOGNAME", "unknown"))

    current_timestamp = None
    zsh_pattern = re.compile(r"^:\s*(\d+):(?:\d+);(.*)$")

    for line in lines:
        line_str = line.rstrip("\r\n")
        if not line_str:
            continue

        z_match = zsh_pattern.match(line_str)
        if z_match:
            epoch_str, cmd = z_match.groups()
            ts = parse_any_timestamp(epoch_str)
            entries.append(
                CommandEntry(
                    timestamp=ts,
                    user=user,
                    command=cmd.strip(),
                    shell="zsh",
                    source=source,
                    extra={"history_file": filepath},
                )
            )
            continue

        if line_str.startswith("#") and len(line_str) > 1 and line_str[1:].isdigit():
            ts = parse_any_timestamp(line_str[1:])
            if ts:
                current_timestamp = ts
                continue

        cmd = line_str.strip()
        if not cmd:
            continue

        entries.append(
            CommandEntry(
                timestamp=current_timestamp,
                user=user,
                command=cmd,
                shell=shell_type,
                source=source,
                extra={"history_file": filepath},
            )
        )
        current_timestamp = None

    return entries


def parse_fish_history_lines(lines: List[str], source: str, filepath: str) -> List[CommandEntry]:
    """Parse Fish shell YAML-like history file."""
    entries = []
    user = os.environ.get("USER", os.environ.get("LOGNAME", "unknown"))

    current_cmd = None
    current_ts = None

    for line in lines:
        line_str = line.rstrip("\r\n")
        if line_str.startswith("- cmd: "):
            if current_cmd:
                entries.append(
                    CommandEntry(
                        timestamp=current_ts,
                        user=user,
                        command=current_cmd,
                        shell="fish",
                        source=source,
                        extra={"history_file": filepath},
                    )
                )
            current_cmd = line_str[7:].replace(r"\n", "\n")
            current_ts = None
        elif line_str.startswith("  when: ") and current_cmd:
            when_val = line_str[8:].strip()
            current_ts = parse_any_timestamp(when_val)

    if current_cmd:
        entries.append(
            CommandEntry(
                timestamp=current_ts,
                user=user,
                command=current_cmd,
                shell="fish",
                source=source,
                extra={"history_file": filepath},
            )
        )

    return entries


def parse_generic_lines(lines: List[str], source: str, filepath: str) -> List[CommandEntry]:
    """Smart fallback parser for any arbitrary text log file.

    Extracts timestamps, log levels, PIDs, and users when available.
    """
    entries = []
    stem = Path(filepath).stem.replace(".log", "")
    current_year = datetime.now().year

    ts_start_pattern = re.compile(
        r"^[\[\(]?(\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[,\.]\d+)?|[A-Z][a-z]{2}\s+\d+\s+\d{2}:\d{2}:\d{2}|\d{1,2}/[A-Z][a-z]{2}/\d{4}:\d{2}:\d{2}:\d{2})[\]\)]?\s*(.*)$"
    )
    level_pattern = re.compile(
        r"\b(DEBUG|INFO|WARN|WARNING|ERROR|FATAL|CRITICAL|TRACE|NOTICE)\b", re.IGNORECASE)
    pid_pattern = re.compile(
        r"(?:\[pid\s*(\d+)\]|\[(\d+)\]|\bpid[=:](\d+))", re.IGNORECASE)

    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue

        ts = None
        msg = line_str

        m_ts = ts_start_pattern.match(line_str)
        if m_ts:
            ts_str, rest = m_ts.groups()
            ts = parse_any_timestamp(ts_str, default_year=current_year)
            if ts:
                msg = rest.strip() or line_str

        level_m = level_pattern.search(msg)
        status = level_m.group(1).upper() if level_m else None

        pid_m = pid_pattern.search(msg)
        pid = None
        if pid_m:
            p_val = pid_m.group(1) or pid_m.group(2) or pid_m.group(3)
            if p_val and p_val.isdigit():
                pid = int(p_val)

        entries.append(
            CommandEntry(
                timestamp=ts,
                user="system",
                command=msg,
                shell=stem[:30],
                source=source,
                pid=pid,
                status=status,
                extra={"file": filepath},
            )
        )

    return entries


# ---------------------------------------------------------------------------
# Master Parsing Dispatcher
# ---------------------------------------------------------------------------

PARSER_MAP = {
    "syslog": parse_syslog_lines,
    "syslog_iso": parse_syslog_iso_lines,
    "auth": parse_auth_lines,
    "web_access": parse_web_access_lines,
    "web_error": parse_web_error_lines,
    "json": parse_json_lines,
    "app": parse_app_lines,
    "dpkg": parse_dpkg_lines,
    "apt_history": parse_apt_history_lines,
    "alternatives": parse_alternatives_lines,
    "cron": parse_cron_lines,
    "kernel": parse_kernel_lines,
    "audit": parse_audit_lines,
    "fail2ban": parse_fail2ban_lines,
    "database": parse_database_lines,
    "shell_history": parse_shell_history_lines,
    "fish_history": parse_fish_history_lines,
    "generic": parse_generic_lines,
}


def parse_log_file(
    filepath: str,
    log_type: str = "auto",
    source_name: str = "",
    max_lines: int = 50000,
) -> List[CommandEntry]:
    """Parse any log file given its path and format type.

    If log_type is 'auto', automatically detects the format from file content.
    Returns a list of CommandEntry objects.
    """
    expanded = os.path.expanduser(os.path.expandvars(filepath))

    if not source_name:
        source_name = os.path.basename(expanded)

    lines = read_log_file_lines(expanded, max_lines=max_lines)
    if not lines:
        return []

    if not log_type or log_type == "auto" or log_type not in PARSER_MAP:
        detected = detect_log_type(expanded, sample_lines=lines[:30])
        effective_type = detected
    else:
        effective_type = log_type

    parser_fn = PARSER_MAP.get(effective_type, parse_generic_lines)

    try:
        entries = parser_fn(lines, source_name, expanded)
        logger.info(
            f"Parsed {len(entries)} entries from {filepath} using '{effective_type}' parser")
        return entries
    except Exception as e:
        logger.warning(
            f"Error parsing {filepath} with '{effective_type}': {e}")
        try:
            return parse_generic_lines(lines, source_name, expanded)
        except Exception:
            return []
