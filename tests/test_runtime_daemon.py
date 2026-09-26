import unittest
import os
import subprocess
import tempfile
import time
import signal
from pathlib import Path

class TestDaemonRuntime(unittest.TestCase):
    """
    Real runtime integration tests for the C keylogger daemon.
    These tests do not mock the OS; they actually compile (if needed),
    execute, and monitor the binary in a controlled environment.
    """
    
    @classmethod
    def setUpClass(cls):
        cls.base_dir = Path(__file__).parent.parent
        cls.c_src = cls.base_dir / "keylogger" / "keylogger.c"
        cls.c_bin = cls.base_dir / "keylogger" / "keylogger_test_bin"
        
        # Compile the binary explicitly for runtime testing
        subprocess.run(
            ["gcc", "-O2", "-o", str(cls.c_bin), str(cls.c_src), "-lX11"],
            check=True,
            capture_output=True
        )

    @classmethod
    def tearDownClass(cls):
        if cls.c_bin.exists():
            cls.c_bin.unlink()

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_file = Path(self.temp_dir.name) / "test_keylogs.txt"
        
        self.pid_file = Path(self.temp_dir.name) / "keylogger.pid"
        if self.pid_file.exists():
            self.pid_file.unlink()

    def tearDown(self):
        # Ensure we don't leave zombie daemons
        if self.pid_file.exists():
            try:
                pid = int(self.pid_file.read_text().strip())
                os.kill(pid, signal.SIGKILL)
            except (ValueError, ProcessLookupError, PermissionError):
                pass
            self.pid_file.unlink(missing_ok=True)
        self.temp_dir.cleanup()

    def test_daemon_lifecycle(self):
        """Test that the daemon can start, write its PID, run detached, and shut down cleanly."""
        
        # Start daemon
        proc = subprocess.Popen(
            [str(self.c_bin), str(self.log_file), "--daemon"],
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Give it a moment to fork and write the PID file (wait up to 5 seconds)
        for _ in range(50):
            if self.pid_file.exists():
                break
            time.sleep(0.1)
            
        if not self.pid_file.exists():
            out, err = proc.communicate()
            self.fail(f"Daemon did not create PID file. STDOUT: {out} STDERR: {err}")
        
        pid_str = self.pid_file.read_text().strip()
        self.assertTrue(pid_str.isdigit(), "PID file contains invalid data.")
        pid = int(pid_str)
        
        # Verify it's actually running
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            self.fail("Daemon process is not actually running after starting.")
            
        # Verify it created the log file (the daemon touches it immediately)
        self.assertTrue(self.log_file.exists(), "Daemon did not create the log file.")
        
        # Send graceful termination
        os.kill(pid, signal.SIGTERM)
        
        # Wait for shutdown
        shutdown_clean = False
        for _ in range(20):
            time.sleep(0.1)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                shutdown_clean = True
                break
                
        self.assertTrue(shutdown_clean, "Daemon did not shut down cleanly upon SIGTERM.")

    def test_foreground_execution(self):
        """Test that the binary runs in the foreground without --daemon flag."""
        proc = subprocess.Popen(
            [str(self.c_bin), str(self.log_file)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        time.sleep(0.5)
        
        # In foreground mode, it shouldn't detach, so proc.poll() should be None (still running)
        self.assertIsNone(proc.poll(), "Foreground process exited prematurely.")
        
        # Terminate
        proc.terminate()
        proc.wait(timeout=2.0)
        
        self.assertIsNotNone(proc.poll(), "Foreground process failed to terminate.")
        self.assertTrue(self.log_file.exists(), "Foreground execution did not create log file.")

if __name__ == "__main__":
    unittest.main()
