import unittest
import os
import csv
import tempfile
from datetime import datetime
from catlogs.models import CommandEntry
from catlogs.exporter import export_to_csv, generate_default_filename

class TestExporter(unittest.TestCase):

    def setUp(self):
        self.entries = [
            CommandEntry(
                timestamp=datetime(2026, 9, 25, 10, 0, 0),
                user="testuser",
                command="echo 'Hello'",
                shell="bash",
                source="history"
            ),
            CommandEntry(
                timestamp=None,
                user="root",
                command="rm -rf /",
                shell="zsh",
                source="syslog",
                pid=123
            )
        ]

    def test_export_to_csv_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "empty.csv")
            count = export_to_csv([], path)
            self.assertEqual(count, 0)
            self.assertFalse(os.path.exists(path))

    def test_export_to_csv_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "export.csv")
            filters = {"Search": "echo", "User Included": "testuser"}
            count = export_to_csv(self.entries, path, filters=filters, version="9.9.9")
            
            self.assertEqual(count, 2)
            self.assertTrue(os.path.exists(path))
            
            # Verify CSV contents
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                rows = list(reader)
                
            self.assertIn(["Timestamp", "User", "Command", "Shell", "Source", "PID", "TTY", "Working Directory", "Exit Code", "Hostname", "CPU %", "MEM %", "Status"], rows)
            self.assertIn(["2026-09-25 10:00:00", "testuser", "echo 'Hello'", "bash", "history", "", "", "", "", "", "", "", ""], rows)
            self.assertIn(["Unknown", "root", "rm -rf /", "zsh", "syslog", "123", "", "", "", "", "", "", ""], rows)
            
            # Verify footer
            self.assertIn(["Release", "9.9.9"], rows)
            self.assertIn(["Total Records", "2"], rows)
            self.assertIn(["Filter - Search", "echo"], rows)
            self.assertIn(["Filter - User Included", "testuser"], rows)
            self.assertIn(["Note", "This data was fetched from CatLogs software"], rows)

    def test_generate_default_filename(self):
        fname = generate_default_filename()
        self.assertTrue(fname.startswith("catlogs_export_"))
        self.assertTrue(fname.endswith(".csv"))

if __name__ == "__main__":
    unittest.main()
