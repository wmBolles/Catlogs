import unittest
import os
import tempfile
from unittest import mock
from catlogs import keylogger

class TestKeylogger(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.pid_file = os.path.join(self.temp_dir.name, "keylogger.pid")
        self.log_file = os.path.join(self.temp_dir.name, "keylogs.txt")
        self.bin_file = os.path.join(self.temp_dir.name, "keylogger_bin")
        
        self.patchers = [
            mock.patch("catlogs.keylogger.PID_FILE", mock.MagicMock(is_file=lambda: os.path.exists(self.pid_file), read_text=lambda: open(self.pid_file).read(), unlink=lambda missing_ok: os.remove(self.pid_file) if os.path.exists(self.pid_file) else None)),
            mock.patch("catlogs.keylogger.KEYLOGS_FILE", mock.MagicMock(is_file=lambda: os.path.exists(self.log_file), stat=lambda: os.stat(self.log_file))),
            mock.patch("catlogs.keylogger.KEYLOGGER_BINARY", mock.MagicMock(is_file=lambda: os.path.exists(self.bin_file))),
        ]
        
        for p in self.patchers:
            p.start()
            
        # mock decrypt_data for read_keylogs
        self.crypto_patcher = mock.patch("catlogs.keylogger.decrypt_data", side_effect=lambda x: x)
        self.crypto_patcher.start()

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        self.crypto_patcher.stop()
        self.temp_dir.cleanup()

    @mock.patch("os.kill")
    def test_get_daemon_pid(self, mock_kill):
        mock_kill.return_value = None
        self.assertIsNone(keylogger.get_daemon_pid())
        
        with open(self.pid_file, "w") as f:
            f.write("12345\n")
            
        self.assertEqual(keylogger.get_daemon_pid(), 12345)
        
        with open(self.pid_file, "w") as f:
            f.write("bad_pid\n")
            
        self.assertIsNone(keylogger.get_daemon_pid())

    @mock.patch("os.kill")
    def test_is_running(self, mock_kill):
        with open(self.pid_file, "w") as f:
            f.write("12345\n")
            
        mock_kill.return_value = None
        self.assertTrue(keylogger.is_running())
        mock_kill.assert_called_with(12345, 0)
        
        mock_kill.side_effect = ProcessLookupError()
        self.assertFalse(keylogger.is_running())

    def test_read_keylogs(self):
        self.assertEqual(keylogger.read_keylogs(), [])
        
        # mock keylogs file content (we patched decrypt_data to return the raw bytes)
        with open(self.log_file, "wb") as f:
            f.write(b"line1\nline2\n\nline3\n")
            
        with mock.patch("builtins.open", mock.mock_open(read_data=b"line1\nline2\n\nline3\n")):
            with mock.patch.object(keylogger.KEYLOGS_FILE, '__str__', return_value=self.log_file):
                lines = keylogger.read_keylogs()
                self.assertEqual(len(lines), 3)
                self.assertEqual(lines[0], "line1")
                self.assertEqual(lines[2], "line3")

if __name__ == "__main__":
    unittest.main()
