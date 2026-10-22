"""Tests for the MVP B watcher core, with fake Dropbox store, camera and describer.

Run: cd watcher && python3 -m unittest -v test_whiteboard_watcher
"""

import unittest

import whiteboard_watcher as ww


class FakeStore(object):
    """In-memory stand-in for the Dropbox client. Records every write in order."""

    def __init__(self, requests=None):
        self.files = {}
        self.events = []
        self.fail_upload_on = None  # substring; upload to a matching path raises
        for name, text in (requests or {}).items():
            self.files['/Requests/' + name] = text.encode('utf-8')

    def list_names(self, folder):
        prefix = folder.rstrip('/') + '/'
        return [p[len(prefix):] for p in self.files
                if p.startswith(prefix) and '/' not in p[len(prefix):]]

    def exists(self, path):
        return path in self.files

    def read_text(self, path):
        return self.files[path].decode('utf-8')

    def upload(self, path, data):
        if self.fail_upload_on and self.fail_upload_on in path:
            raise IOError('simulated upload failure')
        self.events.append(('upload', path))
        self.files[path] = data

    def move(self, src, dst):
        self.events.append(('move', dst))
        self.files[dst] = self.files.pop(src)

    def text(self, path):
        return self.files[path].decode('utf-8')


class FakeCamera(object):
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0

    def take_photo(self):
        self.calls += 1
        if self.fail:
            raise ww.CameraError('no frame within 20 s')
        return b'fake-jpeg'


class FakeDescriber(object):
    def __init__(self, text='## Text\nHELLO', fail=False):
        self.text = text
        self.fail = fail
        self.calls = []

    def describe(self, photo, fields):
        self.calls.append(dict(fields))
        if self.fail:
            raise ww.DescribeError('claude timed out after 120 s')
        return self.text


VALID = 'request: "0003"\n'


class ParseRequestTests(unittest.TestCase):

    def test_minimal_request(self):
        self.assertEqual(ww.parse_request(VALID, '0003'), {'request': '0003'})

    def test_all_fields_and_blank_and_comment_lines(self):
        text = ('# note\n\nrequest: "0003"\nmarker_color: red\n'
                "region_v: 'top'\nregion_h: left\nmode: snapshot\n")
        fields = ww.parse_request(text, '0003')
        self.assertEqual(fields['marker_color'], 'red')
        self.assertEqual(fields['region_v'], 'top')
        self.assertEqual(fields['region_h'], 'left')
        self.assertEqual(fields['mode'], 'snapshot')

    def test_unknown_field_rejected(self):
        with self.assertRaises(ww.RequestError):
            ww.parse_request(VALID + 'colour: red\n', '0003')

    def test_invalid_value_rejected(self):
        with self.assertRaises(ww.RequestError):
            ww.parse_request(VALID + 'marker_color: pink\n', '0003')

    def test_request_number_must_match_file_name(self):
        with self.assertRaises(ww.RequestError):
            ww.parse_request(VALID, '0004')

    def test_missing_request_field_rejected(self):
        with self.assertRaises(ww.RequestError):
            ww.parse_request('mode: snapshot\n', '0003')

    def test_duplicate_field_rejected(self):
        with self.assertRaises(ww.RequestError):
            ww.parse_request(VALID + 'mode: snapshot\nmode: diff\n', '0003')

    def test_line_that_is_not_name_value_rejected(self):
        for bad in ['- red\n', 'marker_color:\n', 'nested:\n  a: b\n']:
            with self.assertRaises(ww.RequestError):
                ww.parse_request(VALID + bad, '0003')


