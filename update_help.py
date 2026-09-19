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

insert_str = """        help_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        if getattr(self, '_help_photo', None):
            self.help_text.image_create(tk.END, image=self._help_photo)
            self.help_text.insert(tk.END, "\\n\\n")

        help_content = \"\"\"CatLogs - System Logs"""

content = content.replace("""        help_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        help_content = \"\"\"CatLogs - System Logs""", insert_str)

with open("catlogs/gui.py", "w") as f:
    f.write(content)
