"""Tests for the MVP B watcher core, with fakes for the store, cameras, describer and memory.

Run: cd watcher && python3 -m unittest -v test_whiteboard_watcher
"""

import unittest

import whiteboard_watcher as ww

NOW = 1000000
VALID = 'request: "0003"\n'
YES = 'whiteboard: yes\n## Text\nHELLO'


class FakeStore(object):
    """In-memory stand-in for the Dropbox store. Records every write in order."""

    def __init__(self, requests=None, age=0):
        self.files = {}
        self.events = []
        self.fail_upload_on = None  # substring; upload to a matching path raises
        self.mtimes = {}
        for name, text in (requests or {}).items():
            self.files['/Requests/' + name] = text.encode('utf-8')
            self.mtimes['/Requests/' + name] = NOW - age

    def list_names(self, folder):
        prefix = folder.rstrip('/') + '/'
        return [p[len(prefix):] for p in self.files
                if p.startswith(prefix) and '/' not in p[len(prefix):]]

    def exists(self, path):
        return path in self.files

    def modified(self, path):
        return self.mtimes.get(path, NOW)

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


class FakeCameras(object):
    """Camera list and per-index behaviour. `plan[index]` is a photo, or an error message."""

    def __init__(self, indices=(0,), plan=None, list_error=None):
        self.indices = list(indices)
        self.plan = plan or {}
        self.list_error = list_error
        self.captures = []

    def list(self):
        if self.list_error:
            raise ww.CameraError(self.list_error)
        return [(i, 'cam %d' % i) for i in self.indices]

    def capture(self, index):
        self.captures.append(index)
        result = self.plan.get(index, b'photo-%d' % index)
        if isinstance(result, str):
            raise ww.CameraError(result)
        return result


class FakeDescriber(object):
    """Answers per photo. `answers[photo]` is the text, or an error message to raise."""

    def __init__(self, answers=None, default=YES):
        self.answers = answers or {}
        self.default = default
        self.calls = []

    def describe(self, photo, fields):
        self.calls.append(photo)
        answer = self.answers.get(photo, self.default)
        if answer.startswith('ERR:'):
            raise ww.DescribeError(answer[4:])
        return answer


class FakeMemory(object):
    def __init__(self, index=None):
        self.last = index
        self.remembered = []

    def index(self):
        return self.last

    def remember(self, index):
        self.remembered.append(index)
        self.last = index


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


class SplitAnswerTests(unittest.TestCase):

    def test_yes_strips_the_line(self):
        self.assertEqual(ww.split_answer('whiteboard: yes\nbody\n'), (True, 'body'))

    def test_no(self):
        self.assertEqual(ww.split_answer('whiteboard: no'), (False, ''))

    def test_case_and_spaces_tolerated(self):
        self.assertEqual(ww.split_answer('  Whiteboard: YES \nx')[0], True)

    def test_missing_line_is_an_error(self):
        with self.assertRaises(ww.DescribeError):
            ww.split_answer('This is a whiteboard with notes.')

    def test_empty_answer_is_an_error(self):
        with self.assertRaises(ww.DescribeError):
            ww.split_answer('   \n')


class CameraOrderTests(unittest.TestCase):

    def test_remembered_first_then_listing_order(self):
        self.assertEqual(ww.camera_order([0, 1, 2], 1), [1, 0, 2])

    def test_no_memory_keeps_listing_order(self):
        self.assertEqual(ww.camera_order([0, 1], None), [0, 1])

    def test_remembered_but_not_listed_is_ignored(self):
        self.assertEqual(ww.camera_order([0, 2], 5), [0, 2])

    def test_each_index_once(self):
        order = ww.camera_order([0, 1, 2], 2)
        self.assertEqual(sorted(order), [0, 1, 2])


