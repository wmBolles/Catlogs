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

target = "mono_font_combo.pack(anchor=tk.W)"

settings_checkbox = """mono_font_combo.pack(anchor=tk.W)

        ttk.Separator(theme_card, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=16)
        
        ttk.Label(theme_card, text="Security & Protection:", font=(self.main_font, 11, "bold"),
                  background=self.colors["bg_secondary"]).pack(anchor=tk.W, pady=(0, 4))
                  
        prot_frame = ttk.Frame(theme_card, style="Toolbar.TFrame")
        prot_frame.pack(fill=tk.X, anchor=tk.W)
        self.prot_mode_var = tk.BooleanVar(value=self.config.get("protection_mode", True))
        
        def save_prot_mode():
            self.config["protection_mode"] = self.prot_mode_var.get()
            from .config import save_config
            save_config(self.config)
            
        cb = ttk.Checkbutton(prot_frame, text="Enable Protection Mode (Prevents log deletion)",
                        variable=self.prot_mode_var, command=save_prot_mode)
        cb.pack(side=tk.LEFT)
"""

content = content.replace(target, settings_checkbox)

with open("catlogs/gui.py", "w") as f:
    f.write(content)
