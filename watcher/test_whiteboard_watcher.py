"""Tests for the MVP B watcher core, with fakes for the store, cameras, describer and memory.

Run: cd watcher && python3 -m unittest -v test_whiteboard_watcher
"""

import unittest

import whiteboard_watcher as ww
from stopwatch import MARKER, Watch

NOW = 1000000
VALID = 'request: "0003"\n'
YES = 'whiteboard: yes\n## Text\nHELLO'
MODELS = {'haiku': 'claude-haiku-5-5', 'sonnet': 'claude-sonnet-5-5', 'opus': 'claude-opus-5-5'}
SETTINGS = {'models': MODELS, 'default_model': 'haiku'}


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
        self.last = {}

    def list(self):
        if self.list_error:
            raise ww.CameraError(self.list_error)
        return [(i, 'cam %d' % i) for i in self.indices]

    def capture(self, index):
        self.captures.append(index)
        self.last = {'photo_s': 0.5, 'brightness': 120.0, 'brightness_s': 0.1}
        result = self.plan.get(index, b'photo-%d' % index)
        if isinstance(result, list):
            result = result.pop(0)  # a sequence of results: one per call
        if isinstance(result, str) and result.startswith('DARK:'):
            raise ww.DarkFrameError(result[5:])
        if isinstance(result, str):
            raise ww.CameraError(result)
        return result


