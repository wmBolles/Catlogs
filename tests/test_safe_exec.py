import unittest
from catlogs.safe_exec import build_command_preview_args

class TestSafeExec(unittest.TestCase):

    def test_build_command_preview_args(self):
        # Empty inputs
        self.assertEqual(build_command_preview_args(""), [])
        self.assertEqual(build_command_preview_args("   "), [])
        self.assertEqual(build_command_preview_args(None), [])
        
        # Simple commands
        self.assertEqual(build_command_preview_args("ls -la /tmp"), ["ls", "-la", "/tmp"])
        
        # Quotes and escapes
        self.assertEqual(
            build_command_preview_args('echo "Hello World" \'Single Quotes\' \\"Escaped\\"'), 
            ["echo", "Hello World", "Single Quotes", '"Escaped"']
        )
        
        # Unmatched quotes (shlex raises ValueError, so we should expect it unless caught in safe_exec, wait, safe_exec doesn't catch it. 
        # But for tests, we should just expect the ValueError).
        with self.assertRaises(ValueError):
            build_command_preview_args('echo "unmatched')

if __name__ == "__main__":
    unittest.main()
