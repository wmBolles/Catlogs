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

import os
import getpass
import signal
import subprocess
import threading
from typing import List, Optional
from datetime import datetime
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ModuleNotFoundError:  # pragma: no cover - GUI-only environment
    tk = None
    ttk = None
    filedialog = None
    messagebox = None

from . import __version__
from .safe_exec import build_command_preview_args
from .models import CommandEntry
from .collectors import collect_all
from .exporter import export_to_csv, generate_default_filename, export_audit_report_pdf, generate_default_pdf_filename
from .config import load_config, save_config, load_log_paths, save_log_paths, get_default_log_paths, check_path_status
from .export_log import log_export, load_export_history, clear_export_history
from .read_errors import load_read_errors, clear_read_errors
from .log_parsers import LOG_FORMAT_CHOICES, detect_log_type, parse_log_file
from .process_monitor import parse_process_snapshot
from .scanner import create_scan_session, add_scan_finding, list_findings, scan_directory
from .updater import check_for_update, fetch_latest_version, get_update_state, install_local_update


class MultiSelectMenu(ttk.Button):
    def __init__(self, parent, title="Select", on_change=None, **kwargs):
        super().__init__(parent, text=title, command=self.toggle_popup, **kwargs)
        self.title_prefix = title
        self.on_change = on_change

        self.items = []
        self.selected_items = set()
        self.popup = None

    def set_items(self, items, selected=None):
        self.items = items
        self.selected_items = set(selected or [])
        self._update_label(notify=False)

    def toggle_popup(self):
        if self.popup:
            self.close_popup()
        else:
            self.show_popup()

    def show_popup(self):
        self.popup = tk.Toplevel(self)
        self.popup.wm_overrideredirect(True)

        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        self.popup.wm_geometry(f"+{x}+{y}")

        # Use theme-aware colors from the root app
        try:
            app_root = self.winfo_toplevel()
            popup_bg = app_root.cget("bg")
        except Exception:
            popup_bg = "#ffffff"
        popup_border = "#888888"

        frame = tk.Frame(self.popup, bd=1, relief=tk.SOLID, bg=popup_border)
        frame.pack(fill=tk.BOTH, expand=True)

        btn_frame = tk.Frame(frame, bg=popup_bg)
        btn_frame.pack(fill=tk.X, padx=2, pady=2)
        ttk.Button(btn_frame, text="Clear Excl",
                   command=self.clear_all, width=10).pack(side=tk.LEFT, padx=1)
        ttk.Button(btn_frame, text="Excl All", command=self.select_all,
                   width=10).pack(side=tk.LEFT, padx=1)

        list_frame = tk.Frame(frame, bg=popup_bg)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        self.listbox = tk.Listbox(
            list_frame, selectmode=tk.MULTIPLE, height=12, width=25, exportselection=False)
        scrollbar = ttk.Scrollbar(
            list_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)

        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for i, item in enumerate(self.items):
            self.listbox.insert(tk.END, item)
            if item in self.selected_items:
                self.listbox.selection_set(i)

        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        self.popup.grab_set()
        self.popup.bind("<ButtonPress-1>", self._on_click_outside)
        self.listbox.focus_set()

    def _on_click_outside(self, event):
        x, y = event.x_root, event.y_root
        x0 = self.popup.winfo_rootx()
        y0 = self.popup.winfo_rooty()
        x1 = x0 + self.popup.winfo_width()
        y1 = y0 + self.popup.winfo_height()

        if not (x0 <= x <= x1 and y0 <= y <= y1):
            self.close_popup()

    def close_popup(self):
        if self.popup:
            if hasattr(self, 'listbox') and self.listbox:
                self.listbox.unbind("<<ListboxSelect>>")
            self.popup.grab_release()
            self.popup.destroy()
            self.popup = None

    def _on_select(self, event):
        if not self.popup:
            return
        selections = self.listbox.curselection()
        self.selected_items = {self.items[i] for i in selections}
        self._update_label(notify=True)

    def clear_all(self):
        self.selected_items.clear()
        if self.popup:
            self.listbox.selection_clear(0, tk.END)
        self._update_label(notify=True)

    def select_all(self):
        self.selected_items = set(self.items)
        if self.popup:
            self.listbox.selection_set(0, tk.END)
        self._update_label(notify=True)

    def _update_label(self, notify=True):
        excluded = list(self.selected_items)
        if not excluded:
            self.configure(text=f"{self.title_prefix}")
        elif len(excluded) == 1:
            name = excluded[0]
            if len(name) > 10:
                name = name[:8] + ".."
            self.configure(text=f"{self.title_prefix} (-{name})")
        else:
            self.configure(text=f"{self.title_prefix} ({len(excluded)} excl)")

        if notify and self.on_change:
            self.on_change()

    def get_excluded(self):
        return list(self.selected_items)


THEMES = {
    "dark": {
        "bg":           "#2d2d2d",
        "bg_secondary": "#353535",
        "bg_table":     "#2d2d2d",
        "fg":           "#e0e0e0",
        "fg_dim":       "#999999",
        "accent":       "#e0e0e0",
        "accent_hover": "#ffffff",
        "success":      "#8fbf7f",
        "warning":      "#d4a846",
        "error":        "#c45050",
        "border":       "#4a4a4a",
        "select_bg":    "#404040",
        "header_bg":    "#262626",
        "btn_bg":       "#404040",
        "btn_fg":       "#e0e0e0",
        "entry_bg":     "#383838",
        "detail_bg":    "#000000",
        "nav_bg":       "#262626",
        "nav_active":   "#404040",
    },
    "light": {
        "bg":           "#f3f3f3",
        "bg_secondary": "#ffffff",
        "bg_table":     "#ffffff",
        "fg":           "#333333",
        "fg_dim":       "#666666",
        "accent":       "#005a9e",
        "accent_hover": "#0078d4",
        "success":      "#107c10",
        "warning":      "#d83b01",
        "error":        "#a80000",
        "border":       "#cccccc",
        "select_bg":    "#cce8ff",
        "header_bg":    "#e6e6e6",
        "btn_bg":       "#e1dfdd",
        "btn_fg":       "#333333",
        "entry_bg":     "#ffffff",
        "detail_bg":    "#f9f9f9",
        "nav_bg":       "#e6e6e6",
        "nav_active":   "#d0d0d0",
    },
    "dracula": {
        "bg":           "#282a36",
        "bg_secondary": "#44475a",
        "bg_table":     "#282a36",
        "fg":           "#f8f8f2",
        "fg_dim":       "#6272a4",
        "accent":       "#bd93f9",
        "accent_hover": "#ff79c6",
        "success":      "#50fa7b",
        "warning":      "#f1fa8c",
        "error":        "#ff5555",
        "border":       "#6272a4",
        "select_bg":    "#44475a",
        "header_bg":    "#21222c",
        "btn_bg":       "#6272a4",
        "btn_fg":       "#f8f8f2",
        "entry_bg":     "#44475a",
        "detail_bg":    "#282a36",
        "nav_bg":       "#21222c",
        "nav_active":   "#44475a",
    },
    "monokai": {
        "bg":           "#272822",
        "bg_secondary": "#3e3d32",
        "bg_table":     "#272822",
        "fg":           "#f8f8f2",
        "fg_dim":       "#75715e",
        "accent":       "#a6e22e",
        "accent_hover": "#fd971f",
        "success":      "#a6e22e",
        "warning":      "#e6db74",
        "error":        "#f92672",
        "border":       "#75715e",
        "select_bg":    "#49483e",
        "header_bg":    "#1e1f1c",
        "btn_bg":       "#49483e",
        "btn_fg":       "#f8f8f2",
        "entry_bg":     "#3e3d32",
        "detail_bg":    "#272822",
        "nav_bg":       "#1e1f1c",
        "nav_active":   "#49483e",
    },
    "cappuccino": {
        "bg":           "#3e2723",
        "bg_secondary": "#4e342e",
        "bg_table":     "#3e2723",
        "fg":           "#d7ccc8",
        "fg_dim":       "#a1887f",
        "accent":       "#ffb300",
        "accent_hover": "#ffe54c",
        "success":      "#81c784",
        "warning":      "#ffb74d",
        "error":        "#e57373",
        "border":       "#5d4037",
        "select_bg":    "#5d4037",
        "header_bg":    "#261410",
        "btn_bg":       "#5d4037",
        "btn_fg":       "#d7ccc8",
        "entry_bg":     "#4e342e",
        "detail_bg":    "#3e2723",
        "nav_bg":       "#261410",
        "nav_active":   "#4e342e",
    },
    "nord": {
        "bg":           "#2e3440",
        "bg_secondary": "#3b4252",
        "bg_table":     "#2e3440",
        "fg":           "#d8dee9",
        "fg_dim":       "#4c566a",
        "accent":       "#88c0d0",
        "accent_hover": "#81a1c1",
        "success":      "#a3be8c",
        "warning":      "#ebcb8b",
        "error":        "#bf616a",
        "border":       "#4c566a",
        "select_bg":    "#434c5e",
        "header_bg":    "#242933",
        "btn_bg":       "#4c566a",
        "btn_fg":       "#d8dee9",
        "entry_bg":     "#3b4252",
        "detail_bg":    "#2e3440",
        "nav_bg":       "#242933",
        "nav_active":   "#3b4252",
    },
    "solarized_dark": {
        "bg":           "#002b36",
        "bg_secondary": "#073642",
        "bg_table":     "#002b36",
        "fg":           "#839496",
        "fg_dim":       "#586e75",
        "accent":       "#2aa198",
        "accent_hover": "#268bd2",
        "success":      "#859900",
        "warning":      "#b58900",
        "error":        "#dc322f",
        "border":       "#586e75",
        "select_bg":    "#073642",
        "header_bg":    "#001f27",
        "btn_bg":       "#586e75",
        "btn_fg":       "#eee8d5",
        "entry_bg":     "#073642",
        "detail_bg":    "#002b36",
        "nav_bg":       "#001f27",
        "nav_active":   "#073642",
    },
    "gruvbox": {
        "bg":           "#282828",
        "bg_secondary": "#3c3836",
        "bg_table":     "#282828",
        "fg":           "#ebdbb2",
        "fg_dim":       "#928374",
        "accent":       "#fabd2f",
        "accent_hover": "#d79921",
        "success":      "#b8bb26",
        "warning":      "#fe8019",
        "error":        "#fb4934",
        "border":       "#665c54",
        "select_bg":    "#504945",
        "header_bg":    "#1d2021",
        "btn_bg":       "#665c54",
        "btn_fg":       "#fbf1c7",
        "entry_bg":     "#3c3836",
        "detail_bg":    "#282828",
        "nav_bg":       "#1d2021",
        "nav_active":   "#3c3836",
    },
    "tokyo_night": {
        "bg": "#1a1b26", "bg_secondary": "#24283b", "bg_table": "#1f2335",
        "fg": "#a9b1d6", "fg_secondary": "#c0caf5", "accent": "#7aa2f7",
        "header_bg": "#16161e", "btn_bg": "#414868", "btn_fg": "#c0caf5",
        "border": "#292e42", "row_even": "#1f2335", "row_odd": "#1a1b26",
        "select_bg": "#364a82", "select_fg": "#c0caf5", "nav_bg": "#1a1b26", "nav_active": "#24283b", "accent_hover": "#7aa2f7", "fg_dim": "#a9b1d6", "success": "#81c784", "warning": "#ffb74d", "error": "#e57373",
        "entry_bg": "#24283b", "detail_bg": "#1f2335"},
    "catppuccin": {
        "bg": "#1e1e2e", "bg_secondary": "#181825", "bg_table": "#1e1e2e",
        "fg": "#cdd6f4", "fg_secondary": "#bac2de", "accent": "#89b4fa",
        "header_bg": "#11111b", "btn_bg": "#313244", "btn_fg": "#cdd6f4",
        "border": "#313244", "row_even": "#1e1e2e", "row_odd": "#181825",
        "select_bg": "#585b70", "select_fg": "#cdd6f4", "nav_bg": "#1e1e2e", "nav_active": "#181825", "accent_hover": "#89b4fa", "fg_dim": "#cdd6f4", "success": "#81c784", "warning": "#ffb74d", "error": "#e57373",
        "entry_bg": "#181825", "detail_bg": "#1e1e2e"},
    "synthwave": {
        "bg": "#262335", "bg_secondary": "#1f1d2e", "bg_table": "#262335",
        "fg": "#f0f0f0", "fg_secondary": "#ff7edb", "accent": "#36f9f6",
        "header_bg": "#241b2f", "btn_bg": "#2a2139", "btn_fg": "#f0f0f0",
        "border": "#34294f", "row_even": "#262335", "row_odd": "#1f1d2e",
        "select_bg": "#4954e8", "select_fg": "#ffffff", "nav_bg": "#262335", "nav_active": "#1f1d2e", "accent_hover": "#36f9f6", "fg_dim": "#f0f0f0", "success": "#81c784", "warning": "#ffb74d", "error": "#e57373",
        "entry_bg": "#1f1d2e", "detail_bg": "#262335"},
    "oceanic": {
        "bg": "#1b2b34", "bg_secondary": "#17252c", "bg_table": "#1b2b34",
        "fg": "#d8dee9", "fg_secondary": "#cdd3de", "accent": "#6699cc",
        "header_bg": "#121b21", "btn_bg": "#343d46", "btn_fg": "#d8dee9",
        "border": "#4f5b66", "row_even": "#1b2b34", "row_odd": "#17252c",
        "select_bg": "#4f5b66", "select_fg": "#ffffff", "nav_bg": "#1b2b34", "nav_active": "#17252c", "accent_hover": "#6699cc", "fg_dim": "#d8dee9", "success": "#81c784", "warning": "#ffb74d", "error": "#e57373",
        "entry_bg": "#17252c", "detail_bg": "#1b2b34"},
    "github_dark": {
        "bg": "#0d1117", "bg_secondary": "#010409", "bg_table": "#0d1117",
        "fg": "#c9d1d9", "fg_secondary": "#8b949e", "accent": "#58a6ff",
        "header_bg": "#161b22", "btn_bg": "#21262d", "btn_fg": "#c9d1d9",
        "border": "#30363d", "row_even": "#0d1117", "row_odd": "#010409",
        "select_bg": "#388bfd", "select_fg": "#ffffff", "nav_bg": "#0d1117", "nav_active": "#010409", "accent_hover": "#58a6ff", "fg_dim": "#c9d1d9", "success": "#81c784", "warning": "#ffb74d", "error": "#e57373",
        "entry_bg": "#010409", "detail_bg": "#0d1117"},
    "material_palenight": {
        "bg": "#292d3e", "bg_secondary": "#202331", "bg_table": "#292d3e",
        "fg": "#a6accd", "fg_secondary": "#676e95", "accent": "#82aaff",
        "header_bg": "#1b1e2b", "btn_bg": "#32374d", "btn_fg": "#a6accd",
        "border": "#444267", "row_even": "#292d3e", "row_odd": "#202331",
        "select_bg": "#444267", "select_fg": "#ffffff", "nav_bg": "#292d3e", "nav_active": "#202331", "accent_hover": "#82aaff", "fg_dim": "#a6accd", "success": "#81c784", "warning": "#ffb74d", "error": "#e57373",
        "entry_bg": "#202331", "detail_bg": "#292d3e"}
}

ROW_TAG_EVEN = "row_even"
ROW_TAG_ODD = "row_odd"