class ProcessTests(unittest.TestCase):

    def run_one(self, store, cameras=None, describer=None, memory=None):
        cameras = cameras or FakeCameras()
        describer = describer or FakeDescriber()
        memory = memory or FakeMemory()
        handled = ww.process_pending(store, cameras, describer, memory, now=NOW)
        return handled, cameras, describer, memory

    def test_remembered_camera_works_with_exactly_one_photo(self):
        store = FakeStore({'request-0003.yaml': VALID})
        handled, cameras, describer, memory = self.run_one(
            store, FakeCameras([0, 1]), memory=FakeMemory(1))
        self.assertEqual(handled, ['0003'])
        self.assertEqual(cameras.captures, [1])
        self.assertEqual(len(describer.calls), 1)
        self.assertEqual(store.files['/Images/image-0003.jpg'], b'photo-1')
        desc = store.text('/Descriptions/description-0003.md')
        self.assertTrue(desc.startswith('status: ok\n'))
        self.assertNotIn('whiteboard:', desc)
        self.assertIn('HELLO', desc)
        self.assertEqual(memory.remembered, [1])

    def test_description_is_written_after_image(self):
        store = FakeStore({'request-0003.yaml': VALID})
        self.run_one(store)
        moved = [dst for kind, dst in store.events if kind == 'move']
        self.assertEqual(moved, ['/Images/image-0003.jpg',
                                 '/Descriptions/description-0003.md'])

    def test_remembered_wrong_then_second_camera_works(self):
        store = FakeStore({'request-0003.yaml': VALID})
        cameras = FakeCameras([0, 1], plan={})
        describer = FakeDescriber(answers={b'photo-1': 'whiteboard: no\nroom'})
        handled, cameras, _, memory = self.run_one(
            store, cameras, describer, FakeMemory(1))
        self.assertEqual(handled, ['0003'])
        self.assertEqual(cameras.captures, [1, 0])
        self.assertEqual(store.files['/Images/image-0003.jpg'], b'photo-0')
        self.assertEqual(memory.remembered, [0])

    def test_dark_camera_is_skipped_and_the_next_one_used(self):
        store = FakeStore({'request-0003.yaml': VALID})
        cameras = FakeCameras([0, 1], plan={0: 'dark, closed lid (mean 2)'})
        handled, cameras, describer, _ = self.run_one(store, cameras)
        self.assertEqual(handled, ['0003'])
        self.assertEqual(cameras.captures, [0, 1])
        self.assertEqual(describer.calls, [b'photo-1'])
        self.assertEqual(store.files['/Images/image-0003.jpg'], b'photo-1')

    def test_all_cameras_fail_writes_one_error_with_a_line_per_camera(self):
        store = FakeStore({'request-0003.yaml': VALID})
        cameras = FakeCameras([0, 1], plan={0: 'dark, closed lid (mean 2)', 1: 'no frame'})
        describer = FakeDescriber(default='whiteboard: no\nroom')
        self.run_one(store, cameras, describer)
        self.assertFalse(store.exists('/Images/image-0003.jpg'))
        desc = store.text('/Descriptions/description-0003.md')
        self.assertTrue(desc.startswith('status: error\n'))
        self.assertIn('reason: camera 0: dark, closed lid (mean 2)', desc)
        self.assertIn('reason: camera 1: no frame', desc)
        self.assertEqual(sum(1 for p in store.files if p.startswith('/Descriptions/')), 1)

    def test_not_a_whiteboard_on_every_camera_is_an_error_without_image(self):
        store = FakeStore({'request-0003.yaml': VALID})
        describer = FakeDescriber(default='whiteboard: no')
        self.run_one(store, FakeCameras([0, 1]), describer)
        self.assertFalse(store.exists('/Images/image-0003.jpg'))
        self.assertIn('reason: camera 0: not a whiteboard',
                      store.text('/Descriptions/description-0003.md'))

    def test_describe_without_whiteboard_line_counts_as_failure(self):
        store = FakeStore({'request-0003.yaml': VALID})
        describer = FakeDescriber(default='a whiteboard with text')
        self.run_one(store, FakeCameras([0]), describer)
        desc = store.text('/Descriptions/description-0003.md')
        self.assertIn('status: error', desc)
        self.assertIn('describe: answer did not start with a whiteboard line', desc)

    def test_describe_error_counts_as_failure_for_that_camera(self):
        store = FakeStore({'request-0003.yaml': VALID})
        describer = FakeDescriber(answers={b'photo-0': 'ERR:claude timed out after 120 s'})
        handled, cameras, _, _ = self.run_one(store, FakeCameras([0, 1]), describer)
        self.assertEqual(cameras.captures, [0, 1])
        self.assertEqual(handled, ['0003'])
        self.assertEqual(store.files['/Images/image-0003.jpg'], b'photo-1')

    def test_single_camera_works(self):
        store = FakeStore({'request-0003.yaml': VALID})
        handled, cameras, _, _ = self.run_one(store, FakeCameras([4]))
        self.assertEqual(handled, ['0003'])
        self.assertEqual(cameras.captures, [4])

    def test_single_camera_fails_gives_error(self):
        store = FakeStore({'request-0003.yaml': VALID})
        self.run_one(store, FakeCameras([4], plan={4: 'no frame'}))
        self.assertIn('reason: camera 4: no frame', store.text('/Descriptions/description-0003.md'))

    def test_no_camera_listed_gives_error(self):
        store = FakeStore({'request-0003.yaml': VALID})
        self.run_one(store, FakeCameras(list_error='ffmpeg lists no camera'))
        self.assertIn('reason: camera: ffmpeg lists no camera',
                      store.text('/Descriptions/description-0003.md'))

    def test_each_camera_tried_at_most_once_no_loop(self):
        store = FakeStore({'request-0003.yaml': VALID})
        cameras = FakeCameras([0, 1, 2], plan={0: 'no', 1: 'no', 2: 'no'})
        self.run_one(store, cameras, memory=FakeMemory(1))
        self.assertEqual(cameras.captures, [1, 0, 2])

    def test_memory_none_uses_listing_order(self):
        store = FakeStore({'request-0003.yaml': VALID})
        cameras = FakeCameras([0, 1], plan={0: 'no frame'})
        self.run_one(store, cameras, memory=FakeMemory(None))
        self.assertEqual(cameras.captures, [0, 1])

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

    def test_image_without_description_is_closed_as_interrupted(self):
        store = FakeStore({'request-0003.yaml': VALID})
        store.files['/Images/image-0003.jpg'] = b'old'
        handled, cameras, describer, _ = self.run_one(store)
        self.assertEqual(handled, [])
        self.assertEqual(cameras.captures, [])
        self.assertEqual(describer.calls, [])
        desc = store.text('/Descriptions/description-0003.md')
        self.assertTrue(desc.startswith('status: error\n'))
        self.assertIn('reason: interrupted before the description was written', desc)

    def test_request_older_than_limit_is_expired_without_photo(self):
        store = FakeStore({'request-0003.yaml': VALID}, age=ww.MAX_REQUEST_AGE + 1)
        handled, cameras, describer, _ = self.run_one(store)
        self.assertEqual(handled, [])
        self.assertEqual(cameras.captures, [])
        self.assertEqual(describer.calls, [])
        self.assertFalse(store.exists('/Images/image-0003.jpg'))
        desc = store.text('/Descriptions/description-0003.md')
        self.assertTrue(desc.startswith('status: error\n'))
        self.assertIn('reason: expired', desc)

    def test_request_at_the_limit_is_still_processed(self):
        store = FakeStore({'request-0003.yaml': VALID}, age=ww.MAX_REQUEST_AGE)
        handled, _, _, _ = self.run_one(store)
        self.assertEqual(handled, ['0003'])

    def test_expired_request_does_not_block_a_fresh_one(self):
        store = FakeStore({'request-0002.yaml': 'request: "0002"\n'}, age=500)
        store.files['/Requests/request-0003.yaml'] = VALID.encode('utf-8')
        store.mtimes['/Requests/request-0003.yaml'] = NOW - 5
        handled, _, _, _ = self.run_one(store)
        self.assertEqual(handled, ['0003'])
        self.assertIn('reason: expired', store.text('/Descriptions/description-0002.md'))

    def test_already_described_request_is_skipped(self):
        store = FakeStore({'request-0003.yaml': VALID})
        store.files['/Descriptions/description-0003.md'] = b'status: ok\n'
        handled, cameras, _, _ = self.run_one(store)
        self.assertEqual(handled, [])
        self.assertEqual(cameras.captures, [])

    def test_invalid_request_writes_error_without_camera(self):
        store = FakeStore({'request-0003.yaml': VALID + 'marker_color: pink\n'})
        handled, cameras, describer, _ = self.run_one(store)
        self.assertEqual(cameras.captures, [])
        self.assertEqual(describer.calls, [])
        desc = store.text('/Descriptions/description-0003.md')
        self.assertIn('status: error', desc)
        self.assertIn('marker_color', desc)

    def test_oldest_request_first(self):
        store = FakeStore({'request-0007.yaml': 'request: "0007"\n',
                           'request-0002.yaml': 'request: "0002"\n'})
        handled, _, _, _ = self.run_one(store)
        self.assertEqual(handled, ['0002', '0007'])

    def test_old_txt_requests_are_ignored(self):
        store = FakeStore({'request-0001.txt': 'old format\n',
                           'request-0002.txt': 'old format\n'})
        handled, cameras, _, _ = self.run_one(store)
        self.assertEqual(handled, [])
        self.assertEqual(cameras.captures, [])

    def test_mode_diff_is_described_as_snapshot_with_note(self):
        store = FakeStore({'request-0003.yaml': VALID + 'mode: diff\n'})
        self.run_one(store)
        desc = store.text('/Descriptions/description-0003.md')
        self.assertIn('status: ok', desc)
        self.assertIn('mode diff is not supported yet', desc)


if __name__ == '__main__':
    unittest.main()
