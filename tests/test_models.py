import unittest
from datetime import datetime, timedelta
from catlogs.models import CommandEntry

class TestCommandEntry(unittest.TestCase):

    def setUp(self):
        self.now = datetime.now()
        self.entry = CommandEntry(
            timestamp=self.now,
            user="testuser",
            command="ls -la",
            shell="bash",
            source="history",
            pid=1234,
            tty="pts/0",
            working_dir="/home/testuser",
            exit_code=0,
            hostname="testhost",
            cpu_percent="1.5",
            mem_percent="2.0",
            status="running",
            extra={"custom_field": "custom_value"}
        )

    def test_timestamp_str(self):
        self.assertEqual(self.entry.timestamp_str, self.now.strftime("%Y-%m-%d %H:%M:%S"))
        
        entry_no_ts = CommandEntry(
            timestamp=None, user="u", command="c", shell="s", source="src"
        )
        self.assertEqual(entry_no_ts.timestamp_str, "Unknown")

    def test_detail_text(self):
        detail = self.entry.detail_text
        self.assertIn("Command    : ls -la", detail)
        self.assertIn(f"Timestamp  : {self.now.strftime('%Y-%m-%d %H:%M:%S')}", detail)
        self.assertIn("User       : testuser", detail)
        self.assertIn("PID        : 1234", detail)
        self.assertIn("Custom Field: custom_value", detail)

    def test_matches_filter_text(self):
        self.assertTrue(self.entry.matches_filter(text="ls -la"))
        self.assertTrue(self.entry.matches_filter(text="testuser"))
        self.assertTrue(self.entry.matches_filter(text="bash"))
        self.assertTrue(self.entry.matches_filter(text="pts/0"))
        self.assertFalse(self.entry.matches_filter(text="nonexistent"))

    def test_matches_filter_exclusions(self):
        self.assertFalse(self.entry.matches_filter(user_exc_list=["testuser"]))
        self.assertTrue(self.entry.matches_filter(user_exc_list=["otheruser"]))
        
        self.assertFalse(self.entry.matches_filter(shell_exc_list=["bash"]))
        self.assertTrue(self.entry.matches_filter(shell_exc_list=["zsh"]))
        
        self.assertFalse(self.entry.matches_filter(source_exc_list=["history"]))
        self.assertTrue(self.entry.matches_filter(source_exc_list=["syslog"]))

    def test_matches_filter_time(self):
        past = self.now - timedelta(hours=1)
        future = self.now + timedelta(hours=1)
        
        self.assertTrue(self.entry.matches_filter(start_time=past))
        self.assertFalse(self.entry.matches_filter(start_time=future))
        
        self.assertTrue(self.entry.matches_filter(end_time=future))
        self.assertFalse(self.entry.matches_filter(end_time=past))
        
        self.assertTrue(self.entry.matches_filter(start_time=past, end_time=future))

    def test_to_dict(self):
        d = self.entry.to_dict()
        self.assertEqual(d["Command"], "ls -la")
        self.assertEqual(d["User"], "testuser")
        self.assertEqual(d["PID"], 1234)
        self.assertEqual(d["Exit Code"], 0)
        
        entry_minimal = CommandEntry(
            timestamp=None, user="u", command="c", shell="s", source="src"
        )
        d_min = entry_minimal.to_dict()
        self.assertEqual(d_min["PID"], "")
        self.assertEqual(d_min["Exit Code"], "")

if __name__ == "__main__":
    unittest.main()
