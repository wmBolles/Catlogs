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
from catlogs.collectors import collect_custom_logs, collect_all


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


if __name__ == "__main__":
    unittest.main()
