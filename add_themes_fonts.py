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

new_themes = """
    "tokyo_night": {
        "bg": "#1a1b26", "bg_secondary": "#24283b", "bg_table": "#1f2335",
        "fg": "#a9b1d6", "fg_secondary": "#c0caf5", "accent": "#7aa2f7",
        "header_bg": "#16161e", "btn_bg": "#414868", "btn_fg": "#c0caf5",
        "border": "#292e42", "row_even": "#1f2335", "row_odd": "#1a1b26",
        "select_bg": "#364a82", "select_fg": "#c0caf5", "nav_bg": "#1a1b26", "nav_active": "#24283b"
    },
    "catppuccin": {
        "bg": "#1e1e2e", "bg_secondary": "#181825", "bg_table": "#1e1e2e",
        "fg": "#cdd6f4", "fg_secondary": "#bac2de", "accent": "#89b4fa",
        "header_bg": "#11111b", "btn_bg": "#313244", "btn_fg": "#cdd6f4",
        "border": "#313244", "row_even": "#1e1e2e", "row_odd": "#181825",
        "select_bg": "#585b70", "select_fg": "#cdd6f4", "nav_bg": "#1e1e2e", "nav_active": "#181825"
    },
    "synthwave": {
        "bg": "#262335", "bg_secondary": "#1f1d2e", "bg_table": "#262335",
        "fg": "#f0f0f0", "fg_secondary": "#ff7edb", "accent": "#36f9f6",
        "header_bg": "#241b2f", "btn_bg": "#2a2139", "btn_fg": "#f0f0f0",
        "border": "#34294f", "row_even": "#262335", "row_odd": "#1f1d2e",
        "select_bg": "#4954e8", "select_fg": "#ffffff", "nav_bg": "#262335", "nav_active": "#1f1d2e"
    },
    "oceanic": {
        "bg": "#1b2b34", "bg_secondary": "#17252c", "bg_table": "#1b2b34",
        "fg": "#d8dee9", "fg_secondary": "#cdd3de", "accent": "#6699cc",
        "header_bg": "#121b21", "btn_bg": "#343d46", "btn_fg": "#d8dee9",
        "border": "#4f5b66", "row_even": "#1b2b34", "row_odd": "#17252c",
        "select_bg": "#4f5b66", "select_fg": "#ffffff", "nav_bg": "#1b2b34", "nav_active": "#17252c"
    },
    "github_dark": {
        "bg": "#0d1117", "bg_secondary": "#010409", "bg_table": "#0d1117",
        "fg": "#c9d1d9", "fg_secondary": "#8b949e", "accent": "#58a6ff",
        "header_bg": "#161b22", "btn_bg": "#21262d", "btn_fg": "#c9d1d9",
        "border": "#30363d", "row_even": "#0d1117", "row_odd": "#010409",
        "select_bg": "#388bfd", "select_fg": "#ffffff", "nav_bg": "#0d1117", "nav_active": "#010409"
    },
    "material_palenight": {
        "bg": "#292d3e", "bg_secondary": "#202331", "bg_table": "#292d3e",
        "fg": "#a6accd", "fg_secondary": "#676e95", "accent": "#82aaff",
        "header_bg": "#1b1e2b", "btn_bg": "#32374d", "btn_fg": "#a6accd",
        "border": "#444267", "row_even": "#292d3e", "row_odd": "#202331",
        "select_bg": "#444267", "select_fg": "#ffffff", "nav_bg": "#292d3e", "nav_active": "#202331"
    }
}"""

content = content.replace("    }\n}\n", "    },\n" + new_themes[1:] + "\n")

old_main_fonts = 'values=["sans-serif", "Arial", "Helvetica", "Ubuntu", "DejaVu Sans", "Segoe UI", "Roboto", "Open Sans", "Tahoma"]'
new_main_fonts = 'values=["sans-serif", "Arial", "Helvetica", "Ubuntu", "DejaVu Sans", "Segoe UI", "Roboto", "Open Sans", "Tahoma", "Noto Sans", "Liberation Sans", "Cantarell", "Fira Sans", "Droid Sans", "Inter"]'

old_mono_fonts = 'values=["Consolas", "monospace", "Courier New", "DejaVu Sans Mono", "Ubuntu Mono", "Fira Code", "JetBrains Mono", "Hack", "Cascadia Code"]'
new_mono_fonts = 'values=["Consolas", "monospace", "Courier New", "DejaVu Sans Mono", "Ubuntu Mono", "Fira Code", "JetBrains Mono", "Hack", "Cascadia Code", "Inconsolata", "Source Code Pro", "Anonymous Pro", "Droid Sans Mono", "Liberation Mono", "Bitstream Vera Sans Mono"]'

content = content.replace(old_main_fonts, new_main_fonts)
content = content.replace(old_mono_fonts, new_mono_fonts)

with open("catlogs/gui.py", "w") as f:
    f.write(content)
