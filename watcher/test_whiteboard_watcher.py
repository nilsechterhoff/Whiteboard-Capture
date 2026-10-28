"""Tests for the MVP B watcher core, with fakes for the store, cameras, describer and memory.

Run: cd watcher && python3 -m unittest -v test_whiteboard_watcher
"""

import time
import unittest

import whiteboard_watcher as ww
from stopwatch import MARKER, Watch

NOW = 1000000
VALID = 'request: "0003"\n'
YES = 'whiteboard_visible: yes\nboard_fill_percent: 90\nis_board_camera: yes\n\n\n## Text\nHELLO'
MODELS = {'haiku': 'claude-haiku-5-5', 'sonnet': 'claude-sonnet-5-5', 'opus': 'claude-opus-5-5'}
SETTINGS = {'models': MODELS, 'default_model': 'haiku'}


class FakeStore(object):
    """In-memory stand-in for the Dropbox store. Records every write in order."""

    def __init__(self, requests=None, age=0):
        self.files = {}
        self.events = []
        self.fail_upload_on = None  # substring; upload to a matching path raises
        self.raise_on = {}          # substring -> exception to raise on upload
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
        for part, error in self.raise_on.items():
            if part in path:
                raise error
        if self.fail_upload_on and self.fail_upload_on in path:
            raise IOError('simulated upload failure')
        self.events.append(('upload', path))
        self.files[path] = data

    def move(self, src, dst):
        if dst in self.files:  # Dropbox move_v2 refuses to overwrite (autorename is off)
            raise IOError('conflict: destination exists')
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


class FakeResults(object):
    """In-memory local copy: saved results, done markers."""

    def __init__(self, saved=None):
        self.saved = dict(saved or {})   # number -> (photo or None, text)
        self.done = set()

    def save(self, number, photo, text):
        self.saved[number] = (photo, text)

    def load(self, number):
        return self.saved.get(number)

    def mark_done(self, number):
        self.done.add(number)

    def is_done(self, number):
        return number in self.done


class FakeMemory(object):
    def __init__(self, index=None):
        self.last = index
        self.remembered = []

    def index(self):
        return self.last

    def remember(self, index):
        self.remembered.append(index)
        self.last = index


class WarmCameras(FakeCameras):
    """Cameras that can open the remembered camera's stream (headstart)."""

    def warm(self, indices, last_board):
        self.warmed = (list(indices), last_board)
        return indices[0] if indices else None


class WarmDescriber(FakeDescriber):
    def warm(self, model):
        self.warmed = model


class SelectingCameras(FakeCameras):
    """Selection stand-in: the first listed camera whose check passes is the board camera."""

    def select_board(self, indices, check, watch, last_board):
        out = _Outcome()
        for index in indices:
            photo = b'photo-%d' % index
            passes, body, label = check(index, photo)
            if passes:
                out.ok, out.index, out.photo, out.body = True, index, photo, body
                return out
            out.reasons.append('camera %d: %s' % (index, label))
        return out


class _Outcome(object):
    def __init__(self):
        self.ok, self.index, self.photo, self.body = False, None, None, ''
        self.reasons = []
        self.rejected = []


class SnapshotNameTests(unittest.TestCase):

    def name(self, requested_by):
        return ww.snapshot_name('0007', requested_by, time.mktime((2026, 10, 28, 12, 0, 0, 0, 0, -1)))

    def test_name_is_the_first_six_letters_with_capital_and_the_date(self):
        self.assertEqual(self.name('nils'), 'WBC_SNAP_0007_Nils_20261028.jpg')
        self.assertEqual(self.name('Christian'), 'WBC_SNAP_0007_Christ_20261028.jpg')

    def test_only_letters_and_digits_count(self):
        self.assertEqual(self.name('mary ann'), 'WBC_SNAP_0007_Maryan_20261028.jpg')

    def test_noname_when_nothing_is_left(self):
        self.assertEqual(self.name('Noname'), 'WBC_SNAP_0007_Noname_20261028.jpg')
        self.assertEqual(self.name('!!'), 'WBC_SNAP_0007_Noname_20261028.jpg')


