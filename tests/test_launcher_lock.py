"""Isolated Windows lock regression tests; never touch the user's launcher lock."""
import errno
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

import launcher


@unittest.skipUnless(sys.platform == 'win32', 'Windows byte-range locks')
class LauncherLockTests(unittest.TestCase):
    def setUp(self):
        self.path = launcher.DATA / ('launcher-test-' + str(uuid4()) + '.lock')
        self.path.parent.mkdir(exist_ok=True)

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_empty_file_can_be_locked_and_reacquired(self):
        first = launcher.try_launcher_lock(self.path)
        self.assertIsNotNone(first)
        first.close()
        self.assertEqual(self.path.stat().st_size, 0)
        second = launcher.try_launcher_lock(self.path)
        self.assertIsNotNone(second)
        second.close()

    def test_other_process_detects_existing_lock_without_reading(self):
        self.path.write_bytes(b'0')
        owner = launcher.try_launcher_lock(self.path)
        self.assertIsNotNone(owner)
        try:
            result = subprocess.run([sys.executable, '-c',
                'from pathlib import Path; import launcher,sys; lock=launcher.try_launcher_lock(Path(sys.argv[1])); assert lock is None',
                str(self.path)], cwd=launcher.ROOT, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
        finally:
            owner.close()
        replacement = launcher.try_launcher_lock(self.path)
        self.assertIsNotNone(replacement)
        replacement.close()

    def test_unexpected_lock_errors_close_handle_and_propagate(self):
        handle = Mock()
        path = Mock()
        path.open.return_value = handle
        with patch('msvcrt.locking', side_effect=OSError(errno.EBADF, 'invalid handle')):
            with self.assertRaises(OSError):
                launcher.try_launcher_lock(path)
        handle.close.assert_called_once()
        handle.read.assert_not_called()
        handle.write.assert_not_called()

    def test_open_permission_failure_propagates(self):
        path = Mock()
        path.open.side_effect = PermissionError('Cannot open lock file')
        with self.assertRaises(PermissionError):
            launcher.try_launcher_lock(path)


class LauncherCompatibilityTests(unittest.TestCase):
    def test_old_server_is_rejected_with_recovery_command(self):
        with patch.object(launcher, 'urlopen', return_value=io.BytesIO(b'{"paths":{}}')):
            with self.assertRaisesRegex(RuntimeError, '--port 8766'):
                launcher.require_current_api()

    def test_recorder_endpoints_are_accepted(self):
        paths = {'/api/kalshi/btc-research': {'get': {}},
                 '/api/kalshi/btc-research/start': {'post': {}},
                 '/api/kalshi/btc-research/stop': {'post': {}}}
        with patch.object(launcher, 'urlopen', return_value=io.BytesIO(json.dumps({'paths':paths}).encode())):
            launcher.require_current_api()

    def test_port_options(self):
        self.assertEqual(launcher.parse_args([]).port, 8765)
        self.assertEqual(launcher.parse_args(['--port','8766']).port, 8766)
        with patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit):
            launcher.parse_args(['--port','70000'])


if __name__ == '__main__':
    unittest.main()
