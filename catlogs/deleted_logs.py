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

from .config import CONFIG_DIR
from .crypto import encrypt_data, decrypt_data, get_encrypted_filename

DELETED_LOGS_PATH = str(
    CONFIG_DIR / get_encrypted_filename("deleted_logs.json"))


def add_deleted_log(command: str):
    os.makedirs(os.path.dirname(DELETED_LOGS_PATH), exist_ok=True)
    deleted = load_deleted_logs()
    if command not in deleted:
        deleted.append(command)
        with open(DELETED_LOGS_PATH, 'wb') as f:
            data = json.dumps(deleted, indent=4).encode('utf-8')
            f.write(encrypt_data(data))


def load_deleted_logs():
    if not os.path.exists(DELETED_LOGS_PATH):
        return []
    try:
        with open(DELETED_LOGS_PATH, 'rb') as f:
            data = f.read()
        return json.loads(decrypt_data(data).decode('utf-8'))
    except Exception:
        return []