class SnapshotFlowTests(unittest.TestCase):

    def run_snapshot(self, request, cameras=None, describer=None):
        store = FakeStore({'request-0003.yaml': VALID + request})
        describer = describer or FakeDescriber()
        results = FakeResults()
        watch = Watch(machine='test-mac', clock=lambda: NOW)
        ww.process_pending(store, cameras or SelectingCameras([0]), describer, FakeMemory(None), watch,
                           results, NOW, SETTINGS)
        return store, describer, results

    def snapshot_path(self, name):
        return '/Snapshots/WBC_SNAP_0003_%s_%s.jpg' % (name, time.strftime('%Y%m%d', time.localtime(NOW)))

    def test_photo_is_saved_to_snapshots_and_the_description_is_saved_plus_name(self):
        store, describer, results = self.run_snapshot('request_type: snapshot\nrequested_by: Nils\n')
        path = self.snapshot_path('Nils')
        self.assertEqual(store.files[path], b'photo-0')
        self.assertEqual(store.text('/Descriptions/description-0003.md'), 'saved\n%s\n' % path.rsplit('/', 1)[1])
        self.assertTrue(store.text('/status.md').startswith('status: ok\n'))
        self.assertNotIn('/Images/image-0003.jpg', store.files)

    def test_no_description_text_is_written_or_sent_to_the_picture_file(self):
        store, describer, results = self.run_snapshot('request_type: snapshot\n')
        self.assertNotIn('HELLO', store.text('/Descriptions/description-0003.md'))
        self.assertIn(self.snapshot_path('Noname'), store.files)

    def test_no_board_camera_is_an_error_and_nothing_is_saved(self):
        store, describer, results = self.run_snapshot(
            'request_type: snapshot\n', cameras=SelectingCameras([0]),
            describer=FakeDescriber(default='whiteboard_visible: no\nboard_fill_percent: 0\nis_board_camera: no'))
        self.assertFalse([p for p in store.files if p.startswith('/Snapshots/')])
        self.assertIn('code: CAMERA_FAILED', store.text('/status.md'))

    def test_snapshot_upload_failure_is_an_image_error(self):
        store = FakeStore({'request-0003.yaml': VALID + 'request_type: snapshot\n'})
        store.fail_upload_on = '/Snapshots/'
        watch = Watch(machine='test-mac', clock=lambda: NOW)
        ww.process_pending(store, SelectingCameras([0]), FakeDescriber(), FakeMemory(None), watch,
                           FakeResults(), NOW, SETTINGS)
        self.assertIn('code: IMAGE_UPLOAD_FAILED', store.text('/status.md'))


class HeadstartTests(unittest.TestCase):

    def run_headstart(self, cameras, describer=None, memory=None):
        store = FakeStore({'request-0003.yaml': VALID + 'request_type: headstart\n'})
        describer = describer or WarmDescriber()
        memory = memory or FakeMemory(None)
        results = FakeResults()
        watch = Watch(machine='test-mac', clock=lambda: 1000.0)
        ww.process_pending(store, cameras, describer, memory, watch, results, NOW, SETTINGS)
        return store, describer

    def test_ready_when_a_stream_is_open_and_nothing_is_described_or_photographed(self):
        cameras = WarmCameras([0, 1])
        store, describer = self.run_headstart(cameras, memory=FakeMemory(1))
        self.assertEqual(store.text('/Descriptions/description-0003.md'), 'ready\n')
        self.assertEqual(cameras.warmed, ([0, 1], 1))
        self.assertEqual(cameras.captures, [])
        self.assertEqual(describer.calls, [])
        self.assertEqual(describer.warmed, 'haiku')
        self.assertTrue(store.text('/status.md').startswith('status: ok\n'))
        self.assertNotIn('/Images/image-0003.jpg', store.files)

    def test_no_board_camera_when_no_stream_opens(self):
        store, describer = self.run_headstart(FakeCameras([0]))
        self.assertEqual(store.text('/Descriptions/description-0003.md'), 'no board camera\n')
        self.assertIn('code: CAMERA_FAILED', store.text('/status.md'))
        self.assertEqual(describer.calls, [])


