import unittest
import os
import json
import tempfile
from unittest import mock
from catlogs import read_errors

class TestReadErrors(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_path = os.path.join(self.temp_dir.name, "test_errors.json")
        self.patcher = mock.patch("catlogs.read_errors.ERROR_LOG_PATH", self.test_path)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_empty_load(self):
        self.assertEqual(read_errors.load_read_errors(), [])

    def test_log_and_load(self):
        read_errors.log_read_error("/var/log/syslog", "Permission Denied", "SyslogCollector")
        
        errors = read_errors.load_read_errors()
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["filepath"], "/var/log/syslog")
        self.assertEqual(errors[0]["error"], "Permission Denied")
        self.assertEqual(errors[0]["collector"], "SyslogCollector")
        self.assertIn("timestamp", errors[0])

        # Test append
        read_errors.log_read_error("/var/log/auth.log", "File Not Found", "AuthCollector")
        errors2 = read_errors.load_read_errors()
        self.assertEqual(len(errors2), 2)
        self.assertEqual(errors2[1]["filepath"], "/var/log/auth.log")

    def test_clear_errors(self):
        read_errors.log_read_error("/test/file", "error", "test")
        self.assertTrue(os.path.exists(self.test_path))
        
        read_errors.clear_read_errors()
        self.assertFalse(os.path.exists(self.test_path))
        self.assertEqual(read_errors.load_read_errors(), [])

    def test_load_corrupted(self):
        with open(self.test_path, "wb") as f:
            f.write(b"not json/encrypted data")
        
        self.assertEqual(read_errors.load_read_errors(), [])

if __name__ == "__main__":
    unittest.main()
