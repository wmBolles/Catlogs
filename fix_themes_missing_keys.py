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
        if "entry_bg" not in block:
            import re
            bg_sec_m = re.search(r'"bg_secondary":\s*"([^"]+)"', block)
            bg_sec = bg_sec_m.group(1) if bg_sec_m else "#353535"
            bg_table_m = re.search(r'"bg_table":\s*"([^"]+)"', block)
            bg_table = bg_table_m.group(1) if bg_table_m else "#2d2d2d"

            insert_str = f',\n        "entry_bg": "{bg_sec}", "detail_bg": "{bg_table}"'

            new_block = block + insert_str
            content = content[:start] + new_block + content[end:]

with open("catlogs/gui.py", "w") as f:
    f.write(content)
