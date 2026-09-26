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

# Add security_frame
content = content.replace(
    'appearance_frame = ttk.Frame(content_container)',
    'appearance_frame = ttk.Frame(content_container)\n        security_frame = ttk.Frame(content_container)'
)

# Update switch_tab
switch_tab_old = """
        def switch_tab(tab_name):
            if tab_name == "paths":
                appearance_frame.pack_forget()
                paths_frame.pack(fill=tk.BOTH, expand=True)
                btn_tab_paths.configure(style="NavActive.TButton")
                btn_tab_appearance.configure(style="Nav.TButton")
            else:
                paths_frame.pack_forget()
                appearance_frame.pack(fill=tk.BOTH, expand=True)
                btn_tab_paths.configure(style="Nav.TButton")
                btn_tab_appearance.configure(style="NavActive.TButton")
"""

switch_tab_new = """
        def switch_tab(tab_name):
            paths_frame.pack_forget()
            appearance_frame.pack_forget()
            security_frame.pack_forget()
            btn_tab_paths.configure(style="Nav.TButton")
            btn_tab_appearance.configure(style="Nav.TButton")
            btn_tab_security.configure(style="Nav.TButton")
            
            if tab_name == "paths":
                paths_frame.pack(fill=tk.BOTH, expand=True)
                btn_tab_paths.configure(style="NavActive.TButton")
            elif tab_name == "appearance":
                appearance_frame.pack(fill=tk.BOTH, expand=True)
                btn_tab_appearance.configure(style="NavActive.TButton")
            else:
                security_frame.pack(fill=tk.BOTH, expand=True)
                btn_tab_security.configure(style="NavActive.TButton")
"""
content = content.replace(switch_tab_old.strip(), switch_tab_new.strip())

# Add btn_tab_security
btn_appearance_code = 'btn_tab_appearance.pack(side=tk.LEFT)'
btn_security_code = """btn_tab_appearance.pack(side=tk.LEFT, padx=(0, 6))

        btn_tab_security = ttk.Button(tab_nav_frame, text="🔒 Security", style="Nav.TButton",
                                        command=lambda: switch_tab("security"))
        btn_tab_security.pack(side=tk.LEFT)"""
content = content.replace(btn_appearance_code, btn_security_code)

# Add security content right before BOTTOM SAVE & CANCEL BAR
bottom_bar_comment = "# BOTTOM SAVE & CANCEL BAR"
security_content = """        # -------------------------------------------------------------------
        # TAB 3: SECURITY
        # -------------------------------------------------------------------
        sec_header = ttk.Frame(security_frame)
        sec_header.pack(fill=tk.X, pady=(0, 16))

        ttk.Label(sec_header, text="Security & Protection",
                  font=(self.main_font, 12, "bold")).pack(anchor=tk.W)
        ttk.Label(sec_header, text="Manage application security settings.",
                  font=(self.main_font, 9), foreground=self.colors["fg_dim"]).pack(anchor=tk.W, pady=(2, 0))

        sec_card = ttk.Frame(security_frame, style="Toolbar.TFrame", padding=20)
        sec_card.pack(fill=tk.X, pady=(0, 16))

        ttk.Label(sec_card, text="Protection Mode:", font=(self.main_font, 11, "bold"),
                  background=self.colors["bg_secondary"]).pack(anchor=tk.W, pady=(0, 4))
                  
        prot_frame = ttk.Frame(sec_card, style="Toolbar.TFrame")
        prot_frame.pack(fill=tk.X, anchor=tk.W)
        self.prot_mode_var = tk.BooleanVar(value=self.config.get("protection_mode", True))
        
        def save_prot_mode():
            self.config["protection_mode"] = self.prot_mode_var.get()
            from .config import save_config
            save_config(self.config)
            
        cb = ttk.Checkbutton(prot_frame, text="Enable Protection Mode (Prevents log deletion)",
                        variable=self.prot_mode_var, command=save_prot_mode)
        cb.pack(side=tk.LEFT)

        # """
content = content.replace(
    bottom_bar_comment, security_content + bottom_bar_comment)

with open("catlogs/gui.py", "w") as f:
    f.write(content)