class ProcessTests(unittest.TestCase):

    def run_one(self, store, camera=None, describer=None):
        camera = camera or FakeCamera()
        describer = describer or FakeDescriber()
        handled = ww.process_pending(store, camera, describer)
        return handled, camera, describer

    def test_new_request_gets_image_then_description(self):
        store = FakeStore({'request-0003.yaml': VALID})
        handled, camera, describer = self.run_one(store)
        self.assertEqual(handled, ['0003'])
        self.assertEqual(camera.calls, 1)
        self.assertEqual(store.files['/Images/image-0003.jpg'], b'fake-jpeg')
        desc = store.text('/Descriptions/description-0003.md')
        self.assertIn('status: ok', desc)
        self.assertIn('request: "0003"', desc)
        self.assertIn('HELLO', desc)
        self.assertEqual(describer.calls, [{'request': '0003'}])

    def test_description_is_written_last(self):
        store = FakeStore({'request-0003.yaml': VALID})
        self.run_one(store)
        moved = [dst for kind, dst in store.events if kind == 'move']
        self.assertEqual(moved, ['/Images/image-0003.jpg',
                                 '/Descriptions/description-0003.md'])

    def test_already_described_request_is_skipped(self):
        store = FakeStore({'request-0003.yaml': VALID})
        store.files['/Descriptions/description-0003.md'] = b'status: ok\n'
        handled, camera, _ = self.run_one(store)
        self.assertEqual(handled, [])
        self.assertEqual(camera.calls, 0)

    def test_request_with_image_but_no_description_is_not_taken_again(self):
        store = FakeStore({'request-0003.yaml': VALID})
        store.files['/Images/image-0003.jpg'] = b'old'
        handled, camera, _ = self.run_one(store)
        self.assertEqual(handled, [])
        self.assertEqual(camera.calls, 0)

    def test_camera_failure_writes_error_description_only(self):
        store = FakeStore({'request-0003.yaml': VALID})
        self.run_one(store, camera=FakeCamera(fail=True))
        self.assertFalse(store.exists('/Images/image-0003.jpg'))
        desc = store.text('/Descriptions/description-0003.md')
        self.assertIn('status: error', desc)
        self.assertIn('no frame within 20 s', desc)
        self.assertNotIn('status: ok', desc)

    def test_describe_failure_keeps_image_and_writes_error(self):
        store = FakeStore({'request-0003.yaml': VALID})
        self.run_one(store, describer=FakeDescriber(fail=True))
        self.assertEqual(store.files['/Images/image-0003.jpg'], b'fake-jpeg')
        desc = store.text('/Descriptions/description-0003.md')
        self.assertIn('status: error', desc)
        self.assertIn('claude timed out', desc)

    def test_empty_description_is_an_error(self):
        store = FakeStore({'request-0003.yaml': VALID})
        self.run_one(store, describer=FakeDescriber(text='   \n'))
        self.assertIn('status: error', store.text('/Descriptions/description-0003.md'))

    def test_invalid_request_writes_error_without_camera(self):
        store = FakeStore({'request-0003.yaml': VALID + 'marker_color: pink\n'})
        _, camera, describer = self.run_one(store)
        self.assertEqual(camera.calls, 0)
        self.assertEqual(describer.calls, [])
        desc = store.text('/Descriptions/description-0003.md')
        self.assertIn('status: error', desc)
        self.assertIn('marker_color', desc)

    def test_error_reason_is_one_line(self):
        store = FakeStore({'request-0003.yaml': 'request: "0003"\nfoo\nbar\n'})
        self.run_one(store)
        desc = store.text('/Descriptions/description-0003.md')
        reason = [l for l in desc.splitlines() if l.startswith('reason:')]
        self.assertEqual(len(reason), 1)

    def test_half_written_file_never_visible(self):
        store = FakeStore({'request-0003.yaml': VALID})
        store.fail_upload_on = '.partial'  # the temporary upload breaks
        self.run_one(store)
        self.assertFalse(store.exists('/Descriptions/description-0003.md'))
        self.assertFalse(store.exists('/Images/image-0003.jpg'))
        self.assertEqual([e for e in store.events if e[0] == 'move'], [])

    def test_final_names_only_appear_through_a_move(self):
        store = FakeStore({'request-0003.yaml': VALID})
        self.run_one(store)
        for kind, path in store.events:
            if kind == 'upload':
                self.assertTrue(path.endswith('.partial'), path)

    def test_oldest_request_first(self):
        store = FakeStore({'request-0007.yaml': 'request: "0007"\n',
                           'request-0002.yaml': 'request: "0002"\n'})
        handled, _, _ = self.run_one(store)
        self.assertEqual(handled, ['0002', '0007'])

    def test_old_txt_requests_are_ignored(self):
        store = FakeStore({'request-0001.txt': 'old format\n',
                           'request-0002.txt': 'old format\n'})
        handled, camera, _ = self.run_one(store)
        self.assertEqual(handled, [])
        self.assertEqual(camera.calls, 0)

    def test_mode_diff_is_described_as_snapshot_with_note(self):
        store = FakeStore({'request-0003.yaml': VALID + 'mode: diff\n'})
        self.run_one(store)
        desc = store.text('/Descriptions/description-0003.md')
        self.assertIn('status: ok', desc)
        self.assertIn('mode diff is not supported yet', desc)


if __name__ == '__main__':
    unittest.main()
