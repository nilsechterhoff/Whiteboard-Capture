"""Tests for parallel camera selection (ADR-0012) with fake streams, a fake clock and a fake ffmpeg.

No camera, no network, no sleeping: the fake clock advances when the code sleeps.
Run: cd watcher && python3 -m unittest -v test_selection
"""

import os
import shutil
import subprocess
import unittest

import selection
import testroot
import whiteboard_watcher as ww
from stopwatch import Watch
from test_whiteboard_watcher import FakeDescriber, FakeMemory, FakeResults, FakeStore, NOW, VALID, YES

SETTINGS = {'models': {'haiku': 'claude-haiku-5-5'}, 'default_model': 'haiku',
            'min_board_fill_percent': 0, 'failed_photos_keep': 0}


class FakeClock(object):
    def __init__(self):
        self.now = 1000.0
        self.sleeps = []
        self.at = []            # (time, path): a stream frame that is written at that time

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds
        for due, path in list(self.at):
            if due <= self.now:
                _write_frame(path)
                self.at.remove((due, path))


class FakeProc(object):
    def __init__(self, cmd, started):
        self.cmd = cmd
        self.started = started
        self.pid = 4000 + len(cmd)
        self.killed = False

    def poll(self):
        return 0 if self.killed else None

    def kill(self):
        self.killed = True

    def wait(self):
        return 0


class FakePopen(object):
    """Starts a fake stream: writes one frame at once, like ffmpeg does with -update."""

    def __init__(self, clock, fail=False, late=0.0):
        self.clock = clock
        self.fail = fail
        self.late = late
        self.procs = []

    def __call__(self, cmd, **kwargs):
        if self.fail:
            raise OSError('ffmpeg not found')
        proc = FakeProc(cmd, self.clock())
        if self.late:
            self.clock.at.append((self.clock() + self.late, cmd[-1]))
        else:
            _write_frame(cmd[-1])
        self.procs.append(proc)
        return proc


def _write_frame(path):
    with open(path, 'wb') as handle:
        handle.write(b'stream-frame')


class FakeRun(object):
    """Answers the two ffmpeg uses: brightness (signalstats) and the grayscale copy for sharpness."""

    def __init__(self, dark=()):
        self.dark = set(dark)   # basenames of stream files that are dark

    def __call__(self, cmd, **kwargs):
        if 'rawvideo' in cmd:
            return subprocess.CompletedProcess(cmd, 0, b'\x80' * (selection.SHARP_WIDTH * selection.SHARP_HEIGHT), b'')
        path = cmd[cmd.index('-i') + 1]
        value = 1.0 if os.path.basename(path) in self.dark else 120.0
        return subprocess.CompletedProcess(cmd, 0, ('lavfi.signalstats.YAVG=%s\n' % value).encode(), b'')


class FakeLean(object):
    def __init__(self, indices=(0, 1)):
        self.indices = list(indices)
        self.captures = []
        self.last = {}

    def list(self):
        return [(i, 'cam %d' % i) for i in self.indices]

    def capture(self, index):
        self.captures.append(index)
        return b'lean-%d' % index


class Harness(object):
    def __init__(self, folder, indices=(0, 1), dark=(), plan=None, retries=2, fail_popen=False,
                 idle_timeout=600, late=0.0):
        self.clock = FakeClock()
        self.popen = FakePopen(self.clock, fail=fail_popen, late=late)
        self.run = FakeRun(dark)
        self.lean = FakeLean(indices)
        self.plan = {k: list(v) for k, v in (plan or {}).items()}
        self.checks = []        # (index, clock time) of every board check
        self.watch = Watch(machine='test-mac', clock=self.clock)
        self.cameras = selection.ParallelCameras(
            folder, self.lean, 0, 20, idle_timeout, {'request': 'yes'}, 0.1, 2.0, 1.0, retries, 2,
            popen=self.popen, clock=self.clock, sleep=self.clock.sleep, run=self.run)

    def check(self, index, photo):
        self.checks.append((index, self.clock()))
        result = self.plan.get(index, ['reject']).pop(0) if self.plan.get(index) else 'reject'
        if result == 'ERR':
            raise ww.DescribeError('boom')
        if result == 'pass':
            return True, 'HELLO', 'ok'
        return False, '', 'not a whiteboard'

    def select(self, last_board=None):
        return self.cameras.select_board([i for i, _ in self.cameras.list()], self.check, self.watch, last_board)


class CheckOrderTests(unittest.TestCase):

    def test_two_cameras_other_index_first_when_the_board_was_last_on_one(self):
        self.assertEqual(selection.check_order([0, 1], 0), [1, 0])
        self.assertEqual(selection.check_order([0, 1], 1), [0, 1])

    def test_two_cameras_without_memory_last_index_first(self):
        self.assertEqual(selection.check_order([0, 1], None), [1, 0])

    def test_remembered_index_not_listed_last_index_first(self):
        self.assertEqual(selection.check_order([0, 1], 7), [1, 0])

    def test_three_cameras_last_index_first_rest_in_listing_order(self):
        self.assertEqual(selection.check_order([0, 1, 2], 0), [2, 0, 1])

    def test_one_camera_and_none(self):
        self.assertEqual(selection.check_order([3], 3), [3])
        self.assertEqual(selection.check_order([], None), [])


