import os
import sqlite3
import tempfile
import unittest
from unittest import mock


from catlogs.scanner import (
    add_scan_finding,
    create_scan_session,
    list_scan_sessions,
    list_findings,
    scan_directory,
)
from catlogs.keylogger import start_daemon


class TestScannerM0(unittest.TestCase):
    def test_scan_session_and_findings_are_persisted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["CATLOGS_SCANNER_DB"] = os.path.join(tmpdir, "scanner.db")
            try:
                session = create_scan_session(
                    name="Baseline system scan",
                    target="/etc",
                    mode="unprivileged",
                    status="running",
                )
                self.assertIsNotNone(session)
                self.assertEqual(session["name"], "Baseline system scan")

                finding = add_scan_finding(
                    session_id=session["id"],
                    rule_name="filesystem_baseline",
                    severity="info",
                    path="/etc/os-release",
                    summary="System release file is readable.",
                    details="The OS release file was inspected successfully.",
                )
                self.assertIsNotNone(finding)
                self.assertEqual(finding["rule_name"], "filesystem_baseline")

                sessions = list_scan_sessions()
                self.assertEqual(len(sessions), 1)
                self.assertEqual(sessions[0]["name"], "Baseline system scan")

                findings = list_findings(session_id=session["id"])
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0]["path"], "/etc/os-release")
            finally:
                os.environ.pop("CATLOGS_SCANNER_DB", None)

    def test_scanner_db_is_sqlite_and_created_on_demand(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "scanner.db")
            os.environ["CATLOGS_SCANNER_DB"] = db_path
            try:
                session = create_scan_session(name="DB test", target="/tmp", mode="unprivileged")
                self.assertTrue(os.path.exists(db_path))
                with sqlite3.connect(db_path) as conn:
                    tables = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                    ).fetchall()
                    self.assertIn(("scan_sessions",), tables)
                    self.assertIn(("scan_findings",), tables)
                self.assertIsNotNone(session)
            finally:
                os.environ.pop("CATLOGS_SCANNER_DB", None)

    def test_scan_directory_returns_suspicious_findings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            suspicious_file = os.path.join(tmpdir, "payload.ps1")
            with open(suspicious_file, "w", encoding="utf-8") as handle:
                handle.write("powershell -enc <base64>\n")

            result = scan_directory(tmpdir, max_depth=2, max_files=25)
            self.assertGreaterEqual(result["files_scanned"], 1)
            self.assertTrue(any(item["rule_name"] == "suspicious_extension" for item in result["findings"]))




class TestDaemonPersistence(unittest.TestCase):
    def test_start_daemon_uses_systemd_user_service_when_available(self):
        with mock.patch("catlogs.keylogger.shutil.which", side_effect=lambda cmd: "/usr/bin/systemctl" if cmd == "systemctl" else None), \
             mock.patch("catlogs.keylogger.is_compiled", return_value=True), \
             mock.patch("catlogs.keylogger.is_running", side_effect=[False, True]), \
             mock.patch("catlogs.keylogger._systemd_user_available", return_value=True), \
             mock.patch("catlogs.keylogger.SERVICE_FILE", new=mock.Mock(exists=mock.Mock(return_value=True))), \
             mock.patch("catlogs.keylogger.subprocess.run") as run_mock, \
             mock.patch("catlogs.keylogger.time.sleep"):
            run_mock.return_value.returncode = 0

            result = start_daemon()

            self.assertTrue(result["success"])
            self.assertIn("systemd service", result["message"])
            run_mock.assert_called_with(
                ["systemctl", "--user", "start", "catlogs-keylogger"],
                capture_output=True,
                text=True,
                env=unittest.mock.ANY,
                timeout=15,
            )


if __name__ == "__main__":
    unittest.main()