class ParseRequestTests(unittest.TestCase):

    def parse(self, text, number='0003'):
        return ww.parse_request(text, number, MODELS, 'haiku')

    def test_minimal_request_gets_default_model_type_and_name(self):
        self.assertEqual(self.parse(VALID), {'request': '0003', 'model': 'haiku',
                                             'request_type': 'interaction', 'requested_by': 'Noname'})

    def test_requested_by_is_kept_and_empty_means_noname(self):
        self.assertEqual(self.parse(VALID + 'requested_by: Nils\n')['requested_by'], 'Nils')
        self.assertEqual(self.parse(VALID + 'requested_by:\n')['requested_by'], 'Noname')
        self.assertEqual(self.parse(VALID + 'requested_by:   \n')['requested_by'], 'Noname')

    def test_request_type_is_interaction_headstart_or_snapshot(self):
        for kind in ('interaction', 'headstart', 'snapshot'):
            self.assertEqual(self.parse(VALID + 'request_type: %s\n' % kind)['request_type'], kind)
        with self.assertRaises(ww.RequestError):
            self.parse(VALID + 'request_type: photo\n')

    def test_scope_is_full_or_changes(self):
        self.assertEqual(self.parse(VALID + 'scope: changes\n')['scope'], 'changes')
        with self.assertRaises(ww.RequestError):
            self.parse(VALID + 'scope: some\n')

    def test_old_mode_is_read_as_scope_once(self):
        fields = self.parse(VALID + 'mode: snapshot\n')
        self.assertEqual(fields['scope'], 'full')
        self.assertEqual(fields['legacy_mode'], 'snapshot')
        self.assertNotIn('mode', fields)
        self.assertEqual(self.parse(VALID + 'mode: diff\n')['scope'], 'changes')

    def test_old_mode_with_scope_or_bad_value_is_rejected(self):
        with self.assertRaises(ww.RequestError):
            self.parse(VALID + 'mode: snapshot\nscope: full\n')
        with self.assertRaises(ww.RequestError):
            self.parse(VALID + 'mode: other\n')

    def test_all_fields_and_blank_and_comment_lines(self):
        text = ('# note\n\nrequest: "0003"\nmarker_color: red\n'
                "region_v: 'top'\nregion_h: left\nscope: full\n")
        fields = self.parse(text)
        self.assertEqual(fields['marker_color'], 'red')
        self.assertEqual(fields['region_v'], 'top')
        self.assertEqual(fields['region_h'], 'left')
        self.assertEqual(fields['scope'], 'full')

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
            self.parse('scope: full\n')

    def test_duplicate_field_rejected(self):
        with self.assertRaises(ww.RequestError):
            self.parse(VALID + 'scope: full\nscope: changes\n')

    def test_line_that_is_not_name_value_rejected(self):
        for bad in ['- red\n', 'marker_color:\n', 'nested:\n  a: b\n']:
            with self.assertRaises(ww.RequestError):
                self.parse(VALID + bad)


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

    def run_one(self, store, cameras=None, describer=None, memory=None, settings=SETTINGS,
                results=None):
        cameras = cameras or FakeCameras()
        describer = describer or FakeDescriber()
        memory = memory or FakeMemory()
        watch = Watch(machine='test-mac', clock=lambda: 1000.0)
        results = results if results is not None else FakeResults()
        handled = ww.process_pending(store, cameras, describer, memory, watch, results, NOW, settings)
        self.watch = watch
        self.results = results
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
        self.assertEqual(desc.split('\n')[1], 'status: ok')
        self.assertNotIn('whiteboard:', desc)
        self.assertIn('HELLO', desc)
        self.assertEqual(memory.remembered, [1])

    def test_normal_order_is_description_then_image_then_status(self):
        store = FakeStore({'request-0003.yaml': VALID})
        self.run_one(store)
        moved = [dst for kind, dst in store.events if kind == 'move']
        self.assertEqual(moved, ['/Descriptions/description-0003.md', '/Images/image-0003.jpg'])
        self.assertTrue(store.text('/status.md').startswith('status: ok\n'))
        self.assertIn('description delivered: yes\nimage saved: yes\n', store.text('/status.md'))
        self.assertIn('0003', self.results.done)

    def test_remembered_wrong_then_second_camera_works(self):
        store = FakeStore({'request-0003.yaml': VALID})
        describer = FakeDescriber(answers={b'photo-1': 'whiteboard_visible: no\nboard_fill_percent: 0\nis_board_camera: no\nroom'})
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
        self.run_one(store, cameras, FakeDescriber(default='whiteboard_visible: no\nboard_fill_percent: 0\nis_board_camera: no\nroom'))
        self.assertFalse(store.exists('/Images/image-0003.jpg'))
        desc = self.description(store)
        self.assertTrue(desc.startswith('status: error\n'))
        self.assertIn('reason: camera 0: dark, closed lid (mean 2)', desc)
        self.assertIn('reason: camera 1: no frame', desc)
        self.assertEqual(sum(1 for p in store.files if p.startswith('/Descriptions/')), 1)

    def test_not_a_whiteboard_on_every_camera_is_an_error_without_image(self):
        store = FakeStore({'request-0003.yaml': VALID})
        self.run_one(store, FakeCameras([0, 1]), FakeDescriber(default='whiteboard_visible: no\nboard_fill_percent: 0\nis_board_camera: no'))
        self.assertFalse(store.exists('/Images/image-0003.jpg'))
        self.assertIn('reason: camera 0: not a whiteboard', self.description(store))

    def test_describe_without_whiteboard_line_counts_as_failure(self):
        store = FakeStore({'request-0003.yaml': VALID})
        self.run_one(store, FakeCameras([0]), FakeDescriber(default='a whiteboard with text'))
        desc = self.description(store)
        self.assertIn('status: error', desc)
        self.assertIn('describe: answer has no whiteboard_visible line', desc)

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
            if kind == 'upload' and path != '/status.md':  # status.md is replaced in one upload
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

    def test_scope_changes_is_described_as_full_with_note(self):
        store = FakeStore({'request-0003.yaml': VALID + 'scope: changes\n'})
        self.run_one(store)
        desc = self.description(store)
        self.assertIn('status: ok', desc)
        self.assertIn('scope changes is not supported yet', desc)

    def test_old_mode_gets_one_note_and_is_not_in_the_fields_line(self):
        store = FakeStore({'request-0003.yaml': VALID + 'mode: diff\n'})
        self.run_one(store)
        desc = self.description(store)
        self.assertEqual(desc.count('field mode is replaced by scope'), 1)
        self.assertNotIn('legacy_mode', desc)

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
        handled = ww.process_pending(store, cameras, FakeDescriber(), FakeMemory(), watch, FakeResults(), NOW, SETTINGS)
        self.assertEqual(handled, ['0004'])

    def test_network_error_on_listing_requests_does_not_raise(self):
        store = FakeStore({'request-0003.yaml': VALID})

        def down(folder):
            raise OSError('no connection to Dropbox (timeout)')
        store.list_names = down
        cameras = FakeCameras([0])
        watch = Watch(machine='test-mac', clock=lambda: 1000.0)
        handled = ww.process_pending(store, cameras, FakeDescriber(), FakeMemory(), watch, FakeResults(), NOW, SETTINGS)
        self.assertEqual(handled, [])
        self.assertEqual(cameras.captures, [])

    def test_other_camera_error_is_not_retried(self):
        store = FakeStore({'request-0003.yaml': VALID})
        cameras = FakeCameras([0, 1], plan={0: 'no frame'})
        _, cameras, _, _ = self.run_one(store, cameras)
        self.assertEqual(cameras.captures, [0, 1])


