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


import gzip
import json
import os
import tempfile
import unittest

from catlogs.log_parsers import (
    detect_log_type,
    parse_any_timestamp,
    parse_app_lines,
    parse_apt_history_lines,
    parse_audit_lines,
    parse_auth_lines,
    parse_database_lines,
    parse_dpkg_lines,
    parse_fail2ban_lines,
    parse_fish_history_lines,
    parse_generic_lines,
    parse_json_lines,
    parse_log_file,
    parse_shell_history_lines,
    parse_syslog_iso_lines,
    parse_syslog_lines,
    parse_web_access_lines,
    parse_web_error_lines,
    read_log_file_lines,
)


class TestTimestampParsing(unittest.TestCase):

    def test_iso_timestamps(self):
        ts = parse_any_timestamp('2026-09-12T15:04:05.123456Z')
        self.assertIsNotNone(ts)
        self.assertEqual(ts.year, 2026)
        self.assertEqual(ts.month, 9)
        self.assertEqual(ts.day, 12)
        self.assertEqual(ts.hour, 15)
        self.assertEqual(ts.minute, 4)
        self.assertEqual(ts.second, 5)

        ts2 = parse_any_timestamp('2026-09-12 15:04:05,123')
        self.assertIsNotNone(ts2)
        self.assertEqual(ts2.year, 2026)

    def test_bsd_syslog_timestamp(self):
        ts = parse_any_timestamp('Sep 12 15:04:05', default_year=2026)
        self.assertIsNotNone(ts)
        self.assertEqual(ts.month, 9)
        self.assertEqual(ts.day, 12)
        self.assertEqual(ts.hour, 15)

    def test_clf_timestamp(self):
        ts = parse_any_timestamp('12/Sep/2026:15:04:05')
        self.assertIsNotNone(ts)
        self.assertEqual(ts.year, 2026)
        self.assertEqual(ts.month, 9)
        self.assertEqual(ts.day, 12)

    def test_epoch_timestamp(self):
        ts = parse_any_timestamp('1726153445')
        self.assertIsNotNone(ts)


class TestDetectLogType(unittest.TestCase):
    """Test format auto-detection by filename and sample content."""

    def test_filename_detection(self):
        self.assertEqual(detect_log_type('/var/log/auth.log'), 'auth')
        self.assertEqual(detect_log_type('/var/log/secure'), 'auth')
        self.assertEqual(detect_log_type('/var/log/dpkg.log'), 'dpkg')
        self.assertEqual(detect_log_type('/var/log/cron.log'), 'cron')
        self.assertEqual(detect_log_type(
            '/var/log/nginx/access.log'), 'web_access')
        self.assertEqual(detect_log_type(
            '/var/log/nginx/error.log'), 'web_error')
        self.assertEqual(detect_log_type('/var/log/audit/audit.log'), 'audit')
        self.assertEqual(detect_log_type('/var/log/fail2ban.log'), 'fail2ban')
        self.assertEqual(detect_log_type(
            '/home/user/.bash_history'), 'shell_history')
        self.assertEqual(detect_log_type('/var/log/service.json'), 'json')

    def test_content_detection_web_access(self):
        lines = [
            '192.168.1.1 - admin [12/Sep/2026:15:04:05 +0000] "GET /api/status HTTP/1.1" 200 4532 "-" "Mozilla/5.0"',
            '192.168.1.2 - - [12/Sep/2026:15:04:06 +0000] "POST /login HTTP/1.1" 302 0 "https://example.com" "curl/7.88"',
        ]
        detected = detect_log_type('/var/log/custom.log', sample_lines=lines)
        self.assertEqual(detected, 'web_access')

    def test_content_detection_json(self):
        lines = [
            json.dumps({'time': '2026-09-12T15:04:05Z',
                       'level': 'info', 'msg': 'started'}),
            json.dumps({'time': '2026-09-12T15:04:06Z',
                       'level': 'warn', 'msg': 'high mem'}),
        ]
        detected = detect_log_type('/var/log/custom.log', sample_lines=lines)
        self.assertEqual(detected, 'json')

    def test_content_detection_app(self):
        lines = [
            '2026-09-12 15:04:05,123 [INFO] [main] com.example.Server: Started server on port 8080',
            '2026-09-12 15:04:06,456 [WARN] [worker] Database pool exhausted, retrying...',
        ]
        detected = detect_log_type('/var/log/custom.log', sample_lines=lines)
        self.assertEqual(detected, 'app')


