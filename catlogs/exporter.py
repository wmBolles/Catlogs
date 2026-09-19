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


def _pdf_escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")).replace("\n", " ")


def export_audit_report_pdf(target: str, findings: Sequence[dict], filepath: str,
                            generated_at: str = None) -> int:
    """Export a concise, professional dark-themed PDF audit report."""
    generated_at = generated_at or datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    parent = os.path.dirname(filepath)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)

    safe_findings = list(findings or [])
    severity_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
    for finding in safe_findings:
        severity = str(finding.get("severity", "info")).upper()
        severity_counts.setdefault(severity, 0)
        severity_counts[severity] = severity_counts.get(severity, 0) + 1

    def esc(value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def short_text(value: str, limit: int = 90) -> str:
        text = (value or "").strip()
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."

    def wrap_text(value: str, limit: int = 58) -> list[str]:
        text = (value or "").strip()
        if not text:
            return [""]
        words = text.split()
        lines = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) <= limit:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word if len(word) <= limit else word[:limit-3] + "..."
        if current:
            lines.append(current)
        return lines[:3]

    def add_text(cmds: list[str], text: str, x: int, y: int, size: int = 10, color: tuple = (1, 1, 1), font: str = "/F1"):
        cmds.append(f"q {color[0]} {color[1]} {color[2]} rg BT {font} {size} Tf {x} {y} Td ({esc(text)}) Tj ET Q")

    content_commands: list[str] = []
    content_commands.append("q 0 0 0 rg 0 0 612 792 re f Q")
    content_commands.append("q 0.08 0.10 0.14 rg 34 36 544 720 re f Q")
    content_commands.append("q 0.12 0.17 0.22 rg 52 700 508 72 re f Q")
    content_commands.append("q 1 1 1 rg BT /F2 26 Tf 68 742 Td (CatLogs Audit Report) Tj ET Q")
    content_commands.append(f"q 0.60 0.92 1 rg BT /F1 9 Tf 68 718 Td ({esc(f'Target: {target}')}) Tj ET Q")
    content_commands.append(f"q 0.82 0.87 0.93 rg BT /F1 9 Tf 68 706 Td ({esc(f'Generated: {generated_at}')}) Tj ET Q")
    content_commands.append(f"q 0.82 0.87 0.93 rg BT /F1 9 Tf 68 694 Td ({esc(f'Findings: {len(safe_findings)}')}) Tj ET Q")

    badge_map = {
        "HIGH": (0.96, 0.34, 0.47),
        "MEDIUM": (0.98, 0.71, 0.22),
        "LOW": (0.40, 0.83, 0.73),
        "INFO": (0.58, 0.72, 1.0),
    }

    if safe_findings:
        y = 660
        for idx, finding in enumerate(safe_findings[:8], 1):
            severity = str(finding.get("severity", "info")).upper()
            rule_name = short_text(str(finding.get("rule_name", "unknown")), 32)
            path = short_text(str(finding.get("path", "unknown")), 72)
            summary = short_text(str(finding.get("summary", "")), 80)
            details = short_text(str(finding.get("details", "")), 104)
            badge = badge_map.get(severity, (0.58, 0.72, 1.0))

            content_commands.append(f"q 0.18 0.22 0.29 rg 52 {y - 6} 500 74 re f Q")
            content_commands.append(f"q {badge[0]} {badge[1]} {badge[2]} rg 60 {y + 44} 88 16 re f Q")
            content_commands.append(f"q 0 0 0 rg BT /F2 8 Tf 66 {y + 49} Td ({esc(f'[{severity}]')}) Tj ET Q")
            content_commands.append(f"q 1 1 1 rg BT /F2 11 Tf 160 {y + 48} Td ({esc(f'{idx}. {rule_name}')}) Tj ET Q")
            add_text(content_commands, f"Path: {path}", 66, y + 30, size=8, color=(0.80, 0.86, 0.93), font="/F1")
            add_text(content_commands, f"Summary: {summary}", 66, y + 18, size=8, color=(0.80, 0.86, 0.93), font="/F1")
            add_text(content_commands, f"Details: {details}", 66, y + 6, size=8, color=(0.80, 0.86, 0.93), font="/F1")
            y -= 90
    else:
        content_commands.append("q 0.18 0.22 0.29 rg 52 270 500 100 re f Q")
        content_commands.append("q 1 1 1 rg BT /F2 18 Tf 120 320 Td (No suspicious findings detected.) Tj ET Q")

    content_stream = "\n".join(content_commands) + "\n"

    catalog_obj = "<< /Type /Catalog /Pages 2 0 R >>"
    pages_obj = "<< /Type /Pages /Kids [3 0 R] /Count 1 >>"
    page_obj = "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>"
    font1_obj = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    font2_obj = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"
    stream_obj = f"<< /Length {len(content_stream.encode('latin-1'))} >>\nstream\n{content_stream}endstream"

    objects = [catalog_obj, pages_obj, page_obj, font1_obj, font2_obj, stream_obj]
    pdf_bytes = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for idx, obj in enumerate(objects, 1):
        offsets.append(len(pdf_bytes))
        pdf_bytes.extend(f"{idx} 0 obj\n".encode("latin-1"))
        pdf_bytes.extend(obj.encode("latin-1", errors="replace"))
        pdf_bytes.extend(b"\nendobj\n")
    xref_offset = len(pdf_bytes)
    pdf_bytes.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    pdf_bytes.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        pdf_bytes.extend(f"{off:010d} 00000 n \n".encode("latin-1"))
    pdf_bytes.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("latin-1"))

    with open(filepath, "wb") as handle:
        handle.write(pdf_bytes)

    return len(safe_findings)


def generate_default_pdf_filename() -> str:
    """Generate a default PDF filename with a timestamp."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"catlogs_audit_report_{ts}.pdf"


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
