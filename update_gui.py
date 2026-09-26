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

start_idx = content.find("def _apply_theme(self):")
end_idx = content.find("def _build_ui(self):", start_idx)

theme_code = content[start_idx:end_idx]

theme_code = theme_code.replace(
    'c = self.colors\n', 'c = self.colors\n\n        zl = getattr(self, "zoom_level", 0)\n        def fs(base): return max(6, base + zl)\n')

theme_code = re.sub(r'font=\(self\.(main_font|mono_font),\s*(\d+)\)',
                    r'font=(self.\1, fs(\2))', theme_code)
theme_code = re.sub(
    r'font=\(self\.(main_font|mono_font),\s*(\d+),\s*"([^"]+)"\)', r'font=(self.\1, fs(\2), "\3")', theme_code)

content = content[:start_idx] + theme_code + content[end_idx:]

content = content.replace(
    'values=["sans-serif", "Arial", "Helvetica", "Ubuntu", "DejaVu Sans", "Segoe UI"]',
    'values=["sans-serif", "Arial", "Helvetica", "Ubuntu", "DejaVu Sans", "Segoe UI", "Roboto", "Open Sans", "Tahoma"]'
)

content = content.replace(
    'values=["Consolas", "monospace", "Courier New", "DejaVu Sans Mono", "Ubuntu Mono", "Fira Code"]',
    'values=["Consolas", "monospace", "Courier New", "DejaVu Sans Mono", "Ubuntu Mono", "Fira Code", "JetBrains Mono", "Hack", "Cascadia Code"]'
)

bind_code = """
        self.root.bind("<Control-plus>", lambda _: self._zoom(1))
        self.root.bind("<Control-minus>", lambda _: self._zoom(-1))
        self.root.bind("<Control-equal>", lambda _: self._zoom(1))
        self.root.bind("<Control-0>", lambda _: self._zoom(0, reset=True))
"""
content = content.replace("self.root.bind(\"<Escape>\", lambda _: self._clear_filters())\n",
                          "self.root.bind(\"<Escape>\", lambda _: self._clear_filters())\n" + bind_code)

zoom_func = """
    def _zoom(self, delta: int, reset: bool = False):
        if reset:
            self.zoom_level = 0
        else:
            self.zoom_level = getattr(self, "zoom_level", 0) + delta
        self.config["zoom_level"] = self.zoom_level
        
        import threading
        from .config import save_config
        threading.Thread(target=lambda: save_config(self.config)).start()
        
        self._apply_theme()
"""

refresh_idx = content.find("def _refresh_data(self):")
content = content[:refresh_idx] + zoom_func + "\n    " + content[refresh_idx:]

init_vars = """
        self.main_font = self.config.get("main_font", "sans-serif")
        self.mono_font = self.config.get("mono_font", "Consolas")
        self.zoom_level = self.config.get("zoom_level", 0)
"""
content = content.replace(
    '        self.main_font = self.config.get("main_font", "sans-serif")\n        self.mono_font = self.config.get("mono_font", "Consolas")\n',
    init_vars
)

content = content.replace("System Command Monitor", "System Logs")

with open("catlogs/gui.py", "w") as f:
    f.write(content)
