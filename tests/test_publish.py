import subprocess
import unittest
from unittest.mock import patch

from scripts import run_local_grok_update as runner


class PublishTests(unittest.TestCase):
    def test_transient_push_failure_is_retried(self):
        with patch.object(runner, 'run', side_effect=[subprocess.CalledProcessError(128, ['git', 'push']), None]) as run, patch.object(runner.time, 'sleep'), patch.object(runner, 'log'):
            self.assertTrue(runner.push_remote())
        self.assertEqual(run.call_count, 2)

    def test_push_retries_are_bounded_and_failure_is_returned(self):
        with patch.object(runner, 'run', side_effect=subprocess.TimeoutExpired(['git', 'push'], 25)) as run, patch.object(runner.time, 'sleep'), patch.object(runner, 'log'):
            self.assertFalse(runner.push_remote())
        self.assertEqual(run.call_count, 3)


if __name__ == '__main__':
    unittest.main()