def _get_icon_path():
    import sys
    base = getattr(sys, '_MEIPASS', os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    # Prefer the pre-sized 256x256 icon, fall back to full-size
    for name in ("icon_256.png", "icon.png", "icon.jpeg"):
        p = os.path.join(base, "icon", name)
        if os.path.isfile(p):
            return p
    # Check XDG system icon locations
    xdg_dirs = os.environ.get(
        "XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
    for d in xdg_dirs:
        for name in ("catlogs.png", "catlogs.jpeg"):
            p = os.path.join(d, "icons", "hicolor", "256x256", "apps", name)
            if os.path.isfile(p):
                return p
    # Also check pixmaps
    for d in xdg_dirs:
        p = os.path.join(d, "pixmaps", "catlogs.png")
        if os.path.isfile(p):
            return p
    return None


class CatLogsApp:
    COLUMNS = ("timestamp", "user", "command", "shell", "source", "pid")
    COLUMN_LABELS = {
        "timestamp": "Timestamp",
        "user":      "User",
        "command":   "Command",
        "shell":     "Shell",
        "source":    "Source",
        "pid":       "PID",
    }
    COLUMN_WIDTHS = {
        "timestamp": 170,
        "user":      110,
        "command":   460,
        "shell":     90,
        "source":    110,
        "pid":       80,
    }

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("CatLogs")
        self.root.geometry("1280x760")
        self.root.minsize(900, 520)

        self._set_icon()

        try:
            self.root.attributes('-zoomed', True)  # X11
        except tk.TclError:
            try:
                self.root.state('zoomed')  # fallback
            except tk.TclError:
                # Wayland or other — maximise by setting geometry to screen size
                try:
                    sw = self.root.winfo_screenwidth()
                    sh = self.root.winfo_screenheight()
                    self.root.geometry(f"{sw}x{sh}+0+0")
                except Exception:
                    pass

        self.all_entries: List[CommandEntry] = []
        self.filtered_entries: List[CommandEntry] = []
        self._sort_column: Optional[str] = "timestamp"
        self._sort_reverse: bool = True
        self._current_page: str = "logs"
        self._max_tabs = 0
        self._custom_tab_pages = {}
        self._custom_tab_order = []
        self._custom_tab_buttons = {}
        self._custom_tab_close_buttons = {}
        self._header_plus_button = None
        self._process_refresh_lock = False
        self._last_process_rows_signature = None
        self._last_system_summary = None

        self.config = load_config()
        self.current_theme = self.config.get("theme", "dark")
        self.colors = THEMES.get(self.current_theme, THEMES["dark"])

        self.main_font = self.config.get("main_font", "sans-serif")
        self.mono_font = self.config.get("mono_font", "monospace")
        self.zoom_level = self.config.get("zoom_level", 0)

        self._build_ui()
        self._apply_theme()
        self._bind_shortcuts()

        if self.config.get("first_run", True):
            self.root.after(100, self._show_first_run_dialog)
        elif not self.config.get("window_feature_shown", False):
            self.root.after(100, self._show_window_feature_dialog)
            self._refresh_data()
        else:
            self._refresh_data()

        # Check for updates in the background
        self._update_bar = None
        self.root.after(2000, self._check_for_update)

    def _check_for_update(self):
        """Start background update check."""
        def _on_update_available(latest_version):
            self.root.after(0, lambda: self._show_update_bar(latest_version))
        check_for_update(callback=_on_update_available)

    def _show_update_bar(self, latest_version):
        """Show a non-intrusive update notification bar at the top."""
        if self._update_bar is not None:
            return
        c = self.colors
        self._update_bar = tk.Frame(
            self.root, bg=c.get("warning", "#d4a846"), height=32)
        self._update_bar.pack(fill=tk.X, before=self.root.winfo_children()[0])
        self._update_bar.pack_propagate(False)

        from . import __version__
        msg = f"  [Up] CatLogs {latest_version} is available (you have {__version__}). Visit catlogs.wassim.tech/download.html to update."
        tk.Label(
            self._update_bar, text=msg,
            bg=c.get("warning", "#d4a846"), fg="#000000",
            font=(self.main_font, 10), anchor="w"
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)

        dismiss_btn = tk.Label(
            self._update_bar, text="✕",
            bg=c.get("warning", "#d4a846"), fg="#000000",
            font=(self.main_font, 12, "bold"), cursor="hand2",
            bd=0, relief=tk.FLAT, padx=8, pady=2
        )
        dismiss_btn.pack(side=tk.RIGHT, padx=(8, 12))
        dismiss_btn.bind("<Button-1>", lambda e: self._dismiss_update_bar())

    def _dismiss_update_bar(self):
        """Dismiss the update notification bar."""
        if self._update_bar:
            self._update_bar.destroy()
            self._update_bar = None

    def _check_for_update_from_settings(self, status_var=None, latest_var=None):
        """Perform a manual update check from the Settings dialog."""
        if status_var is not None:
            status_var.set("Checking latest release...")
        if latest_var is not None:
            latest_var.set("Checking...")

        try:
            latest = fetch_latest_version()
            if latest is None:
                if latest_var is not None:
                    latest_var.set("Unavailable")
                if status_var is not None:
                    status_var.set("The update server could not be reached right now.")
                return

            if latest_var is not None:
                latest_var.set(latest)

            state = get_update_state(__version__, latest)
            if state["available"]:
                result = install_local_update(
                    repo_root=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    base_url="https://catlogs.wassim.tech",
                )
                if status_var is not None:
                    status_var.set(result.get("message", f"Update {latest} is available."))
                if result.get("updated"):
                    if latest_var is not None:
                        latest_var.set(latest)
                return

            if status_var is not None:
                status_var.set("You are already on the latest version available.")
        except Exception as exc:  # pragma: no cover - GUI-specific error path
            if latest_var is not None:
                latest_var.set("Unavailable")
            if status_var is not None:
                status_var.set(f"Update check failed: {exc}")

    def _set_icon(self):
        icon_path = _get_icon_path()
        if not icon_path:
            return

        # Pre-initialise so the rest of the UI never hits AttributeError
        self._icon_photo = None
        self._icon_photo_small = None
        self._help_photo = None

        try:
            from PIL import Image, ImageTk
            img = Image.open(icon_path)

            # Provide multiple sizes so every WM/DE picks the right one
            icon_sizes = []
            for sz in (16, 24, 32, 48, 64, 128, 256):
                resized = img.resize((sz, sz), Image.LANCZOS)
                icon_sizes.append(ImageTk.PhotoImage(resized))
            self._icon_photos_all = icon_sizes  # prevent garbage-collection
            self.root.iconphoto(True, *icon_sizes)

            self._icon_photo = icon_sizes[4]        # 64x64
            self._icon_photo_small = icon_sizes[2]  # 32x32
        except ImportError:
            try:
                if not icon_path.lower().endswith(('.png', '.gif', '.ppm', '.pgm')):
                    return  # Tk PhotoImage can't load JPEG without PIL
                self._icon_photo = tk.PhotoImage(file=icon_path)
                self.root.iconphoto(True, self._icon_photo)
                # Create a smaller version for the header
                w = self._icon_photo.width()
                if w > 0:
                    factor = max(1, w // 32)
                    self._icon_photo_small = self._icon_photo.subsample(
                        factor, factor)
            except tk.TclError:
                pass
        except Exception:
            pass

        # Load help/about illustration independently so it survives
        # even if the main icon loading above failed.
        try:
            import sys
            base = getattr(sys, '_MEIPASS', os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))))
            help_pic = os.path.join(base, "icon", "icon-removebg.png")
            if os.path.exists(help_pic):
                try:
                    from PIL import Image, ImageTk
                    h_img = Image.open(help_pic)
                    h_img.thumbnail((200, 200), Image.LANCZOS)
                    self._help_photo = ImageTk.PhotoImage(h_img)
                except ImportError:
                    try:
                        temp_photo = tk.PhotoImage(file=help_pic)
                        w = temp_photo.width()
                        if w > 0:
                            factor = max(1, w // 200)
                            self._help_photo = temp_photo.subsample(
                                factor, factor)
                    except tk.TclError:
                        pass
        except Exception:
            pass

    def _apply_theme(self):
        self.colors = THEMES.get(self.current_theme, THEMES["dark"])
        c = self.colors

        zl = getattr(self, "zoom_level", 0)
        def fs(base): return max(6, base + zl)

        self.root.configure(bg=c["bg"])

        style = ttk.Style()
        style.theme_use("clam")

        style.configure("TFrame", background=c["bg"])
        style.configure("TLabel", background=c["bg"], foreground=c["fg"],
                        font=(self.main_font, fs(10)))

        style.configure("Toolbar.TFrame", background=c["bg_secondary"])
        style.configure("Toolbar.TLabel", background=c["bg_secondary"],
                        foreground=c["fg"], font=(self.main_font, fs(10)))

        style.configure("Nav.TFrame", background=c["nav_bg"])
        style.configure("Nav.TLabel", background=c["nav_bg"],
                        foreground=c["fg"], font=(self.main_font, fs(10)))

        style.configure("TButton", background=c["btn_bg"], foreground=c["btn_fg"],
                        font=(self.main_font, fs(10)), borderwidth=0, padding=(12, 5))
        style.map("TButton",
                  background=[("active", c["accent"]),
                              ("pressed", c["accent_hover"])],
                  foreground=[("active", c["header_bg"])])

        style.configure("Accent.TButton", background=c["accent"],
                        foreground=c["header_bg"], font=(
                            self.main_font, fs(10), "bold"),
                        padding=(14, 5))
        style.map("Accent.TButton",
                  background=[("active", c["accent_hover"])])

        style.configure("Icon.TButton", background=c["bg_secondary"], foreground=c["accent"],
                        font=(self.main_font, fs(14)), borderwidth=0, padding=(8, 2))
        style.map("Icon.TButton",
                  background=[("active", c["border"])],
                  foreground=[("active", c["accent_hover"])])

        style.configure("Nav.TButton", background=c["nav_bg"], foreground=c["fg"],
                        font=(self.main_font, fs(10)), borderwidth=0, padding=(14, 8))
        style.map("Nav.TButton",
                  background=[("active", c["nav_active"])],
                  foreground=[("active", c["accent"])])

        style.configure("TabPanel.TButton", background=c["bg_secondary"], foreground=c["fg"],
                        font=(self.main_font, fs(10)), borderwidth=0, padding=(12, 8))
        style.map("TabPanel.TButton",
                  background=[("active", c["bg_table"])],
                  foreground=[("active", c["accent"])])

        style.configure("NavActive.TButton", background=c["nav_active"], foreground=c["accent"],
                        font=(self.main_font, fs(10), "bold"), borderwidth=0, padding=(14, 8))
        style.map("NavActive.TButton",
                  background=[("active", c["nav_active"])])

        style.configure("TabPanelActive.TButton", background=c["bg_table"], foreground=c["accent"],
                        font=(self.main_font, fs(10), "bold"), borderwidth=0, padding=(12, 8))
        style.map("TabPanelActive.TButton",
                  background=[("active", c["bg_table"])])

        style.configure("TCombobox", fieldbackground=c["entry_bg"],
                        background=c["btn_bg"], foreground=c["fg"],
                        arrowcolor=c["fg"], borderwidth=1)
        style.map("TCombobox",
                  fieldbackground=[("readonly", c["entry_bg"]),
                                   ("focus", c["entry_bg"])],
                  foreground=[("readonly", c["fg"]), ("focus", c["fg"])],
                  selectbackground=[("readonly", c["select_bg"]),
                                    ("focus", c["select_bg"])],
                  selectforeground=[("readonly", c["fg"]), ("focus", c["fg"])])

        style.configure("TEntry", fieldbackground=c["entry_bg"],
                        foreground=c["fg"], insertcolor=c["fg"],
                        borderwidth=1)

        style.configure("Treeview",
                        background=c["bg_table"],
                        foreground=c["fg"],
                        fieldbackground=c["bg_table"],
                        borderwidth=0,
                        rowheight=max(20, 26 + zl * 2),
                        font=(self.main_font, fs(10)))
        style.configure("Treeview.Heading",
                        background=c["header_bg"],
                        foreground=c["accent"],
                        font=(self.main_font, fs(10), "bold"),
                        borderwidth=0,
                        relief="flat")
        style.map("Treeview",
                  background=[("selected", c["select_bg"])],
                  foreground=[("selected", "#000000")])
        style.map("Treeview.Heading",
                  background=[("active", c["border"])])

        self.tree.tag_configure(ROW_TAG_EVEN, background=c["bg_table"])
        self.tree.tag_configure(ROW_TAG_ODD, background=c["bg_secondary"])

        style.configure("Detail.TLabelframe", background=c["bg_secondary"],
                        foreground=c["accent"], borderwidth=1,
                        relief="solid")
        style.configure("Detail.TLabelframe.Label", background=c["bg_secondary"],
                        foreground=c["accent"], font=(self.main_font, fs(11), "bold"))

        style.configure("TSeparator", background=c["border"])

        style.configure("Horizontal.TProgressbar", background=c["accent"],
                        troughcolor=c["bg_secondary"], borderwidth=0)

        style.configure("Vertical.TScrollbar", background=c["btn_bg"],
                        troughcolor=c["bg_secondary"], borderwidth=0,
                        arrowcolor=c["fg"])
        style.configure("Horizontal.TScrollbar", background=c["btn_bg"],
                        troughcolor=c["bg_secondary"], borderwidth=0,
                        arrowcolor=c["fg"])

        self.details_text.configure(
            bg=c["detail_bg"], fg=c["fg"], font=(self.mono_font, fs(11)),
            insertbackground=c["fg"],
            selectbackground=c["accent"],
            selectforeground="#000000"
        )
        self.details_text.tag_configure(
            "label", foreground=c["accent"], font=(self.mono_font, fs(11), "bold"))
        self.details_text.tag_configure(
            "value", foreground=c["fg"], font=(self.mono_font, fs(11)))
        self.details_text.tag_configure(
            "placeholder", foreground=c["fg_dim"], font=(self.mono_font, fs(11), "italic"))
        self.details_text.tag_raise("sel")

        self.output_text.configure(
            bg=c["detail_bg"], fg=c["fg"], font=(self.mono_font, fs(10)),
            insertbackground=c["fg"],
            selectbackground=c["accent"],
            selectforeground="#000000"
        )
        self.output_text.tag_configure(
            "label", foreground=c["accent"], font=(self.mono_font, fs(11), "bold"))
        self.output_text.tag_configure(
            "output", foreground=c["fg"], font=(self.mono_font, fs(10)))
        self.output_text.tag_configure(
            "error", foreground=c["error"], font=(self.mono_font, fs(10)))
        self.output_text.tag_configure(
            "placeholder", foreground=c["fg_dim"], font=(self.mono_font, fs(11), "italic"))
        self.output_text.tag_configure(
            "info", foreground=c["warning"], font=(self.mono_font, fs(10), "italic"))
        self.output_text.tag_raise("sel")

        if hasattr(self, 'expected_output_text'):
            self.expected_output_text.configure(
                bg=c["detail_bg"], fg=c["fg"], font=(self.mono_font, fs(10)),
                insertbackground=c["fg"],
                selectbackground=c["accent"],
                selectforeground="#000000"
            )
            self.expected_output_text.tag_configure(
                "label", foreground=c["accent"], font=(self.mono_font, fs(11), "bold"))
            self.expected_output_text.tag_configure(
                "output", foreground=c["fg"], font=(self.mono_font, fs(10)))
            self.expected_output_text.tag_configure(
                "error", foreground=c["error"], font=(self.mono_font, fs(10)))
            self.expected_output_text.tag_configure(
                "placeholder", foreground=c["fg_dim"], font=(self.mono_font, fs(11), "italic"))
            self.expected_output_text.tag_configure(
                "info", foreground=c["warning"], font=(self.mono_font, fs(10), "italic"))
            self.expected_output_text.tag_raise("sel")

        self.export_history_text.configure(
            bg=c["bg_table"], fg=c["fg"], font=(self.mono_font, fs(11)),
            insertbackground=c["fg"],
            selectbackground=c["accent"],
            selectforeground="#000000"
        )
        self.export_history_text.tag_configure(
            "header", foreground=c["accent"], font=(self.mono_font, fs(12), "bold"))
        self.export_history_text.tag_configure(
            "label", foreground=c["accent"], font=(self.mono_font, fs(11), "bold"))
        self.export_history_text.tag_configure(
            "value", foreground=c["fg"], font=(self.mono_font, fs(11)))
        self.export_history_text.tag_configure(
            "dim", foreground=c["fg_dim"], font=(self.mono_font, fs(10), "italic"))
        self.export_history_text.tag_configure(
            "separator", foreground=c["border"], font=(self.mono_font, fs(10)))
        self.export_history_text.tag_raise("sel")

        self.read_errors_text.configure(
            bg=c["bg_table"], fg=c["fg"], font=(self.mono_font, fs(11)),
            insertbackground=c["fg"],
            selectbackground=c["accent"],
            selectforeground="#000000"
        )
        self.read_errors_text.tag_configure(
            "header", foreground=c["accent"], font=(self.mono_font, fs(12), "bold"))
        self.read_errors_text.tag_configure(
            "label", foreground=c["accent"], font=(self.mono_font, fs(11), "bold"))
        self.read_errors_text.tag_configure(
            "value", foreground=c["fg"], font=(self.mono_font, fs(11)))
        self.read_errors_text.tag_configure(
            "error_text", foreground=c["error"], font=(self.mono_font, fs(10)))
        self.read_errors_text.tag_configure(
            "dim", foreground=c["fg_dim"], font=(self.mono_font, fs(10), "italic"))
        self.read_errors_text.tag_configure(
            "separator", foreground=c["border"], font=(self.mono_font, fs(10)))
        self.read_errors_text.tag_raise("sel")

        if hasattr(self, 'help_text'):
            self.help_text.configure(
                bg=c["bg_table"], fg=c["fg"], font=(self.main_font, fs(11)),
                insertbackground=c["fg"],
                selectbackground=c["accent"],
                selectforeground="#000000"
            )
            self.help_text.tag_raise("sel")

        if hasattr(self, 'kl_status_text'):
            self.kl_status_text.configure(
                bg=c["detail_bg"], fg=c["fg"], font=(self.mono_font, fs(10)),
                insertbackground=c["fg"],
            )
            self.kl_status_text.tag_configure("label", foreground=c["accent"],
                                              font=(self.mono_font, fs(10), "bold"))
            self.kl_status_text.tag_configure("value", foreground=c["fg"],
                                              font=(self.mono_font, fs(10)))
            self.kl_status_text.tag_configure("running", foreground=c.get("success", "#8fbf7f"),
                                              font=(self.mono_font, fs(11), "bold"))
            self.kl_status_text.tag_configure("stopped", foreground=c.get("error", "#c45050"),
                                              font=(self.mono_font, fs(11), "bold"))
            self.kl_status_text.tag_configure("dim", foreground=c.get("fg_dim", "#999999"),
                                              font=(self.mono_font, fs(9), "italic"))

        if hasattr(self, 'kl_log_text'):
            for tw in (self.kl_log_text, getattr(self, 'kl_raw_text', None)):
                if tw:
                    tw.configure(
                        bg=c["bg_table"], fg=c["fg"], font=(self.mono_font, fs(10)),
                        insertbackground=c["fg"],
                    )
                    tw.tag_configure("timestamp", foreground=c["accent"],
                                                   font=(self.mono_font, fs(10)))
                    tw.tag_configure("key", foreground=c["fg"],
                                                   font=(self.mono_font, fs(10)))
                    tw.tag_configure("marker", foreground=c.get("warning", "#d4a846"),
                                                   font=(self.mono_font, fs(10), "italic"))
                    tw.tag_configure("dim", foreground=c.get("fg_dim", "#999999"),
                                                   font=(self.mono_font, fs(10), "italic"))

        self.nav_frame.configure(style="Nav.TFrame")
        for btn_name, btn_widget in self._nav_buttons.items():
            if btn_name == self._current_page:
                btn_widget.configure(style="NavActive.TButton")
            else:
                btn_widget.configure(style="Nav.TButton")

        if hasattr(self, 'filtered_entries'):
            self._show_detail_placeholder()
            self._show_output_placeholder()

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=0)
        main.pack(fill=tk.BOTH, expand=True)

        self._build_header(main)

        self._build_nav(main)

        ttk.Separator(main, orient=tk.HORIZONTAL).pack(fill=tk.X)

        self.content_container = ttk.Frame(main)
        self.content_container.pack(fill=tk.BOTH, expand=True)

        self.logs_page = ttk.Frame(self.content_container)

        self._build_toolbar(self.logs_page)
        ttk.Separator(self.logs_page, orient=tk.HORIZONTAL).pack(fill=tk.X)

        paned = ttk.PanedWindow(self.logs_page, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=(4, 0))

        self._build_table(paned)
        self._build_details(paned)

        self.processes_page = ttk.Frame(self.content_container)
        self._build_processes_page(self.processes_page)

        self.scanner_page = ttk.Frame(self.content_container)
        self._build_scanner_page(self.scanner_page)

        self.history_page = ttk.Frame(self.content_container)
        self.history_notebook = ttk.Notebook(self.history_page)
        self.history_notebook.pack(fill=tk.BOTH, expand=True)

        self.export_history_page = ttk.Frame(self.history_notebook)
        self._build_export_history_page(self.export_history_page)
        self.history_notebook.add(self.export_history_page, text="Export History")

        self.deletion_history_page = ttk.Frame(self.history_notebook)
        self._build_deletion_history_page(self.deletion_history_page)
        self.history_notebook.add(self.deletion_history_page, text="Deletion History")

        self.lock_history_page = ttk.Frame(self.history_notebook)
        self._build_lock_history_page(self.lock_history_page)
        self.history_notebook.add(self.lock_history_page, text="Lock Screen History")

        self.read_errors_page = ttk.Frame(self.content_container)
        self._build_read_errors_page(self.read_errors_page)

        self.help_page = ttk.Frame(self.content_container)
        self._build_help_page(self.help_page)

        self.keylogger_page = ttk.Frame(self.content_container)
        self._build_keylogger_page(self.keylogger_page)

        self._build_status(main)

        self._show_page("logs")

    def _build_header(self, parent):
        header = ttk.Frame(parent, style="Toolbar.TFrame")
        header.pack(fill=tk.X)

        inner = ttk.Frame(header, style="Toolbar.TFrame")
        inner.pack(fill=tk.X, padx=14, pady=(10, 6))

        if getattr(self, '_icon_photo_small', None):
            ttk.Label(inner, image=self._icon_photo_small,
                      style="Toolbar.TLabel").pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(inner, text="Settings", style="Icon.TButton",
                   command=self._show_settings).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(inner, text="About", style="Icon.TButton",
                   command=self._show_about).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(inner, text="Shortcuts", style="Icon.TButton",
                   command=self._show_shortcuts).pack(side=tk.RIGHT, padx=(4, 0))

    def _build_nav(self, parent):
        self.nav_frame = ttk.Frame(parent, style="Nav.TFrame")
        self.nav_frame.pack(fill=tk.X)

        nav_inner = ttk.Frame(self.nav_frame, style="Nav.TFrame")
        nav_inner.pack(fill=tk.X, padx=10, pady=2)

        self._nav_buttons = {}

        pages = [
            ("logs", "Logs"),
            ("processes", "Process Monitor"),
            ("scanner", "Scanner"),
            ("history", "History"),
            ("read_errors", "Read Errors"),
            ("keylogger", "Key Logger"),
            ("help", "Help"),
        ]

        for page_id, label in pages:
            btn = ttk.Button(nav_inner, text=label, style="Nav.TButton",
                             command=lambda p=page_id: self._show_page(p))
            btn.pack(side=tk.LEFT, padx=(0, 2))
            self._nav_buttons[page_id] = btn

    def _show_page(self, page_id: str):
        self._current_page = page_id

        self.logs_page.pack_forget()
        self.processes_page.pack_forget()
        self.scanner_page.pack_forget()
        if hasattr(self, "history_page"):
            self.history_page.pack_forget()
        self.read_errors_page.pack_forget()
        self.help_page.pack_forget()
        self.keylogger_page.pack_forget()
        for custom_page in self._custom_tab_pages.values():
            custom_page["frame"].pack_forget()
        if hasattr(self, "processes_refresh_id") and self.processes_refresh_id is not None:
            self.root.after_cancel(self.processes_refresh_id)
            self.processes_refresh_id = None

        for btn_name, btn_widget in self._nav_buttons.items():
            if btn_name == page_id:
                btn_widget.configure(style="NavActive.TButton")
            else:
                btn_widget.configure(style="Nav.TButton")

        if page_id == "logs":
            self.logs_page.pack(in_=self.content_container,
                                fill=tk.BOTH, expand=True)
        elif page_id == "processes":
            self.processes_page.pack(in_=self.content_container,
                                    fill=tk.BOTH, expand=True)
            self._refresh_processes()
            self._schedule_process_refresh()
        elif page_id == "scanner":
            self.scanner_page.pack(in_=self.content_container, fill=tk.BOTH, expand=True)
            self._refresh_scanner_results()
        elif page_id == "history":
            self.history_page.pack(
                in_=self.content_container, fill=tk.BOTH, expand=True)
            self._refresh_export_history()
            self._refresh_deletion_history()
            self._refresh_lock_history()
        elif page_id == "read_errors":
            self.read_errors_page.pack(
                in_=self.content_container, fill=tk.BOTH, expand=True)
            self._refresh_read_errors()
        elif page_id == "keylogger":
            self.keylogger_page.pack(
                in_=self.content_container, fill=tk.BOTH, expand=True)
            self._refresh_keylogger_page()
        elif page_id == "help":
            self.help_page.pack(in_=self.content_container,
                                fill=tk.BOTH, expand=True)

    def _build_toolbar(self, parent):
        toolbar = ttk.Frame(parent, style="Toolbar.TFrame")
        toolbar.pack(fill=tk.X)

        top_inner = ttk.Frame(toolbar, style="Toolbar.TFrame")
        top_inner.pack(fill=tk.X, padx=14, pady=(8, 4))

        bottom_inner = ttk.Frame(toolbar, style="Toolbar.TFrame")
        bottom_inner.pack(fill=tk.X, padx=14, pady=(0, 8))

        ttk.Label(top_inner, text="Search:", style="Toolbar.TLabel").pack(
            side=tk.LEFT, padx=(0, 4))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._apply_filters())
        search_entry = ttk.Entry(
            top_inner, textvariable=self.search_var, width=22)
        search_entry.pack(side=tk.LEFT, padx=(0, 16))

        ttk.Label(top_inner, text="User:", style="Toolbar.TLabel").pack(
            side=tk.LEFT, padx=(0, 4))
        self.user_menu = MultiSelectMenu(
            top_inner, title="All", on_change=self._apply_filters, width=12)
        self.user_menu.pack(side=tk.LEFT, padx=(0, 16))

        ttk.Label(top_inner, text="Shell:", style="Toolbar.TLabel").pack(
            side=tk.LEFT, padx=(0, 4))
        self.shell_menu = MultiSelectMenu(
            top_inner, title="All", on_change=self._apply_filters, width=12)
        self.shell_menu.pack(side=tk.LEFT, padx=(0, 16))

        ttk.Label(top_inner, text="Source:", style="Toolbar.TLabel").pack(
            side=tk.LEFT, padx=(0, 4))
        self.source_menu = MultiSelectMenu(
            top_inner, title="All", on_change=self._apply_filters, width=12)
        self.source_menu.pack(side=tk.LEFT, padx=(0, 16))

        ttk.Button(top_inner, text="Export CSV", style="Accent.TButton",
                   command=self._export_csv).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(top_inner, text="Refresh", command=self._refresh_data).pack(
            side=tk.RIGHT, padx=(6, 0))

        ttk.Label(bottom_inner, text="From:", style="Toolbar.TLabel").pack(
            side=tk.LEFT, padx=(0, 4))
        self.start_time_var = tk.StringVar()
        self.start_time_var.trace_add(
            "write", lambda *_: self._apply_filters())
        start_entry = ttk.Entry(
            bottom_inner, textvariable=self.start_time_var, width=20)
        start_entry.pack(side=tk.LEFT, padx=(0, 16))

        self.start_hint = ttk.Label(
            bottom_inner, text="(YYYY-MM-DD HH:MM)", style="Toolbar.TLabel", font=(self.main_font, 8))
        self.start_hint.pack(side=tk.LEFT, padx=(0, 16))

        ttk.Label(bottom_inner, text="To:", style="Toolbar.TLabel").pack(
            side=tk.LEFT, padx=(0, 4))
        self.end_time_var = tk.StringVar()
        self.end_time_var.trace_add("write", lambda *_: self._apply_filters())
        end_entry = ttk.Entry(
            bottom_inner, textvariable=self.end_time_var, width=20)
        end_entry.pack(side=tk.LEFT, padx=(0, 16))

        self.end_hint = ttk.Label(
            bottom_inner, text="(YYYY-MM-DD HH:MM)", style="Toolbar.TLabel", font=(self.main_font, 8))
        self.end_hint.pack(side=tk.LEFT, padx=(0, 16))

        self.count_var = tk.StringVar(value="")
        count_lbl = ttk.Label(bottom_inner, textvariable=self.count_var,
                              style="Toolbar.TLabel",
                              font=(self.main_font, 10))
        count_lbl.pack(side=tk.RIGHT, padx=(0, 14))

    def _build_table(self, parent):
        table_frame = ttk.Frame(parent)
        parent.add(table_frame, weight=4)

        self.tree = ttk.Treeview(table_frame, columns=self.COLUMNS,
                                 show="headings", selectmode="browse")

        for col in self.COLUMNS:
            label = self.COLUMN_LABELS[col]
            width = self.COLUMN_WIDTHS[col]
            anchor = tk.W if col == "command" else tk.CENTER
            self.tree.heading(col, text=label,
                              command=lambda c=col: self._on_sort(c))
            self.tree.column(col, width=width, minwidth=60, anchor=anchor)

        vsb = ttk.Scrollbar(table_frame, orient=tk.VERTICAL,
                            command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL,
                            command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        self.log_context_menu = tk.Menu(self.tree, tearoff=0)
        self.log_context_menu.add_command(
            label="Delete Command Log", command=self._delete_selected_log)

        def show_context_menu(event):
            item = self.tree.identify_row(event.y)
            if item:
                self.tree.selection_set(item)
                self.log_context_menu.post(event.x_root, event.y_root)

        self.tree.bind("<Button-3>", show_context_menu)

    def _build_details(self, parent):
        details_outer = ttk.LabelFrame(parent, text="  Command Details  ",
                                       style="Detail.TLabelframe", padding=6)
        parent.add(details_outer, weight=2)

        split_pane = ttk.PanedWindow(details_outer, orient=tk.HORIZONTAL)
        split_pane.pack(fill=tk.BOTH, expand=True)

        details_frame = ttk.Frame(split_pane)
        split_pane.add(details_frame, weight=1)

        details_label = ttk.Label(details_frame, text="Details",
                                  font=(self.main_font, 10, "bold"))
        details_label.pack(anchor=tk.W, padx=4, pady=(0, 2))

        self.details_text = tk.Text(
            details_frame, wrap=tk.WORD, height=7, state=tk.DISABLED,
            font=(self.mono_font, 11),
            borderwidth=0, padx=10, pady=8,
        )
        details_scroll = ttk.Scrollbar(details_frame, orient=tk.VERTICAL,
                                       command=self.details_text.yview)
        self.details_text.configure(yscrollcommand=details_scroll.set)

        self.details_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        details_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.output_notebook = ttk.Notebook(split_pane)
        split_pane.add(self.output_notebook, weight=1)

        output_tab1 = ttk.Frame(self.output_notebook)
        self.output_notebook.add(output_tab1, text="Command Output")

        self.output_text = tk.Text(
            output_tab1, wrap=tk.WORD, height=7, state=tk.DISABLED,
            font=(self.mono_font, 10),
            borderwidth=0, padx=10, pady=8,
        )
        output_scroll = ttk.Scrollbar(output_tab1, orient=tk.VERTICAL,
                                      command=self.output_text.yview)
        self.output_text.configure(yscrollcommand=output_scroll.set)

        self.output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        output_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        output_tab2 = ttk.Frame(self.output_notebook)
        self.output_notebook.add(output_tab2, text="Expected Output")

        self.expected_output_text = tk.Text(
            output_tab2, wrap=tk.WORD, height=7, state=tk.DISABLED,
            font=(self.mono_font, 10),
            borderwidth=0, padx=10, pady=8,
        )
        expected_output_scroll = ttk.Scrollbar(output_tab2, orient=tk.VERTICAL,
                                      command=self.expected_output_text.yview)
        self.expected_output_text.configure(yscrollcommand=expected_output_scroll.set)

        self.expected_output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        expected_output_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_export_history_page(self, parent):
        header_frame = ttk.Frame(parent, style="Toolbar.TFrame")
        header_frame.pack(fill=tk.X)

        inner = ttk.Frame(header_frame, style="Toolbar.TFrame")
        inner.pack(fill=tk.X, padx=14, pady=10)

        ttk.Label(inner, text="Export History",
                  style="Toolbar.TLabel",
                  font=(self.main_font, 14, "bold")).pack(side=tk.LEFT)

        ttk.Button(inner, text="Export CSV",
                   command=self._export_export_history_csv).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(inner, text="Refresh",
                   command=self._refresh_export_history).pack(side=tk.RIGHT, padx=(6, 0))

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X)

        content_frame = ttk.Frame(parent)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.export_history_text = tk.Text(
            content_frame, wrap=tk.WORD, state=tk.DISABLED,
            font=(self.mono_font, 11),
            borderwidth=0, padx=14, pady=10,
        )
        eh_scroll = ttk.Scrollbar(content_frame, orient=tk.VERTICAL,
                                  command=self.export_history_text.yview)
        self.export_history_text.configure(yscrollcommand=eh_scroll.set)

        self.export_history_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        eh_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_read_errors_page(self, parent):
        header_frame = ttk.Frame(parent, style="Toolbar.TFrame")
        header_frame.pack(fill=tk.X)

        inner = ttk.Frame(header_frame, style="Toolbar.TFrame")
        inner.pack(fill=tk.X, padx=14, pady=10)

        ttk.Label(inner, text="Inaccessible Paths",
                  style="Toolbar.TLabel",
                  font=(self.main_font, 14, "bold")).pack(side=tk.LEFT)

        ttk.Button(inner, text="Export CSV",
                   command=self._export_read_errors_csv).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(inner, text="Clear Errors",
                   command=self._clear_read_errors).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(inner, text="Refresh",
                   command=self._refresh_read_errors).pack(side=tk.RIGHT, padx=(6, 0))

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X)

        content_frame = ttk.Frame(parent)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.read_errors_text = tk.Text(
            content_frame, wrap=tk.WORD, state=tk.DISABLED,
            font=(self.mono_font, 11),
            borderwidth=0, padx=14, pady=10,
        )
        re_scroll = ttk.Scrollbar(content_frame, orient=tk.VERTICAL,
                                  command=self.read_errors_text.yview)
        self.read_errors_text.configure(yscrollcommand=re_scroll.set)

        self.read_errors_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        re_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_deletion_history_page(self, parent):
        header_frame = ttk.Frame(parent, style="Toolbar.TFrame")
        header_frame.pack(fill=tk.X)

        inner = ttk.Frame(header_frame, style="Toolbar.TFrame")
        inner.pack(fill=tk.X, padx=14, pady=10)

        ttk.Label(inner, text="Deletion History",
                  style="Toolbar.TLabel",
                  font=(self.main_font, fs(14) if 'fs' in globals() else 14, "bold")).pack(side=tk.LEFT)

        ttk.Button(inner, text="Export CSV",
                   command=self._export_deletion_history_csv).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(inner, text="Refresh",
                   command=self._refresh_deletion_history).pack(side=tk.RIGHT, padx=(6, 0))

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X)

        self.deletion_tree = ttk.Treeview(parent, columns=(
            "timestamp", "user", "item_type", "detail", "allowed"), show="headings")
        self.deletion_tree.heading("timestamp", text="Time")
        self.deletion_tree.heading("user", text="User")
        self.deletion_tree.heading("item_type", text="Action Type")
        self.deletion_tree.heading("detail", text="Details")
        self.deletion_tree.heading("allowed", text="Allowed?")

        self.deletion_tree.column("timestamp", width=150)
        self.deletion_tree.column("user", width=100)
        self.deletion_tree.column("item_type", width=150)
        self.deletion_tree.column("detail", width=400)
        self.deletion_tree.column("allowed", width=80)

        vsb = ttk.Scrollbar(parent, orient=tk.VERTICAL,
                            command=self.deletion_tree.yview)
        self.deletion_tree.configure(yscrollcommand=vsb.set)

        self.deletion_tree.pack(
            side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=10)
        vsb.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10), pady=10)

    def _refresh_deletion_history(self):
        from .deletion_history import load_deletion_history
        for item in self.deletion_tree.get_children():
            self.deletion_tree.delete(item)

        history = load_deletion_history()
        for entry in reversed(history):
            self.deletion_tree.insert("", "end", values=(
                entry.get("timestamp", "")[:19].replace("T", " "),
                entry.get("user", "unknown"),
                entry.get("item_type", "Unknown"),
                entry.get("detail", ""),
                "Yes" if entry.get("allowed") else "NO"
            ))

    def _build_lock_history_page(self, parent):
        header_frame = ttk.Frame(parent, style="Toolbar.TFrame")
        header_frame.pack(fill=tk.X)

        inner = ttk.Frame(header_frame, style="Toolbar.TFrame")
        inner.pack(fill=tk.X, padx=14, pady=10)

        ttk.Label(inner, text="Lock Screen History",
                  style="Toolbar.TLabel",
                  font=(self.main_font, 14, "bold")).pack(side=tk.LEFT)

        ttk.Button(inner, text="Refresh",
                   command=self._refresh_lock_history).pack(side=tk.RIGHT, padx=(6, 0))

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X)

        self.lock_history_tree = ttk.Treeview(parent, columns=(
            "timestamp", "event", "details"), show="headings")
        self.lock_history_tree.heading("timestamp", text="Time")
        self.lock_history_tree.heading("event", text="Event")
        self.lock_history_tree.heading("details", text="Details")

        self.lock_history_tree.column("timestamp", width=180)
        self.lock_history_tree.column("event", width=180)
        self.lock_history_tree.column("details", width=500)

        vsb = ttk.Scrollbar(parent, orient=tk.VERTICAL,
                            command=self.lock_history_tree.yview)
        self.lock_history_tree.configure(yscrollcommand=vsb.set)

        self.lock_history_tree.pack(
            side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=10)
        vsb.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10), pady=10)

    def _refresh_lock_history(self):
        for item in self.lock_history_tree.get_children():
            self.lock_history_tree.delete(item)

        entries = []
        try:
            from .collectors import collect_session_lifecycle_events
            entries = collect_session_lifecycle_events()
        except Exception:
            entries = []

        for entry in sorted(entries, key=lambda e: (e.timestamp or datetime.min, str(e.command))):
            self.lock_history_tree.insert("", "end", values=(
                (entry.timestamp or datetime.min).strftime("%Y-%m-%d %H:%M:%S") if entry.timestamp else "Unknown",
                str(entry.command or "Session Event"),
                str(entry.source or "logind")
            ))

    def _build_help_page(self, parent):
        header_frame = ttk.Frame(parent, style="Toolbar.TFrame")
        header_frame.pack(fill=tk.X)

        inner = ttk.Frame(header_frame, style="Toolbar.TFrame")
        inner.pack(fill=tk.X, padx=14, pady=10)

        if getattr(self, '_icon_photo_small', None):
            ttk.Label(inner, image=self._icon_photo_small,
                      style="Toolbar.TLabel").pack(side=tk.LEFT, padx=(0, 10))

        ttk.Label(inner, text="Help & Documentation",
                  style="Toolbar.TLabel",
                  font=(self.main_font, 14, "bold")).pack(side=tk.LEFT)

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X)

        content_frame = ttk.Frame(parent)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.help_text = tk.Text(
            content_frame, wrap=tk.WORD, state=tk.NORMAL,
            font=(self.main_font, 11),
            borderwidth=0, padx=14, pady=10, bg=self.colors["bg_table"], fg=self.colors["fg"]
        )
        help_scroll = ttk.Scrollbar(content_frame, orient=tk.VERTICAL,
                                    command=self.help_text.yview)
        self.help_text.configure(yscrollcommand=help_scroll.set)

        self.help_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        help_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        if getattr(self, '_help_photo', None):
            self.help_text.image_create(tk.END, image=self._help_photo)
            self.help_text.insert(tk.END, "\n\n")

        help_content_1 = """CatLogs - System Logs

Overview:
CatLogs securely gathers and displays historical commands and system events from various logs across your Linux machine without needing to send data anywhere.

Documentation:
For full documentation and a user guide, visit our website:
"""
        help_url = "https://catlogs.wassim.tech/features.html"
        help_content_2 = """

Pages:
* Logs: The main interface displaying commands and logs. Click on any row to view its full details and related system context in the panel below.
* Process Monitor: Live process explorer with CPU, memory, state, TTY, parent info, daemon summaries, and one-click termination controls.
* Export History: A read-only record of all data exports you've made to CSV.
* Read Errors: Displays logs or files the application didn't have permission to read.
* Key Logger: Monitor keyboard input via an opt-in daemon. Start/stop the daemon, view key logs, install auto-start service for reboot persistence.
* Deletion History: Review a history of logs that have been deleted.
* Help: This documentation page.

Filtering Data:
Use the top toolbar to filter logs:
* Search: Type any text to find matching commands, users, or log sources.
* Exclude Menus: Click on the User, Shell, or Source buttons to open a dropdown of checkboxes. Checking an item excludes it from the results. You can use 'Exclude All' and 'Clear Exclusions' for rapid filtering.
* From / To: Filter by date. Use format YYYY-MM-DD or YYYY-MM-DD HH:MM:SS.

Exporting & Managing:
* Export CSV: Click the 'Export CSV' button to save your current filtered view to a spreadsheet. The export contains metadata about your filters and the software version.
* Delete Logs: Right-click on a log entry to delete it, unless Protection Mode is enabled.

Settings & Log File Paths:
Click the Settings icon in the top right (or press Ctrl+,) to open Settings:
* [File] Log File Paths: View all system and user log files monitored by CatLogs. You can add any custom log file path on your machine with auto-detection for Syslog, Auth/Sudo, Web Servers (Nginx/Apache), JSON Lines, Application logs, DPKG, Auditd, Database logs, etc., test/preview the format before adding, toggle active state, or delete unwanted paths.
* [Art] Appearance: Switch between color themes (Dark, Light, Dracula, Monokai, Nord, Cappuccino) and customize Main and Monospace fonts.
* Security: Configure Protection Mode to prevent unauthorized or accidental log deletion.

Keyboard Shortcuts:
* F5 / Ctrl+R: Refresh data
* F11: Toggle fullscreen
* Ctrl+E: Export to CSV
* Ctrl+,: Open Settings & Log Paths
* Esc: Clear all filters
* Ctrl++ / Ctrl+-: Zoom in and out
* Ctrl+0: Reset zoom level
* Ctrl+Q: Quit application
"""

        self.help_text.insert(tk.END, help_content_1)

        # Insert clickable link
        self.help_text.insert(tk.END, help_url, "link")

        def open_docs(event):
            import webbrowser
            webbrowser.open(help_url)

        self.help_text.tag_config("link", foreground="#3584e4", underline=True)
        self.help_text.tag_bind("link", "<Button-1>", open_docs)
        self.help_text.tag_bind(
            "link", "<Enter>", lambda e: self.help_text.config(cursor="hand2"))
        self.help_text.tag_bind(
            "link", "<Leave>", lambda e: self.help_text.config(cursor=""))

        self.help_text.insert(tk.END, help_content_2)

        self.help_text.configure(state=tk.DISABLED)

    def _build_processes_page(self, parent):
        self.processes_auto_refresh = tk.BooleanVar(value=True)
        self.processes_refresh_id = None

        header_frame = ttk.Frame(parent, style="Toolbar.TFrame")
        header_frame.pack(fill=tk.X)

        inner = ttk.Frame(header_frame, style="Toolbar.TFrame")
        inner.pack(fill=tk.X, padx=14, pady=10)

        ttk.Label(inner, text="Process Monitor",
                  style="Toolbar.TLabel",
                  font=(self.main_font, 14, "bold")).pack(side=tk.LEFT)

        ttk.Button(inner, text="Help", width=6,
                   command=self._show_process_help).pack(side=tk.RIGHT, padx=(0, 6))
        ttk.Button(inner, text="Export CSV",
                   command=self._export_processes_csv).pack(side=tk.RIGHT, padx=(0, 6))
        ttk.Button(inner, text="Refresh",
                   command=self._refresh_processes).pack(side=tk.RIGHT, padx=(0, 6))
        ttk.Button(inner, text="Kill Selected",
                   command=self._kill_selected_process).pack(side=tk.RIGHT, padx=(0, 6))

        toolbar = ttk.Frame(parent, style="Toolbar.TFrame")
        toolbar.pack(fill=tk.X, padx=10, pady=(0, 6))

        ttk.Label(toolbar, text="Filter:", style="Toolbar.TLabel").pack(side=tk.LEFT, padx=(0, 6))
        self.processes_search_var = tk.StringVar()
        self.processes_search_var.trace_add("write", lambda *_: self._filter_processes_table())
        ttk.Entry(toolbar, textvariable=self.processes_search_var, width=28).pack(side=tk.LEFT)
        ttk.Checkbutton(toolbar, text="Auto refresh", variable=self.processes_auto_refresh,
                        command=self._toggle_process_auto_refresh).pack(side=tk.RIGHT, padx=(0, 8))
        self.processes_summary_var = tk.StringVar(value="Loading processes...")
        ttk.Label(toolbar, textvariable=self.processes_summary_var, style="Toolbar.TLabel").pack(side=tk.RIGHT)

        layout = ttk.Frame(parent)
        layout.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        layout.grid_rowconfigure(0, weight=4)
        layout.grid_rowconfigure(1, weight=2)
        layout.grid_columnconfigure(0, weight=1)

        tree_frame = ttk.Frame(layout)
        tree_frame.grid(row=0, column=0, sticky="nsew")

        columns = ("pid", "user", "cpu", "mem", "state", "tty", "ppid", "elapsed", "command")
        self.processes_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="tree headings",
            selectmode="browse",
            height=12,
        )
        self.processes_tree.heading("#0", text="Name")
        self.processes_tree.heading("pid", text="PID")
        self.processes_tree.heading("user", text="User")
        self.processes_tree.heading("cpu", text="CPU %")
        self.processes_tree.heading("mem", text="MEM %")
        self.processes_tree.heading("state", text="State")
        self.processes_tree.heading("tty", text="TTY")
        self.processes_tree.heading("ppid", text="PPID")
        self.processes_tree.heading("elapsed", text="Elapsed")
        self.processes_tree.heading("command", text="Command")

        self.processes_tree.column("#0", width=180, stretch=tk.YES)
        self.processes_tree.column("pid", width=70, anchor=tk.CENTER)
        self.processes_tree.column("user", width=90)
        self.processes_tree.column("cpu", width=90, anchor=tk.CENTER)
        self.processes_tree.column("mem", width=90, anchor=tk.CENTER)
        self.processes_tree.column("state", width=90, anchor=tk.CENTER)
        self.processes_tree.column("tty", width=90, anchor=tk.CENTER)
        self.processes_tree.column("ppid", width=80, anchor=tk.CENTER)
        self.processes_tree.column("elapsed", width=150)
        self.processes_tree.column("command", width=500, stretch=tk.YES)

        yscroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.processes_tree.yview)
        xscroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.processes_tree.xview)
        self.processes_tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.processes_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        xscroll.pack(side=tk.BOTTOM, fill=tk.X)

        self.processes_tree.bind("<<TreeviewSelect>>", self._show_selected_process_details)

        bottom_container = ttk.Frame(layout)
        bottom_container.grid(row=1, column=0, sticky="nsew")

        details_frame = ttk.Frame(bottom_container, padding=(0, 8, 0, 0))
        details_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Label(details_frame, text="Selected process", style="Toolbar.TLabel").pack(anchor=tk.W)
        self.processes_details = tk.Text(
            details_frame,
            height=6,
            wrap=tk.WORD,
            state=tk.NORMAL,
            bg="#000000",
            fg=self.colors["fg"],
            font=(self.main_font, 10),
            borderwidth=0,
            padx=8,
            pady=8,
        )
        self.processes_details.pack(fill=tk.BOTH, expand=True)
        self.processes_details.configure(state=tk.DISABLED)

        summary_frame = ttk.Frame(bottom_container, padding=(12, 8, 0, 0), width=420)
        summary_frame.pack(side=tk.RIGHT, fill=tk.Y)
        summary_frame.pack_propagate(False)
        ttk.Label(summary_frame, text="System summary", style="Toolbar.TLabel").pack(anchor=tk.W)

        self.system_summary_text = tk.Text(
            summary_frame,
            height=9,
            wrap=tk.WORD,
            state=tk.NORMAL,
            bg="#000000",
            fg=self.colors["fg"],
            font=(self.mono_font, 10),
            borderwidth=0,
            padx=8,
            pady=8,
        )
        self.system_summary_text.pack(fill=tk.BOTH, expand=True)
        self.system_summary_text.configure(state=tk.DISABLED)

        self._refresh_system_summary()

        self._refresh_processes()

    def _build_scanner_page(self, parent):
        header = ttk.Frame(parent, style="Toolbar.TFrame")
        header.pack(fill=tk.X)

        inner = ttk.Frame(header, style="Toolbar.TFrame")
        inner.pack(fill=tk.X, padx=14, pady=10)

        ttk.Label(inner, text="Scanner",
                  style="Toolbar.TLabel",
                  font=(self.main_font, 14, "bold")).pack(side=tk.LEFT)

        ttk.Button(inner, text="Export PDF Audit",
                   command=self._export_scanner_pdf).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(inner, text="Scan Folder",
                   command=self._run_scanner).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(inner, text="Choose Folder",
                   command=self._choose_scanner_directory).pack(side=tk.RIGHT, padx=(6, 0))

        toolbar = ttk.Frame(parent, style="Toolbar.TFrame")
        toolbar.pack(fill=tk.X, padx=10, pady=(0, 6))

        ttk.Label(toolbar, text="Target:", style="Toolbar.TLabel").pack(side=tk.LEFT, padx=(0, 6))
        self.scanner_target_var = tk.StringVar(value=os.path.expanduser("~/"))
        ttk.Entry(toolbar, textvariable=self.scanner_target_var, width=50).pack(side=tk.LEFT)

        content = ttk.Frame(parent)
        content.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)

        self.scanner_text = tk.Text(
            content,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg="#000000",
            fg=self.colors["fg"],
            font=(self.mono_font, 10),
            borderwidth=0,
            padx=10,
            pady=10,
        )
        scrollbar = ttk.Scrollbar(content, orient=tk.VERTICAL, command=self.scanner_text.yview)
        self.scanner_text.configure(yscrollcommand=scrollbar.set)
        self.scanner_text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.scanner_summary_var = tk.StringVar(value="No scan yet.")
        self.scanner_summary_label = ttk.Label(
            parent,
            textvariable=self.scanner_summary_var,
            style="Toolbar.TLabel",
            font=(self.main_font, 10)
        )
        self.scanner_summary_label.pack(fill=tk.X, padx=10, pady=(0, 10))

    def _choose_scanner_directory(self):
        if filedialog is None:
            return
        selected = filedialog.askdirectory(title="Choose a folder to scan")
        if selected:
            self.scanner_target_var.set(selected)

    def _run_scanner(self):
        target = self.scanner_target_var.get().strip()
        if not target:
            target = os.path.expanduser("~")
        if not os.path.exists(target):
            messagebox.showerror("Scanner", f"Target path does not exist: {target}")
            return

        self.scanner_summary_var.set("Scanning…")
        self.scanner_text.configure(state=tk.NORMAL)
        self.scanner_text.delete("1.0", tk.END)
        self.scanner_text.insert(tk.END, f"Scanning {target}...\n\n")
        self.scanner_text.configure(state=tk.DISABLED)

        def worker():
            session = create_scan_session(
                name=f"Directory scan: {os.path.basename(target) or target}",
                target=target,
                mode="unprivileged",
                status="running",
            )
            result = scan_directory(target, max_depth=2, max_files=500)
            for finding in result.get("findings", []):
                add_scan_finding(
                    session_id=session["id"],
                    rule_name=finding["rule_name"],
                    severity=finding["severity"],
                    path=finding["path"],
                    summary=finding["summary"],
                    details=finding["details"],
                )
            self.root.after(0, lambda: self._apply_scanner_result(result, session))

        threading.Thread(target=worker, daemon=True).start()

    def _export_scanner_pdf(self):
        target = self.scanner_target_var.get().strip() or os.path.expanduser("~")
        if not os.path.exists(target):
            messagebox.showerror("Scanner", f"Target path does not exist: {target}")
            return

        findings = list_findings()[:50]
        if not findings:
            messagebox.showinfo("Audit Report", "No findings are available to export yet. Run a scan first.")
            return

        default_name = generate_default_pdf_filename()
        filepath = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
            initialfile=default_name,
            title="Export Scanner Audit Report as PDF",
        )
        if not filepath:
            return

        try:
            count = export_audit_report_pdf(
                target=target,
                findings=findings,
                filepath=filepath,
                generated_at=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
            messagebox.showinfo(
                "PDF Export Successful",
                f"Exported {count} findings to:\n{filepath}",
            )
        except Exception as exc:  # pragma: no cover - GUI only
            messagebox.showerror("PDF Export Error", f"Failed to export PDF:\n{exc}")

    def _apply_scanner_result(self, result, session):
        findings = result.get("findings", [])
        self.scanner_summary_var.set(
            f"Scanned {result.get('files_scanned', 0)} files • {len(findings)} findings"
        )
        self.scanner_text.configure(state=tk.NORMAL)
        self.scanner_text.delete("1.0", tk.END)
        self.scanner_text.insert(tk.END, f"Scan target: {result.get('directory', '')}\n")
        self.scanner_text.insert(tk.END, f"Files scanned: {result.get('files_scanned', 0)}\n")
        self.scanner_text.insert(tk.END, f"Session ID: {session['id']}\n\n")
        if not findings:
            self.scanner_text.insert(tk.END, "No suspicious files found in the selected target.\n")
        else:
            self.scanner_text.insert(tk.END, "Findings:\n")
            for idx, finding in enumerate(findings, 1):
                self.scanner_text.insert(
                    tk.END,
                    f"[{idx}] {finding['severity'].upper()} • {finding['rule_name']}\n"
                )
                self.scanner_text.insert(tk.END, f"Path: {finding['path']}\n")
                self.scanner_text.insert(tk.END, f"Summary: {finding['summary']}\n")
                self.scanner_text.insert(tk.END, f"Details: {finding['details']}\n\n")
        self.scanner_text.configure(state=tk.DISABLED)

    def _refresh_scanner_results(self):
        session_rows = list_findings()
        if not session_rows:
            self.scanner_text.configure(state=tk.NORMAL)
            self.scanner_text.delete("1.0", tk.END)
            self.scanner_text.insert(tk.END, "Scanner is ready. Choose a folder and run a scan.\n")
            self.scanner_text.configure(state=tk.DISABLED)
            self.scanner_summary_var.set("No scan history yet.")
            return

        history_text = []
        for item in session_rows[:8]:
            history_text.append(f"[{item['created_at']}] {item['rule_name']} | {item['severity']} | {item['path']}")
        self.scanner_text.configure(state=tk.NORMAL)
        self.scanner_text.delete("1.0", tk.END)
        self.scanner_text.insert(tk.END, "\n".join(history_text) + "\n")
        self.scanner_text.configure(state=tk.DISABLED)
        self.scanner_summary_var.set(f"{len(session_rows)} findings in local history")

    def _show_process_help(self):
        if getattr(self, '_proc_help_dialog', None) and self._proc_help_dialog.winfo_exists():
            self._proc_help_dialog.lift()
            return

        dialog = tk.Toplevel(self.root)
        self._proc_help_dialog = dialog
        dialog.title("Process Monitor Help")
        dialog.transient(self.root)
        dialog.geometry("700x500")
        
        main_frame = ttk.Frame(dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(main_frame, text="Understanding Processes & Daemons", font=(self.main_font, 14, "bold")).pack(anchor=tk.W, pady=(0, 10))
        
        content = tk.Text(main_frame, wrap=tk.WORD, font=(self.main_font, 10), borderwidth=0, bg=self.colors["bg_table"], fg=self.colors["fg"])
        
        scroll = ttk.Scrollbar(main_frame, command=content.yview)
        content.configure(yscrollcommand=scroll.set)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        text = """The Process Monitor displays a real-time snapshot of currently running processes (programs) and daemons (background services) on your system.

Key Columns:
• PID (Process ID): The unique number assigned by the OS to identify the process.
• PPID (Parent Process ID): The PID of the process that started this process.
• CPU % & MEM %: The percentage of system resources currently consumed.
• State: The current state of the process (e.g., R for running, S for sleeping, Z for zombie).
• TTY: The terminal associated with the process, if any.
• Elapsed: How long the process has been running.
• Command: The exact command line used to launch the process.

Daemons vs User Processes:
Daemons (often ending in 'd', like 'systemd' or 'sshd') are background services that manage system components and run independently of user sessions. User processes are applications launched by logged-in users.

Useful Resources & Documentation:"""
        
        content.insert(tk.END, text + "\n\n")
        
        links = [
            ("• Linux Process Management Guide", "https://tldp.org/LDP/sag/html/processes.html"),
            ("• Understanding 'ps' Output", "https://man7.org/linux/man-pages/man1/ps.1.html"),
            ("• What is a Daemon?", "https://en.wikipedia.org/wiki/Daemon_(computing)")
        ]
        
        for name, url in links:
            content.insert(tk.END, name + "\n", ("link", url))
            
        def open_url(event):
            try:
                idx = content.index(f"@{event.x},{event.y}")
                tags = content.tag_names(idx)
                for tag in tags:
                    if tag.startswith("http"):
                        import webbrowser
                        webbrowser.open(tag)
                        break
            except Exception:
                pass
                
        content.tag_config("link", foreground="#3584e4", underline=True)
        content.tag_bind("link", "<Button-1>", open_url)
        content.tag_bind("link", "<Enter>", lambda e: content.config(cursor="hand2"))
        content.tag_bind("link", "<Leave>", lambda e: content.config(cursor=""))
        
        content.configure(state=tk.DISABLED)

    def _toggle_process_auto_refresh(self):
        if self.processes_auto_refresh.get():
            self._schedule_process_refresh()
        else:
            if self.processes_refresh_id is not None:
                self.root.after_cancel(self.processes_refresh_id)
                self.processes_refresh_id = None

    def _schedule_process_refresh(self):
        if not self.processes_auto_refresh.get():
            return
        if self.processes_refresh_id is not None:
            self.root.after_cancel(self.processes_refresh_id)
        self.processes_refresh_id = self.root.after(5000, self._auto_refresh_processes)

    def _auto_refresh_processes(self):
        self.processes_refresh_id = None
        if self._current_page == "processes" and self.processes_auto_refresh.get():
            self._refresh_processes()
            self._schedule_process_refresh()

    def _refresh_processes(self):
        if self._process_refresh_lock:
            return
        self._process_refresh_lock = True
        self.processes_summary_var.set("Refreshing process list...")

        def worker():
            try:
                result = subprocess.run(
                    [
                        "ps",
                        "-eo",
                        "pid,ppid,user,comm,pcpu,pmem,stat,tty,etime,args",
                        "--no-headers",
                        "--sort=-pcpu,-pmem",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
            except Exception as exc:
                self.root.after(0, lambda: self._apply_process_refresh_result(None, f"Unable to read process list: {exc}"))
                return

            rows = parse_process_snapshot(result.stdout or "")
            signature = tuple(
                (
                    str(row.get("pid", "")),
                    str(row.get("ppid", "")),
                    str(row.get("user", "")),
                    str(row.get("name", "")),
                    str(row.get("cpu", "")),
                    str(row.get("mem", "")),
                    str(row.get("state", "")),
                    str(row.get("tty", "")),
                    str(row.get("elapsed", "")),
                    str(row.get("command", "")),
                )
                for row in rows
            )
            self.root.after(0, lambda rows=rows, signature=signature: self._apply_process_refresh_result(rows, None, signature))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_process_refresh_result(self, rows, error_message, signature=None):
        self._process_refresh_lock = False
        if error_message:
            self.processes_summary_var.set(error_message)
            return

        current_filter = self.processes_search_var.get().strip().lower()
        if signature is None:
            signature = self._last_process_rows_signature

        if (not current_filter and signature == self._last_process_rows_signature and self.processes_tree.get_children() and rows):
            self.processes_summary_var.set(f"{len(rows)} processes • process snapshot unchanged")
            return

        self._last_process_rows_signature = signature

        for child in self.processes_tree.get_children():
            self.processes_tree.delete(child)

        if not rows:
            self.processes_summary_var.set("No running processes found")
            self.processes_details.configure(state=tk.NORMAL)
            self.processes_details.delete("1.0", tk.END)
            self.processes_details.insert(tk.END, "No process data available.\n")
            self.processes_details.configure(state=tk.DISABLED)
            return

        daemon_count = sum(1 for row in rows if row["ppid"] == 1 or row["user"] == "root")
        top_cpu = max(float(row["cpu"]) for row in rows)
        self.processes_summary_var.set(f"{len(rows)} processes • {daemon_count} daemons • top CPU {top_cpu:.1f}%")

        pid_map = {row["pid"]: row for row in rows}
        children_map = {}
        for row in rows:
            children_map.setdefault(row["ppid"], []).append(row)

        inserted = set()

        def insert_tree(pid, parent_iid=""):
            if pid in inserted:
                return
            row = pid_map.get(pid)
            if row is None:
                return

            filtered = self.processes_search_var.get().strip().lower()
            if filtered:
                haystack = " ".join([
                    str(row["pid"]), row["user"], row["name"], row["command"], row["tty"], row["state"]
                ]).lower()
                if filtered not in haystack:
                    return

            values = (
                row["pid"],
                row["user"],
                row["cpu"],
                row["mem"],
                row["state"],
                row["tty"],
                row["ppid"],
                row["started"],
                row["command"],
            )
            node_id = self.processes_tree.insert(parent_iid, tk.END, iid=str(pid), text=row["name"], values=values, open=True)
            inserted.add(pid)

            children = sorted(children_map.get(pid, []), key=lambda r: (-(float(r["cpu"])), -(float(r["mem"])), r["pid"]))
            for child in children:
                if child["pid"] != pid:
                    insert_tree(child["pid"], node_id)

        roots = []
        for row in rows:
            if row["pid"] == 1 or row["ppid"] == 1 or row["ppid"] not in pid_map or row["ppid"] == 0:
                roots.append(row["pid"])
        roots = sorted(set(roots), key=lambda pid: (pid != 1, pid))
        if not roots:
            roots = [min(pid_map)]

        for root_pid in roots:
            insert_tree(root_pid)

        if self.processes_tree.get_children():
            first = self.processes_tree.get_children()[0]
            self.processes_tree.selection_set(first)
            self._show_selected_process_details()

    def _refresh_system_summary(self):
        try:
            load_avg = subprocess.run(["uptime"], capture_output=True, text=True, timeout=4, check=False)
            mem_info = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=4, check=False)
            proc_info = subprocess.run(["ps", "-eo", "comm", "--no-headers"], capture_output=True, text=True, timeout=4, check=False)
        except Exception:
            return

        total_tasks = 0
        running_tasks = 0
        if proc_info.returncode == 0:
            total_tasks = sum(1 for line in proc_info.stdout.splitlines() if line.strip())
            running_tasks = sum(1 for line in proc_info.stdout.splitlines() if line.strip() and line.strip() == "")

        load_text = load_avg.stdout.strip() if load_avg.returncode == 0 else "load average unavailable"
        load_text = load_text.replace("up ", "").replace("users", "users")

        mem_total = 0
        mem_used = 0
        swap_total = 0
        swap_used = 0
        if mem_info.returncode == 0:
            lines = mem_info.stdout.splitlines()
            for line in lines:
                if line.startswith("Mem:"):
                    parts = line.split()
                    if len(parts) >= 3:
                        mem_total = int(parts[1])
                        mem_used = int(parts[2])
                elif line.startswith("Swap:"):
                    parts = line.split()
                    if len(parts) >= 3:
                        swap_total = int(parts[1])
                        swap_used = int(parts[2])

        uptime_text = ""
        if load_avg.returncode == 0:
            uptime_text = load_avg.stdout.strip().split("up ", 1)[1].split(",", 1)[0] if " up " in load_avg.stdout else "uptime unavailable"

        summary = (
            f"Tasks: {total_tasks} total, {running_tasks or '0'} running\n"
            f"Load average: {load_text.split('load average:')[-1].strip() if 'load average:' in load_text.lower() else load_text}\n"
            f"Uptime: {uptime_text}\n"
            f"Mem: {mem_used}/{mem_total} MB\n"
            f"Swap: {swap_used}/{swap_total} MB\n"
        )
        if summary == self._last_system_summary:
            return
        self._last_system_summary = summary
        self.system_summary_text.configure(state=tk.NORMAL)
        self.system_summary_text.delete("1.0", tk.END)
        self.system_summary_text.insert(tk.END, summary)
        self.system_summary_text.configure(state=tk.DISABLED)

    def _filter_processes_table(self):
        self._refresh_processes()

    def _show_selected_process_details(self, event=None):
        selection = self.processes_tree.selection()
        if not selection:
            return
        item = self.processes_tree.item(selection[0])
        values = item.get("values", "")
        name = item.get("text", "")
        if not values:
            return
        pid, user, cpu, mem, state, tty, ppid, elapsed, command = values
        self.processes_details.configure(state=tk.NORMAL)
        self.processes_details.delete("1.0", tk.END)
        details = (
            f"PID: {pid}\n"
            f"User: {user}\n"
            f"Name: {name}\n"
            f"PPID: {ppid}\n"
            f"CPU: {cpu}%\n"
            f"Memory: {mem}%\n"
            f"State: {state}\n"
            f"TTY: {tty}\n"
            f"Elapsed: {elapsed}\n"
            f"Command: {command}\n"
        )
        self.processes_details.insert(tk.END, details)
        self.processes_details.configure(state=tk.DISABLED)

    def _prompt_signal_selection(self, pid: int, name: str):
        if messagebox is None:
            return signal.SIGTERM

        choices = {
            "TERM": signal.SIGTERM,
            "INT": signal.SIGINT,
            "KILL": signal.SIGKILL,
            "QUIT": signal.SIGQUIT,
            "HUP": signal.SIGHUP,
            "STOP": signal.SIGSTOP,
            "CONT": signal.SIGCONT,
            "USR1": signal.SIGUSR1,
            "USR2": signal.SIGUSR2,
        }

        dialog = tk.Toplevel(self.root)
        dialog.withdraw()
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.attributes("-topmost", True)
        dialog.minsize(500, 420)
        dialog.configure(bg="#1c1f22")
        dialog.resizable(False, False)

        width = 500
        height = 440
        x = self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - height) // 2
        dialog.geometry(f"{width}x{height}+{x}+{y}")

        header = tk.Frame(dialog, bg="#2b2f33", height=52)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        title = tk.Label(header, text="CatLogs", bg="#2b2f33", fg="#f0f0f0",
                         font=(self.main_font, 20, "bold"), anchor="w")
        title.pack(side=tk.LEFT, padx=(18, 0), pady=(8, 0), fill=tk.X, expand=True)

        close_btn = tk.Button(
            header,
            text="×",
            bg="#2b2f33",
            fg="#f0f0f0",
            activebackground="#3a3f45",
            activeforeground="#ffffff",
            command=dialog.destroy,
            bd=0,
            padx=14,
            pady=4,
            font=(self.main_font, 20, "bold"),
        )
        close_btn.pack(side=tk.RIGHT, padx=(0, 12))

        body = tk.Frame(dialog, bg="#dfe1e2", padx=22, pady=18)
        body.pack(fill=tk.BOTH, expand=True)

        heading = tk.Label(
            body,
            text="Select signal",
            bg="#dfe1e2",
            fg="#1a1d20",
            justify=tk.LEFT,
            anchor="w",
            font=(self.main_font, 28, "bold"),
        )
        heading.pack(anchor=tk.W, pady=(0, 4))

        target = tk.Label(
            body,
            text=f"Kill PID {pid} ({name})",
            bg="#dfe1e2",
            fg="#1a1d20",
            justify=tk.LEFT,
            anchor="w",
            font=(self.main_font, 22, "bold"),
            wraplength=440,
        )
        target.pack(anchor=tk.W, pady=(0, 12))

        choice_var = tk.StringVar(value="TERM")
        option_frame = tk.LabelFrame(
            body,
            text="Signal to send",
            bg="#dfe1e2",
            fg="#1d2125",
            font=(self.main_font, 13, "bold"),
            padx=14,
            pady=12,
        )
        option_frame.pack(fill=tk.BOTH, expand=True)

        for label in ["TERM", "INT", "KILL", "QUIT", "HUP", "STOP", "CONT", "USR1", "USR2"]:
            rb = tk.Radiobutton(
                option_frame,
                text=label,
                variable=choice_var,
                value=label,
                bg="#dfe1e2",
                fg="#1d2125",
                activebackground="#dfe1e2",
                activeforeground="#1d2125",
                selectcolor="#dfe1e2",
                font=(self.main_font, 18),
                indicatoron=1,
                highlightthickness=0,
                padx=8,
                pady=4,
            )
            rb.pack(anchor=tk.W)

        result = {"signal": signal.SIGTERM}

        def apply_action():
            result["signal"] = choices.get(choice_var.get(), signal.SIGTERM)
            dialog.destroy()

        action_row = tk.Frame(body, bg="#dfe1e2")
        action_row.pack(fill=tk.X, pady=(16, 0))

        cancel_btn = tk.Button(
            action_row,
            text="Cancel",
            bg="#dfe1e2",
            fg="#1d2125",
            activebackground="#dfe1e2",
            activeforeground="#1d2125",
            command=dialog.destroy,
            font=(self.main_font, 14),
            bd=1,
            padx=16,
            pady=8,
        )
        cancel_btn.pack(side=tk.RIGHT, padx=(8, 0))

        send_btn = tk.Button(
            action_row,
            text="Send signal",
            bg="#2d3d4d",
            fg="#f2f2f2",
            activebackground="#3e536a",
            activeforeground="#ffffff",
            command=apply_action,
            font=(self.main_font, 14, "bold"),
            bd=1,
            padx=18,
            pady=8,
        )
        send_btn.pack(side=tk.RIGHT)
        send_btn.focus_set()
        dialog.bind("<Return>", lambda _e: apply_action())

        dialog.deiconify()
        dialog.wait_window(dialog)
        return result["signal"]

    def _kill_selected_process(self):
        selection = self.processes_tree.selection()
        if not selection:
            messagebox.showinfo("Process Monitor", "Select a process to kill.")
            return

        item = self.processes_tree.item(selection[0])
        values = item.get("values", "")
        pid = int(values[0])
        name = item.get("text", "")
        signal_to_send = self._prompt_signal_selection(pid, name)
        if signal_to_send is None:
            return

        try:
            os.kill(pid, signal_to_send)
            signal_name = next((name for name, sig in {
                "TERM": signal.SIGTERM,
                "INT": signal.SIGINT,
                "KILL": signal.SIGKILL,
                "QUIT": signal.SIGQUIT,
                "HUP": signal.SIGHUP,
                "STOP": signal.SIGSTOP,
                "CONT": signal.SIGCONT,
                "USR1": signal.SIGUSR1,
                "USR2": signal.SIGUSR2,
            }.items() if sig == signal_to_send), "SIGTERM")
            messagebox.showinfo("Process Monitor", f"Signal {signal_name} sent to PID {pid} ({name}).")
            self._refresh_processes()
            return
        except PermissionError:
            messagebox.showerror(
                "Permission denied",
                f"You do not have permission to send signal to PID {pid} ({name}).\nTry running CatLogs with elevated privileges.")
            return
        except ProcessLookupError:
            messagebox.showinfo("Process Monitor", f"PID {pid} is already gone.")
            return
        except Exception as exc:
            messagebox.showerror("Kill failed", f"Could not signal PID {pid}: {exc}")

    def _build_keylogger_page(self, parent):
        from .keylogger import get_status

        # Header with title and action buttons
        header_frame = ttk.Frame(parent, style="Toolbar.TFrame")
        header_frame.pack(fill=tk.X)

        inner = ttk.Frame(header_frame, style="Toolbar.TFrame")
        inner.pack(fill=tk.X, padx=14, pady=10)

        ttk.Label(inner, text="Key Logger",
                  style="Toolbar.TLabel",
                  font=(self.main_font, 14, "bold")).pack(side=tk.LEFT)

        ttk.Button(inner, text="Export CSV",
                   command=self._export_keylogger_csv).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(inner, text="Refresh",
                   command=self._refresh_keylogger_page).pack(side=tk.RIGHT, padx=(6, 0))

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X)

        # Warning / Info banner
        banner_frame = ttk.Frame(parent, style="Toolbar.TFrame")
        banner_frame.pack(fill=tk.X)

        banner_inner = ttk.Frame(banner_frame, style="Toolbar.TFrame")
        banner_inner.pack(fill=tk.X, padx=14, pady=(8, 4))

        ttk.Label(banner_inner,
                  text="Warning: This feature monitors keyboard input. The user must explicitly activate it.\n"
                       "   Key logs are stored locally and never sent anywhere. You can stop or clear logs at any time.",
                  style="Toolbar.TLabel",
                  font=(self.main_font, 9),
                  foreground=self.colors.get("warning", "#d4a846"),
                  wraplength=900, justify=tk.LEFT).pack(anchor=tk.W)

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X)

        # Main content split: left = controls/status, right = log viewer
        content_pane = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        content_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left panel: Status & Controls
        left_frame = ttk.LabelFrame(content_pane, text="  Daemon Status & Controls  ",
                                    style="Detail.TLabelframe", padding=12)
        content_pane.add(left_frame, weight=1)

        # Status info text widget
        self.kl_status_text = tk.Text(
            left_frame, wrap=tk.WORD, height=12, state=tk.DISABLED,
            font=(self.mono_font, 10),
            borderwidth=0, padx=10, pady=8,
            bg=self.colors["detail_bg"], fg=self.colors["fg"],
        )
        self.kl_status_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.kl_status_text.tag_configure("label", foreground=self.colors["accent"],
                                          font=(self.mono_font, 10, "bold"))
        self.kl_status_text.tag_configure("value", foreground=self.colors["fg"],
                                          font=(self.mono_font, 10))
        self.kl_status_text.tag_configure("running", foreground=self.colors.get("success", "#8fbf7f"),
                                          font=(self.mono_font, 11, "bold"))
        self.kl_status_text.tag_configure("stopped", foreground=self.colors.get("error", "#c45050"),
                                          font=(self.mono_font, 11, "bold"))
        self.kl_status_text.tag_configure("dim", foreground=self.colors.get("fg_dim", "#999999"),
                                          font=(self.mono_font, 9, "italic"))

        # Action buttons
        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 6))

        self.kl_start_btn = ttk.Button(btn_frame, text="Start Daemon",
                                       command=self._kl_start_daemon, style="Accent.TButton")
        self.kl_start_btn.pack(fill=tk.X, pady=(0, 4))

        self.kl_stop_btn = ttk.Button(btn_frame, text="Stop Daemon",
                                      command=self._kl_stop_daemon)
        self.kl_stop_btn.pack(fill=tk.X, pady=(0, 4))

        ttk.Separator(btn_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)

        self.kl_service_btn = ttk.Button(btn_frame, text="Install Auto-Start Service",
                                         command=self._kl_install_service)
        self.kl_service_btn.pack(fill=tk.X, pady=(0, 4))

        self.kl_uninstall_btn = ttk.Button(btn_frame, text="Remove Auto-Start Service",
                                           command=self._kl_uninstall_service)
        self.kl_uninstall_btn.pack(fill=tk.X, pady=(0, 4))

        ttk.Separator(btn_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)

        ttk.Button(btn_frame, text="Clear Key Logs",
                   command=self._kl_clear_logs).pack(fill=tk.X, pady=(0, 4))

        ttk.Button(btn_frame, text="Recompile Binary",
                   command=self._kl_recompile).pack(fill=tk.X, pady=(0, 4))

        # Right panel: Log viewer
        right_frame = ttk.LabelFrame(content_pane, text="  Key Log Viewer  ",
                                     style="Detail.TLabelframe", padding=6)
        content_pane.add(right_frame, weight=3)

        self.kl_notebook = ttk.Notebook(right_frame)
        self.kl_notebook.pack(fill=tk.BOTH, expand=True)

        # Tab 1: Readable Format
        tab_readable = ttk.Frame(self.kl_notebook)
        self.kl_notebook.add(tab_readable, text="Readable Format")

        self.kl_log_text = tk.Text(
            tab_readable, wrap=tk.WORD, state=tk.DISABLED,
            font=(self.mono_font, 10),
            borderwidth=0, padx=10, pady=8,
            bg=self.colors["bg_table"], fg=self.colors["fg"],
        )
        kl_scroll = ttk.Scrollbar(tab_readable, orient=tk.VERTICAL,
                                  command=self.kl_log_text.yview)
        self.kl_log_text.configure(yscrollcommand=kl_scroll.set)
        self.kl_log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        kl_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Tab 2: Raw Format
        tab_raw = ttk.Frame(self.kl_notebook)
        self.kl_notebook.add(tab_raw, text="Raw Format (with Timestamps)")

        self.kl_raw_text = tk.Text(
            tab_raw, wrap=tk.WORD, state=tk.DISABLED,
            font=(self.mono_font, 10),
            borderwidth=0, padx=10, pady=8,
            bg=self.colors["bg_table"], fg=self.colors["fg"],
        )
        raw_scroll = ttk.Scrollbar(tab_raw, orient=tk.VERTICAL,
                                   command=self.kl_raw_text.yview)
        self.kl_raw_text.configure(yscrollcommand=raw_scroll.set)
        self.kl_raw_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        raw_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        for text_widget in (self.kl_log_text, self.kl_raw_text):
            text_widget.tag_configure("timestamp", foreground=self.colors["accent"],
                                           font=(self.mono_font, 10))
            text_widget.tag_configure("key", foreground=self.colors["fg"],
                                           font=(self.mono_font, 10))
            text_widget.tag_configure("marker", foreground=self.colors.get("warning", "#d4a846"),
                                           font=(self.mono_font, 10, "italic"))
            text_widget.tag_configure("dim", foreground=self.colors.get("fg_dim", "#999999"),
                                           font=(self.mono_font, 10, "italic"))

    def _refresh_keylogger_page(self):
        """Refresh the keylogger status panel and log viewer."""
        from .keylogger import get_status, read_keylogs

        status = get_status()

        # Update status text
        self.kl_status_text.configure(state=tk.NORMAL)
        self.kl_status_text.delete("1.0", tk.END)

        if status["running"]:
            self.kl_status_text.insert(tk.END, "  RUNNING\n\n", "running")
        else:
            self.kl_status_text.insert(tk.END, "  STOPPED\n\n", "stopped")

        self.kl_status_text.insert(tk.END, "  PID:        ", "label")
        self.kl_status_text.insert(
            tk.END, f"{status['pid'] or '—'}\n", "value")

        self.kl_status_text.insert(tk.END, "  Binary:     ", "label")
        self.kl_status_text.insert(
            tk.END, f"{'Compiled' if status['binary_exists'] else 'Not compiled'}\n", "value")

        self.kl_status_text.insert(tk.END, "  Log File:   ", "label")
        self.kl_status_text.insert(tk.END, f"{status['log_file']}\n", "value")

        self.kl_status_text.insert(tk.END, "  Log Size:   ", "label")
        self.kl_status_text.insert(
            tk.END, f"{status['log_size_str']}\n", "value")

        self.kl_status_text.insert(tk.END, "  Platform:   ", "label")
        self.kl_status_text.insert(
            tk.END, f"{status.get('platform', 'Unknown')}\n", "value")

        self.kl_status_text.insert(tk.END, "  Auto-Start: ", "label")
        self.kl_status_text.insert(
            tk.END, f"{'Installed' if status['service_installed'] else 'Not installed'}\n", "value")

        if status.get("process_info"):
            self.kl_status_text.insert(
                tk.END, "\n  Process Details:\n", "label")
            self.kl_status_text.insert(
                tk.END, f"  {status['process_info']}\n", "dim")

        self.kl_status_text.configure(state=tk.DISABLED)

        # Update button states
        if status["running"]:
            self.kl_start_btn.configure(state="disabled")
            self.kl_stop_btn.configure(state="normal")
        else:
            self.kl_start_btn.configure(state="normal")
            self.kl_stop_btn.configure(state="disabled")

        if status["service_installed"]:
            self.kl_service_btn.configure(state="disabled")
            self.kl_uninstall_btn.configure(state="normal")
        else:
            self.kl_service_btn.configure(state="normal")
            self.kl_uninstall_btn.configure(state="disabled")

        # Update log viewer
        for text_widget in (self.kl_log_text, getattr(self, 'kl_raw_text', None)):
            if text_widget:
                text_widget.configure(state=tk.NORMAL)
                text_widget.delete("1.0", tk.END)

        lines = read_keylogs(max_lines=1500)
        if not lines:
            for text_widget in (self.kl_log_text, getattr(self, 'kl_raw_text', None)):
                if text_widget:
                    text_widget.insert(tk.END,
                                            "  No key logs recorded yet.\n\n"
                                            "  Start the daemon to begin monitoring keyboard input.\n"
                                            "  Key logs are stored locally at:\n"
                                            f"  {status['log_file']}\n",
                                            "dim")
        else:
            line_buf = []

            def flush_line():
                if line_buf:
                    text = "".join(line_buf)
                    self.kl_log_text.insert(tk.END, f"{text}\n", "key")
                    line_buf.clear()

            for line in lines:
                if not line.strip():
                    continue

                if "[Active Window:" in line:
                    flush_line()
                    self.kl_log_text.insert(
                        tk.END, "\n" + line.strip() + "\n", "marker")
                    if hasattr(self, 'kl_raw_text'):
                        self.kl_raw_text.insert(
                            tk.END, "\n" + line.strip() + "\n", "marker")
                    continue

                if line.startswith("[") and "]" in line:
                    bracket_end = line.index("]") + 1
                    ts_part = line[:bracket_end]
                    key_part = line[bracket_end:].strip()
                    
                    if hasattr(self, 'kl_raw_text'):
                        self.kl_raw_text.insert(tk.END, ts_part + " ", "timestamp")
                        if "---" in key_part:
                            self.kl_raw_text.insert(tk.END, key_part + "\n", "marker")
                        else:
                            self.kl_raw_text.insert(tk.END, key_part + "\n", "key")

                    if "---" in key_part:
                        flush_line()
                        self.kl_log_text.insert(
                            tk.END, ts_part + " ", "timestamp")
                        self.kl_log_text.insert(
                            tk.END, key_part + "\n", "marker")
                        continue

                    if key_part.startswith("^"):
                        continue

                    if key_part == "space":
                        line_buf.append(" ")
                    elif key_part == "Return":
                        flush_line()
                    elif key_part == "BackSpace":
                        line_buf.append("[Backspace]")
                    elif len(key_part) == 1:
                        line_buf.append(key_part)
                    else:
                        line_buf.append(f"<{key_part}>")
                else:
                    flush_line()
                    self.kl_log_text.insert(tk.END, line + "\n", "key")
                    if hasattr(self, 'kl_raw_text'):
                        self.kl_raw_text.insert(tk.END, line + "\n", "key")

            flush_line()
            for text_widget in (self.kl_log_text, getattr(self, 'kl_raw_text', None)):
                if text_widget:
                    text_widget.see(tk.END)
                    
        for text_widget in (self.kl_log_text, getattr(self, 'kl_raw_text', None)):
            if text_widget:
                text_widget.configure(state=tk.DISABLED)

    def _kl_start_daemon(self):
        """Start the keylogger daemon with user confirmation."""
        from .keylogger import is_compiled, compile_keylogger, start_daemon

        if not is_compiled():
            compile_result = compile_keylogger()
            if not compile_result["success"]:
                messagebox.showerror("Compilation Failed",
                                     f"Could not compile the keylogger binary.\n\n{compile_result.get('error', compile_result['message'])}")
                return

        confirm = messagebox.askyesno(
            "Start Key Logger Daemon",
            "Warning: You are about to start the key logger daemon.\n\n"
            "This will monitor all keyboard input on this X11 session and "
            "save it to a local file. No data is sent externally.\n\n"
            "The daemon will continue running in the background even after "
            "CatLogs is closed.\n\n"
            "Do you want to proceed?",
        )
        if not confirm:
            return

        result = start_daemon()
        if result["success"]:
            self.status_var.set(result["message"])
        else:
            messagebox.showerror("Start Failed",
                                 f"{result['message']}\n\n{result.get('error', '')}")

        self._refresh_keylogger_page()

    def _kl_stop_daemon(self):
        """Stop the keylogger daemon."""
        from .keylogger import stop_daemon

        result = stop_daemon()
        if result["success"]:
            self.status_var.set(result["message"])
        else:
            messagebox.showerror("Stop Failed", result["message"])

        self._refresh_keylogger_page()

    def _kl_clear_logs(self):
        from .deletion_history import log_deletion
        prot_mode = self.config.get("protection_mode", True)

        if prot_mode:
            log_deletion("Keylogger Clear",
                         "Attempted to clear keylogs", False)
            messagebox.showwarning(
                "Permission Denied", "Protection Mode is active. You do not have permission to delete logs.")
            return

        confirm = messagebox.askyesno(
            "Clear Logs", "Are you sure you want to permanently delete all key logs?")
        if confirm:
            from .keylogger import clear_keylogs
            result = clear_keylogs()
            log_deletion("Keylogger Clear",
                         "Successfully cleared keylogs", True)
            if result["success"]:
                messagebox.showinfo("Logs Cleared", result["message"])
            else:
                messagebox.showerror("Error", result["message"])
            self._refresh_keylogger_page()

    def _kl_recompile(self):
        """Recompile the keylogger binary from source."""
        from .keylogger import compile_keylogger

        result = compile_keylogger()
        if result["success"]:
            messagebox.showinfo("Compiled", result["message"])
            self.status_var.set("Key logger binary compiled successfully.")
        else:
            messagebox.showerror("Compilation Failed",
                                 f"{result['message']}\n\n{result.get('error', '')}")

        self._refresh_keylogger_page()

    def _kl_install_service(self):
        """Install systemd user service for auto-start."""
        from .keylogger import install_systemd_service

        confirm = messagebox.askyesno(
            "Install Auto-Start Service",
            "This will install a systemd user service that automatically starts "
            "the key logger daemon when you log in.\n\n"
            "The daemon will persist across reboots.\n\n"
            "Do you want to proceed?",
        )
        if not confirm:
            return

        result = install_systemd_service()
        if result["success"]:
            messagebox.showinfo("Service Installed", result["message"])
            self.status_var.set(result["message"])
        else:
            messagebox.showerror("Install Failed",
                                 f"{result['message']}\n\n{result.get('error', '')}")

        self._refresh_keylogger_page()

    def _kl_uninstall_service(self):
        """Remove systemd user service."""
        from .keylogger import uninstall_systemd_service

        confirm = messagebox.askyesno(
            "Remove Auto-Start Service",
            "This will remove the auto-start service.\n"
            "The daemon will no longer start on login.\n\n"
            "Do you want to proceed?",
        )
        if not confirm:
            return

        result = uninstall_systemd_service()
        if result["success"]:
            messagebox.showinfo("Service Removed", result["message"])
            self.status_var.set(result["message"])
        else:
            messagebox.showerror("Uninstall Failed",
                                 f"{result['message']}\n\n{result.get('error', '')}")

        self._refresh_keylogger_page()

    def _build_status(self, parent):
        status_frame = ttk.Frame(parent, style="Toolbar.TFrame")
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)

        inner = ttk.Frame(status_frame, style="Toolbar.TFrame")
        inner.pack(fill=tk.X, padx=14, pady=4)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(inner, textvariable=self.status_var, style="Toolbar.TLabel",
                  font=(self.main_font, 9)).pack(side=tk.LEFT)

        self.progress = ttk.Progressbar(inner, mode="determinate", length=160)
        self.progress.pack(side=tk.RIGHT)

    def _refresh_export_history(self):
        self.export_history_text.configure(state=tk.NORMAL)
        self.export_history_text.delete("1.0", tk.END)

        history = load_export_history()
        if not history:
            self.export_history_text.insert(tk.END,
                                            "  No exports have been recorded yet.\n\n"
                                            "  Export data from the Logs page to see history here.",
                                            "dim")
        else:
            self.export_history_text.insert(
                tk.END, f"  Total Exports: {len(history)}\n\n", "header")
            for idx, entry in enumerate(reversed(history), 1):
                self.export_history_text.insert(
                    tk.END, f"  Export #{idx}\n", "label")
                self.export_history_text.insert(
                    tk.END, f"    Date:          ", "label")
                self.export_history_text.insert(
                    tk.END, f"{entry.get('timestamp', 'N/A')}\n", "value")
                self.export_history_text.insert(
                    tk.END, f"    User:          ", "label")
                self.export_history_text.insert(
                    tk.END, f"{entry.get('username', 'N/A')}\n", "value")
                self.export_history_text.insert(
                    tk.END, f"    File:          ", "label")
                self.export_history_text.insert(
                    tk.END, f"{entry.get('filepath', 'N/A')}\n", "value")
                self.export_history_text.insert(
                    tk.END, f"    Records:       ", "label")
                self.export_history_text.insert(
                    tk.END, f"{entry.get('record_count', 'N/A')}\n", "value")
                self.export_history_text.insert(
                    tk.END, f"    Version:       ", "label")
                self.export_history_text.insert(
                    tk.END, f"{entry.get('version', 'N/A')}\n", "value")

                filters = entry.get("filters", {})
                if filters:
                    self.export_history_text.insert(
                        tk.END, f"    Filters:\n", "label")
                    for k, v in filters.items():
                        if v and v != "All":
                            self.export_history_text.insert(
                                tk.END, f"      {k}: ", "label")
                            self.export_history_text.insert(
                                tk.END, f"{v}\n", "value")

                self.export_history_text.insert(
                    tk.END, "  " + "-" * 60 + "\n\n", "separator")

        self.export_history_text.configure(state=tk.DISABLED)

    def _refresh_read_errors(self):
        self.read_errors_text.configure(state=tk.NORMAL)
        self.read_errors_text.delete("1.0", tk.END)

        errors = load_read_errors()
        if not errors:
            self.read_errors_text.insert(tk.END,
                                         "  No read errors have been recorded.\n\n"
                                         "  Paths that the software cannot access will appear here.",
                                         "dim")
        else:
            seen_paths = {}
            for err in errors:
                path = err.get("filepath", "unknown")
                if path not in seen_paths:
                    seen_paths[path] = err
                else:
                    if err.get("timestamp", "") > seen_paths[path].get("timestamp", ""):
                        seen_paths[path] = err

            unique_errors = list(seen_paths.values())
            self.read_errors_text.insert(tk.END,
                                         f"  Inaccessible Paths: {len(unique_errors)} unique path(s)\n\n", "header")

            for idx, err in enumerate(unique_errors, 1):
                self.read_errors_text.insert(tk.END, f"  #{idx}  ", "label")
                self.read_errors_text.insert(
                    tk.END, f"{err.get('filepath', 'N/A')}\n", "value")
                self.read_errors_text.insert(
                    tk.END, f"      Error:     ", "label")
                self.read_errors_text.insert(
                    tk.END, f"{err.get('error', 'N/A')}\n", "error_text")
                self.read_errors_text.insert(
                    tk.END, f"      Collector: ", "label")
                self.read_errors_text.insert(
                    tk.END, f"{err.get('collector', 'N/A')}\n", "value")
                self.read_errors_text.insert(
                    tk.END, f"      Last Seen: ", "label")
                self.read_errors_text.insert(
                    tk.END, f"{err.get('timestamp', 'N/A')}\n", "value")
                self.read_errors_text.insert(
                    tk.END, "  " + "-" * 60 + "\n\n", "separator")

        self.read_errors_text.configure(state=tk.DISABLED)

    def _clear_read_errors(self):
        if messagebox.askyesno("Clear Read Errors",
                               "Are you sure you want to clear the read errors log?"):
            clear_read_errors()
            self._refresh_read_errors()

    def _show_first_run_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Welcome to CatLogs")
        dialog.transient(self.root)
        dialog.grab_set()

        dialog.geometry("1000x650")
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        dialog.configure(bg=self.colors["bg_secondary"])

        ttk.Label(dialog, text="Welcome to CatLogs!", font=(self.main_font, 16, "bold"),
                  background=self.colors["bg_secondary"]).pack(pady=(50, 20))

        ttk.Label(dialog, text="Which theme would you prefer to use?", font=(self.main_font, 12),
                  background=self.colors["bg_secondary"]).pack(pady=(0, 40))

        btn_frame = ttk.Frame(dialog, style="Toolbar.TFrame")
        btn_frame.pack(fill=tk.X, padx=100)

        def set_theme(theme_name):
            self.current_theme = theme_name
            self.config["theme"] = theme_name
            self.config["first_run"] = False
            self.config["window_feature_shown"] = True
            save_config(self.config)
            self._apply_theme()
            dialog.destroy()
            self._refresh_data()

        ttk.Button(btn_frame, text="Dark Theme", command=lambda: set_theme(
            "dark")).pack(side=tk.LEFT, expand=True, padx=20, fill=tk.X)
        ttk.Button(btn_frame, text="Light Theme", command=lambda: set_theme(
            "light")).pack(side=tk.RIGHT, expand=True, padx=20, fill=tk.X)

    def _show_window_feature_dialog(self):
        messagebox.showinfo("New Feature: Window Tracking",
                            "CatLogs now tracks which application window you are typing in!\n\n"
                            "This helps you see the environment where your keys were pressed.")
        self.config["window_feature_shown"] = True
        save_config(self.config)

    def _show_about(self):
        if getattr(self, '_about_dialog', None) and self._about_dialog.winfo_exists():
            self._about_dialog.lift()
            return

        dialog = tk.Toplevel(self.root)
        self._about_dialog = dialog
        dialog.title("About")
        dialog.transient(self.root)
        dialog.resizable(True, True)
        dialog.grab_set()
        dialog.geometry("600x600")
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        dialog.configure(bg=self.colors["bg"])

        main_frame = ttk.Frame(dialog)
        main_frame.pack(fill=tk.BOTH, expand=True)

        if getattr(self, '_help_photo', None):
            ttk.Label(main_frame, image=self._help_photo).pack(pady=(30, 10))

        ttk.Label(main_frame, text="CatLogs", font=(
            self.main_font, 18, "bold")).pack()

        from . import __version__
        ttk.Label(main_frame, text=f"{__version__}", font=(
            self.main_font, 12)).pack(pady=(0, 10))

        ttk.Label(main_frame, text="View and search system logs securely.", font=(
            self.main_font, 10)).pack()

        def open_web(e):
            import webbrowser
            webbrowser.open("https://catlogs.wassim.tech/")

        link = tk.Label(main_frame, text="Website", font=(self.main_font, 10),
                        fg="#3584e4", bg=self.colors["bg"], cursor="hand2")
        link.pack(pady=(5, 10))
        link.bind("<Button-1>", open_web)

        ttk.Label(main_frame, text="Copyright © 2026 Wassim\nDeveloped by https://github.com/wmBolles",
                  justify=tk.CENTER, font=(self.main_font, 9)).pack(pady=(10, 5))
        ttk.Label(main_frame, text="This program comes with absolutely no warranty.",
                  justify=tk.CENTER, font=(self.main_font, 8)).pack()

    def _show_shortcuts(self):
        if getattr(self, '_shortcuts_dialog', None) and self._shortcuts_dialog.winfo_exists():
            self._shortcuts_dialog.lift()
            return

        dialog = tk.Toplevel(self.root)
        self._shortcuts_dialog = dialog
        dialog.title("Shortcuts")
        dialog.transient(self.root)
        dialog.resizable(True, True)
        dialog.grab_set()
        dialog.geometry("800x600")
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        dialog.configure(bg=self.colors["bg"])

        main_frame = ttk.Frame(dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10)

        ttk.Label(left_frame, text="General", font=(
            self.main_font, 12, "bold")).pack(anchor="w", pady=(0, 15))
        ttk.Label(right_frame, text="Application", font=(
            self.main_font, 12, "bold")).pack(anchor="w", pady=(0, 15))

        def add_shortcut(parent, keys, desc):
            f = ttk.Frame(parent)
            f.pack(fill=tk.X, pady=8)
            for key in keys:
                if key == "+":
                    ttk.Label(f, text="+").pack(side=tk.LEFT, padx=5)
                else:
                    k = tk.Label(f, text=key, font=(self.main_font, 9), bg="#444",
                                 fg="white", relief="solid", borderwidth=1, padx=6, pady=2)
                    k.pack(side=tk.LEFT)
            ttk.Label(f, text=desc).pack(side=tk.LEFT, padx=15)

        add_shortcut(left_frame, ["F5"], "Refresh data")
        add_shortcut(left_frame, ["Esc"], "Clear all filters")
        add_shortcut(left_frame, ["Ctrl", "+", "?"], "Keyboard shortcuts")
        add_shortcut(left_frame, ["Ctrl", "+", "+"], "Zoom in")
        add_shortcut(left_frame, ["Ctrl", "+", "-"], "Zoom out")

        add_shortcut(right_frame, ["Ctrl", "+", "E"], "Export logs to a file")
        add_shortcut(right_frame, ["Ctrl", "+", "R"], "Refresh data")
        add_shortcut(right_frame, ["Ctrl", "+", ","],
                     "Open Settings & Log Paths")
        add_shortcut(right_frame, ["Ctrl", "+", "Q"], "Quit application")

    def _show_settings(self):
        if getattr(self, '_settings_dialog', None) and self._settings_dialog.winfo_exists():
            self._settings_dialog.lift()
            return

        dialog = tk.Toplevel(self.root)
        self._settings_dialog = dialog
        dialog.title("Settings")
        dialog.resizable(True, True)
        dialog.transient(self.root)

        d_width = 1060
        d_height = 720
        self.root.update_idletasks()
        rx = self.root.winfo_x()
        ry = self.root.winfo_y()
        rw = self.root.winfo_width()
        rh = self.root.winfo_height()
        x = max(10, rx + (rw - d_width) // 2)
        y = max(10, ry + (rh - d_height) // 2)
        dialog.geometry(f"{d_width}x{d_height}+{x}+{y}")
        dialog.minsize(920, 620)
        dialog.configure(bg=self.colors["bg"])
        dialog.grab_set()

        # Working copy of log paths and cache of statuses
        working_paths = [dict(p) for p in load_log_paths()]
        status_cache = {}

        def update_status_cache():
            for p in working_paths:
                status_cache[p.get("path", "")] = check_path_status(
                    p.get("path", ""))

        update_status_cache()

        # Format mapping dict for readable display
        format_display_map = dict(LOG_FORMAT_CHOICES)

        # Main wrapper layout
        main_frame = ttk.Frame(dialog, padding=0)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Header with navigation tabs
        header_bar = ttk.Frame(main_frame, style="Toolbar.TFrame")
        header_bar.pack(fill=tk.X)

        header_inner = ttk.Frame(header_bar, style="Toolbar.TFrame")
        header_inner.pack(fill=tk.X, padx=16, pady=(12, 10))

        ttk.Label(header_inner, text="Settings", font=(self.main_font, 14, "bold"),
                  background=self.colors["bg_secondary"], foreground=self.colors["accent"]).pack(side=tk.LEFT, padx=(0, 24))

        # Nav tab buttons
        tab_nav_frame = ttk.Frame(header_inner, style="Toolbar.TFrame")
        tab_nav_frame.pack(side=tk.LEFT)

        # Content areas
        content_container = ttk.Frame(main_frame)
        content_container.pack(fill=tk.BOTH, expand=True,
                               padx=16, pady=(10, 0))

        paths_frame = ttk.Frame(content_container)
        appearance_frame = ttk.Frame(content_container)
        security_frame = ttk.Frame(content_container)

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

        btn_tab_paths = ttk.Button(tab_nav_frame, text="[File] Log File Paths", style="NavActive.TButton",
                                   command=lambda: switch_tab("paths"))
        btn_tab_paths.pack(side=tk.LEFT, padx=(0, 6))

        btn_tab_appearance = ttk.Button(tab_nav_frame, text="[Art] Appearance", style="Nav.TButton",
                                        command=lambda: switch_tab("appearance"))
        btn_tab_appearance.pack(side=tk.LEFT, padx=(0, 6))

        btn_tab_security = ttk.Button(tab_nav_frame, text="Security", style="Nav.TButton",
                                      command=lambda: switch_tab("security"))
        btn_tab_security.pack(side=tk.LEFT)

        # -------------------------------------------------------------------
        # TAB 1: LOG FILE PATHS
        # -------------------------------------------------------------------
        paths_header = ttk.Frame(paths_frame)
        paths_header.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(paths_header, text="Monitored Log File Paths",
                  font=(self.main_font, 12, "bold")).pack(anchor=tk.W)
        ttk.Label(paths_header,
                  text="View all log files read by CatLogs, add custom log files (web servers, JSON lines, application logs, audit logs, etc.), or delete paths.",
                  font=(self.main_font, 9), foreground=self.colors["fg_dim"]).pack(anchor=tk.W, pady=(2, 0))

        # Filter and Search bar for paths
        filter_bar = ttk.Frame(
            paths_frame, style="Toolbar.TFrame", padding=(10, 8))
        filter_bar.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(filter_bar, text="Filter:", style="Toolbar.TLabel").pack(
            side=tk.LEFT, padx=(0, 6))
        path_search_var = tk.StringVar()
        search_entry = ttk.Entry(
            filter_bar, textvariable=path_search_var, width=28)
        search_entry.pack(side=tk.LEFT, padx=(0, 16))

        ttk.Label(filter_bar, text="Status:", style="Toolbar.TLabel").pack(
            side=tk.LEFT, padx=(0, 6))
        status_filter_var = tk.StringVar(value="All")
        status_combo = ttk.Combobox(filter_bar, textvariable=status_filter_var,
                                    values=["All", "Active Only",
                                            "Inaccessible / Missing"],
                                    state="readonly", width=20)
        status_combo.pack(side=tk.LEFT, padx=(0, 10))

        # Table for paths
        tree_frame = ttk.Frame(paths_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("enabled", "name", "path", "type", "status")
        paths_tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", selectmode="browse")

        paths_tree.heading("enabled", text="Active", anchor=tk.CENTER)
        paths_tree.heading("name", text="Name / Label", anchor=tk.W)
        paths_tree.heading("path", text="Log File Path", anchor=tk.W)
        paths_tree.heading("type", text="Format / Type", anchor=tk.W)
        paths_tree.heading("status", text="File Status", anchor=tk.W)

        paths_tree.column("enabled", width=65, minwidth=50, anchor=tk.CENTER)
        paths_tree.column("name", width=150, minwidth=100, anchor=tk.W)
        paths_tree.column("path", width=380, minwidth=200, anchor=tk.W)
        paths_tree.column("type", width=150, minwidth=100, anchor=tk.W)
        paths_tree.column("status", width=200, minwidth=120, anchor=tk.W)

        paths_vsb = ttk.Scrollbar(
            tree_frame, orient=tk.VERTICAL, command=paths_tree.yview)
        paths_hsb = ttk.Scrollbar(
            tree_frame, orient=tk.HORIZONTAL, command=paths_tree.xview)
        paths_tree.configure(yscrollcommand=paths_vsb.set,
                             xscrollcommand=paths_hsb.set)

        paths_tree.grid(row=0, column=0, sticky="nsew")
        paths_vsb.grid(row=0, column=1, sticky="ns")
        paths_hsb.grid(row=1, column=0, sticky="ew")

        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # Configure tags for row styling
        paths_tree.tag_configure("even", background=self.colors["bg_table"])
        paths_tree.tag_configure("odd", background=self.colors["bg_secondary"])
        paths_tree.tag_configure(
            "disabled_row", foreground=self.colors["fg_dim"])

        # Summary counter label
        paths_summary_var = tk.StringVar(value="")
        summary_lbl = ttk.Label(paths_frame, textvariable=paths_summary_var, font=(self.main_font, 9),
                                foreground=self.colors["fg_dim"])
        summary_lbl.pack(anchor=tk.W, pady=(6, 4))

        # Refresh table contents
        item_id_to_index = {}

        def refresh_paths_table():
            nonlocal item_id_to_index
            item_id_to_index = {}
            for item in paths_tree.get_children():
                paths_tree.delete(item)

            search_query = path_search_var.get().lower().strip()
            status_filter = status_filter_var.get()

            enabled_count = 0
            active_count = 0
            missing_count = 0

            row_idx = 0
            for idx, item in enumerate(working_paths):
                path_str = item.get("path", "")
                name_str = item.get("name", "")
                type_str = item.get("type", "auto")
                is_enabled = item.get("enabled", True)

                if is_enabled:
                    enabled_count += 1

                st = status_cache.get(path_str, check_path_status(path_str))
                status_code = st.get("status_code", "not_found")
                if status_code == "active":
                    active_count += 1
                else:
                    missing_count += 1

                # Apply filters
                if search_query:
                    searchable = f"{name_str} {path_str} {type_str} {st.get('status_text', '')}".lower(
                    )
                    if search_query not in searchable:
                        continue

                if status_filter == "Active Only" and status_code != "active":
                    continue
                if status_filter == "Inaccessible / Missing" and status_code == "active":
                    continue

                display_type = format_display_map.get(
                    type_str, type_str.title())
                enabled_text = "Yes" if is_enabled else "No"

                tags = ["even" if row_idx % 2 == 0 else "odd"]
                if not is_enabled:
                    tags.append("disabled_row")

                item_id = paths_tree.insert(
                    "", tk.END,
                    values=(
                        enabled_text,
                        name_str,
                        path_str,
                        display_type,
                        st.get("status_text", "-"),
                    ),
                    tags=tags,
                )
                item_id_to_index[item_id] = idx
                row_idx += 1

            paths_summary_var.set(
                f"Total Paths: {len(working_paths)}  *  Enabled: {enabled_count}  *  "
                f"Active & Readable: {active_count}  *  Inaccessible / Missing: {missing_count}"
            )

        path_search_var.trace_add("write", lambda *_: refresh_paths_table())
        status_filter_var.trace_add("write", lambda *_: refresh_paths_table())

        def get_selected_path_index() -> Optional[int]:
            selected = paths_tree.selection()
            if not selected:
                return None
            return item_id_to_index.get(selected[0])

        def toggle_selected_path():
            idx = get_selected_path_index()
            if idx is not None and 0 <= idx < len(working_paths):
                working_paths[idx]["enabled"] = not working_paths[idx].get(
                    "enabled", True)
                refresh_paths_table()

        def delete_selected_path():
            idx = get_selected_path_index()
            if idx is None or not (0 <= idx < len(working_paths)):
                messagebox.showinfo(
                    "Delete Path", "Please select a log path from the table to delete.", parent=dialog)
                return

            target = working_paths[idx]
            path_name = target.get("name") or target.get("path")
            confirm = messagebox.askyesno(
                "Confirm Deletion",
                f"Are you sure you want to remove the log path:\n\n{target.get('path')} ({path_name})?\n\n"
                f"CatLogs will no longer read logs from this path.",
                parent=dialog,
            )
            if confirm:
                del working_paths[idx]
                refresh_paths_table()

        # Modal dialog to Add or Edit a log path
        def open_path_modal(edit_index: Optional[int] = None):
            is_edit = edit_index is not None and 0 <= edit_index < len(
                working_paths)
            target_data = working_paths[edit_index] if is_edit else {}

            modal = tk.Toplevel(dialog)
            modal.title(
                "Edit Log File Path" if is_edit else "Add Log File Path")
            modal.transient(dialog)
            modal.configure(bg=self.colors["bg_secondary"])

            m_width = 750
            m_height = 580
            dialog.update_idletasks()
            dx = dialog.winfo_x()
            dy = dialog.winfo_y()
            dw = dialog.winfo_width()
            dh = dialog.winfo_height()
            mx = max(10, dx + (dw - m_width) // 2)
            my = max(10, dy + (dh - m_height) // 2)
            modal.geometry(f"{m_width}x{m_height}+{mx}+{my}")
            modal.grab_set()
            modal.minsize(680, 520)

            # 1. Pinned bottom action bar (pack side=tk.BOTTOM first so it never gets cut off)
            modal_btn_row = ttk.Frame(
                modal, style="Toolbar.TFrame", padding=(24, 12, 24, 16))
            modal_btn_row.pack(side=tk.BOTTOM, fill=tk.X)

            ttk.Button(modal_btn_row, text="Save Changes" if is_edit else "Add Path",
                       command=lambda: save_modal(), style="Accent.TButton").pack(side=tk.RIGHT)
            ttk.Button(modal_btn_row, text="Cancel",
                       command=modal.destroy).pack(side=tk.RIGHT, padx=12)

            ttk.Separator(modal, orient=tk.HORIZONTAL).pack(
                side=tk.BOTTOM, fill=tk.X)

            # 2. Main content area
            modal_frame = ttk.Frame(
                modal, style="Toolbar.TFrame", padding=(24, 20, 24, 8))
            modal_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

            ttk.Label(modal_frame, text="Edit Log File Path" if is_edit else "Add New Log File Path",
                      font=(self.main_font, 13, "bold"), background=self.colors["bg_secondary"]).pack(anchor=tk.W, pady=(0, 4))
            ttk.Label(modal_frame,
                      text="Enter the file path of any log file on your system, or browse to select one.",
                      font=(self.main_font, 9), foreground=self.colors["fg_dim"],
                      background=self.colors["bg_secondary"]).pack(anchor=tk.W, pady=(0, 14))

            # Path Entry + Browse Button
            ttk.Label(modal_frame, text="Log File Path:", font=(self.main_font, 10, "bold"),
                      background=self.colors["bg_secondary"]).pack(anchor=tk.W, pady=(2, 2))

            path_input_frame = ttk.Frame(modal_frame, style="Toolbar.TFrame")
            path_input_frame.pack(fill=tk.X, pady=(0, 10))

            path_var = tk.StringVar(value=target_data.get("path", ""))
            path_entry = ttk.Entry(
                path_input_frame, textvariable=path_var, font=(self.mono_font, 10))
            path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

            def browse_file():
                chosen = filedialog.askopenfilename(
                    parent=modal,
                    title="Select Log File to Monitor",
                    filetypes=[
                        ("Log & Text Files",
                         "*.log *.txt *.json *.jsonl *.ndjson *.gz *.1 *"),
                        ("All Files", "*.*")
                    ]
                )
                if chosen:
                    path_var.set(chosen)
                    file_name = Path(chosen).name
                    cur_name = name_var.get().strip()
                    if not cur_name or cur_name == Path(path_var.get()).name or cur_name == target_data.get("name", ""):
                        name_var.set(file_name)
                    run_preview()

            ttk.Button(path_input_frame, text="Browse...",
                       command=browse_file).pack(side=tk.RIGHT)

            # Name / Label and Type Row in balanced 2-column grid
            name_row = ttk.Frame(modal_frame, style="Toolbar.TFrame")
            name_row.pack(fill=tk.X, pady=(0, 10))
            name_row.columnconfigure(0, weight=1)
            name_row.columnconfigure(1, weight=1)

            name_col = ttk.Frame(name_row, style="Toolbar.TFrame")
            name_col.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

            ttk.Label(name_col, text="Display Name / Label:", font=(self.main_font, 10, "bold"),
                      background=self.colors["bg_secondary"]).pack(anchor=tk.W, pady=(0, 2))
            name_var = tk.StringVar(value=target_data.get("name", ""))
            name_entry = ttk.Entry(name_col, textvariable=name_var)
            name_entry.pack(fill=tk.X)

            type_col = ttk.Frame(name_row, style="Toolbar.TFrame")
            type_col.grid(row=0, column=1, sticky="nsew")

            ttk.Label(type_col, text="Log Format / Type:", font=(self.main_font, 10, "bold"),
                      background=self.colors["bg_secondary"]).pack(anchor=tk.W, pady=(0, 2))

            type_labels = [label for _, label in LOG_FORMAT_CHOICES]
            type_val_to_label = dict(LOG_FORMAT_CHOICES)
            type_label_to_val = {l: v for v, l in LOG_FORMAT_CHOICES}

            curr_type_val = target_data.get("type", "auto")
            curr_type_label = type_val_to_label.get(
                curr_type_val, type_labels[0])

            type_var = tk.StringVar(value=curr_type_label)
            type_combo = ttk.Combobox(
                type_col, textvariable=type_var, values=type_labels, state="readonly", width=28)
            type_combo.pack(fill=tk.X)

            # Enabled Checkbox
            enabled_var = tk.BooleanVar(value=target_data.get("enabled", True))
            enabled_cb = ttk.Checkbutton(
                modal_frame, text="Enable log reading from this path", variable=enabled_var)
            enabled_cb.pack(anchor=tk.W, pady=(2, 10))

            # Preview box with header button
            preview_frame = ttk.LabelFrame(
                modal_frame, text=" File Verification & Format Preview ", padding=10)
            preview_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

            preview_header = ttk.Frame(preview_frame)
            preview_header.pack(fill=tk.X, pady=(0, 6))

            preview_status_lbl = ttk.Label(preview_header, text="Click 'Test & Preview' to inspect and verify file parsing.",
                                           font=(self.main_font, 9, "italic"), foreground=self.colors["fg_dim"])
            preview_status_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

            btn_test = ttk.Button(
                preview_header, text="Test & Preview", command=lambda: run_preview())
            btn_test.pack(side=tk.RIGHT)

            preview_text = tk.Text(
                preview_frame, wrap=tk.WORD, height=5, state=tk.DISABLED,
                bg=self.colors["detail_bg"], fg=self.colors["fg"],
                font=(self.mono_font, 9), borderwidth=0, padx=8, pady=6
            )
            preview_text.pack(fill=tk.BOTH, expand=True)

            def run_preview():
                p = path_var.get().strip()
                if not p:
                    preview_status_lbl.configure(
                        text="Please enter or browse to a file path first.", foreground=self.colors["warning"])
                    return

                selected_type = type_label_to_val.get(type_var.get(), "auto")
                chk = check_path_status(p)

                preview_text.configure(state=tk.NORMAL)
                preview_text.delete("1.0", tk.END)

                if chk["status_code"] == "not_found":
                    preview_status_lbl.configure(
                        text="Warning: File does not exist on disk.", foreground=self.colors["warning"])
                    preview_text.insert(
                        tk.END, f"Path: {chk['resolved_path']}\nStatus: Not found.\nNote: You can still add this path if the log file will be generated later.")
                elif chk["status_code"] == "permission_denied":
                    preview_status_lbl.configure(
                        text="Error: Permission Denied: Cannot read file.", foreground=self.colors["error"])
                    preview_text.insert(
                        tk.END, f"Path: {chk['resolved_path']}\nError: Read permission denied for current user.\nTip: Run as root/sudo or add read permissions to monitor this file.")
                elif chk["status_code"] == "not_a_file":
                    preview_status_lbl.configure(
                        text="[File] Path is a directory, not a log file.", foreground=self.colors["warning"])
                    preview_text.insert(
                        tk.END, f"Path: {chk['resolved_path']}\nPlease select a specific log file inside this directory.")
                else:
                    # File is readable! Let's test parsing
                    try:
                        sample_entries = parse_log_file(
                            p, log_type=selected_type, max_lines=100)
                        if sample_entries:
                            e = sample_entries[0]
                            preview_status_lbl.configure(
                                text=f"Successfully detected and parsed {len(sample_entries)} entries! (Size: {chk['size_str']})",
                                foreground=self.colors["success"]
                            )
                            preview_text.insert(tk.END, f"Sample Entry #1:\n")
                            preview_text.insert(
                                tk.END, f"  Timestamp : {e.timestamp_str}\n")
                            preview_text.insert(
                                tk.END, f"  User      : {e.user}\n")
                            preview_text.insert(
                                tk.END, f"  Shell/Type: {e.shell}\n")
                            preview_text.insert(
                                tk.END, f"  Command   : {e.command[:90]}\n")
                            if e.status:
                                preview_text.insert(
                                    tk.END, f"  Status    : {e.status}\n")
                        else:
                            preview_status_lbl.configure(
                                text=f"File readable ({chk['size_str']}), but contains no entries yet.", foreground=self.colors["success"])
                            preview_text.insert(
                                tk.END, "File is empty or currently contains no matching log lines.")
                    except Exception as err:
                        preview_status_lbl.configure(
                            text=f"Parsing error: {err}", foreground=self.colors["error"])
                        preview_text.insert(tk.END, str(err))

                preview_text.configure(state=tk.DISABLED)

            type_combo.bind("<<ComboboxSelected>>", lambda _: run_preview())

            def save_modal():
                p = path_var.get().strip()
                if not p:
                    messagebox.showwarning(
                        "Missing Path", "Please enter a valid log file path.", parent=modal)
                    return

                expanded = os.path.expanduser(os.path.expandvars(p))
                if os.path.isdir(expanded):
                    messagebox.showwarning(
                        "Invalid Path",
                        f"The path '{p}' is a directory, not a log file.\n\nPlease enter or browse to a specific file inside this folder.",
                        parent=modal
                    )
                    return

                n = name_var.get().strip()
                if not n:
                    n = Path(p).name or p

                sel_type = type_label_to_val.get(type_var.get(), "auto")
                en = enabled_var.get()

                norm_new = os.path.expanduser(os.path.expandvars(p))
                for i, existing in enumerate(working_paths):
                    if is_edit and i == edit_index:
                        continue
                    if os.path.expanduser(os.path.expandvars(existing.get("path", ""))) == norm_new:
                        messagebox.showwarning(
                            "Duplicate Path", f"The log path '{p}' is already in the list.", parent=modal)
                        return

                item_obj = {
                    "path": p,
                    "name": n,
                    "type": sel_type,
                    "enabled": en,
                }

                if is_edit:
                    working_paths[edit_index] = item_obj
                else:
                    working_paths.append(item_obj)

                status_cache[p] = check_path_status(p)
                refresh_paths_table()
                modal.destroy()

            if path_var.get():
                modal.after(100, run_preview)

        # Paths Action Buttons Toolbar
        btn_toolbar = ttk.Frame(paths_frame)
        btn_toolbar.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(btn_toolbar, text="Add Log Path...", command=lambda: open_path_modal(None),
                   style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(btn_toolbar, text="Edit Selected...",
                   command=lambda: open_path_modal(get_selected_path_index()) if get_selected_path_index() is not None else messagebox.showinfo("Edit Path", "Please select a log path from the table to edit.", parent=dialog)).pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(btn_toolbar, text="Delete Path",
                   command=delete_selected_path).pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(btn_toolbar, text="Toggle Active",
                   command=toggle_selected_path).pack(side=tk.LEFT, padx=(0, 16))

        def reset_to_defaults():
            confirm = messagebox.askyesno(
                "Reset Log Paths",
                "Are you sure you want to reset all log file paths to the system defaults?\n\n"
                "Any custom added log file paths will be removed.",
                parent=dialog
            )
            if confirm:
                working_paths[:] = [dict(p) for p in get_default_log_paths()]
                update_status_cache()
                refresh_paths_table()

        def recheck_all_statuses():
            update_status_cache()
            refresh_paths_table()
            messagebox.showinfo(
                "Status Check", "File statuses have been re-checked across the system.", parent=dialog)

        ttk.Button(btn_toolbar, text="Reset Defaults",
                   command=reset_to_defaults).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(btn_toolbar, text="Refresh Statuses",
                   command=recheck_all_statuses).pack(side=tk.RIGHT)

        # Table event bindings
        paths_tree.bind("<Double-Button-1>", lambda _: toggle_selected_path())
        paths_tree.bind("<space>", lambda _: toggle_selected_path())
        paths_tree.bind("<Delete>", lambda _: delete_selected_path())
        paths_tree.bind("<Return>", lambda _: open_path_modal(
            get_selected_path_index()) if get_selected_path_index() is not None else None)

        # -------------------------------------------------------------------
        # TAB 2: APPEARANCE
        # -------------------------------------------------------------------
        app_header = ttk.Frame(appearance_frame)
        app_header.pack(fill=tk.X, pady=(0, 16))

        ttk.Label(app_header, text="Visual Appearance & Typography",
                  font=(self.main_font, 12, "bold")).pack(anchor=tk.W)
        ttk.Label(app_header, text="Customize the application theme and font families.",
                  font=(self.main_font, 9), foreground=self.colors["fg_dim"]).pack(anchor=tk.W, pady=(2, 0))

        theme_card = ttk.Frame(
            appearance_frame, style="Toolbar.TFrame", padding=20)
        theme_card.pack(fill=tk.X, pady=(0, 16))

        ttk.Label(theme_card, text="Theme:", font=(self.main_font, 11, "bold"),
                  background=self.colors["bg_secondary"]).pack(anchor=tk.W, pady=(0, 4))
        theme_var = tk.StringVar(value=self.current_theme)
        theme_combo = ttk.Combobox(theme_card, textvariable=theme_var, values=list(THEMES.keys()),
                                   state="readonly", width=30, font=(self.main_font, 11))
        theme_combo.pack(anchor=tk.W, pady=(0, 16))

        ttk.Label(theme_card, text="Main UI Font:", font=(self.main_font, 11, "bold"),
                  background=self.colors["bg_secondary"]).pack(anchor=tk.W, pady=(0, 4))
        main_font_var = tk.StringVar(value=self.main_font)
        main_font_combo = ttk.Combobox(theme_card, textvariable=main_font_var,
                                       values=["sans-serif", "Arial", "Helvetica", "Ubuntu", "DejaVu Sans",
                                               "Segoe UI", "Roboto", "Open Sans", "Tahoma", "Noto Sans",
                                               "Liberation Sans", "Cantarell", "Fira Sans", "Droid Sans", "Inter"],
                                       width=30, font=(self.main_font, 11))
        main_font_combo.pack(anchor=tk.W, pady=(0, 16))

        ttk.Label(theme_card, text="Monospace / Log Font:", font=(self.main_font, 11, "bold"),
                  background=self.colors["bg_secondary"]).pack(anchor=tk.W, pady=(0, 4))
        mono_font_var = tk.StringVar(value=self.mono_font)
        mono_font_combo = ttk.Combobox(theme_card, textvariable=mono_font_var,
                                       values=["Consolas", "monospace", "Courier New", "DejaVu Sans Mono",
                                               "Ubuntu Mono", "Fira Code", "JetBrains Mono", "Hack",
                                               "Cascadia Code", "Inconsolata", "Source Code Pro",
                                               "Anonymous Pro", "Droid Sans Mono", "Liberation Mono",
                                               "Bitstream Vera Sans Mono"],
                                       width=30, font=(self.main_font, 11))
        mono_font_combo.pack(anchor=tk.W)

        # -------------------------------------------------------------------
        # -------------------------------------------------------------------
        # TAB 3: SECURITY
        # -------------------------------------------------------------------
        sec_header = ttk.Frame(security_frame)
        sec_header.pack(fill=tk.X, pady=(0, 16))

        ttk.Label(sec_header, text="Security & Protection",
                  font=(self.main_font, 12, "bold")).pack(anchor=tk.W)
        ttk.Label(sec_header, text="Manage application security settings.",
                  font=(self.main_font, 9), foreground=self.colors["fg_dim"]).pack(anchor=tk.W, pady=(2, 0))

        sec_card = ttk.Frame(
            security_frame, style="Toolbar.TFrame", padding=20)
        sec_card.pack(fill=tk.X, pady=(0, 16))

        ttk.Label(sec_card, text="Protection Mode:", font=(self.main_font, 11, "bold"),
                  background=self.colors["bg_secondary"]).pack(anchor=tk.W, pady=(0, 4))

        prot_frame = ttk.Frame(sec_card, style="Toolbar.TFrame")
        prot_frame.pack(fill=tk.X, anchor=tk.W)
        self.prot_mode_var = tk.BooleanVar(
            value=self.config.get("protection_mode", True))

        def save_prot_mode():
            self.config["protection_mode"] = self.prot_mode_var.get()
            from .config import save_config
            save_config(self.config)

        cb = ttk.Checkbutton(prot_frame, text="Enable Protection Mode (Prevents log deletion)",
                             variable=self.prot_mode_var, command=save_prot_mode)
        cb.pack(side=tk.LEFT)

        ttk.Label(sec_card, text="Screen Lock History:", font=(self.main_font, 11, "bold"),
                  background=self.colors["bg_secondary"]).pack(anchor=tk.W, pady=(12, 4))

        lock_hist_frame = ttk.Frame(sec_card, style="Toolbar.TFrame")
        lock_hist_frame.pack(fill=tk.X, anchor=tk.W)
        self.screen_lock_history_var = tk.BooleanVar(
            value=self.config.get("screen_lock_history", False))

        def save_lock_history_mode():
            self.config["screen_lock_history"] = self.screen_lock_history_var.get()
            from .config import save_config
            save_config(self.config)

        lock_cb = ttk.Checkbutton(lock_hist_frame, text="Track screen lock/unlock, login and logout events in History",
                                  variable=self.screen_lock_history_var, command=save_lock_history_mode)
        lock_cb.pack(side=tk.LEFT)

        update_row = ttk.Frame(sec_card, style="Toolbar.TFrame", padding=(12, 14, 12, 0))
        update_row.pack(fill=tk.X, pady=(16, 0), anchor=tk.W)

        update_label = ttk.Label(update_row, text="Software Update:", font=(self.main_font, 11, "bold"),
                                 background=self.colors["bg_secondary"])
        update_label.pack(anchor=tk.W)

        update_box = ttk.Frame(sec_card, style="Toolbar.TFrame", padding=(12, 10, 12, 12))
        update_box.pack(fill=tk.X, pady=(4, 0))

        current_version_var = tk.StringVar(value=__import__("catlogs").__version__)
        latest_version_var = tk.StringVar(value="Checking...")
        update_status_var = tk.StringVar(value="Checking online release status...")

        ttk.Label(update_box, text="Current:", font=(self.main_font, 10, "bold")).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(update_box, textvariable=current_version_var, font=(self.main_font, 10)).pack(side=tk.LEFT)

        ttk.Label(update_box, text="Latest:", font=(self.main_font, 10, "bold")).pack(side=tk.LEFT, padx=(12, 8))
        ttk.Label(update_box, textvariable=latest_version_var, font=(self.main_font, 10)).pack(side=tk.LEFT)

        ttk.Button(update_box, text="Check for Updates", command=lambda: self._check_for_update_from_settings(update_status_var, latest_version_var)).pack(side=tk.RIGHT)
        ttk.Label(update_box, textvariable=update_status_var, font=(self.main_font, 9), foreground=self.colors["fg_dim"]).pack(side=tk.LEFT, padx=(18, 0), fill=tk.X, expand=True)

        def load_update_status():
            try:
                latest = fetch_latest_version()
                if latest is None:
                    latest_version_var.set("Unavailable")
                    update_status_var.set("Could not reach the update server. Retry later.")
                    return
                latest_version_var.set(latest)
                state = get_update_state(__import__("catlogs").__version__, latest)
                if state["available"]:
                    update_status_var.set(f"Update available: {latest} is ready to install.")
                else:
                    update_status_var.set("You are on the latest available version.")
            except Exception:
                latest_version_var.set("Unavailable")
                update_status_var.set("Update check failed. Please try again later.")

        load_update_status()

        # # BOTTOM SAVE & CANCEL BAR
        # -------------------------------------------------------------------
        bottom_bar = ttk.Frame(main_frame, style="Toolbar.TFrame")
        bottom_bar.pack(fill=tk.X, side=tk.BOTTOM, pady=(16, 0))

        ttk.Separator(bottom_bar, orient=tk.HORIZONTAL).pack(fill=tk.X)

        bottom_inner = ttk.Frame(
            bottom_bar, style="Toolbar.TFrame", padding=(16, 12))
        bottom_inner.pack(fill=tk.X)

        def save_all_settings():
            new_theme = theme_var.get()
            new_main_font = main_font_var.get()
            new_mono_font = mono_font_var.get()

            app_changed = False
            if new_theme != self.current_theme:
                self.current_theme = new_theme
                self.config["theme"] = new_theme
                app_changed = True

            if new_main_font != self.main_font:
                self.main_font = new_main_font
                self.config["main_font"] = new_main_font
                app_changed = True

            if new_mono_font != self.mono_font:
                self.mono_font = new_mono_font
                self.config["mono_font"] = new_mono_font
                app_changed = True

            # Save paths to config
            save_log_paths(working_paths)
            self.config["log_paths"] = working_paths
            save_config(self.config)

            if app_changed:
                self._apply_theme()

            # Trigger a refresh of logs with the updated paths!
            self.status_var.set(
                "Log configuration updated — Collecting data...")
            self._refresh_data()

            dialog.destroy()

        ttk.Button(bottom_inner, text="Save & Apply", command=save_all_settings,
                   style="Accent.TButton").pack(side=tk.RIGHT)
        ttk.Button(bottom_inner, text="Cancel", command=dialog.destroy).pack(
            side=tk.RIGHT, padx=12)

        # Initialize default view
        switch_tab("paths")
        refresh_paths_table()

    def _toggle_fullscreen(self):
        try:
            current = self.root.attributes("-fullscreen")
            self.root.attributes("-fullscreen", not current)
        except tk.TclError:
            try:
                self.root.state("zoomed" if self.root.wm_state() != "zoomed" else "normal")
            except Exception:
                pass

    def _bind_shortcuts(self):
        self.root.bind("<Control-r>", lambda _: self._refresh_data())
        self.root.bind("<Control-e>", lambda _: self._export_csv())
        self.root.bind("<F5>", lambda _: self._refresh_data())
        self.root.bind("<F11>", lambda _: self._toggle_fullscreen())
        self.root.bind("<Control-q>", lambda _: self.root.quit())
        self.root.bind("<Escape>", lambda _: self._clear_filters())
        self.root.bind("<Control-comma>", lambda _: self._show_settings())

        self.root.bind("<Control-plus>", lambda _: self._zoom(1))
        self.root.bind("<Control-minus>", lambda _: self._zoom(-1))
        self.root.bind("<Control-equal>", lambda _: self._zoom(1))
        self.root.bind("<Control-KP_Add>", lambda _: self._zoom(1))
        self.root.bind("<Control-KP_Subtract>", lambda _: self._zoom(-1))
        self.root.bind("<Control-KP_0>", lambda _: self._zoom(0, reset=True))
        self.root.bind("<Control-question>", lambda _: self._show_shortcuts())
        self.root.bind("<Control-0>", lambda _: self._zoom(0, reset=True))
        self.root.bind("<Control-Button-4>", lambda _: self._zoom(1))
        self.root.bind("<Control-Button-5>", lambda _: self._zoom(-1))
        self.root.bind("<Control-MouseWheel>",
                       lambda e: self._zoom(1 if e.delta > 0 else -1))

    def _zoom(self, delta: int, reset: bool = False):
        if reset:
            self.zoom_level = 0
        else:
            new_zoom = getattr(self, "zoom_level", 0) + delta
            # Limit zoom from -4 (smallest readable) to 20 (largest reasonable)
            self.zoom_level = max(-4, min(20, new_zoom))

        self.config["zoom_level"] = self.zoom_level

        import threading
        from .config import save_config
        threading.Thread(target=lambda: save_config(self.config)).start()

        self._apply_theme()

    def _refresh_data(self):
        self.status_var.set("Collecting data...")
        self.progress["value"] = 0

        self._set_controls_state(False)

        def collect():
            entries = collect_all(
                include_session_lifecycle=self.config.get("screen_lock_history", False),
                progress_callback=self._on_progress,
            )
            self.root.after(0, lambda: self._on_collection_done(entries))

        thread = threading.Thread(target=collect, daemon=True)
        thread.start()

    def _on_progress(self, message: str, percent: int):
        self.root.after(0, lambda: self._update_progress(message, percent))

    def _update_progress(self, message: str, percent: int):
        self.status_var.set(message)
        self.progress["value"] = percent

    def _on_collection_done(self, entries: List[CommandEntry]):
        from .deleted_logs import load_deleted_logs
        deleted = set(load_deleted_logs())
        self.all_entries = [e for e in entries if getattr(
            e, 'command', '') not in deleted]
        self._update_filter_options()
        self._apply_filters()
        self._set_controls_state(True)
        self.status_var.set(f"Loaded {len(entries)} commands from system")
        self.progress["value"] = 100

    def _set_controls_state(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        for menu in (self.user_menu, self.shell_menu, self.source_menu):
            menu.configure(state=state)

    def _update_filter_options(self):
        users = sorted({e.user for e in self.all_entries})
        shells = sorted({e.shell for e in self.all_entries})
        sources = sorted({e.source for e in self.all_entries})

        curr_user_excl = self.user_menu.get_excluded()
        curr_shell_excl = self.shell_menu.get_excluded()
        curr_source_excl = self.source_menu.get_excluded()

        self.user_menu.set_items(users, selected=curr_user_excl)
        self.shell_menu.set_items(shells, selected=curr_shell_excl)
        self.source_menu.set_items(sources, selected=curr_source_excl)

    def _parse_time(self, text: str, is_end: bool = False) -> Optional[datetime]:
        text = text.strip()
        if not text:
            return None
        formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"]
        for fmt in formats:
            try:
                dt = datetime.strptime(text, fmt)
                if is_end and fmt == "%Y-%m-%d":
                    dt = dt.replace(hour=23, minute=59, second=59)
                return dt
            except ValueError:
                pass
        return None

    def _apply_filters(self, *args):
        if hasattr(self, '_filter_after_id'):
            self.root.after_cancel(self._filter_after_id)
        self._filter_after_id = self.root.after(250, self._do_apply_filters)

    def _do_apply_filters(self):
        text = self.search_var.get().lower()
        user_exc_list = set(self.user_menu.get_excluded())
        shell_exc_list = set(self.shell_menu.get_excluded())
        source_exc_list = set(self.source_menu.get_excluded())

        start_dt = self._parse_time(self.start_time_var.get())
        if start_dt and start_dt.tzinfo:
            start_dt = start_dt.replace(tzinfo=None)

        end_dt = self._parse_time(self.end_time_var.get(), is_end=True)
        if end_dt and end_dt.tzinfo:
            end_dt = end_dt.replace(tzinfo=None)

        filtered = []
        for e in self.all_entries:
            if user_exc_list and e.user in user_exc_list:
                continue
            if shell_exc_list and e.shell in shell_exc_list:
                continue
            if source_exc_list and e.source in source_exc_list:
                continue

            if start_dt or end_dt:
                if not e.timestamp:
                    continue
                ts = e.timestamp.replace(
                    tzinfo=None) if e.timestamp.tzinfo else e.timestamp
                if start_dt and ts < start_dt:
                    continue
                if end_dt and ts > end_dt:
                    continue

            if text:
                if (text not in e.command.lower() and
                    text not in e.user.lower() and
                    text not in e.shell.lower() and
                    text not in e.source.lower() and
                    (not e.tty or text not in e.tty.lower()) and
                        (not e.working_dir or text not in e.working_dir.lower())):
                    continue

            filtered.append(e)

        self.filtered_entries = filtered

        self._populate_table()
        self.count_var.set(
            f"{len(self.filtered_entries)} / {len(self.all_entries)} commands"
        )

    def _clear_filters(self):
        self.search_var.set("")
        self.user_menu.clear_all()
        self.shell_menu.clear_all()
        self.source_menu.clear_all()
        self.start_time_var.set("")
        self.end_time_var.set("")

    def _get_current_filters(self) -> dict:
        user_excluded = set(self.user_menu.get_excluded())
        shell_excluded = set(self.shell_menu.get_excluded())
        source_excluded = set(self.source_menu.get_excluded())

        user_included = [
            u for u in self.user_menu.items if u not in user_excluded]
        shell_included = [
            s for s in self.shell_menu.items if s not in shell_excluded]
        source_included = [
            s for s in self.source_menu.items if s not in source_excluded]

        return {
            "Search": self.search_var.get(),
            "User Included": ", ".join(user_included) or "None",
            "Shell Included": ", ".join(shell_included) or "None",
            "Source Included": ", ".join(source_included) or "None",
            "From": self.start_time_var.get(),
            "To": self.end_time_var.get(),
        }

    def _populate_table(self):
        if hasattr(self, '_populate_after_id'):
            self.root.after_cancel(self._populate_after_id)

        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)

        self._populate_chunk(0)

    def _populate_chunk(self, start_idx, chunk_size=500):
        MAX_ITEMS = 5000
        end_idx = min(start_idx + chunk_size,
                      len(self.filtered_entries), MAX_ITEMS)

        tree_insert = self.tree.insert
        for idx in range(start_idx, end_idx):
            entry = self.filtered_entries[idx]
            tag = ROW_TAG_EVEN if idx % 2 == 0 else ROW_TAG_ODD
            display_cmd = entry.command
            if len(display_cmd) > 200:
                display_cmd = display_cmd[:197] + "..."

            tree_insert(
                "", tk.END,
                iid=str(idx),
                values=(
                    entry.timestamp_str,
                    entry.user,
                    display_cmd,
                    entry.shell,
                    entry.source,
                    entry.pid if entry.pid is not None else "",
                ),
                tags=(tag,),
            )

        if end_idx < len(self.filtered_entries) and end_idx < MAX_ITEMS:
            self._populate_after_id = self.root.after(
                1, lambda: self._populate_chunk(end_idx, chunk_size))
        elif end_idx == MAX_ITEMS and len(self.filtered_entries) > MAX_ITEMS:
            tree_insert(
                "", tk.END,
                iid="more_items",
                values=(
                    "...", "...", f"Showing first {MAX_ITEMS} items. Refine search to see more.", "...", "...", ""),
                tags=(ROW_TAG_EVEN,)
            )

    def _on_sort(self, column: str):
        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = False

        key_map = {
            "timestamp": lambda e: (e.timestamp is None, e.timestamp or datetime.min),
            "user": lambda e: e.user.lower(),
            "command": lambda e: e.command.lower(),
            "shell": lambda e: e.shell.lower(),
            "source": lambda e: e.source.lower(),
            "pid": lambda e: (e.pid is None, e.pid or 0),
        }

        key_fn = key_map.get(column, lambda e: "")
        try:
            self.filtered_entries.sort(key=key_fn, reverse=self._sort_reverse)
        except TypeError:
            pass

        self._populate_table()

        for col in self.COLUMNS:
            label = self.COLUMN_LABELS[col]
            if col == column:
                arrow = " v" if self._sort_reverse else " ^"
                self.tree.heading(col, text=label + arrow)
            else:
                self.tree.heading(col, text=label)

    def _delete_selected_log(self):
        selected = self.tree.selection()
        if not selected:
            return

        item_id = selected[0]
        # fetch the data to log it
        values = self.tree.item(item_id, "values")
        if not values:
            return
        cmd = values[2]  # Command column

        from .deletion_history import log_deletion
        prot_mode = self.config.get("protection_mode", True)

        if prot_mode:
            log_deletion("Command Delete",
                         f"Attempted to delete command: {cmd}", False)
            messagebox.showwarning(
                "Permission Denied", "Protection Mode is active. You do not have permission to delete logs.")
            return

        confirm = messagebox.askyesno(
            "Delete Log", f"Are you sure you want to delete this log entry?\n\n{cmd}")
        if confirm:
            log_deletion("Command Delete", f"Deleted command: {cmd}", True)
            from .deleted_logs import add_deleted_log
            add_deleted_log(cmd)
            self.tree.delete(item_id)

            # Find in self.all_entries and remove
            for i in range(len(self.all_entries) - 1, -1, -1):
                if hasattr(self.all_entries[i], 'command') and self.all_entries[i].command == cmd:
                    del self.all_entries[i]

            self._apply_filters()

    def _on_select(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return

        try:
            idx = int(selection[0])
            entry = self.filtered_entries[idx]
        except (ValueError, IndexError):
            return

        self._show_detail(entry)
        self._fetch_command_output(entry)

    def _show_detail(self, entry: CommandEntry):
        self.details_text.configure(state=tk.NORMAL)
        self.details_text.delete("1.0", tk.END)

        detail = entry.detail_text
        for line in detail.split("\n"):
            if ":" in line:
                colon_pos = line.index(":")
                label_part = line[:colon_pos + 1]
                value_part = line[colon_pos + 1:]
                self.details_text.insert(tk.END, label_part, "label")
                self.details_text.insert(tk.END, value_part + "\n", "value")
            else:
                self.details_text.insert(tk.END, line + "\n", "value")

        self.details_text.configure(state=tk.DISABLED)

    def _show_detail_placeholder(self):
        """Show a placeholder message in the detail panel."""
        self.details_text.configure(state=tk.NORMAL)
        self.details_text.delete("1.0", tk.END)
        self.details_text.insert(
            tk.END,
            "  Click on a command above to view its full details here.\n\n"
            "  Shortcuts:  F5 / Ctrl+R = Refresh  |  Ctrl+E = Export CSV  |  "
            "Esc = Clear Filters  |  Ctrl+Q = Quit",
            "placeholder",
        )
        self.details_text.configure(state=tk.DISABLED)

    def _fetch_expected_output(self, command_str):
        self.expected_output_text.configure(state=tk.NORMAL)
        self.expected_output_text.delete("1.0", tk.END)
        self.expected_output_text.insert(tk.END, "  Executing command to get real output...\n", "info")
        self.expected_output_text.configure(state=tk.DISABLED)

        def execute():
            try:
                args = build_command_preview_args(command_str)
                if not args:
                    output = "(No command provided)"
                else:
                    result = subprocess.run(args, capture_output=True, text=True, timeout=5)
                    output = result.stdout
                    if result.stderr:
                        output += "\n--- STDERR ---\n" + result.stderr
                    if not output.strip():
                        output = "(No output)"
            except subprocess.TimeoutExpired:
                output = "(Command timed out after 5 seconds)"
            except FileNotFoundError:
                output = "(Command not found on this system)"
            except Exception as e:
                output = f"(Error executing command: {e})"

            def update_ui():
                self.expected_output_text.configure(state=tk.NORMAL)
                self.expected_output_text.delete("1.0", tk.END)
                self.expected_output_text.insert(tk.END, output + "\n", "output")
                self.expected_output_text.configure(state=tk.DISABLED)

            self.root.after(0, update_ui)

        threading.Thread(target=execute, daemon=True).start()

    def _fetch_command_output(self, entry: CommandEntry):
        """Fetch and display contextual information about the selected command.

        IMPORTANT: We NEVER re-execute commands. Instead we show relevant
        system context gathered from log files, process info, etc.
        """
        self.output_text.configure(state=tk.NORMAL)
        self.output_text.delete("1.0", tk.END)

        command = entry.command.strip()
        self._fetch_expected_output(command)

        if entry.source == "process":
            self.output_text.insert(
                tk.END, "  Currently running process\n", "info")
            self.output_text.insert(tk.END, "  " + "-" * 50 + "\n\n", "label")
            if entry.pid:
                self.output_text.configure(state=tk.DISABLED)
                thread = threading.Thread(
                    target=self._fetch_process_info,
                    args=(entry.pid,),
                    daemon=True
                )
                thread.start()
            else:
                self.output_text.insert(
                    tk.END, "  No PID available for this entry.\n", "placeholder")
                self.output_text.configure(state=tk.DISABLED)

        elif entry.source == "history":
            self.output_text.insert(
                tk.END, "  Shell History Entry\n", "info")
            self.output_text.insert(tk.END, "  " + "-" * 50 + "\n\n", "label")
            self.output_text.insert(
                tk.END, f"  Command:  {command}\n", "label")
            self.output_text.insert(
                tk.END, f"  User:     {entry.user}\n", "label")
            self.output_text.insert(
                tk.END, f"  Shell:    {entry.shell}\n", "label")
            if entry.extra.get("history_file"):
                self.output_text.insert(
                    tk.END, f"  File:     {entry.extra['history_file']}\n", "label")
            self.output_text.insert(tk.END, "\n", "output")
            self.output_text.insert(
                tk.END, "  Original output was not captured by the shell history.\n", "placeholder")
            self.output_text.insert(
                tk.END, "  Shell history files only store the commands, not their output.\n\n", "placeholder")

            self.output_text.configure(state=tk.DISABLED)
            thread = threading.Thread(
                target=self._search_system_logs,
                args=(command, entry),
                daemon=True
            )
            thread.start()

        elif entry.source in ("auth.log", "journal"):
            self.output_text.insert(
                tk.END, "  System Auth/Journal Log Entry\n", "info")
            self.output_text.insert(tk.END, "  " + "-" * 50 + "\n\n", "label")
            self.output_text.insert(
                tk.END, f"  Command:  {command}\n", "label")
            self.output_text.insert(
                tk.END, f"  User:     {entry.user}\n", "label")
            if entry.tty:
                self.output_text.insert(
                    tk.END, f"  TTY:      {entry.tty}\n", "label")
            if entry.working_dir:
                self.output_text.insert(
                    tk.END, f"  WorkDir:  {entry.working_dir}\n", "label")
            self.output_text.insert(tk.END, "\n", "output")
            self.output_text.insert(
                tk.END, "  This command was logged by the system auth/journal service.\n", "placeholder")
            self.output_text.insert(
                tk.END, "  Original command output was not captured by the log system.\n\n", "placeholder")
            self.output_text.configure(state=tk.DISABLED)

            thread = threading.Thread(
                target=self._search_system_logs,
                args=(command, entry),
                daemon=True
            )
            thread.start()

        elif entry.source == "accounting":
            self.output_text.insert(
                tk.END, "  Process Accounting Entry\n", "info")
            self.output_text.insert(tk.END, "  " + "-" * 50 + "\n\n", "label")
            self.output_text.insert(
                tk.END, f"  Command:  {command}\n", "label")
            self.output_text.insert(
                tk.END, f"  User:     {entry.user}\n", "label")
            self.output_text.insert(
                tk.END, "\n  Logged by process accounting (acct/lastcomm).\n", "placeholder")
            self.output_text.insert(
                tk.END, "  Original output was not captured.\n", "placeholder")
            self.output_text.configure(state=tk.DISABLED)

        elif entry.source == "last":
            self.output_text.insert(
                tk.END, "  Login Session Record\n", "info")
            self.output_text.insert(tk.END, "  " + "-" * 50 + "\n\n", "label")
            self.output_text.insert(
                tk.END, f"  Session:  {command}\n", "label")
            self.output_text.insert(
                tk.END, f"  User:     {entry.user}\n", "label")
            if entry.tty:
                self.output_text.insert(
                    tk.END, f"  TTY:      {entry.tty}\n", "label")
            if entry.extra.get("session_status"):
                self.output_text.insert(
                    tk.END, f"  Status:   {entry.extra['session_status']}\n", "label")
            if entry.extra.get("remote_host"):
                self.output_text.insert(
                    tk.END, f"  Remote:   {entry.extra['remote_host']}\n", "label")
            self.output_text.insert(
                tk.END, "\n  This is a login session record from the `last` command.\n", "placeholder")
            self.output_text.configure(state=tk.DISABLED)

        elif entry.source in ("syslog", "kern.log", "daemon.log", "boot.log",
                              "cron.log", "Xorg.log", "dmesg", "journal-errors", "power"):
            label_name = "Power Event" if entry.source == "power" else "System Log Entry"
            self.output_text.insert(
                tk.END, f"  {label_name} ({entry.source})\n", "info")
            self.output_text.insert(tk.END, "  " + "-" * 50 + "\n\n", "label")
            self.output_text.insert(tk.END, f"  {command}\n", "output")
            detail_text = "This entry was read directly from system log files." if entry.source != "power" else "This entry records a power-cycle event such as reboot or shutdown."
            self.output_text.insert(
                tk.END, f"\n  {detail_text}\n", "placeholder")
            self.output_text.configure(state=tk.DISABLED)

        elif entry.source in ("dpkg.log", "apt.log"):
            self.output_text.insert(
                tk.END, f"  Package Manager Log ({entry.source})\n", "info")
            self.output_text.insert(tk.END, "  " + "-" * 50 + "\n\n", "label")
            self.output_text.insert(tk.END, f"  {command}\n", "output")
            self.output_text.insert(
                tk.END, "\n  This entry was read from package manager logs.\n", "placeholder")
            self.output_text.configure(state=tk.DISABLED)

        elif entry.source == "lastb":
            self.output_text.insert(
                tk.END, "  Failed Login Attempt\n", "info")
            self.output_text.insert(tk.END, "  " + "-" * 50 + "\n\n", "label")
            self.output_text.insert(tk.END, f"  {command}\n", "output")
            self.output_text.insert(tk.END, f"  User: {entry.user}\n", "label")
            self.output_text.insert(
                tk.END, "\n  This is a failed login attempt from `lastb`.\n", "placeholder")
            self.output_text.configure(state=tk.DISABLED)

        else:
            self.output_text.insert(
                tk.END, f"  Log Entry (Source: {entry.source})\n", "info")
            self.output_text.insert(tk.END, "  " + "-" * 50 + "\n\n", "label")
            self.output_text.insert(tk.END, f"  {command}\n", "output")
            self.output_text.insert(
                tk.END, "\n  Original output is not available for this log source.\n", "placeholder")
            self.output_text.configure(state=tk.DISABLED)

    def _search_system_logs(self, command: str, entry: CommandEntry):
        """Search system logs for mentions of the command (read-only, no execution)."""
        results = []

        cmd_base = command.split()[0] if command.split() else command
        cmd_name = os.path.basename(cmd_base)

        log_files = [
            "/var/log/syslog",
            "/var/log/messages",
            "/var/log/auth.log",
        ]

        for log_file in log_files:
            if not os.path.isfile(log_file) or not os.access(log_file, os.R_OK):
                continue
            try:
                result = subprocess.run(
                    ["grep", "-i", "-m", "5", cmd_name, log_file],
                    capture_output=True, text=True, timeout=5,
                )
                if result.stdout.strip():
                    results.append((log_file, result.stdout.strip()))
            except Exception:
                pass

        try:
            result = subprocess.run(
                ["journalctl", "--no-pager", "-n", "5", "--output=short-iso",
                 "-g", cmd_name, "--quiet"],
                capture_output=True, text=True, timeout=5,
            )
            if result.stdout.strip():
                results.append(("journalctl", result.stdout.strip()))
        except Exception:
            pass

        def update_ui():
            self.output_text.configure(state=tk.NORMAL)
            if results:
                self.output_text.insert(
                    tk.END, "\n  Related System Log Entries:\n", "label")
                self.output_text.insert(
                    tk.END, "  " + "-" * 50 + "\n", "label")
                for source, content in results:
                    self.output_text.insert(
                        tk.END, f"\n  [{source}]\n", "info")
                    for line in content.split("\n")[:5]:
                        self.output_text.insert(
                            tk.END, f"    {line}\n", "output")
            else:
                self.output_text.insert(
                    tk.END, "\n  No related entries found in system logs.\n", "placeholder")
            self.output_text.configure(state=tk.DISABLED)

        self.root.after(0, update_ui)

    def _fetch_process_info(self, pid: int):
        """Fetch detailed info about a running process."""
        try:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o",
                 "pid,ppid,user,%cpu,%mem,vsz,rss,tty,stat,start,time,args"],
                capture_output=True, text=True, timeout=5,
            )

            def update_ui():
                self.output_text.configure(state=tk.NORMAL)
                self.output_text.delete("1.0", tk.END)
                self.output_text.insert(
                    tk.END, f"  Process Info (PID {pid}):\n", "label")
                self.output_text.insert(
                    tk.END, "  " + "-" * 50 + "\n\n", "label")

                if result.returncode == 0 and result.stdout.strip():
                    self.output_text.insert(tk.END, result.stdout, "output")
                else:
                    self.output_text.insert(
                        tk.END, "  Process is no longer running.\n", "placeholder")

                if result.stderr:
                    self.output_text.insert(tk.END, "\n  STDERR:\n", "label")
                    self.output_text.insert(tk.END, result.stderr, "error")

                self.output_text.configure(state=tk.DISABLED)

            self.root.after(0, update_ui)

        except Exception as e:
            def update_error():
                self.output_text.configure(state=tk.NORMAL)
                self.output_text.delete("1.0", tk.END)
                self.output_text.insert(
                    tk.END, f"  Warning: Could not fetch process info: {e}\n", "error")
                self.output_text.configure(state=tk.DISABLED)
            self.root.after(0, update_error)

    def _show_output_placeholder(self):
        """Show a placeholder in the output panel."""
        self.output_text.configure(state=tk.NORMAL)
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(
            tk.END,
            "  Select a command to see its output here.",
            "placeholder",
        )
        self.output_text.configure(state=tk.DISABLED)
        
        if hasattr(self, 'expected_output_text'):
            self.expected_output_text.configure(state=tk.NORMAL)
            self.expected_output_text.delete("1.0", tk.END)
            self.expected_output_text.insert(
                tk.END,
                "  Select a command to see its expected output here.",
                "placeholder",
            )
            self.expected_output_text.configure(state=tk.DISABLED)

    def _export_csv(self):
        """Export the currently filtered table to a CSV file."""
        if not self.filtered_entries:
            messagebox.showinfo("Export", "No data to export.")
            return

        default_name = generate_default_filename()
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=default_name,
            title="Export Commands to CSV",
        )

        if not filepath:
            return

        try:
            from . import __version__
            filters = self._get_current_filters()
            count = export_to_csv(
                self.filtered_entries, filepath,
                filters=filters, version=__version__
            )

            log_export(
                filepath=filepath,
                record_count=count,
                filters=filters,
                version=__version__,
            )

            messagebox.showinfo(
                "Export Successful",
                f"Exported {count} commands to:\n{filepath}",
            )
            self.status_var.set(
                f"Exported {count} commands to {os.path.basename(filepath)}")
        except OSError as e:
            messagebox.showerror(
                "Export Failed", f"Could not write file:\n{e}")


    def _export_generic_csv(self, data_list, fieldnames, title, default_prefix):
        if not data_list:
            import tkinter.messagebox as messagebox
            messagebox.showinfo("Export", "No data to export.")
            return

        from .exporter import generate_default_filename
        from .export_log import log_export
        from . import __version__
        import csv
        from datetime import datetime
        import tkinter.filedialog as filedialog
        import tkinter.messagebox as messagebox

        default_name = generate_default_filename().replace("catlogs_export", default_prefix)
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=default_name,
            title=title,
        )

        if not filepath:
            return

        try:
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                for row in data_list:
                    writer.writerow(row)
                
                # Metadata
                writer_list = csv.writer(f)
                writer_list.writerow([])
                writer_list.writerow(["---"])
                writer_list.writerow(["Software", "CatLogs - System Logs"])
                writer_list.writerow(["Release", __version__])
                writer_list.writerow(["Export Date", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                writer_list.writerow(["Total Records", len(data_list)])
                writer_list.writerow(["More Info", "https://catlogs.wassim.tech/"])
                writer_list.writerow(["Note", "This data was fetched from CatLogs software"])
                
            log_export(filepath=filepath, record_count=len(data_list), filters={}, version=__version__)
            messagebox.showinfo("Export Successful", f"Successfully exported {len(data_list)} records to:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export CSV:\n{e}")

    def _export_treeview_csv(self, tree, title, default_prefix):
        children = tree.get_children()
        if not children:
            import tkinter.messagebox as messagebox
            messagebox.showinfo("Export", "No data to export.")
            return

        from .exporter import generate_default_filename
        from .export_log import log_export
        from . import __version__
        import csv
        from datetime import datetime
        import tkinter.filedialog as filedialog
        import tkinter.messagebox as messagebox

        default_name = generate_default_filename().replace("catlogs_export", default_prefix)
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=default_name,
            title=title,
        )

        if not filepath:
            return

        try:
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                headers = [tree.heading(c, "text") for c in tree["columns"]]
                writer.writerow(headers)
                
                count = 0
                for item in children:
                    writer.writerow(tree.item(item, "values"))
                    count += 1
                
                # Metadata
                writer.writerow([])
                writer.writerow(["---"])
                writer.writerow(["Software", "CatLogs - System Logs"])
                writer.writerow(["Release", __version__])
                writer.writerow(["Export Date", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                writer.writerow(["Total Records", count])
                writer.writerow(["More Info", "https://catlogs.wassim.tech/"])
                writer.writerow(["Note", "This data was fetched from CatLogs software"])
                
            log_export(filepath=filepath, record_count=count, filters={}, version=__version__)
            messagebox.showinfo("Export Successful", f"Successfully exported {count} records to:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export CSV:\n{e}")

    def _export_read_errors_csv(self):
        from .read_errors import load_read_errors
        errors = load_read_errors()
        self._export_generic_csv(errors, ["timestamp", "filepath", "error", "collector"], "Export Read Errors", "catlogs_read_errors")

    def _export_deletion_history_csv(self):
        from .deletion_history import load_deletion_history
        history = load_deletion_history()
        self._export_generic_csv(history, ["timestamp", "user", "item_type", "detail", "allowed"], "Export Deletion History", "catlogs_deletions")

    def _export_export_history_csv(self):
        from .export_log import load_export_history
        history = load_export_history()
        self._export_generic_csv(history, ["timestamp", "filepath", "record_count", "version"], "Export Export History", "catlogs_exports")

    def _export_keylogger_csv(self):
        from .keylogger import read_keylogs
        lines = read_keylogs(max_lines=50000)
        import tkinter.messagebox as messagebox
        if not lines:
            messagebox.showinfo("Export", "No data to export.")
            return

        from .exporter import generate_default_filename
        from .export_log import log_export
        from . import __version__
        import csv
        from datetime import datetime
        import tkinter.filedialog as filedialog

        default_name = generate_default_filename().replace("catlogs_export", "catlogs_keylogs")
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=default_name,
            title="Export Key Logs",
        )

        if not filepath:
            return

        try:
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Key Log"])
                for line in lines:
                    writer.writerow([line])
                
                # Metadata
                writer.writerow([])
                writer.writerow(["---"])
                writer.writerow(["Software", "CatLogs - System Logs"])
                writer.writerow(["Release", __version__])
                writer.writerow(["Export Date", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                writer.writerow(["Total Records", len(lines)])
                writer.writerow(["More Info", "https://catlogs.wassim.tech/"])
                writer.writerow(["Note", "This data was fetched from CatLogs software"])
                
            log_export(filepath=filepath, record_count=len(lines), filters={}, version=__version__)
            messagebox.showinfo("Export Successful", f"Successfully exported {len(lines)} records to:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export CSV:\n{e}")

    def _export_processes_csv(self):
        children_ids = []
        def _get_all(node=""):
            for child in self.processes_tree.get_children(node):
                children_ids.append(child)
                _get_all(child)
        _get_all()

        if not children_ids:
            import tkinter.messagebox as messagebox
            messagebox.showinfo("Export", "No data to export.")
            return

        data_list = []
        for child in children_ids:
            item = self.processes_tree.item(child)
            name = item.get("text", "")
            values = item.get("values", [])
            row_dict = {
                "name": name,
                "pid": values[0],
                "user": values[1],
                "cpu": values[2],
                "mem": values[3],
                "state": values[4],
                "tty": values[5],
                "ppid": values[6],
                "elapsed": values[7],
                "command": values[8]
            }
            data_list.append(row_dict)
            
        self._export_generic_csv(data_list, ["name", "pid", "user", "cpu", "mem", "state", "tty", "ppid", "elapsed", "command"], "Export Processes", "catlogs_processes")



def _show_crash_dialog(title, error_details, exit_after=False, exit_code=1):
    import urllib.parse
    import webbrowser
    import platform
    import sys

    os_info = f"OS: {platform.system()} {platform.release()} ({platform.version()})\n"
    os_info += f"Python: {sys.version}\n"
    os_info += f"Architecture: {platform.machine()}\n"

    full_report = f"--- Crash/Signal Report ---\n{os_info}\n--- Details ---\n{error_details}"
    print(full_report)

    try:
        if tk._default_root is None:
            root = tk.Tk()
            root.withdraw()
            dialog = tk.Toplevel(root)
        else:
            dialog = tk.Toplevel()
    except Exception:
        if exit_after:
            sys.exit(exit_code)
        return

    dialog.title(title)
    dialog.geometry("720x500")
    dialog.minsize(600, 400)
    dialog.configure(bg="#1e1e1e")

    try:
        dialog.grab_set()
    except Exception:
        pass

    text = tk.Text(dialog, wrap=tk.WORD, font=("monospace", 10),
                   bg="#252526", fg="#d4d4d4", insertbackground="#ffffff",
                   selectbackground="#264f78", selectforeground="#ffffff",
                   relief=tk.FLAT, padx=12, pady=10)
    text.insert(tk.END, full_report)
    text.config(state=tk.DISABLED)
    text.pack(fill=tk.BOTH, expand=True, padx=12, pady=(12, 6))

    btn_frame = tk.Frame(dialog, bg="#1e1e1e")
    btn_frame.pack(fill=tk.X, padx=12, pady=(0, 12))

    def on_report():
        try:
            dialog.clipboard_clear()
            dialog.clipboard_append(full_report)
            dialog.update()
        except Exception:
            pass
        subject = urllib.parse.quote(f"CatLogs Report: {title}")
        body = urllib.parse.quote(full_report)
        webbrowser.open(
            f"mailto:bolleswassim@gmail.com?subject={subject}&body={body}")

    def on_close():
        dialog.destroy()
        if exit_after:
            sys.exit(exit_code)

    report_btn = ttk.Button(btn_frame, text="Copy & Report", command=on_report)
    report_btn.pack(side=tk.RIGHT, padx=10)

    close_btn = ttk.Button(btn_frame, text="Close", command=on_close)
    close_btn.pack(side=tk.RIGHT, padx=10)

    dialog.protocol("WM_DELETE_WINDOW", on_close)
    dialog.wait_window()


def _handle_exception(exc_type, exc_value, exc_traceback):
    """Global exception handler to show errors in a pop-up."""
    if issubclass(exc_type, KeyboardInterrupt):
        import sys
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    import traceback
    err_msg = "".join(traceback.format_exception(
        exc_type, exc_value, exc_traceback))

    try:
        _show_crash_dialog("Application Error", err_msg)
    except:
        pass


def run():
    """Create and run the CatLogs application."""
    import sys
    import signal
    import traceback

    sys.excepthook = _handle_exception

    def _handle_signal(sig, frame):
        """Handle OS signals (e.g. SIGTERM, SIGINT) gracefully."""
        try:
            sig_name = signal.Signals(sig).name
        except Exception:
            sig_name = f"Signal {sig}"

        err_msg = f"CatLogs received {sig_name} (signal {sig}).\n\nStack trace at time of signal:\n"
        err_msg += "".join(traceback.format_stack(frame))

        _show_crash_dialog("Signal Received", err_msg,
                           exit_after=True, exit_code=128 + sig)

    root = tk.Tk(className="catlogs")
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    root.report_callback_exception = _handle_exception

    try:
        root.iconname("catlogs")
    except tk.TclError:
        pass

    root.withdraw()
    app = CatLogsApp(root)
    root.deiconify()

    root.mainloop()