class OrderAndStatusTests(unittest.TestCase):

    def run_pass(self, store, cameras=None, describer=None, results=None):
        cameras = cameras or FakeCameras()
        describer = describer or FakeDescriber()
        results = results if results is not None else FakeResults()
        watch = Watch(machine='test-mac', clock=lambda: 1000.0)
        ww.process_pending(store, cameras, describer, FakeMemory(), watch, results, NOW, SETTINGS)
        return cameras, describer, results

    def status(self, store):
        return store.text('/status.md')

    def test_status_is_written_last_with_code_on_error(self):
        store = FakeStore({'request-0003.yaml': VALID})
        self.run_pass(store, FakeCameras([0], plan={0: 'no frame'}))
        text = self.status(store)
        self.assertEqual(text.splitlines()[0], 'status: error')
        self.assertIn('last request: 0003', text)
        self.assertIn('code: CAMERA_FAILED', text)
        self.assertIn('description delivered: yes', text)
        self.assertIn('image saved: no', text)

    def test_describe_failure_status_code(self):
        store = FakeStore({'request-0003.yaml': VALID})
        self.run_pass(store, FakeCameras([0]), FakeDescriber(default='whiteboard_visible: no\nboard_fill_percent: 0\nis_board_camera: no'))
        self.assertIn('code: DESCRIBE_FAILED', self.status(store))

    def test_crash_after_describe_is_unknown_error_and_never_described_twice(self):
        store = FakeStore({'request-0003.yaml': VALID})
        store.raise_on = {'/Descriptions/': ValueError('boom')}
        cameras, describer, results = self.run_pass(store)
        self.assertIn('code: UNKNOWN_ERROR', self.status(store))
        self.assertIn('0003', results.done)
        cameras2, describer2, _ = self.run_pass(store, results=results)
        self.assertEqual(cameras2.captures, [])
        self.assertEqual(describer2.calls, [])

    def test_restart_after_describe_uploads_description_from_local_copy_no_new_photo(self):
        store = FakeStore({'request-0003.yaml': VALID})
        results = FakeResults({'0003': (b'saved-photo', 'status: ok\nrequest: "0003"\n\nbody\n')})
        cameras, describer, results = self.run_pass(store, results=results)
        self.assertEqual(cameras.captures, [])
        self.assertEqual(describer.calls, [])
        self.assertTrue(store.exists('/Descriptions/description-0003.md'))
        self.assertEqual(store.files['/Images/image-0003.jpg'], b'saved-photo')
        self.assertIn('status: ok', self.status(store))

    def test_crash_after_description_upload_retries_only_the_image_once(self):
        store = FakeStore({'request-0003.yaml': VALID})
        store.raise_on = {'/Images/': ValueError('boom')}
        cameras, describer, results = self.run_pass(store)
        self.assertIn('code: UNKNOWN_ERROR', self.status(store))
        self.assertTrue(store.exists('/Descriptions/description-0003.md'))
        self.assertIsNotNone(results.load('0003')[0])
        store.raise_on = {}
        cameras2, describer2, _ = self.run_pass(store, results=results)
        self.assertEqual(cameras2.captures, [])
        self.assertEqual(describer2.calls, [])

    def test_image_upload_failing_twice_gives_image_error_and_keeps_local_photo(self):
        store = FakeStore({'request-0003.yaml': VALID})
        store.fail_upload_on = '/Images/'
        cameras, describer, results = self.run_pass(store)
        self.assertEqual(describer.calls.__len__(), 1)
        self.assertFalse(store.exists('/Images/image-0003.jpg'))
        self.assertTrue(store.exists('/Descriptions/description-0003.md'))
        self.assertIsNotNone(results.load('0003')[0])
        text = self.status(store)
        self.assertIn('code: IMAGE_UPLOAD_FAILED', text)
        self.assertIn('description delivered: yes', text)
        self.assertIn('0003', results.done)

    def test_image_retry_on_restart_failing_gives_image_error(self):
        store = FakeStore({'request-0003.yaml': VALID})
        store.files['/Descriptions/description-0003.md'] = b'status: ok\n'
        results = FakeResults({'0003': (b'saved-photo', 'text')})
        store.fail_upload_on = '/Images/'
        self.run_pass(store, results=results)
        self.assertFalse(store.exists('/Images/image-0003.jpg'))
        self.assertIn('code: IMAGE_UPLOAD_FAILED', self.status(store))
        self.assertIn('0003', results.done)

    def test_description_upload_failure_keeps_local_copy_and_retries_later_without_photo(self):
        store = FakeStore({'request-0003.yaml': VALID})
        store.fail_upload_on = '/Descriptions/'
        cameras, describer, results = self.run_pass(store)
        self.assertIn('code: DESCRIPTION_UPLOAD_FAILED', self.status(store))
        self.assertNotIn('0003', results.done)
        self.assertEqual(len(describer.calls), 1)
        store.fail_upload_on = None
        cameras2, describer2, _ = self.run_pass(store, results=results)
        self.assertEqual(describer2.calls, [])
        self.assertEqual(cameras2.captures, [])
        self.assertTrue(store.exists('/Descriptions/description-0003.md'))
        self.assertTrue(store.exists('/Images/image-0003.jpg'))
        self.assertIn('status: ok', self.status(store))

    def test_unexpected_exception_in_describe_is_unknown_error(self):
        class Broken(object):
            def describe(self, photo, fields):
                raise RuntimeError('bad state')
        store = FakeStore({'request-0003.yaml': VALID})
        self.run_pass(store, describer=Broken())
        text = self.status(store)
        self.assertIn('code: UNKNOWN_ERROR', text)
        self.assertIn('RuntimeError', text)

    def test_old_order_image_without_description_is_unknown_error(self):
        store = FakeStore({'request-0003.yaml': VALID})
        store.files['/Images/image-0003.jpg'] = b'old'
        cameras, describer, _ = self.run_pass(store)
        self.assertEqual(cameras.captures, [])
        self.assertIn('code: UNKNOWN_ERROR', self.status(store))
        self.assertIn('reason: interrupted before the description was written',
                      store.text('/Descriptions/description-0003.md'))

    def test_status_is_replaced_when_an_older_status_exists(self):
        store = FakeStore({'request-0003.yaml': VALID})
        store.files['/status.md'] = b'status: error\nlast request: 0002\n'
        self.run_pass(store)
        self.assertIn('last request: 0003', self.status(store))
        self.assertTrue(self.status(store).startswith('status: ok\n'))

    def test_complete_older_request_is_marked_done_without_a_status(self):
        store = FakeStore({'request-0003.yaml': VALID})
        store.files['/Descriptions/description-0003.md'] = b'status: ok\n'
        store.files['/Images/image-0003.jpg'] = b'old'
        cameras, describer, results = self.run_pass(store)
        self.assertIn('0003', results.done)
        self.assertFalse(store.exists('/status.md'))
        self.assertEqual(cameras.captures, [])

    def test_status_first_line_is_exact_and_no_notification_is_sent(self):
        store = FakeStore({'request-0003.yaml': VALID})
        self.run_pass(store)
        self.assertEqual(self.status(store).splitlines()[0], 'status: ok')
        self.assertEqual(sorted(p for p in store.files if not p.startswith(('/Requests', '/Descriptions', '/Images', '/status'))), [])


