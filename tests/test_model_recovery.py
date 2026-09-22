import plistlib
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from scripts import run_local_grok_update as runner


class ModelRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        folder = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.plist = Path(folder) / 'model.plist'
        self.plist.write_bytes(plistlib.dumps({'Label': runner.MODEL_SERVICE}))
        for key, value in [('MODEL_PLIST', self.plist), ('LOCAL_API_BASE', 'http://127.0.0.1:8799'), ('LOCAL_MODEL', runner.MANAGED_MODEL)]:
            self.stack.enter_context(patch.object(runner, key, value))
        self.stack.enter_context(patch.dict(runner.os.environ, {'AID_MODEL_AUTOSTART': '1'}))
        self.stack.enter_context(patch.object(runner, 'log'))
        self.stack.enter_context(patch.object(runner.time, 'sleep'))
        self.ready = self.stack.enter_context(patch.object(runner, 'local_api_ready', side_effect=[False, True]))
        self.run = self.stack.enter_context(patch.object(runner, 'run', return_value=subprocess.CompletedProcess([], 0, stdout='disabled services = {}')))
        self.state = self.stack.enter_context(patch.object(runner.subprocess, 'run', return_value=subprocess.CompletedProcess([], 113, stdout='')))

    def test_healthy_model_does_not_touch_launchd(self):
        self.ready.side_effect = [True]
        self.assertTrue(runner.ensure_local_api())
        self.run.assert_not_called()
        self.state.assert_not_called()

    def test_missing_service_is_registered_and_waited_for(self):
        self.assertTrue(runner.ensure_local_api())
        self.assertEqual(self.run.call_args_list[1].args[0][1], 'bootstrap')

    def test_explicit_disable_is_respected(self):
        self.run.return_value.stdout = f'"{runner.MODEL_SERVICE}" => disabled'
        self.assertFalse(runner.ensure_local_api())
        self.assertEqual(self.run.call_count, 1)
        self.state.assert_not_called()

    def test_plist_disable_is_respected(self):
        self.plist.write_bytes(plistlib.dumps({'Label': runner.MODEL_SERVICE, 'Disabled': True}))
        self.assertFalse(runner.ensure_local_api())
        self.run.assert_not_called()
        self.state.assert_not_called()

    def test_custom_model_is_not_started(self):
        with patch.object(runner, 'LOCAL_MODEL', 'another-model'):
            self.assertFalse(runner.ensure_local_api())
        self.run.assert_not_called()
        self.state.assert_not_called()

    def test_already_running_service_is_not_restarted(self):
        self.state.return_value = subprocess.CompletedProcess([], 0, stdout='state = running')
        self.assertTrue(runner.ensure_local_api())
        self.assertEqual(self.run.call_count, 1)

    def test_loaded_stopped_service_uses_non_destructive_kickstart(self):
        self.state.return_value = subprocess.CompletedProcess([], 0, stdout='state = not running')
        self.assertTrue(runner.ensure_local_api())
        args = self.run.call_args_list[1].args[0]
        self.assertEqual(args[1], 'kickstart')
        self.assertNotIn('-k', args)

    def test_custom_endpoint_or_opt_out_is_not_started(self):
        with patch.object(runner, 'LOCAL_API_BASE', 'http://127.0.0.1:9000'):
            self.assertFalse(runner.ensure_local_api())
        self.ready.side_effect = [False]
        with patch.dict(runner.os.environ, {'AID_MODEL_AUTOSTART': '0'}):
            self.assertFalse(runner.ensure_local_api())
        self.run.assert_not_called()

    def test_startup_failure_returns_false(self):
        self.run.side_effect = subprocess.CalledProcessError(5, ['launchctl'])
        self.assertFalse(runner.ensure_local_api())

    def test_startup_timeout_is_bounded(self):
        self.ready.side_effect = None
        self.ready.return_value = False
        with patch.object(runner.time, 'monotonic', side_effect=[0, 91]):
            self.assertFalse(runner.ensure_local_api(timeout=90))


if __name__ == '__main__':
    unittest.main()
