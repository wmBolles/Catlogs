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

import re

with open("catlogs/gui.py", "r") as f:
    content = f.read()

init_code = """
        self.keylogger_page = ttk.Frame(self.content_container)
        self._build_keylogger_page(self.keylogger_page)
        
        self.deletion_history_page = ttk.Frame(self.content_container)
        self._build_deletion_history_page(self.deletion_history_page)
"""

content = content.replace(
    "        self.keylogger_page = ttk.Frame(self.content_container)\n        self._build_keylogger_page(self.keylogger_page)\n",
    init_code
)

with open("catlogs/gui.py", "w") as f:
    f.write(content)
