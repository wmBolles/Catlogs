import os

C_HEADER = """/*
 * CatLogs
 * A local system logging and diagnostic tool.
 * Copyright (C) 2026 Wassim Bolles
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */
"""

PY_HEADER = """# CatLogs
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
"""


def add_header(file_path):
    with open(file_path, 'r') as f:
        content = f.read()

    if "GNU General Public License" in content:
        return

    ext = os.path.splitext(file_path)[1]

    if ext in ['.c', '.h']:
        new_content = C_HEADER + '\n' + content
    elif ext == '.py':
        # Preserve shebang if present
        if content.startswith('#!'):
            lines = content.split('\n', 1)
            shebang = lines[0] + '\n'
            rest = lines[1] if len(lines) > 1 else ''
            new_content = shebang + '\n' + PY_HEADER + '\n' + rest
        else:
            new_content = PY_HEADER + '\n' + content
    else:
        return

    with open(file_path, 'w') as f:
        f.write(new_content)


for root, _, files in os.walk('.'):
    if '.venv' in root or '.git' in root:
        continue
    for file in files:
        if file.endswith(('.c', '.h', '.py')):
            add_header(os.path.join(root, file))

print("Headers added.")
