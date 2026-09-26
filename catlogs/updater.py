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

"""Lightweight update checker for CatLogs."""

from __future__ import annotations

import os
import re
import ssl
import subprocess
import urllib.error
import urllib.request
from typing import Callable, Iterable, Optional

from . import __version__

DEFAULT_VERSION_URLS = (
    "https://catlogs.wassim.tech/version.txt",
    "https://raw.githubusercontent.com/wmBolles/Catlogs/master/website/version.txt",
)


def _sanitize_version(version: Optional[str]) -> str:
    if version is None:
        return "0"
    match = re.findall(r"\d+", str(version).strip())
    if not match:
        return "0"
    return ".".join(match)


def _version_tuple(version: Optional[str]) -> tuple[int, ...]:
    cleaned = _sanitize_version(version)
    if cleaned == "0":
        return (0,)
    return tuple(int(part) for part in cleaned.split("."))


def compare_versions(current_version: Optional[str], latest_version: Optional[str]) -> int:
    """Return 1 if current > latest, 0 if equal, -1 if current < latest."""
    current = _version_tuple(current_version)
    latest = _version_tuple(latest_version)
    max_len = max(len(current), len(latest))
    current += (0,) * (max_len - len(current))
    latest += (0,) * (max_len - len(latest))
    if current > latest:
        return 1
    if current < latest:
        return -1
    return 0


def get_update_state(current_version: Optional[str] = None, latest_version: Optional[str] = None):
    current = current_version or __version__
    latest = latest_version or current
    comparison = compare_versions(current, latest)
    return {
        "current_version": str(current),
        "latest_version": str(latest),
        "available": comparison < 0,
        "up_to_date": comparison == 0,
        "comparison": comparison,
    }


def fetch_latest_version(urls: Optional[Iterable[str]] = None, timeout: int = 8) -> Optional[str]:
    """Fetch the latest CatLogs version from the website or GitHub release source."""
    candidate_urls = tuple(urls or DEFAULT_VERSION_URLS)

    for url in candidate_urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CatLogsUpdater/1.0"})
            with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
                body = resp.read().decode("utf-8", errors="replace").strip()
            if not body:
                continue
            version = body.splitlines()[0].strip()
            if version and version not in {"", "null", "None"}:
                return version
        except (urllib.error.URLError, ValueError, TimeoutError, ssl.SSLError):
            continue
        except Exception:  # pragma: no cover - defensive fallback
            continue

    return None


def check_for_update(callback: Optional[Callable[[Optional[str]], None]] = None, url_sources: Optional[Iterable[str]] = None):
    """Check the current remote version and invoke callback with the latest version if available."""
    latest_version = fetch_latest_version(url_sources)
    if latest_version is None:
        if callback is not None:
            callback(None)
        return None

    state = get_update_state(__version__, latest_version)
    if callback is not None:
        callback(latest_version if state["available"] else None)
    return state


def install_local_update(repo_root: Optional[str] = None, base_url: str = "https://catlogs.wassim.tech", timeout: int = 20):
    """Attempt a local update by pulling from git when possible or by fetching release metadata."""
    if repo_root:
        git_dir = os.path.join(repo_root, ".git")
        if os.path.isdir(git_dir):
            try:
                subprocess.run(["git", "-C", repo_root, "pull", "--ff-only"], check=True, capture_output=True, text=True)
                return {
                    "updated": True,
                    "source": "git",
                    "message": "CatLogs repository was updated successfully via git pull.",
                }
            except (OSError, subprocess.CalledProcessError):
                pass

    version_url = f"{base_url.rstrip('/')}/version.txt"
    latest_version = fetch_latest_version((version_url,), timeout=timeout)
    if not latest_version:
        return {
            "updated": False,
            "source": "offline",
            "message": "Could not reach the update server; please try again later.",
        }

    state = get_update_state(__version__, latest_version)
    if not state["available"]:
        return {
            "updated": False,
            "source": "version",
            "message": f"CatLogs is already on the latest version ({latest_version}).",
        }

    return {
        "updated": False,
        "source": "version",
        "message": f"An update to {latest_version} is available. Download the latest package from {base_url} and reinstall it.",
    }
