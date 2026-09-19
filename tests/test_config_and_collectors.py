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
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from catlogs.config import (
    DEFAULT_LOG_PATHS,
    add_log_path,
    check_path_status,
    get_default_log_paths,
    load_log_paths,
    remove_log_path,
    reset_log_paths,
    save_log_paths,
)
from catlogs.collectors import collect_custom_logs, collect_all, collect_power_events, collect_session_lifecycle_events
from catlogs.crypto import SEC_KEY, decrypt_data
from catlogs.process_monitor import parse_process_snapshot
from catlogs.safe_exec import build_command_preview_args

try:
    from catlogs.gui import CatLogsApp
except Exception:  # pragma: no cover - GUI-only environment
    CatLogsApp = None


class TestConfigLogPaths(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_file = Path(self.temp_dir.name) / "config.json"
        self.patcher = patch("catlogs.config.CONFIG_FILE", self.config_file)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_default_log_paths(self):
        paths = load_log_paths()
        self.assertGreater(len(paths), 5)
        path_strs = [p["path"] for p in paths]
        self.assertIn("/var/log/syslog", path_strs)
        self.assertIn("/var/log/auth.log", path_strs)

    def test_add_and_remove_log_path(self):
        add_log_path("/var/log/custom/app.log", name="Custom App",
                     log_type="app", enabled=True)
        paths = load_log_paths()
        custom = [p for p in paths if p["path"] == "/var/log/custom/app.log"]
        self.assertEqual(len(custom), 1)
        self.assertEqual(custom[0]["name"], "Custom App")
        self.assertEqual(custom[0]["type"], "app")

        removed = remove_log_path("/var/log/custom/app.log")
        self.assertTrue(removed)
        paths_after = load_log_paths()
        self.assertFalse(
            any(p["path"] == "/var/log/custom/app.log" for p in paths_after))

    def test_reset_log_paths(self):
        add_log_path("/tmp/temporary.log", name="Temp", log_type="generic")
        reset_log_paths()
        paths = load_log_paths()
        self.assertFalse(any(p["path"] == "/tmp/temporary.log" for p in paths))
        self.assertEqual(len(paths), len(DEFAULT_LOG_PATHS))

    def test_check_path_status(self):
        status = check_path_status("/non/existent/path/for/catlogs/test.log")
        self.assertEqual(status["status_code"], "not_found")
        self.assertIn("Not Found", status["status_text"])

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            f.write("Hello CatLogs test\n")
            temp_path = f.name

        try:
            status = check_path_status(temp_path)
            self.assertEqual(status["status_code"], "active")
            self.assertIn("Active", status["status_text"])
            self.assertNotEqual(status["size_str"], "-")
        finally:
            os.unlink(temp_path)


class TestCollectorIntegration(unittest.TestCase):
    def test_collect_power_events(self):
        with patch("catlogs.collectors._run_command") as run_mock:
            run_mock.return_value = """wtmp begins Tue Sep 10 12:00:00 2024
reboot   system boot  6.8.0-52-generic Tue Sep 10 12:00:00 2024 still running
shutdown system down  6.8.0-52-generic Tue Sep 10 12:30:00 2024
"""
            entries = collect_power_events()
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0].source, "power")
            self.assertIn("reboot", entries[0].command.lower())
            self.assertIn("shutdown", entries[1].command.lower())

    def test_collect_session_lifecycle_events(self):
        with patch("catlogs.collectors._run_command") as run_mock:
            run_mock.return_value = """2026-09-19T08:10:11+00:00 host systemd-logind[123]: New session 5 of user wassim.
2026-09-19T08:15:29+00:00 host systemd-logind[123]: Session 5 logged out. Waiting for processes to exit.
2026-09-19T08:17:31+00:00 host gdm-password]: Session 5 unlocked.
2026-09-19T08:17:00+00:00 host gdm-password]: Session 5 locked.
"""
            entries = collect_session_lifecycle_events()
            self.assertEqual(len(entries), 4)
            self.assertIn("login", entries[0].command.lower())
            self.assertIn("logout", entries[1].command.lower())
            self.assertIn("lock", entries[3].command.lower())
            self.assertIn("unlock", entries[2].command.lower())

    def test_collect_custom_logs(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            f.write(
                '{"timestamp": "2026-09-12T15:04:05Z", "user": "appuser", "message": "Service started", "level": "info"}\n')
            temp_path = f.name

        try:
            custom_configs = [
                {"path": temp_path, "name": "MyService",
                    "type": "json", "enabled": True}
            ]
            entries = collect_custom_logs(custom_configs)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].user, "appuser")
            self.assertEqual(entries[0].command, "Service started")
            self.assertEqual(entries[0].source, "MyService")

            custom_configs_disabled = [
                {"path": temp_path, "name": "MyService",
                    "type": "json", "enabled": False}
            ]
            entries_disabled = collect_custom_logs(custom_configs_disabled)
            self.assertEqual(len(entries_disabled), 0)
        finally:
            os.unlink(temp_path)


