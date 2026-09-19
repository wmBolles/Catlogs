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

content = content.replace(
    "dialog.resizable(False, False)", "dialog.resizable(True, True)")

content = content.replace('dialog.geometry(f"450x450+{self.root.winfo_x() + 300}+{self.root.winfo_y() + 150}")',
                          'dialog.geometry(f"600x600+{self.root.winfo_x() + 200}+{self.root.winfo_y() + 100}")')
content = content.replace('dialog.geometry(f"600x400+{self.root.winfo_x() + 200}+{self.root.winfo_y() + 150}")',
                          'dialog.geometry(f"800x600+{self.root.winfo_x() + 200}+{self.root.winfo_y() + 100}")')

if "dialog.resizable" not in content.split("def _show_settings(self):")[1]:
    content = content.replace('dialog.title("Settings")',
                              'dialog.title("Settings")\n        dialog.resizable(True, True)')

with open("catlogs/gui.py", "w") as f:
    f.write(content)
