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

old_set_icon = """    def _set_icon(self):
        icon_path = _get_icon_path()
        if not icon_path:
            return
        try:

            from PIL import Image, ImageTk
            img = Image.open(icon_path)
            img = img.resize((64, 64), Image.LANCZOS)
            self._icon_photo = ImageTk.PhotoImage(img)
            self.root.iconphoto(True, self._icon_photo)
        except ImportError:"""

new_set_icon = """    def _set_icon(self):
        icon_path = _get_icon_path()
        if not icon_path:
            return
        try:
            from PIL import Image, ImageTk
            img = Image.open(icon_path)
            img_64 = img.resize((64, 64), Image.LANCZOS)
            self._icon_photo = ImageTk.PhotoImage(img_64)
            self.root.iconphoto(True, self._icon_photo)
            
            img_32 = img.resize((32, 32), Image.LANCZOS)
            self._icon_photo_small = ImageTk.PhotoImage(img_32)
            
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            help_pic = os.path.join(base, "icon", "icon-removebg.png")
            if os.path.exists(help_pic):
                h_img = Image.open(help_pic)
                h_img.thumbnail((200, 200), Image.LANCZOS)
                self._help_photo = ImageTk.PhotoImage(h_img)
            else:
                self._help_photo = None
        except ImportError:"""

content = content.replace(old_set_icon, new_set_icon)

old_build_header = """    def _build_header(self, parent):
        header = ttk.Frame(parent, style="Toolbar.TFrame")
        header.pack(fill=tk.X)

        inner = ttk.Frame(header, style="Toolbar.TFrame")
        inner.pack(fill=tk.X, padx=14, pady=(10, 6))

        ttk.Button(inner, text="⚙", style="Icon.TButton", width=3,
                   command=self._show_settings).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(inner, text="ℹ", style="Icon.TButton", width=3,
                   command=self._show_about).pack(side=tk.RIGHT, padx=(4, 0))"""

new_build_header = """    def _build_header(self, parent):
        header = ttk.Frame(parent, style="Toolbar.TFrame")
        header.pack(fill=tk.X)

        inner = ttk.Frame(header, style="Toolbar.TFrame")
        inner.pack(fill=tk.X, padx=14, pady=(10, 6))

        if getattr(self, '_icon_photo_small', None):
            ttk.Label(inner, image=self._icon_photo_small, style="Toolbar.TLabel").pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(inner, text="⚙", style="Icon.TButton", width=3,
                   command=self._show_settings).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(inner, text="ℹ", style="Icon.TButton", width=3,
                   command=self._show_about).pack(side=tk.RIGHT, padx=(4, 0))"""

content = content.replace(old_build_header, new_build_header)

with open("catlogs/gui.py", "w") as f:
    f.write(content)
