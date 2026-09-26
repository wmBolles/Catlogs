import unittest
from catlogs.process_monitor import parse_process_snapshot

class TestProcessMonitor(unittest.TestCase):

    def test_parse_process_snapshot_valid(self):
        raw = "123 1 root bash 1.5 0.5 S pts/0 00:00:10 /bin/bash --login\n" \
              "456 123 user1 python 10.0 5.2 R ? 01:23:45 python3 script.py arg1"
        
        parsed = parse_process_snapshot(raw)
        self.assertEqual(len(parsed), 2)
        
        self.assertEqual(parsed[0]["pid"], 123)
        self.assertEqual(parsed[0]["ppid"], 1)
        self.assertEqual(parsed[0]["user"], "root")
        self.assertEqual(parsed[0]["name"], "bash")
        self.assertEqual(parsed[0]["cpu"], "1.5")
        self.assertEqual(parsed[0]["mem"], "0.5")
        self.assertEqual(parsed[0]["state"], "S")
        self.assertEqual(parsed[0]["tty"], "pts/0")
        self.assertEqual(parsed[0]["started"], "00:00:10")
        self.assertEqual(parsed[0]["command"], "/bin/bash --login")
        
        self.assertEqual(parsed[1]["pid"], 456)
        self.assertEqual(parsed[1]["tty"], "none")
        self.assertEqual(parsed[1]["command"], "python3 script.py arg1")

    def test_parse_process_snapshot_invalid(self):
        raw = "bad format missing fields\n" \
              "abc 1 root bash 1.5 0.5 S pts/0 00:00:10 /bin/bash" # PID is not int
        
        parsed = parse_process_snapshot(raw)
        self.assertEqual(len(parsed), 0)

    def test_parse_process_snapshot_empty(self):
        self.assertEqual(parse_process_snapshot(""), [])
        self.assertEqual(parse_process_snapshot(None), [])
        self.assertEqual(parse_process_snapshot("   \n   "), [])

if __name__ == "__main__":
    unittest.main()
