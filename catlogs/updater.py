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


def download_and_install_update(
    base_url: str = "https://catlogs.wassim.tech",
    timeout: int = 60,
    progress_callback=None,
) -> dict:
    """Download the latest .deb package and install it.

    Tries in order:
    1. Download the versioned .deb and run ``sudo dpkg -i`` via pkexec or sudo.
    2. Fallback: overwrite the running binary directly with the downloaded binary.

    *progress_callback* is called with a human-readable status string as the
    install progresses.
    """
    import shutil
    import stat
    import sys
    import tempfile

    def _progress(msg: str) -> None:
        if progress_callback is not None:
            progress_callback(msg)

    # ── 1. Fetch latest version number ──────────────────────────────────────
    _progress("Fetching latest version info…")
    version_url = f"{base_url.rstrip('/')}/version.txt"
    latest_version = fetch_latest_version((version_url,), timeout=8)
    if not latest_version:
        return {"updated": False, "message": "Could not reach the update server; please try again later."}

    state = get_update_state(__version__, latest_version)
    if not state["available"]:
        return {"updated": False, "message": f"Already on the latest version ({latest_version})."}

    # ── 2. Try .deb install ─────────────────────────────────────────────────
    arch = "amd64"
    try:
        result = subprocess.run(["dpkg", "--print-architecture"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            arch = result.stdout.strip()
    except Exception:
        pass

    deb_name = f"catlogs_{latest_version}_{arch}.deb"
    deb_url = f"{base_url.rstrip('/')}/{deb_name}"

    # Check whether dpkg is available at all
    dpkg_available = shutil.which("dpkg") is not None

    if dpkg_available:
        _progress(f"Downloading {deb_name}…")
        try:
            with tempfile.NamedTemporaryFile(suffix=".deb", delete=False) as tmp:
                tmp_path = tmp.name

            req = urllib.request.Request(deb_url, headers={"User-Agent": "CatLogsUpdater/1.0"})
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                with open(tmp_path, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)

            _progress("Installing package (may prompt for password)…")
            # Try pkexec first (graphical sudo), fall back to sudo
            for prefix in (["pkexec"], ["sudo", "-n"], ["sudo"]):
                cmd = prefix + ["dpkg", "-i", tmp_path]
                try:
                    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                    if proc.returncode == 0:
                        try:
                            os.unlink(tmp_path)
                        except OSError:
                            pass
                        return {
                            "updated": True,
                            "message": f"CatLogs {latest_version} installed successfully via .deb. Restart the app to use the new version.",
                        }
                except (OSError, subprocess.TimeoutExpired):
                    continue

            # All elevated runners failed — clean up and fall through to binary replacement
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        except Exception as exc:
            _progress(f"deb download failed ({exc}), trying binary update…")

    # ── 3. Fallback: download and replace the running binary ─────────────────
    bin_url = f"{base_url.rstrip('/')}/catlogs"
    _progress("Downloading standalone binary…")
    try:
        running_exe = os.path.abspath(sys.executable if getattr(sys, "frozen", False) else sys.argv[0])
        with tempfile.NamedTemporaryFile(delete=False, dir=os.path.dirname(running_exe)) as tmp:
            tmp_path = tmp.name

        req = urllib.request.Request(bin_url, headers={"User-Agent": "CatLogsUpdater/1.0"})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)

        os.chmod(tmp_path, os.stat(tmp_path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        os.replace(tmp_path, running_exe)
        return {
            "updated": True,
            "message": f"CatLogs {latest_version} binary updated. Restart the app to use the new version.",
        }
    except Exception as exc:
        return {
            "updated": False,
            "message": f"Update failed: {exc}",
        }


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