class TestParsers(unittest.TestCase):
    """Test all individual parsers."""

    def test_parse_syslog_lines(self):
        lines = [
            'Sep 12 15:04:05 myhost systemd[1]: Started User Manager for UID 1000.',
            'Sep 12 15:04:06 myhost kernel: [ 123.456] eth0: link up',
        ]
        entries = parse_syslog_lines(lines, 'syslog', '/var/log/syslog')
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].user, 'root')
        self.assertEqual(entries[0].pid, 1)
        self.assertEqual(entries[0].command,
                         'systemd: Started User Manager for UID 1000.')

    def test_parse_syslog_iso_lines(self):
        lines = [
            '2026-09-12T15:04:05.123456+00:00 myhost systemd[1]: Finished Daily Cleanup.',
        ]
        entries = parse_syslog_iso_lines(lines, 'syslog', '/var/log/syslog')
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].user, 'root')
        self.assertEqual(entries[0].pid, 1)

    def test_parse_auth_lines(self):
        lines = [
            'Sep 12 15:04:05 host sudo: wabolles : TTY=pts/0 ; PWD=/home/wabolles ; USER=root ; COMMAND=/usr/bin/apt update',
            'Sep 12 15:05:00 host sshd[1234]: Accepted publickey for wabolles from 192.168.1.50 port 54321 ssh2',
        ]
        entries = parse_auth_lines(lines, 'auth', '/var/log/auth.log')
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].user, 'wabolles')
        self.assertEqual(entries[0].command, 'sudo /usr/bin/apt update')
        self.assertEqual(entries[0].shell, 'sudo')
        self.assertEqual(entries[1].user, 'wabolles')
        self.assertEqual(entries[1].shell, 'sshd')

    def test_parse_web_access_lines(self):
        lines = [
            '10.0.0.1 - alice [12/Sep/2026:15:04:05 +0000] "GET /index.html HTTP/1.1" 200 1024 "http://ref.com" "Browser 1.0"',
            '10.0.0.2 - - [12/Sep/2026:15:04:06 +0000] "POST /api/data HTTP/1.1" 404 128 "-" "curl"',
        ]
        entries = parse_web_access_lines(
            lines, 'web_access', '/var/log/nginx/access.log')
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].user, 'alice')
        self.assertEqual(entries[0].status, '200')
        self.assertEqual(entries[0].command, 'GET /index.html HTTP/1.1')
        self.assertEqual(entries[1].user, '10.0.0.2')
        self.assertEqual(entries[1].status, '404')

    def test_parse_web_error_lines(self):
        lines = [
            '2026/09/12 15:04:05 [error] 1234#5678: *1 open() failed (2: No such file) while connecting to upstream',
        ]
        entries = parse_web_error_lines(
            lines, 'web_error', '/var/log/nginx/error.log')
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].status, 'ERROR')
        self.assertEqual(entries[0].pid, 1234)

    def test_parse_json_lines(self):
        lines = [
            json.dumps({'timestamp': '2026-09-12T15:04:05Z', 'level': 'INFO',
                       'message': 'App initialized', 'user': 'admin'}),
            json.dumps({'ts': '2026-09-12T15:04:06Z',
                       'severity': 'ERROR', 'msg': 'DB timeout'}),
        ]
        entries = parse_json_lines(lines, 'json', '/var/log/app.json')
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].user, 'admin')
        self.assertEqual(entries[0].status, 'INFO')
        self.assertEqual(entries[0].command, 'App initialized')
        self.assertEqual(entries[1].status, 'ERROR')
        self.assertEqual(entries[1].command, 'DB timeout')

    def test_parse_app_lines(self):
        lines = [
            '2026-09-12 15:04:05,123 [INFO] [main] com.example.Server: Started successfully',
            '2026-09-12 15:04:06,456 [ERROR] Failed to bind port 8080',
            '2026-09-12 15:04:07 INFO:root:Worker thread spawned',
        ]
        entries = parse_app_lines(lines, 'app', '/var/log/server.log')
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0].status, 'INFO')
        self.assertEqual(entries[0].shell, 'main')
        self.assertIn('Started successfully', entries[0].command)
        self.assertEqual(entries[1].status, 'ERROR')
        self.assertIn('Failed to bind port 8080', entries[1].command)
        self.assertEqual(entries[2].status, 'INFO')

    def test_parse_dpkg_lines(self):
        lines = [
            '2026-09-12 15:04:05 install htop:amd64 <none> 3.2.1-1',
            '2026-09-12 15:04:10 status installed htop:amd64 3.2.1-1',
        ]
        entries = parse_dpkg_lines(lines, 'dpkg', '/var/log/dpkg.log')
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].shell, 'dpkg')
        self.assertEqual(entries[0].command,
                         'install htop:amd64 <none> 3.2.1-1')

    def test_parse_apt_history_lines(self):
        lines = [
            'Start-Date: 2026-09-12  15:04:05',
            'Commandline: apt-get install -y nginx',
            'Requested-By: wabolles (1000)',
            'Install: nginx:amd64 (1.18.0)',
            'End-Date: 2026-09-12  15:04:10',
        ]
        entries = parse_apt_history_lines(
            lines, 'apt', '/var/log/apt/history.log')
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].user, 'wabolles')
        self.assertEqual(entries[0].command, 'apt-get install -y nginx')

    def test_parse_audit_lines(self):
        lines = [
            'type=SYSCALL msg=audit(1726153445.123:456): arch=c000003e syscall=59 success=yes exit=0 auid=1000 uid=0 pid=9876 comm="bash" exe="/bin/bash"',
        ]
        entries = parse_audit_lines(lines, 'audit', '/var/log/audit/audit.log')
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].pid, 9876)
        self.assertEqual(entries[0].command, '/bin/bash')
        self.assertEqual(entries[0].status, 'success=yes')

    def test_parse_fail2ban_lines(self):
        lines = [
            '2026-09-12 15:04:05 fail2ban.actions [1234]: NOTICE [sshd] Ban 192.168.1.100',
        ]
        entries = parse_fail2ban_lines(
            lines, 'fail2ban', '/var/log/fail2ban.log')
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].user, 'fail2ban')
        self.assertEqual(entries[0].pid, 1234)
        self.assertIn('Ban 192.168.1.100', entries[0].command)

    def test_parse_database_lines(self):
        lines = [
            '2026-09-12 15:04:05.123 UTC [1234] postgres@mydb LOG: statement: SELECT * FROM users;',
            '2026-09-12T15:04:06.000Z 5678 [Note] mysqld: ready for connections.',
            '9999:M 12 Sep 2026 15:04:07.000 * Background saving started by pid 10001',
        ]
        entries = parse_database_lines(lines, 'database', '/var/log/db.log')
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0].user, 'postgres')
        self.assertEqual(entries[0].pid, 1234)
        self.assertEqual(entries[1].user, 'mysql')
        self.assertEqual(entries[2].user, 'redis')

    def test_parse_shell_history_lines(self):
        lines = [
            '#1726153445',
            'git status',
            'ls -la',
        ]
        entries = parse_shell_history_lines(
            lines, 'bash', '~/.bash_history', shell_type='bash')
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].command, 'git status')
        self.assertIsNotNone(entries[0].timestamp)
        self.assertEqual(entries[1].command, 'ls -la')

    def test_parse_fish_history_lines(self):
        lines = [
            '- cmd: docker ps',
            '  when: 1726153445',
        ]
        entries = parse_fish_history_lines(
            lines, 'fish', '~/.local/share/fish/fish_history')
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].command, 'docker ps')
        self.assertEqual(entries[0].shell, 'fish')

    def test_parse_generic_lines(self):
        lines = [
            '2026-09-12 15:04:05 [INFO] Compressed log entry',
            'Sep 12 15:04:06 [WARN] [pid 4321] Disk threshold exceeded',
        ]
        entries = parse_generic_lines(lines, 'generic', '/var/log/custom.log')
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].status, 'INFO')
        self.assertIn('Compressed log entry', entries[0].command)
        self.assertEqual(entries[1].status, 'WARN')
        self.assertEqual(entries[1].pid, 4321)


