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

import sys
import os
from PIL import Image, ImageTk
import tkinter as tk

root = tk.Tk()
base = os.path.dirname(os.path.abspath('catlogs/gui.py'))
base = os.path.dirname(base)
help_pic = os.path.join(base, "icon", "icon-removebg.png")
print("Trying to load:", help_pic)
if os.path.exists(help_pic):
    try:
        h_img = Image.open(help_pic)
        h_img.thumbnail((200, 200), Image.LANCZOS)
        help_photo = ImageTk.PhotoImage(h_img)
        print("Success!")
    except Exception as e:
        print("Error:", e)
else:
    print("Does not exist")
