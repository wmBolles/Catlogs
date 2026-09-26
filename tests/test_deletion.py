import unittest
import os
import tempfile
from unittest import mock
from catlogs import deletion_history, deleted_logs

class TestDeletionTracking(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.hist_path = os.path.join(self.temp_dir.name, "hist.json")
        self.logs_path = os.path.join(self.temp_dir.name, "logs.json")
        
        self.patcher1 = mock.patch("catlogs.deletion_history.DELETION_LOG_PATH", self.hist_path)
        self.patcher2 = mock.patch("catlogs.deleted_logs.DELETED_LOGS_PATH", self.logs_path)
        
        self.patcher1.start()
        self.patcher2.start()

    def tearDown(self):
        self.patcher1.stop()
        self.patcher2.stop()
        self.temp_dir.cleanup()

    def test_deletion_history(self):
        self.assertEqual(deletion_history.load_deletion_history(), [])
        
        deletion_history.log_deletion("log_file", "/var/log/syslog", True)
        
        hist = deletion_history.load_deletion_history()
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["item_type"], "log_file")
        self.assertEqual(hist[0]["detail"], "/var/log/syslog")
        self.assertTrue(hist[0]["allowed"])
        self.assertIn("timestamp", hist[0])
        self.assertIn("user", hist[0])
        
        deletion_history.log_deletion("command", "rm -rf", False)
        hist2 = deletion_history.load_deletion_history()
        self.assertEqual(len(hist2), 2)
        self.assertFalse(hist2[1]["allowed"])

    def test_deleted_logs(self):
        self.assertEqual(deleted_logs.load_deleted_logs(), [])
        
        deleted_logs.add_deleted_log("echo 'test'")
        logs = deleted_logs.load_deleted_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0], "echo 'test'")
        
        # Test duplicate avoidance
        deleted_logs.add_deleted_log("echo 'test'")
        logs2 = deleted_logs.load_deleted_logs()
        self.assertEqual(len(logs2), 1)
        
        # Test appending new
        deleted_logs.add_deleted_log("ls -la")
        logs3 = deleted_logs.load_deleted_logs()
        self.assertEqual(len(logs3), 2)
        self.assertIn("ls -la", logs3)

    def test_corrupted_files(self):
        with open(self.hist_path, "wb") as f:
            f.write(b"bad data")
        with open(self.logs_path, "wb") as f:
            f.write(b"bad data")
            
        self.assertEqual(deletion_history.load_deletion_history(), [])
        self.assertEqual(deleted_logs.load_deleted_logs(), [])

if __name__ == "__main__":
    unittest.main()
