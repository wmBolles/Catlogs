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

import tkinter as tk
from tkinter import ttk


class MultiSelectMenu(ttk.Menubutton):
    def __init__(self, parent, title="Select", on_change=None, **kwargs):
        super().__init__(parent, text=title, **kwargs)
        self.title_prefix = title
        self.on_change = on_change

        self.menu = tk.Menu(self, tearoff=0)
        self["menu"] = self.menu

        self.items = []
        self.vars = {}

    def set_items(self, items, selected=None):
        self.menu.delete(0, tk.END)
        self.items = items

        if selected is None:
            selected = []

        self.menu.add_command(label="Clear Exclusions", command=self.clear_all)
        self.menu.add_command(label="Exclude All", command=self.select_all)
        self.menu.add_separator()

        new_vars = {}
        for item in items:
            var = tk.BooleanVar(value=(item in selected))
            var.trace_add("write", lambda *_: self._update_label())
            new_vars[item] = var
            self.menu.add_checkbutton(label=item, variable=var)

        self.vars = new_vars
        self._update_label()

    def clear_all(self):
        for var in self.vars.values():
            var.set(False)
        self._update_label()

    def select_all(self):
        for var in self.vars.values():
            var.set(True)
        self._update_label()

    def _update_label(self):
        excluded = self.get_excluded()
        if not excluded:
            self.configure(text=f"{self.title_prefix}: All")
        elif len(excluded) == 1:
            self.configure(text=f"{self.title_prefix}: -{excluded[0]}")
        else:
            self.configure(
                text=f"{self.title_prefix}: {len(excluded)} excluded")

        if self.on_change:
            self.on_change()

    def get_excluded(self):
        return [item for item, var in self.vars.items() if var.get()]

    def get_included(self):
        return [item for item, var in self.vars.items() if not var.get()]
