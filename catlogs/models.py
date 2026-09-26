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


from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any


@dataclass
class CommandEntry:

    timestamp: Optional[datetime]
    user: str
    command: str
    shell: str
    source: str
    pid: Optional[int] = None
    tty: Optional[str] = None
    working_dir: Optional[str] = None
    exit_code: Optional[int] = None
    hostname: Optional[str] = None
    cpu_percent: Optional[str] = None
    mem_percent: Optional[str] = None
    status: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def timestamp_str(self) -> str:
        if self.timestamp:
            return self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        return "Unknown"

    @property
    def detail_text(self) -> str:
        lines = []
        lines.append(f"  Command    : {self.command}")
        lines.append(f"  Timestamp  : {self.timestamp_str}")
        lines.append(f"  User       : {self.user}")
        lines.append(f"  Shell      : {self.shell}")
        lines.append(f"  Source     : {self.source}")

        if self.pid is not None:
            lines.append(f"  PID        : {self.pid}")
        if self.tty:
            lines.append(f"  TTY        : {self.tty}")
        if self.working_dir:
            lines.append(f"  Work Dir   : {self.working_dir}")
        if self.exit_code is not None:
            lines.append(f"  Exit Code  : {self.exit_code}")
        if self.hostname:
            lines.append(f"  Hostname   : {self.hostname}")
        if self.cpu_percent:
            lines.append(f"  CPU %      : {self.cpu_percent}")
        if self.mem_percent:
            lines.append(f"  MEM %      : {self.mem_percent}")
        if self.status:
            lines.append(f"  Status     : {self.status}")

        for key, value in self.extra.items():
            label = key.replace("_", " ").title()
            lines.append(f"  {label:<11}: {value}")

        return "\n".join(lines)

    def matches_filter(
        self,
        text: str = "",
        user_exc_list: list = None,
        shell_exc_list: list = None,
        source_exc_list: list = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> bool:
        """Check if this entry matches the given filters."""
        if start_time or end_time:
            if not self.timestamp:
                return False
            ts = self.timestamp.replace(
                tzinfo=None) if self.timestamp.tzinfo else self.timestamp
            if start_time:
                st = start_time.replace(
                    tzinfo=None) if start_time.tzinfo else start_time
                if ts < st:
                    return False
            if end_time:
                et = end_time.replace(
                    tzinfo=None) if end_time.tzinfo else end_time
                if ts > et:
                    return False

        if text:
            text_lower = text.lower()
            searchable = f"{self.command} {self.user} {self.shell} {self.source}"
            if self.tty:
                searchable += f" {self.tty}"
            if self.working_dir:
                searchable += f" {self.working_dir}"
            if text_lower not in searchable.lower():
                return False

        if user_exc_list and self.user in user_exc_list:
            return False
        if shell_exc_list and self.shell in shell_exc_list:
            return False
        if source_exc_list and self.source in source_exc_list:
            return False

        return True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary for CSV export."""
        return {
            "Timestamp": self.timestamp_str,
            "User": self.user,
            "Command": self.command,
            "Shell": self.shell,
            "Source": self.source,
            "PID": self.pid or "",
            "TTY": self.tty or "",
            "Working Directory": self.working_dir or "",
            "Exit Code": self.exit_code if self.exit_code is not None else "",
            "Hostname": self.hostname or "",
            "CPU %": self.cpu_percent or "",
            "MEM %": self.mem_percent or "",
            "Status": self.status or "",
        }