class LaplacianTests(unittest.TestCase):

    def test_flat_image_has_no_variance(self):
        self.assertEqual(selection.laplacian_variance(b'\x80' * 25, 5, 5), 0)

    def test_hard_edges_score_higher_than_a_smooth_ramp(self):
        hard = bytes([0, 255, 0, 255] * 4)     # alternating columns: strong edges everywhere
        smooth = bytes([100, 110, 120, 130] * 4)
        self.assertGreater(selection.laplacian_variance(hard, 4, 4),
                           selection.laplacian_variance(smooth, 4, 4))


class SelectionTests(unittest.TestCase):

    def setUp(self):
        self.folder = testroot.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.folder)

    def test_streams_start_one_offset_apart_in_listing_order(self):
        h = Harness(self.folder, plan={1: ['pass']})
        h.select()
        starts = [p.started for p in h.popen.procs]
        self.assertAlmostEqual(starts[1] - starts[0], 0.1, places=9)
        self.assertIn('0:none', h.popen.procs[0].cmd)
        self.assertIn('1:none', h.popen.procs[1].cmd)

    def test_first_check_waits_for_the_frame_delay_after_its_own_start(self):
        h = Harness(self.folder, plan={1: ['pass']})
        h.select()
        index, when = h.checks[0]
        self.assertEqual(index, 1)                      # no memory: the last index goes first
        self.assertAlmostEqual(when, h.popen.procs[1].started + 2.0, places=9)

    def test_first_board_frame_wins_and_the_other_stream_closes_at_once(self):
        h = Harness(self.folder, plan={1: ['pass']})
        out = h.select()
        self.assertTrue(out.ok)
        self.assertEqual(out.index, 1)
        self.assertEqual(out.body, 'HELLO')
        self.assertEqual(out.photo, b'stream-frame')
        self.assertTrue(h.popen.procs[0].killed)
        self.assertFalse(h.popen.procs[1].killed)
        self.assertEqual(len(h.checks), 1)              # camera 0 was never checked
        self.assertEqual(h.cameras.open_index, 1)

    def test_guess_right_is_logged(self):
        h = Harness(self.folder, plan={1: ['pass']})
        with self.assertLogs('whiteboard', 'INFO') as logs:
            h.select()
        self.assertTrue(any('guess 1 was right' in line for line in logs.output))

    def test_second_camera_wins_and_the_guess_is_logged_wrong(self):
        h = Harness(self.folder, plan={1: ['reject'], 0: ['pass']})
        with self.assertLogs('whiteboard', 'INFO') as logs:
            out = h.select()
        self.assertTrue(out.ok)
        self.assertEqual(out.index, 0)
        self.assertEqual([i for i, _ in out.rejected], [1])
        self.assertTrue(any('guess 1 was wrong' in line for line in logs.output))

    def test_dark_frame_is_skipped_without_a_describe_call(self):
        h = Harness(self.folder, dark=('agile-1.jpg',), plan={0: ['pass']})
        out = h.select()
        self.assertTrue(out.ok)
        self.assertEqual(out.index, 0)
        self.assertEqual([i for i, _ in h.checks], [0])
        self.assertIn('camera 1: dark', out.reasons)

    def test_frame_that_comes_late_is_waited_for(self):
        h = Harness(self.folder, plan={1: ['pass']}, late=2.5)
        out = h.select()
        self.assertTrue(out.ok)
        self.assertEqual(out.index, 1)
        index, when = h.checks[0]
        self.assertGreaterEqual(when, h.popen.procs[1].started + 2.5)   # the check waited for the frame

    def test_sharpness_of_each_selection_frame_is_logged(self):
        h = Harness(self.folder, plan={1: ['pass']})
        with self.assertLogs('whiteboard', 'INFO') as logs:
            h.select()
        self.assertTrue(any('sharpness 0.0' in line for line in logs.output))

    def test_retry_runs_a_new_selection_after_the_pause(self):
        h = Harness(self.folder, plan={1: ['reject', 'reject'], 0: ['reject', 'pass']})
        out = h.select()
        self.assertTrue(out.ok)
        self.assertEqual(out.index, 0)
        self.assertEqual(len(h.popen.procs), 4)         # two streams per selection
        self.assertIn(1.0, h.clock.sleeps)              # retry_pause_seconds

    def test_no_board_frame_after_all_retries_is_an_error_with_a_line_per_frame(self):
        h = Harness(self.folder, plan={0: ['reject'] * 3, 1: ['reject'] * 3}, retries=2)
        out = h.select()
        self.assertFalse(out.ok)
        self.assertTrue(out.described)
        self.assertEqual(len(out.rejected), 6)          # 2 cameras, 3 selections
        self.assertEqual(len(out.reasons), 6)
        self.assertTrue(all(p.killed for p in h.popen.procs))
        self.assertIsNone(h.cameras.open_index)

    def test_describe_error_counts_as_a_failed_frame(self):
        h = Harness(self.folder, plan={1: ['ERR'], 0: ['pass']})
        out = h.select()
        self.assertTrue(out.ok)
        self.assertIn('camera 1: describe error: boom', out.reasons)

    def test_open_stream_is_reused_for_the_next_request(self):
        h = Harness(self.folder, plan={1: ['pass', 'pass']})
        h.select()
        out = h.select()
        self.assertTrue(out.ok)
        self.assertEqual(out.index, 1)
        self.assertEqual(len(h.popen.procs), 2)         # no new streams
        self.assertEqual(len(h.checks), 2)

    def test_open_stream_failing_the_check_closes_and_selects_again(self):
        h = Harness(self.folder, plan={1: ['pass', 'reject', 'pass']})
        h.select()
        out = h.select()
        self.assertTrue(out.ok)
        self.assertEqual(len(h.popen.procs), 4)         # the old pair closed, a new pair started
        self.assertTrue(h.popen.procs[1].killed)

    def test_idle_timeout_closes_the_streams(self):
        h = Harness(self.folder, plan={1: ['pass']}, idle_timeout=600)
        h.select()
        h.cameras.note_event('request')
        h.clock.now += 599
        h.cameras.tick()
        self.assertFalse(h.popen.procs[1].killed)
        h.clock.now += 2
        h.cameras.tick()
        self.assertTrue(h.popen.procs[1].killed)

    def test_streams_that_cannot_start_raise_oserror_for_the_lean_fallback(self):
        h = Harness(self.folder, fail_popen=True)
        with self.assertRaises(OSError):
            h.select()

    def test_capture_is_the_lean_path(self):
        h = Harness(self.folder)
        self.assertEqual(h.cameras.capture(1), b'lean-1')
        self.assertEqual(h.lean.captures, [1])

    def test_pidfile_lists_the_streams_and_is_removed_on_close(self):
        h = Harness(self.folder, plan={1: ['pass']})
        h.select()
        pidfile = os.path.join(self.folder, 'streams.pid')
        self.assertTrue(os.path.exists(pidfile))
        h.cameras.close()
        self.assertFalse(os.path.exists(pidfile))


