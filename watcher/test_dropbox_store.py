"""Tests for the Dropbox store with a fake HTTP opener. No network.

Run: cd watcher && python3 -m unittest -v test_dropbox_store
"""

import io
import json
import unittest
import urllib.error

import dropbox_store as ds


class FakeOpener(object):
    """Answers by URL suffix. Each entry: (status, body bytes). Records requests."""

    def __init__(self, answers):
        self.answers = answers
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        url = request.full_url
        for suffix, (status, body) in self.answers.items():
            if url.endswith(suffix):
                if status >= 400:
                    raise urllib.error.HTTPError(url, status, 'err', {}, io.BytesIO(body))
                return io.BytesIO(body)
        raise AssertionError('unexpected URL %s' % url)


TOKEN = json.dumps({'access_token': 'T'}).encode()


def store(answers):
    answers = dict(answers)
    answers.setdefault('/oauth2/token', (200, TOKEN))
    opener = FakeOpener(answers)
    return ds.DropboxStore('K', 'S', 'R', opener=opener), opener


class StoreTests(unittest.TestCase):

    def test_list_names_returns_files_only(self):
        body = json.dumps({'entries': [{'.tag': 'file', 'name': 'a.yaml'},
                                       {'.tag': 'folder', 'name': 'sub'}],
                           'has_more': False}).encode()
        s, opener = store({'/files/list_folder': (200, body)})
        self.assertEqual(s.list_names('/Requests'), ['a.yaml'])
        sent = json.loads(opener.requests[1].data.decode())
        self.assertEqual(sent, {'path': '/Requests'})

    def test_list_names_follows_pages(self):
        first = json.dumps({'entries': [{'.tag': 'file', 'name': 'a'}], 'has_more': True,
                            'cursor': 'c1'}).encode()
        second = json.dumps({'entries': [{'.tag': 'file', 'name': 'b'}], 'has_more': False}).encode()
        s, _ = store({'/files/list_folder': (200, first),
                      '/files/list_folder/continue': (200, second)})
        self.assertEqual(s.list_names('/Requests'), ['a', 'b'])

    def test_missing_folder_is_empty(self):
        err = json.dumps({'error_summary': 'path/not_found/..'}).encode()
        s, _ = store({'/files/list_folder': (409, err)})
        self.assertEqual(s.list_names('/Requests'), [])

    def test_exists_false_on_not_found(self):
        err = json.dumps({'error_summary': 'path/not_found/..'}).encode()
        s, _ = store({'/files/get_metadata': (409, err)})
        self.assertFalse(s.exists('/Descriptions/description-0003.md'))

    def test_exists_true_when_found(self):
        s, _ = store({'/files/get_metadata': (200, b'{}')})
        self.assertTrue(s.exists('/Images/image-0003.jpg'))

    def test_modified_reads_server_time_as_epoch(self):
        body = json.dumps({'server_modified': '2026-10-22T16:00:00Z'}).encode()
        s, _ = store({'/files/get_metadata': (200, body)})
        self.assertEqual(s.modified('/Requests/request-0003.yaml'), 1792684800)

    def test_upload_sends_overwrite_and_no_autorename(self):
        s, opener = store({'/files/upload': (200, b'{}')})
        s.upload('/Descriptions/.description-0003.md.partial', b'text')
        request = opener.requests[-1]
        arg = json.loads(request.get_header('Dropbox-api-arg'))
        self.assertEqual(arg['mode'], 'overwrite')
        self.assertFalse(arg['autorename'])
        self.assertEqual(request.data, b'text')

    def test_move_uses_move_v2(self):
        s, opener = store({'/files/move_v2': (200, b'{}')})
        s.move('/Images/.image-0003.jpg.partial', '/Images/image-0003.jpg')
        sent = json.loads(opener.requests[-1].data.decode())
        self.assertEqual(sent['from_path'], '/Images/.image-0003.jpg.partial')
        self.assertEqual(sent['to_path'], '/Images/image-0003.jpg')

    def test_other_http_error_is_a_store_error_and_an_oserror(self):
        s, _ = store({'/files/get_metadata': (500, b'boom')})
        with self.assertRaises(ds.StoreError) as ctx:
            s.exists('/x')
        self.assertIsInstance(ctx.exception, OSError)

    def test_expired_token_is_refreshed_once(self):
        expired = json.dumps({'error_summary': 'expired_access_token/..'}).encode()
        answers = {'/files/get_metadata': (401, expired)}
        s, opener = store(answers)
        with self.assertRaises(ds.StoreError):
            s.exists('/x')
        token_calls = [r for r in opener.requests if r.full_url.endswith('/oauth2/token')]
        self.assertEqual(len(token_calls), 2)  # first use, then one refresh after the 401

    def test_no_delete_call_is_ever_made(self):
        self.assertFalse(any('delete' in name for name in dir(ds.DropboxStore) if not name.startswith('__')))


if __name__ == '__main__':
    unittest.main()
