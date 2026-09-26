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

"""CSV and PDF export functionality for CatLogs application."""

import csv
import os
from datetime import datetime
from typing import List, Sequence

from .models import CommandEntry




def export_to_csv(entries: List[CommandEntry], filepath: str,
                  filters: dict = None, version: str = '1.0.0') -> int:
    """Export a list of CommandEntry objects to a CSV file.

    Args:
        entries: The command entries to export.
        filepath: Path to the output CSV file.
        filters: Dictionary of filters applied.
        version: Application version.

    Returns:
        Number of rows written.

    Raises:
        OSError: If the file cannot be written.
    """
    if not entries:
        return 0

    fieldnames = [
        "Timestamp",
        "User",
        "Command",
        "Shell",
        "Source",
        "PID",
        "TTY",
        "Working Directory",
        "Exit Code",
        "Hostname",
        "CPU %",
        "MEM %",
        "Status",
    ]

    parent = os.path.dirname(filepath)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)

    with open(filepath, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(
            csvfile, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for entry in entries:
            writer.writerow(entry.to_dict())

        writer_list = csv.writer(csvfile)
        writer_list.writerow([])
        writer_list.writerow(["---"])
        writer_list.writerow(["Software", "CatLogs - System Logs"])
        writer_list.writerow(["Release", version])
        export_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        username = os.environ.get("USER", os.environ.get("LOGNAME", "unknown"))
        writer_list.writerow(["Export Date", export_date])
        writer_list.writerow(["Exported By", username])
        writer_list.writerow(["Total Records", len(entries)])
        if filters:
            if filters.get("Search"):
                writer_list.writerow(
                    ["Filter - Search", filters.get("Search")])
            if filters.get("User Included") and filters.get("User Included") != "None":
                writer_list.writerow(
                    ["Filter - User Included", filters.get("User Included")])
            if filters.get("Shell Included") and filters.get("Shell Included") != "None":
                writer_list.writerow(
                    ["Filter - Shell Included", filters.get("Shell Included")])
            if filters.get("Source Included") and filters.get("Source Included") != "None":
                writer_list.writerow(
                    ["Filter - Source Included", filters.get("Source Included")])
            if filters.get("From"):
                writer_list.writerow(["Filter - From", filters.get("From")])
            if filters.get("To"):
                writer_list.writerow(["Filter - To", filters.get("To")])
        writer_list.writerow(["More Info", "https://catlogs.wassim.tech/"])
        writer_list.writerow(
            ["Note", "This data was fetched from CatLogs software"])

    return len(entries)


def generate_default_filename() -> str:
    """Generate a default CSV filename with a timestamp."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"catlogs_export_{ts}.csv"