class BoardFillFlowTests(ProcessTests):

    def test_low_fill_is_refused_and_next_camera_used(self):
        store = FakeStore({'request-0003.yaml': VALID})
        describer = FakeDescriber(answers={b'photo-0': 'whiteboard_visible: yes\nboard_fill_percent: 30\nis_board_camera: yes\n\nroom'},
                                  default='whiteboard_visible: yes\nboard_fill_percent: 90\nis_board_camera: yes\n\n## Text\nHELLO')
        settings = {'models': MODELS, 'default_model': 'haiku', 'min_board_fill_percent': 80}
        _, cameras, _, _ = self.run_one(store, FakeCameras([0, 1]), describer, settings=settings)
        self.assertEqual(cameras.captures, [0, 1])
        self.assertEqual(store.files['/Images/image-0003.jpg'], b'photo-1')
        self.assertIn('HELLO', self.description(store))
        self.assertNotIn('fill:', self.description(store))

    def test_missing_fill_with_check_on_fails_and_is_logged(self):
        store = FakeStore({'request-0003.yaml': VALID})
        describer = FakeDescriber(default='whiteboard_visible: yes\nis_board_camera: yes\n\nno fill line here')
        settings = {'models': MODELS, 'default_model': 'haiku', 'min_board_fill_percent': 80}
        with self.assertLogs('whiteboard', level='INFO') as logs:
            self.run_one(store, FakeCameras([0]), describer, settings=settings)
        self.assertIn('board fill missing', self.description(store))
        self.assertTrue(any('criteria: visible yes, fill None' in line for line in logs.output))

    def test_check_off_ignores_fill(self):
        store = FakeStore({'request-0003.yaml': VALID})
        describer = FakeDescriber(default='whiteboard_visible: yes\nboard_fill_percent: 5\nis_board_camera: yes\n\nHELLO')
        self.run_one(store, FakeCameras([0]), describer)
        self.assertIn('status: ok', self.description(store))


class FailedPhotoFlowTests(ProcessTests):

    def test_all_no_keeps_each_rejected_photo(self):
        import os
        import shutil
        import testroot
        folder = os.path.join(testroot.mkdtemp(), 'failed-photos')
        try:
            store = FakeStore({'request-0003.yaml': VALID})
            describer = FakeDescriber(default='whiteboard_visible: no\nboard_fill_percent: 0\nis_board_camera: no')
            settings = dict(SETTINGS, failed_photos_dir=folder, failed_photos_keep=5)
            self.run_one(store, FakeCameras([0, 1]), describer, settings=settings)
            self.assertEqual(sorted(os.listdir(folder)), ['request-0003-cam00.jpg', 'request-0003-cam01.jpg'])
            self.assertIn('status: error', self.description(store))
        finally:
            shutil.rmtree(os.path.dirname(folder))


if __name__ == '__main__':
    unittest.main()
