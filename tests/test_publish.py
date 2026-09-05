import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import run_local_grok_update as runner


class PublishTests(unittest.TestCase):
    def test_transient_push_failure_is_retried(self):
        with patch.object(runner, 'run', side_effect=[subprocess.CalledProcessError(128, ['git', 'push']), None]) as run, patch.object(runner, 'sync_remote') as sync, patch.object(runner.time, 'sleep'), patch.object(runner, 'log'):
            self.assertTrue(runner.push_remote())
        self.assertEqual(run.call_count, 2)
        sync.assert_called_once()

    def test_push_retries_are_bounded_and_failure_is_returned(self):
        with patch.object(runner, 'run', side_effect=subprocess.TimeoutExpired(['git', 'push'], 25)) as run, patch.object(runner, 'sync_remote'), patch.object(runner.time, 'sleep'), patch.object(runner, 'log'):
            self.assertFalse(runner.push_remote())
        self.assertEqual(run.call_count, 3)

    def test_concurrent_code_publish_preserves_local_news_commit(self):
        def git(cwd, *args):
            return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True).stdout
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            remote, local, other = [root / name for name in ['remote.git', 'runner', 'developer']]
            git(root, 'init', '--bare', '--initial-branch=main', str(remote))
            git(root, 'clone', str(remote), str(local))
            for key, value in [('user.name', 'test'), ('user.email', 'test@example.com')]:
                git(local, 'config', key, value)
            git(local, 'commit', '--allow-empty', '-m', 'initial')
            git(local, 'push', 'origin', 'main')
            git(root, 'clone', str(remote), str(other))
            (other / 'code.txt').write_text('new code')
            git(other, 'add', 'code.txt')
            git(other, '-c', 'user.name=test', '-c', 'user.email=test@example.com', 'commit', '-m', 'code update')
            git(other, 'push', 'origin', 'main')
            (local / 'news.json').write_text('{"news":"preserved"}')
            git(local, 'add', 'news.json')
            git(local, 'commit', '-m', 'new data')
            with patch.object(runner, 'REPO_DIR', local), patch.object(runner.time, 'sleep'), patch.object(runner, 'log'):
                self.assertTrue(runner.push_remote())
            self.assertEqual((local / 'code.txt').read_text(), 'new code')
            self.assertEqual((local / 'news.json').read_text(), '{"news":"preserved"}')
            self.assertEqual(git(local, 'rev-parse', 'HEAD'), git(local, 'rev-parse', 'origin/main'))


if __name__ == '__main__':
    unittest.main()