class TestFileReadingAndDecompression(unittest.TestCase):
    """Test read_log_file_lines for plain and gzipped files."""

    def test_plain_file(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            f.write("""line 1\nline 2\nline 3\n""")
            filepath = f.name

        try:
            lines = read_log_file_lines(filepath)
            self.assertEqual(len(lines), 3)
            self.assertEqual(lines[0], 'line 1')
        finally:
            os.unlink(filepath)

    def test_gzipped_file(self):
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.log.gz') as f:
            with gzip.GzipFile(fileobj=f, mode='wb') as gz:
                gz.write(b"gz line 1\ngz line 2\n")
            filepath = f.name

        try:
            lines = read_log_file_lines(filepath)
            self.assertEqual(len(lines), 2)
            self.assertEqual(lines[0], 'gz line 1')
        finally:
            os.unlink(filepath)

    def test_parse_log_file_auto(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            f.write(
                '{"timestamp": "2026-09-12T15:04:05Z", "level": "INFO", "message": "Server ready"}\n')
            filepath = f.name

        try:
            entries = parse_log_file(
                filepath, log_type='auto', source_name='TestApp')
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].source, 'TestApp')
            self.assertEqual(entries[0].command, 'Server ready')
            self.assertEqual(entries[0].status, 'INFO')
        finally:
            os.unlink(filepath)


if __name__ == '__main__':
    unittest.main()
