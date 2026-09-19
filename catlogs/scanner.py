import hashlib
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

SUSPICIOUS_EXTENSIONS = {
    ".exe",
    ".dll",
    ".bat",
    ".cmd",
    ".ps1",
    ".vbs",
    ".js",
    ".jar",
    ".scr",
    ".com",
    ".hta",
}

SUSPICIOUS_KEYWORDS = (
    "powershell",
    "wscript",
    "cscript",
    "base64",
    "rundll32",
    "cmd.exe",
    "mshta",
)


def _db_path() -> str:
    db_path = os.environ.get("CATLOGS_SCANNER_DB")
    if db_path:
        return db_path
    return os.path.join(os.path.expanduser("~"), ".config", "catlogs", "scanner.db")


def _connect() -> sqlite3.Connection:
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _init_schema() -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scan_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                target TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scan_findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                rule_name TEXT NOT NULL,
                severity TEXT NOT NULL,
                path TEXT NOT NULL,
                summary TEXT NOT NULL,
                details TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES scan_sessions(id)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def create_scan_session(name: str, target: str, mode: str, status: str = "pending") -> Dict[str, Any]:
    """Create a new scanner session and persist it to the local database."""
    _init_schema()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = _connect()
    try:
        cursor = conn.execute(
            """
            INSERT INTO scan_sessions (name, target, mode, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, target, mode, status, now, now),
        )
        conn.commit()
        session_id = cursor.lastrowid
        row = conn.execute(
            "SELECT * FROM scan_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def list_scan_sessions() -> List[Dict[str, Any]]:
    """Return all persisted scanner sessions."""
    _init_schema()
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM scan_sessions ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def add_scan_finding(
    session_id: int,
    rule_name: str,
    severity: str,
    path: str,
    summary: str,
    details: str,
) -> Optional[Dict[str, Any]]:
    """Add a scanner finding to a session and return the created record."""
    _init_schema()
    conn = _connect()
    try:
        cursor = conn.execute(
            """
            INSERT INTO scan_findings (session_id, rule_name, severity, path, summary, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                rule_name,
                severity,
                path,
                summary,
                details,
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM scan_findings WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def list_findings(session_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """List findings, optionally filtered by session."""
    _init_schema()
    conn = _connect()
    try:
        if session_id is None:
            rows = conn.execute(
                "SELECT * FROM scan_findings ORDER BY created_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM scan_findings WHERE session_id = ? ORDER BY created_at DESC",
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_directory(directory: str, max_depth: int = 3, max_files: int = 500) -> Dict[str, Any]:
    """Run a lightweight local scan over a directory and return findings."""
    files_scanned = 0
    findings: List[Dict[str, Any]] = []
    visited = 0

    for root, _, files in os.walk(directory):
        rel_root = os.path.relpath(root, directory)
        if rel_root == ".":
            depth = 0
        else:
            depth = rel_root.count(os.sep) + 1
        if depth > max_depth:
            continue

        for filename in sorted(files):
            if files_scanned >= max_files:
                break
            file_path = os.path.join(root, filename)
            if os.path.islink(file_path):
                continue
            try:
                stat_result = os.stat(file_path)
            except OSError:
                continue
            if not stat_result.st_size and not filename.lower().endswith(tuple(SUSPICIOUS_EXTENSIONS)):
                continue

            files_scanned += 1
            lower_name = filename.lower()
            ext = os.path.splitext(lower_name)[1]
            suspicious = ext in SUSPICIOUS_EXTENSIONS
            file_hash = _sha256_file(file_path)

            if suspicious:
                finding = {
                    "rule_name": "suspicious_extension",
                    "severity": "medium",
                    "path": file_path,
                    "summary": f"Suspicious executable-like extension: {filename}",
                    "details": f"File extension {ext} is commonly associated with script or executable payloads. SHA256: {file_hash}",
                }
                findings.append(finding)

            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
                    preview = handle.read(4096)
            except Exception:
                preview = ""

            if preview:
                lowered = preview.lower()
                if any(keyword in lowered for keyword in SUSPICIOUS_KEYWORDS):
                    findings.append({
                        "rule_name": "embedded_execution_pattern",
                        "severity": "high",
                        "path": file_path,
                        "summary": "Embedded execution pattern found in file content.",
                        "details": f"The file contains a suspicious execution pattern such as PowerShell or cmd invocation. SHA256: {file_hash}",
                    })

            visited += 1

        if files_scanned >= max_files:
            break

    return {
        "directory": directory,
        "files_scanned": files_scanned,
        "visited_entries": visited,
        "findings": findings,
    }


__all__ = [
    "_db_path",
    "_connect",
    "_init_schema",
    "create_scan_session",
    "list_scan_sessions",
    "add_scan_finding",
    "list_findings",
    "scan_directory",
]
