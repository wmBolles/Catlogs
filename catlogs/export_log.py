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
import json
from datetime import datetime

from .config import CONFIG_DIR
from .crypto import encrypt_data, decrypt_data, get_encrypted_filename
EXPORT_LOG_PATH = str(
    CONFIG_DIR / get_encrypted_filename("export_history.json"))


def log_export(filepath, record_count, filters, version):
    os.makedirs(os.path.dirname(EXPORT_LOG_PATH), exist_ok=True)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "username": os.environ.get("USER", os.environ.get("LOGNAME", "unknown")),
        "filepath": filepath,
        "record_count": record_count,
        "filters": filters or {},
        "version": version
    }

    history = load_export_history()
    history.append(entry)

    try:
        if os.path.exists(EXPORT_LOG_PATH):
            os.chmod(EXPORT_LOG_PATH, 0o600)
    except OSError:
        pass

    with open(EXPORT_LOG_PATH, 'wb') as f:
        data = json.dumps(history, indent=4).encode('utf-8')
        f.write(encrypt_data(data))

    try:
        os.chmod(EXPORT_LOG_PATH, 0o400)
    except OSError:
        pass


def load_export_history():
    if not os.path.exists(EXPORT_LOG_PATH):
        return []
    try:
        with open(EXPORT_LOG_PATH, 'rb') as f:
            data = f.read()
        return json.loads(decrypt_data(data).decode('utf-8'))
    except Exception:
        return []


def clear_export_history():
    if os.path.exists(EXPORT_LOG_PATH):
        os.chmod(EXPORT_LOG_PATH, 0o600)
        os.remove(EXPORT_LOG_PATH)
