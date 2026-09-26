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
import secrets
from pathlib import Path

SECRET_ENV_VAR = "CATLOGS_SECRET_KEY"
LEGACY_KEY = b"CatLogsSecKey123"
KEY_PATH = Path.home() / ".config" / "catlogs" / "secret.key"


def _ensure_key_dir() -> None:
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(str(KEY_PATH.parent), 0o700)
    except OSError:
        pass


def get_secret_key() -> bytes:
    env_key = os.environ.get(SECRET_ENV_VAR)
    if env_key and env_key.strip():
        return env_key.strip().encode("utf-8")

    if KEY_PATH.is_file():
        try:
            secret = KEY_PATH.read_text(encoding="utf-8").strip()
            if secret:
                os.environ[SECRET_ENV_VAR] = secret
                return secret.encode("utf-8")
        except OSError:
            pass

    secret = secrets.token_urlsafe(32)
    _ensure_key_dir()
    try:
        KEY_PATH.write_text(secret, encoding="utf-8")
        os.chmod(str(KEY_PATH), 0o600)
    except OSError:
        pass
    os.environ[SECRET_ENV_VAR] = secret
    return secret.encode("utf-8")


SEC_KEY = get_secret_key()


def _derive_keystream(data: bytes, salt: bytes) -> bytes:
    key_material = hashlib.pbkdf2_hmac(
        "sha256",
        SEC_KEY,
        salt,
        100_000,
        dklen=32,
    )
    out = bytearray()
    for index in range(0, len(data), 32):
        block = hashlib.sha256(key_material + index.to_bytes(4, "big") + salt).digest()
        out.extend(block)
    return bytes(out[:len(data)])


def encrypt_data(data: bytes) -> bytes:
    if not data:
        return b""
    salt = secrets.token_bytes(16)
    keystream = _derive_keystream(data, salt)
    encrypted = bytes(a ^ b for a, b in zip(data, keystream))
    prefix = b"v2:" + salt + b":"
    return prefix + encrypted


def decrypt_data(data: bytes) -> bytes:
    if not data:
        return b""
    if data.startswith(b"v2:"):
        if len(data) >= 20 and data[19] == 58:  # 58 is ord(':')
            salt = data[3:19]
            ciphertext = data[20:]
            keystream = _derive_keystream(ciphertext, salt)
            return bytes(a ^ b for a, b in zip(ciphertext, keystream))

    candidates = []
    env_key = os.environ.get(SECRET_ENV_VAR, "")
    if env_key.strip():
        candidates.append(env_key.strip().encode("utf-8"))
    if SEC_KEY:
        candidates.append(SEC_KEY)
    candidates.append(LEGACY_KEY)
    candidates = list(dict.fromkeys(candidates))

    best = data
    best_score = -1
    for key in candidates:
        if not key:
            continue
        decoded = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
        printable = sum(32 <= c < 127 or c in (9, 10, 13) for c in decoded)
        score = printable / max(1, len(decoded))
        if score > best_score:
            best = decoded
            best_score = score

    return best


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
    # Use sha256 to generate a consistent obscure filename.
    h = hashlib.sha256(original_name.encode('utf-8') + SEC_KEY).hexdigest()
    return f"{h[:16]}.dat"
