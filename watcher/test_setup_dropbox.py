"""Tests for the one-time Dropbox setup. No network: Dropbox calls are faked.

Run: cd watcher && python3 -m unittest -v test_setup_dropbox
"""

import json
import os
import shutil
import stat
import tempfile
import unittest
import urllib.parse

import setup_dropbox as sd


class SetupTests(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
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
        self.assertEqual(data, {'app_key': 'KEY', 'app_secret': 'SECRET',
                                'refresh_token': 'REFRESH'})
        self.assertFalse(os.path.exists(self.path + '.tmp'))

    def test_write_config_replaces_old_file_and_keeps_mode(self):
        sd.write_config(self.path, 'OLD', 'OLD', 'OLD')
        sd.write_config(self.path, 'KEY', 'SECRET', 'REFRESH')
        with open(self.path) as handle:
            self.assertEqual(json.load(handle)['app_key'], 'KEY')
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)

    def test_authorize_url_is_built_from_the_key_only(self):
        self.assertTrue(sd.authorize_url('K').startswith(sd.AUTHORIZE_URL + '?'))


if __name__ == '__main__':
    unittest.main()
