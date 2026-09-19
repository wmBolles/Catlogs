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

target = '        elif page_id == "keylogger":\n            self.keylogger_page.pack(in_=self.content_container, fill=tk.BOTH, expand=True)\n'
replacement = '        elif page_id == "keylogger":\n            self.keylogger_page.pack(in_=self.content_container, fill=tk.BOTH, expand=True)\n        elif page_id == "deletion_history":\n            self.deletion_history_page.pack(in_=self.content_container, fill=tk.BOTH, expand=True)\n'

content = content.replace(target, replacement)

with open("catlogs/gui.py", "w") as f:
    f.write(content)
