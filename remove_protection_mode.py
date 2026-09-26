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

# I will find the code I injected and remove it
start_str = "ttk.Separator(theme_card, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=16)"
end_str = "cb.pack(side=tk.LEFT)"

s_idx = content.find(start_str)
e_idx = content.find(end_str)

if s_idx != -1 and e_idx != -1:
    content = content[:s_idx] + content[e_idx + len(end_str):]

with open("catlogs/gui.py", "w") as f:
    f.write(content)
