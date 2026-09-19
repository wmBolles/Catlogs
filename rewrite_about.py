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

start_about = content.find("    def _show_about(self):")
end_about = content.find("    def _show_settings(self):", start_about)

new_about_shortcuts = """    def _show_about(self):
        if getattr(self, '_about_dialog', None) and self._about_dialog.winfo_exists():
            self._about_dialog.lift()
            return

        dialog = tk.Toplevel(self.root)
        self._about_dialog = dialog
        dialog.title("About")
        dialog.transient(self.root)
        dialog.geometry(f"450x450+{self.root.winfo_x() + 300}+{self.root.winfo_y() + 150}")
        dialog.resizable(False, False)
        dialog.configure(bg=self.colors["bg"])

        main_frame = ttk.Frame(dialog)
        main_frame.pack(fill=tk.BOTH, expand=True)

        if getattr(self, '_help_photo', None):
            ttk.Label(main_frame, image=self._help_photo).pack(pady=(30, 10))

        ttk.Label(main_frame, text="CatLogs", font=(self.main_font, 18, "bold")).pack()
        
        from . import __version__
        ttk.Label(main_frame, text=f"{__version__}", font=(self.main_font, 12)).pack(pady=(0, 10))

        ttk.Label(main_frame, text="View and search system logs securely.", font=(self.main_font, 10)).pack()
        
        def open_web(e):
            import webbrowser
            webbrowser.open("https://catlogs.wassim.tech/")
            
        link = tk.Label(main_frame, text="Website", font=(self.main_font, 10), 
                        fg="#3584e4", bg=self.colors["bg"], cursor="hand2")
        link.pack(pady=(5, 10))
        link.bind("<Button-1>", open_web)

        ttk.Label(main_frame, text="Copyright © 2026 Wassim\\nDeveloped by https://github.com/wmBolles", justify=tk.CENTER, font=(self.main_font, 9)).pack(pady=(10, 5))
        ttk.Label(main_frame, text="This program comes with absolutely no warranty.", justify=tk.CENTER, font=(self.main_font, 8)).pack()

    def _show_shortcuts(self):
        if getattr(self, '_shortcuts_dialog', None) and self._shortcuts_dialog.winfo_exists():
            self._shortcuts_dialog.lift()
            return

        dialog = tk.Toplevel(self.root)
        self._shortcuts_dialog = dialog
        dialog.title("Shortcuts")
        dialog.transient(self.root)
        dialog.geometry(f"600x400+{self.root.winfo_x() + 200}+{self.root.winfo_y() + 150}")
        dialog.resizable(False, False)
        dialog.configure(bg=self.colors["bg"])

        main_frame = ttk.Frame(dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10)

        ttk.Label(left_frame, text="General", font=(self.main_font, 12, "bold")).pack(anchor="w", pady=(0, 15))
        ttk.Label(right_frame, text="Application", font=(self.main_font, 12, "bold")).pack(anchor="w", pady=(0, 15))

        def add_shortcut(parent, keys, desc):
            f = ttk.Frame(parent)
            f.pack(fill=tk.X, pady=8)
            for key in keys:
                if key == "+":
                    ttk.Label(f, text="+").pack(side=tk.LEFT, padx=5)
                else:
                    k = tk.Label(f, text=key, font=(self.main_font, 9), bg="#444", fg="white", relief="solid", borderwidth=1, padx=6, pady=2)
                    k.pack(side=tk.LEFT)
            ttk.Label(f, text=desc).pack(side=tk.LEFT, padx=15)

        add_shortcut(left_frame, ["F5"], "Refresh data")
        add_shortcut(left_frame, ["Esc"], "Clear all filters")
        add_shortcut(left_frame, ["Ctrl", "+", "?"], "Keyboard shortcuts")
        add_shortcut(left_frame, ["Ctrl", "+", "+"], "Zoom in")
        add_shortcut(left_frame, ["Ctrl", "+", "-"], "Zoom out")

        add_shortcut(right_frame, ["Ctrl", "+", "E"], "Export logs to a file")
        add_shortcut(right_frame, ["Ctrl", "+", "R"], "Refresh data")
        add_shortcut(right_frame, ["Ctrl", "+", "Q"], "Quit application")

"""

content = content[:start_about] + new_about_shortcuts + content[end_about:]

old_header = """        ttk.Button(inner, text="ℹ", style="Icon.TButton", width=3,
                   command=self._show_about).pack(side=tk.RIGHT, padx=(4, 0))"""
new_header = """        ttk.Button(inner, text="ℹ", style="Icon.TButton", width=3,
                   command=self._show_about).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(inner, text="⌨", style="Icon.TButton", width=3,
                   command=self._show_shortcuts).pack(side=tk.RIGHT, padx=(4, 0))"""

content = content.replace(old_header, new_header)

with open("catlogs/gui.py", "w") as f:
    f.write(content)