class RequestFlowTests(unittest.TestCase):
    """The request path: handle_request uses the selection when the cameras offer it."""

    def setUp(self):
        self.folder = testroot.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.folder)

    def run_request(self, harness, answer=YES):
        store = FakeStore({'request-0003.yaml': VALID})
        describer = FakeDescriber(default=answer)
        memory = FakeMemory(None)
        results = FakeResults()
        ww.process_pending(store, harness.cameras, describer, memory, harness.watch, results, NOW, SETTINGS)
        return store, describer, memory

    def test_request_uses_the_board_camera_and_its_frame(self):
        h = Harness(self.folder, plan={1: ['pass']})
        store, describer, memory = self.run_request(h)
        self.assertEqual(store.text('/Descriptions/description-0003.md').split('\n')[1], 'status: ok')
        self.assertEqual(store.files['/Images/image-0003.jpg'], b'stream-frame')
        self.assertEqual(memory.remembered, [1])
        self.assertEqual(h.lean.captures, [])

    def test_streams_that_cannot_start_use_the_lean_path_once(self):
        h = Harness(self.folder, fail_popen=True)
        store, describer, memory = self.run_request(h)
        self.assertEqual(store.files['/Images/image-0003.jpg'], b'lean-0')
        self.assertEqual(h.lean.captures, [0])

    def test_no_board_frame_writes_an_error_and_keeps_the_rejected_photos(self):
        h = Harness(self.folder, retries=2)
        store, describer, memory = self.run_request(h, answer='whiteboard_visible: no\nboard_fill_percent: 0\nis_board_camera: no')
        self.assertEqual(len(describer.calls), 6)       # 2 cameras, 3 selections
        self.assertTrue(store.text('/Descriptions/description-0003.md').startswith('status: error\n'))
        self.assertNotIn('/Images/image-0003.jpg', store.files)
        self.assertEqual(memory.remembered, [])


class JpegQualityTests(unittest.TestCase):

    def setUp(self):
        self.folder = testroot.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.folder)

    def test_every_stream_gets_the_quality_flag(self):
        h = Harness(self.folder, plan={1: ['pass']})
        h.select()
        for proc in h.popen.procs:
            self.assertEqual(proc.cmd[proc.cmd.index('-q:v') + 1], '2')

if __name__ == '__main__':
    unittest.main()
