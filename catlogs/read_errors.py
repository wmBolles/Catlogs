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
ERROR_LOG_PATH = str(CONFIG_DIR / get_encrypted_filename("read_errors.json"))


def log_read_error(filepath, error_message, collector_name):
    os.makedirs(os.path.dirname(ERROR_LOG_PATH), exist_ok=True)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "filepath": filepath,
        "error": str(error_message),
        "collector": collector_name
    }

    errors = load_read_errors()
    errors.append(entry)

    with open(ERROR_LOG_PATH, 'wb') as f:
        data = json.dumps(errors, indent=4).encode('utf-8')
        f.write(encrypt_data(data))


def load_read_errors():
    if not os.path.exists(ERROR_LOG_PATH):
        return []
    try:
        with open(ERROR_LOG_PATH, 'rb') as f:
            data = f.read()
        return json.loads(decrypt_data(data).decode('utf-8'))
    except (json.JSONDecodeError, PermissionError, OSError, Exception):
        return []


def clear_read_errors():
    if os.path.exists(ERROR_LOG_PATH):
        os.remove(ERROR_LOG_PATH)
