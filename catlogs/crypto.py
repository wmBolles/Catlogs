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
import base64
import hashlib

SEC_KEY = b"CatLogsSecKey123"


def encrypt_data(data: bytes) -> bytes:
    res = bytearray(len(data))
    for i in range(len(data)):
        res[i] = data[i] ^ SEC_KEY[i % len(SEC_KEY)]
    return bytes(res)


def decrypt_data(data: bytes) -> bytes:
    return encrypt_data(data)  # XOR is symmetric


def encrypt_str(text: str) -> str:
    enc = encrypt_data(text.encode('utf-8'))
    return base64.b64encode(enc).decode('utf-8')


def decrypt_str(b64_text: str) -> str:
    try:
        enc = base64.b64decode(b64_text.encode('utf-8'))
        dec = decrypt_data(enc)
        return dec.decode('utf-8', errors='replace')
    except Exception:
        return ""


def get_encrypted_filename(original_name: str) -> str:
    # Use sha256 to generate a consistent obscure filename
    h = hashlib.sha256(original_name.encode('utf-8') + SEC_KEY).hexdigest()
    return f"{h[:16]}.dat"