class TestSecurityHardening(unittest.TestCase):
    def test_crypto_key_is_not_fixed_literal(self):
        self.assertNotEqual(SEC_KEY, b"CatLogsSecKey123")

    def test_decrypt_data_handles_raw_keylogger_xor_stream(self):
        payload = b"[2026-09-19T12:00:00] a\n[2026-09-19T12:00:01] b\n"
        secret = SEC_KEY
        encrypted = bytes(b ^ secret[i % len(secret)] for i, b in enumerate(payload))
        self.assertEqual(decrypt_data(encrypted), payload)

    def test_command_preview_uses_argument_vector(self):
        args = build_command_preview_args("echo 'hello world' && true")
        self.assertEqual(args, ["echo", "hello world", "&&", "true"])

    def test_process_snapshot_parses_zombie_rows(self):
        sample = """\
123 1 root python 0.1 0.2 Ss ? 1234 python -m http.server 8000
124 1 root <defunct> 0.0 0.0 Z ? 0 [kworker/0:1-events] 
"""
        rows = parse_process_snapshot(sample)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["name"], "<defunct>")
        self.assertEqual(rows[1]["cpu"], "0.0")
        self.assertEqual(rows[1]["command"], "[kworker/0:1-events]")


@unittest.skipUnless(CatLogsApp is not None, "Tkinter not available in this environment")
class TestCustomTabBehavior(unittest.TestCase):
    def test_lock_history_tab_is_available(self):
        self.assertTrue(hasattr(CatLogsApp, "_build_lock_history_page"))
        self.assertTrue(hasattr(CatLogsApp, "_refresh_lock_history"))

    def test_show_page_packs_selected_custom_tab(self):
        app = CatLogsApp.__new__(CatLogsApp)
        app._current_page = "logs"
        app.logs_page = type("FakeWidget", (), {"pack_forget": lambda self: None})()
        app.processes_page = type("FakeWidget", (), {"pack_forget": lambda self: None})()
        app.scanner_page = type("FakeWidget", (), {"pack_forget": lambda self: None})()
        app.history_page = type("FakeWidget", (), {"pack_forget": lambda self: None})()
        app.export_history_page = type("FakeWidget", (), {"pack_forget": lambda self: None})()
        app.read_errors_page = type("FakeWidget", (), {"pack_forget": lambda self: None})()
        app.help_page = type("FakeWidget", (), {"pack_forget": lambda self: None})()
        app.keylogger_page = type("FakeWidget", (), {"pack_forget": lambda self: None})()
        app.deletion_history_page = type("FakeWidget", (), {"pack_forget": lambda self: None})()
        app._custom_tab_pages = {"custom_tab_1": {"frame": type("FakeCustomFrame", (), {"pack_forget": lambda self: None, "pack": lambda self, **kwargs: None})(), "title": "Tab 1"}}
        app._nav_buttons = {}
        app._custom_tab_buttons = {"custom_tab_1": type("FakeButton", (), {"configure": lambda self, **kwargs: None})()}
        app.content_container = object()
        app.processes_refresh_id = None
        app.root = type("FakeRoot", (), {"after_cancel": lambda self, *_: None})()

        app._show_page("custom_tab_1")

        self.assertEqual(app._current_page, "custom_tab_1")

    def test_render_tab_bar_hides_plus_on_limit_and_includes_close_mark(self):
        app = CatLogsApp.__new__(CatLogsApp)
        app._custom_tab_pages = {
            f"custom_tab_{i}": {"frame": object(), "title": f"Tab {i}"}
            for i in range(1, 5)
        }
        app._custom_tab_order = [f"custom_tab_{i}" for i in range(1, 5)]
        app._custom_tab_buttons = {}
        app._custom_tab_close_buttons = {}
        app._header_plus_button = None
        app._max_tabs = 4
        app._tab_bar = type("FakeTabBar", (), {"winfo_children": lambda self: []})()

        created = []

        class FakeButton:
            def __init__(self, *args, **kwargs):
                created.append(kwargs)
                self.kwargs = kwargs
                self.pack = lambda *a, **k: None
                self.pack_forget = lambda *a, **k: None
                self.configure = lambda *a, **k: None

        with patch("catlogs.gui.ttk.Button", side_effect=FakeButton):
            app._render_tab_bar()

        self.assertEqual(len(created), 4)
        self.assertTrue(all("×" in str(item.get("text", "")) or "Tab" in str(item.get("text", "")) for item in created))


if __name__ == "__main__":
    unittest.main()