class FakeDescriber(object):
    """Answers per photo. `answers[photo]` is the text, or 'ERR:...' to raise."""

    def __init__(self, answers=None, default=YES):
        self.answers = answers or {}
        self.default = default
        self.calls = []    # photos
        self.fields = []   # fields per call

    def describe(self, photo, fields):
        self.calls.append(photo)
        self.fields.append(dict(fields))
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

    def parse(self, text, number='0003'):
        return ww.parse_request(text, number, MODELS, 'haiku')

    def test_minimal_request_gets_default_model(self):
        self.assertEqual(self.parse(VALID), {'request': '0003', 'model': 'haiku'})

    def test_all_fields_and_blank_and_comment_lines(self):
        text = ('# note\n\nrequest: "0003"\nmarker_color: red\n'
                "region_v: 'top'\nregion_h: left\nmode: snapshot\n")
        fields = self.parse(text)
        self.assertEqual(fields['marker_color'], 'red')
        self.assertEqual(fields['region_v'], 'top')
        self.assertEqual(fields['region_h'], 'left')
        self.assertEqual(fields['mode'], 'snapshot')

    def test_model_field_is_taken_when_allowed(self):
        self.assertEqual(self.parse(VALID + 'model: sonnet\n')['model'], 'sonnet')

    def test_model_not_in_config_rejected_with_allowed_list(self):
        with self.assertRaises(ww.RequestError) as ctx:
            self.parse(VALID + 'model: gpt\n')
        self.assertIn('allowed: haiku, opus, sonnet', str(ctx.exception))

    def test_unknown_field_rejected(self):
        with self.assertRaises(ww.RequestError):
            self.parse(VALID + 'colour: red\n')

    def test_invalid_value_rejected(self):
        with self.assertRaises(ww.RequestError):
            self.parse(VALID + 'marker_color: pink\n')

    def test_request_number_must_match_file_name(self):
        with self.assertRaises(ww.RequestError):
            self.parse(VALID, '0004')

    def test_missing_request_field_rejected(self):
        with self.assertRaises(ww.RequestError):
            self.parse('mode: snapshot\n')

    def test_duplicate_field_rejected(self):
        with self.assertRaises(ww.RequestError):
            self.parse(VALID + 'mode: snapshot\nmode: diff\n')

    def test_line_that_is_not_name_value_rejected(self):
        for bad in ['- red\n', 'marker_color:\n', 'nested:\n  a: b\n']:
            with self.assertRaises(ww.RequestError):
                self.parse(VALID + bad)


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

    def run_one(self, store, cameras=None, describer=None, memory=None, settings=SETTINGS):
        cameras = cameras or FakeCameras()
        describer = describer or FakeDescriber()
        memory = memory or FakeMemory()
        watch = Watch(machine='test-mac', clock=lambda: 1000.0)
        handled = ww.process_pending(store, cameras, describer, memory, watch, NOW, settings)
        self.watch = watch
        return handled, cameras, describer, memory

    def description(self, store, number='0003'):
        return store.text('/Descriptions/description-%s.md' % number)

    def test_remembered_camera_works_with_exactly_one_photo(self):
        store = FakeStore({'request-0003.yaml': VALID})
        handled, cameras, describer, memory = self.run_one(
            store, FakeCameras([0, 1]), memory=FakeMemory(1))
        self.assertEqual(handled, ['0003'])
        self.assertEqual(cameras.captures, [1])
        self.assertEqual(len(describer.calls), 1)
        self.assertEqual(store.files['/Images/image-0003.jpg'], b'photo-1')
        desc = self.description(store)
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
        describer = FakeDescriber(answers={b'photo-1': 'whiteboard: no\nroom'})
        handled, cameras, _, memory = self.run_one(
            store, FakeCameras([0, 1]), describer, FakeMemory(1))
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
        self.run_one(store, cameras, FakeDescriber(default='whiteboard: no\nroom'))
        self.assertFalse(store.exists('/Images/image-0003.jpg'))
        desc = self.description(store)
        self.assertTrue(desc.startswith('status: error\n'))
        self.assertIn('reason: camera 0: dark, closed lid (mean 2)', desc)
        self.assertIn('reason: camera 1: no frame', desc)
        self.assertEqual(sum(1 for p in store.files if p.startswith('/Descriptions/')), 1)

    def test_not_a_whiteboard_on_every_camera_is_an_error_without_image(self):
        store = FakeStore({'request-0003.yaml': VALID})
        self.run_one(store, FakeCameras([0, 1]), FakeDescriber(default='whiteboard: no'))
        self.assertFalse(store.exists('/Images/image-0003.jpg'))
        self.assertIn('reason: camera 0: not a whiteboard', self.description(store))

    def test_describe_without_whiteboard_line_counts_as_failure(self):
        store = FakeStore({'request-0003.yaml': VALID})
        self.run_one(store, FakeCameras([0]), FakeDescriber(default='a whiteboard with text'))
        desc = self.description(store)
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
        self.assertIn('reason: camera 4: no frame', self.description(store))

    def test_no_camera_listed_gives_error(self):
        store = FakeStore({'request-0003.yaml': VALID})
        self.run_one(store, FakeCameras(list_error='ffmpeg lists no camera'))
        self.assertIn('reason: camera: ffmpeg lists no camera', self.description(store))

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
        desc = self.description(store)
        self.assertTrue(desc.startswith('status: error\n'))
        self.assertIn('reason: interrupted before the description was written', desc)

    def test_request_older_than_limit_is_expired_without_photo(self):
        store = FakeStore({'request-0003.yaml': VALID}, age=ww.MAX_REQUEST_AGE + 1)
        handled, cameras, describer, _ = self.run_one(store)
        self.assertEqual(handled, [])
        self.assertEqual(cameras.captures, [])
        self.assertEqual(describer.calls, [])
        self.assertFalse(store.exists('/Images/image-0003.jpg'))
        desc = self.description(store)
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
        self.assertIn('reason: expired', self.description(store, '0002'))

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
        desc = self.description(store)
        self.assertIn('status: error', desc)
        self.assertIn('marker_color', desc)

    def test_bad_model_writes_error_naming_allowed_values_and_takes_no_photo(self):
        store = FakeStore({'request-0003.yaml': VALID + 'model: gpt\n'})
        _, cameras, describer, _ = self.run_one(store)
        self.assertEqual(cameras.captures, [])
        self.assertEqual(describer.calls, [])
        desc = self.description(store)
        self.assertTrue(desc.startswith('status: error\n'))
        self.assertIn('allowed: haiku, opus, sonnet', desc)

    def test_model_from_request_is_passed_to_describe(self):
        store = FakeStore({'request-0003.yaml': VALID + 'model: sonnet\n'})
        _, _, describer, _ = self.run_one(store)
        self.assertEqual(describer.fields[0]['model'], 'sonnet')
        self.assertIn('fields: model=sonnet', self.description(store))

    def test_default_model_is_used_when_request_has_none(self):
        store = FakeStore({'request-0003.yaml': VALID})
        _, _, describer, _ = self.run_one(store)
        self.assertEqual(describer.fields[0]['model'], 'haiku')

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
        desc = self.description(store)
        self.assertIn('status: ok', desc)
        self.assertIn('mode diff is not supported yet', desc)

    def test_ok_description_ends_with_timing_block_and_no_final_upload_time(self):
        store = FakeStore({'request-0003.yaml': VALID})
        self.run_one(store)
        desc = self.description(store)
        self.assertIn('\n' + MARKER + '\n', desc)
        block = desc.split(MARKER + '\n', 1)[1]
        self.assertIn('machine: test-mac', block)
        self.assertIn('model: haiku', block)
        self.assertIn('camera 0: ok', block)
        self.assertIn('total before description upload', block)
        self.assertNotIn('\ndescription upload:', '\n' + block)
        self.assertNotIn('HELLO', block)  # no whiteboard content in the block

    def test_error_description_also_has_timing_block(self):
        store = FakeStore({'request-0003.yaml': VALID + 'model: gpt\n'})
        self.run_one(store)
        self.assertIn(MARKER, self.description(store))

    def test_one_row_per_request_with_outcome_and_tries(self):
        store = FakeStore({'request-0003.yaml': VALID})
        cameras = FakeCameras([0, 1], plan={0: 'dark, closed lid (mean 2)'})
        self.run_one(store, cameras)
        self.assertEqual(len(self.watch.rows), 1)
        row = self.watch.rows[0]
        self.assertEqual(row['request'], '0003')
        self.assertEqual(row['outcome'], 'ok')
        self.assertEqual(row['model'], 'haiku')
        self.assertIn('0:dark, closed lid (mean 2)', row['tries'])
        self.assertIn('1:ok', row['tries'])
        self.assertNotIn('HELLO', str(row))

    def test_detection_is_time_since_dropbox_saw_the_request(self):
        store = FakeStore({'request-0003.yaml': VALID}, age=7)
        self.run_one(store)
        self.assertEqual(self.watch.rows[0]['detect_s'], '7.00')

    def test_dark_then_bright_after_reopen_uses_the_reopen(self):
        store = FakeStore({'request-0003.yaml': VALID})
        cameras = FakeCameras([0], plan={0: ['DARK:mean 1', b'photo-retry']})
        handled, cameras, describer, _ = self.run_one(store, cameras)
        self.assertEqual(handled, ['0003'])
        self.assertEqual(cameras.captures, [0, 0])
        self.assertEqual(store.files['/Images/image-0003.jpg'], b'photo-retry')
        self.assertEqual(self.watch.rows[0]['outcome'], 'ok')
        self.assertIn('0:mean 1', self.watch.rows[0]['tries'])
        self.assertIn('0:ok', self.watch.rows[0]['tries'])

    def test_bright_first_frame_is_one_capture_no_reopen(self):
        store = FakeStore({'request-0003.yaml': VALID})
        cameras = FakeCameras([0, 1])
        _, cameras, _, _ = self.run_one(store, cameras)
        self.assertEqual(cameras.captures, [0])
        self.assertEqual(self.watch.rows[0]['tries'], '0:ok:0.50:120.0:0.00')

    def test_dark_three_times_moves_on_to_the_next_camera(self):
        store = FakeStore({'request-0003.yaml': VALID})
        cameras = FakeCameras([0, 1], plan={0: ['DARK:mean 1', 'DARK:mean 2', 'DARK:mean 3']})
        _, cameras, _, _ = self.run_one(store, cameras)
        self.assertEqual(cameras.captures, [0, 0, 0, 1])
        self.assertEqual(store.files['/Images/image-0003.jpg'], b'photo-1')

    def test_dark_after_two_reopens_is_not_tried_a_fourth_time(self):
        store = FakeStore({'request-0003.yaml': VALID})
        cameras = FakeCameras([0], plan={0: ['DARK:mean 1', 'DARK:mean 2', 'DARK:mean 3']})
        self.run_one(store, cameras)
        self.assertEqual(cameras.captures, [0, 0, 0])

    def test_dark_on_every_try_gives_error_with_the_last_reason(self):
        store = FakeStore({'request-0003.yaml': VALID})
        cameras = FakeCameras([0], plan={0: ['DARK:dark, closed lid (mean 1)',
                                             'DARK:dark, closed lid (mean 2)',
                                             'DARK:dark, closed lid (mean 3)']})
        self.run_one(store, cameras)
        self.assertEqual(cameras.captures, [0, 0, 0])
        self.assertIn('reason: camera 0: dark, closed lid (mean 3)', self.description(store))

    def test_network_error_on_the_description_check_does_not_raise(self):
        store = FakeStore({'request-0003.yaml': VALID, 'request-0004.yaml': 'request: "0004"\n'})
        real_exists = store.exists

        def flaky(path):
            if path.startswith('/Descriptions/description-0003'):
                raise OSError('no connection to Dropbox (URLError)')
            return real_exists(path)
        store.exists = flaky
        cameras = FakeCameras([0])
        watch = Watch(machine='test-mac', clock=lambda: 1000.0)
        handled = ww.process_pending(store, cameras, FakeDescriber(), FakeMemory(), watch, NOW, SETTINGS)
        self.assertEqual(handled, ['0004'])

    def test_network_error_on_listing_requests_does_not_raise(self):
        store = FakeStore({'request-0003.yaml': VALID})

        def down(folder):
            raise OSError('no connection to Dropbox (timeout)')
        store.list_names = down
        cameras = FakeCameras([0])
        watch = Watch(machine='test-mac', clock=lambda: 1000.0)
        handled = ww.process_pending(store, cameras, FakeDescriber(), FakeMemory(), watch, NOW, SETTINGS)
        self.assertEqual(handled, [])
        self.assertEqual(cameras.captures, [])

    def test_other_camera_error_is_not_retried(self):
        store = FakeStore({'request-0003.yaml': VALID})
        cameras = FakeCameras([0, 1], plan={0: 'no frame'})
        _, cameras, _, _ = self.run_one(store, cameras)
        self.assertEqual(cameras.captures, [0, 1])


if __name__ == '__main__':
    unittest.main()
