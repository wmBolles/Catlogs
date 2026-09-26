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

with open("catlogs/gui.py", "r") as f:
    content = f.read()

themes = ["tokyo_night", "catppuccin", "synthwave",
          "oceanic", "github_dark", "material_palenight"]
for theme in themes:
    if f'"{theme}": {{' in content:
        start = content.find(f'"{theme}": {{')
        end = content.find("    },", start)
        if end == -1:
            end = content.find("    }\n}", start)

        block = content[start:end]
        if "accent_hover" not in block:
            import re
            accent_m = re.search(r'"accent":\s*"([^"]+)"', block)
            accent = accent_m.group(1) if accent_m else "#ffffff"
            fg_m = re.search(r'"fg":\s*"([^"]+)"', block)
            fg = fg_m.group(1) if fg_m else "#ffffff"

            insert_str = f',\n        "accent_hover": "{accent}", "fg_dim": "{fg}", "success": "#81c784", "warning": "#ffb74d", "error": "#e57373"'

            new_block = block + insert_str
            content = content[:start] + new_block + content[end:]

with open("catlogs/gui.py", "w") as f:
    f.write(content)
