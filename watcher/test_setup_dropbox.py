"""Tests for the one-time Dropbox setup. No network: Dropbox calls are faked.

Run: cd watcher && python3 -m unittest -v test_setup_dropbox
"""

import builtins
import json
import os
import plistlib
import shutil
import stat
import subprocess
import testroot
import unittest
import urllib.parse

import setup_dropbox as sd


class SetupTests(unittest.TestCase):

    def setUp(self):
        self.dir = testroot.mkdtemp()
        self.path = os.path.join(self.dir, 'whiteboard-watcher', 'config.json')

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_authorize_url_asks_for_offline_code_and_no_secret(self):
        url = sd.authorize_url('KEY123')
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(query['client_id'], ['KEY123'])
        self.assertEqual(query['response_type'], ['code'])
        self.assertEqual(query['token_access_type'], ['offline'])
        self.assertNotIn('client_secret', url)

    def test_exchange_code_returns_refresh_token(self):
        sent = {}

        def fake_post(url, fields):
            sent.update(fields)
            return {'refresh_token': 'REFRESH'}

        token = sd.exchange_code('KEY', 'SECRET', 'CODE', post=fake_post)
        self.assertEqual(token, 'REFRESH')
        self.assertEqual(sent['grant_type'], 'authorization_code')
        self.assertEqual(sent['code'], 'CODE')

    def test_exchange_code_without_refresh_token_fails(self):
        with self.assertRaises(sd.SetupError):
            sd.exchange_code('KEY', 'SECRET', 'CODE', post=lambda u, f: {})

    def test_access_token_uses_refresh_grant(self):
        sent = {}

        def fake_post(url, fields):
            sent.update(fields)
            return {'access_token': 'ACCESS'}

        self.assertEqual(sd.access_token('KEY', 'SECRET', 'REFRESH', post=fake_post), 'ACCESS')
        self.assertEqual(sent['grant_type'], 'refresh_token')
        self.assertEqual(sent['refresh_token'], 'REFRESH')

    def test_list_app_root_returns_sorted_names(self):
        def fake_post(url, token, body):
            self.assertEqual(body, {'path': ''})
            return {'entries': [{'name': 'Requests'}, {'name': 'Images'}]}

        self.assertEqual(sd.list_app_root('T', post=fake_post), ['Images', 'Requests'])

    def test_list_app_root_empty_is_fine(self):
        self.assertEqual(sd.list_app_root('T', post=lambda u, t, b: {'entries': []}), [])

    def test_write_config_is_mode_600_and_complete(self):
        sd.write_config(self.path, 'KEY', 'SECRET', 'REFRESH')
        mode = stat.S_IMODE(os.stat(self.path).st_mode)
        self.assertEqual(mode, 0o600)
        folder_mode = stat.S_IMODE(os.stat(os.path.dirname(self.path)).st_mode)
        self.assertEqual(folder_mode, 0o700)
        with open(self.path) as handle:
            data = json.load(handle)
        self.assertEqual(data['app_key'], 'KEY')
        self.assertEqual(data['app_secret'], 'SECRET')
        self.assertEqual(data['refresh_token'], 'REFRESH')
        self.assertEqual(data['default_model']['value'], 'haiku')
        self.assertEqual(data['jpeg_quality']['default'], 4)
        self.assertIn('claude-sonnet-5-5', data['models'].values())
        self.assertFalse(os.path.exists(self.path + '.tmp'))

    def test_write_config_replaces_old_file_and_keeps_mode(self):
        sd.write_config(self.path, 'OLD', 'OLD', 'OLD')
        sd.write_config(self.path, 'KEY', 'SECRET', 'REFRESH')
        with open(self.path) as handle:
            self.assertEqual(json.load(handle)['app_key'], 'KEY')
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)

    def test_authorize_url_is_built_from_the_key_only(self):
        self.assertTrue(sd.authorize_url('K').startswith(sd.AUTHORIZE_URL + '?'))


class ServiceTests(unittest.TestCase):

    def setUp(self):
        self.dir = testroot.mkdtemp()
        self.paths = {
            'plist': os.path.join(self.dir, 'LaunchAgents', 'com.nilsechterhoff.whiteboard-watcher.plist'),
            'log': os.path.join(self.dir, 'Logs', 'whiteboard-watcher.launchd.log'),
            'script': '/repo/watcher/watcher.py',
            'python': '/usr/bin/python3',
        }
        self.calls = []

    def tearDown(self):
        shutil.rmtree(self.dir)

    def runner(self, cmd, **kwargs):
        self.calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, b'', b'')

    def test_plist_runs_the_watcher_and_logs_to_the_launchd_log(self):
        job = plistlib.loads(sd.plist_bytes(self.paths))
        self.assertEqual(job['Label'], sd.LABEL)
        self.assertEqual(job['ProgramArguments'], ['/usr/bin/python3', '/repo/watcher/watcher.py'])
        self.assertTrue(job['RunAtLoad'])
        self.assertTrue(job['KeepAlive'])
        self.assertEqual(job['StandardOutPath'], self.paths['log'])
        self.assertIn('/opt/homebrew/bin', job['EnvironmentVariables']['PATH'])

    def test_install_writes_plist_and_log_then_bootstraps(self):
        sd.install_service(self.paths, runner=self.runner, uid=501)
        self.assertTrue(os.path.exists(self.paths['plist']))
        self.assertTrue(os.path.exists(self.paths['log']))
        self.assertEqual(self.calls[-1][:3], ['launchctl', 'bootstrap', 'gui/501'])

    def test_install_fails_when_bootstrap_fails(self):
        def failing(cmd, **kwargs):
            code = 0 if 'bootout' in cmd else 5
            return subprocess.CompletedProcess(cmd, code, b'', b'')
        with self.assertRaises(sd.SetupError):
            sd.install_service(self.paths, runner=failing, uid=501)

    def test_uninstall_removes_plist_and_log_and_keeps_config(self):
        sd.install_service(self.paths, runner=self.runner, uid=501)
        config_dir = os.path.join(self.dir, 'config')
        os.makedirs(config_dir)
        keep = os.path.join(config_dir, 'config.json')
        open(keep, 'w').close()
        removed = sd.uninstall_service(self.paths, runner=self.runner, uid=501)
        self.assertEqual(sorted(removed), sorted([self.paths['plist'], self.paths['log']]))
        self.assertFalse(os.path.exists(self.paths['plist']))
        self.assertFalse(os.path.exists(self.paths['log']))
        self.assertTrue(os.path.exists(keep))
        self.assertIn('bootout', self.calls[-1])

    def test_uninstall_when_nothing_is_there_is_fine(self):
        self.assertEqual(sd.uninstall_service(self.paths, runner=self.runner, uid=501), [])

    def test_service_paths_point_at_the_watcher_next_to_the_setup_script(self):
        paths = sd.service_paths(script_dir='/repo/watcher', python='/usr/bin/python3')
        self.assertEqual(paths['script'], '/repo/watcher/watcher.py')
        self.assertEqual(paths['plist'], os.path.expanduser(
            '~/Library/LaunchAgents/com.nilsechterhoff.whiteboard-watcher.plist'))
        self.assertEqual(paths['log'], os.path.expanduser(
            '~/Library/Logs/whiteboard-watcher.launchd.log'))

    def test_consent_needs_the_word_yes(self):
        original = builtins.input
        try:
            builtins.input = lambda prompt='': 'y'
            self.assertFalse(sd.confirm('Create?'))
            builtins.input = lambda prompt='': 'yes'
            self.assertTrue(sd.confirm('Create?'))
        finally:
            builtins.input = original


if __name__ == '__main__':
    unittest.main()
