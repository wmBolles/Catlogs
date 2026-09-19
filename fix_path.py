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

import re

old_get = """def _get_icon_path():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))"""
new_get = """def _get_icon_path():
    import sys
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))"""
content = content.replace(old_get, new_get)

old_set = """            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            help_pic = os.path.join(base, "icon", "icon-removebg.png")"""
new_set = """            import sys
            base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            help_pic = os.path.join(base, "icon", "icon-removebg.png")"""
content = content.replace(old_set, new_set)

with open("catlogs/gui.py", "w") as f:
    f.write(content)
