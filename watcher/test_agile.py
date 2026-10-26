"""Tests for agile mode phase 1 with a fake stream and a fake lean path. No camera.

Run: cd watcher && python3 -m unittest -v test_agile
"""

import os
import shutil
import subprocess
import unittest

import agile
import camera as cam
import testroot
from whiteboard_watcher import CameraError


class FakeProc(object):
    def __init__(self, cmd):
        self.cmd = cmd
        self.killed = False
        self.pid = 4242

    def poll(self):
        return 0 if self.killed else None

    def kill(self):
        self.killed = True

    def wait(self):
        return 0


class FakeLean(object):
    def __init__(self, photo=b'lean', fail=False):
        self.photo = photo
        self.fail = fail
        self.captures = []
        self.last = {}

    def list(self):
        return [(0, 'cam 0')]

    def capture(self, index):
        self.captures.append(index)
        if self.fail:
            raise CameraError('lean failed')
        return self.photo


class Harness(object):
    def __init__(self, folder, lean=None, brightness=120.0, write_frames=True):
        self.now = 1000.0
        self.procs = []
        self.write_frames = write_frames
        self.brightness = brightness
        self.lean = lean or FakeLean()
        self.folder = folder
        self.agile = agile.AgileCameras(folder, self.lean, 0, 20, 600, None,
                                        popen=self.popen, clock=lambda: self.now, run=self.run)

    def popen(self, cmd, **kwargs):
        proc = FakeProc(cmd)
        self.procs.append(proc)
        if self.write_frames:
            out = cmd[-1]
            with open(out, 'wb') as handle:
                handle.write(b'stream-frame')
        return proc

    def run(self, cmd, **kwargs):
        value = self.brightness
        return subprocess.CompletedProcess(cmd, 0, ('lavfi.signalstats.YAVG=%s\n' % value).encode(), b'')


class AgileTests(unittest.TestCase):

    def setUp(self):
        self.folder = testroot.mkdtemp()
        self.old_wait = agile.START_WAIT
        agile.START_WAIT = 0.2

    def tearDown(self):
        agile.START_WAIT = self.old_wait
        shutil.rmtree(self.folder)

    def test_request_wakes_the_stream_and_reads_the_newest_frame(self):
        h = Harness(self.folder)
        self.assertEqual(h.agile.capture(0), b'stream-frame')
        self.assertEqual(len(h.procs), 1)
        self.assertEqual(h.lean.captures, [])

    def test_second_request_reuses_the_open_stream(self):
        h = Harness(self.folder)
        h.agile.capture(0)
        h.agile.capture(0)
        self.assertEqual(len(h.procs), 1)

    def test_idle_timeout_closes_the_stream(self):
        h = Harness(self.folder)
        h.agile.capture(0)
        h.now += 599
        h.agile.tick()
        self.assertFalse(h.procs[0].killed)
        h.now += 2
        h.agile.tick()
        self.assertTrue(h.procs[0].killed)
        self.assertFalse(os.path.exists(os.path.join(self.folder, 'agile.pid')))

    def test_only_reset_events_move_the_timer(self):
        h = Harness(self.folder)
        h.agile.capture(0)
        h.now += 500
        h.agile.note_event('other')          # not a reset event: no effect
        h.now += 200
        h.agile.tick()
        self.assertTrue(h.procs[0].killed)

    def test_request_event_resets_the_timer(self):
        h = Harness(self.folder)
        h.agile.capture(0)
        h.now += 500
        h.agile.note_event('request')
        h.now += 500
        h.agile.tick()
        self.assertFalse(h.procs[0].killed)

    def test_no_fresh_frame_falls_back_to_lean_once_and_restarts_the_stream(self):
        h = Harness(self.folder, write_frames=False)
        self.assertEqual(h.agile.capture(0), b'lean')
        self.assertEqual(h.lean.captures, [0])
        self.assertEqual(len(h.procs), 2)     # the failed stream, then a new one after the lean success

    def test_lean_fallback_failure_propagates(self):
        h = Harness(self.folder, lean=FakeLean(fail=True), write_frames=False)
        with self.assertRaises(CameraError):
            h.agile.capture(0)

    def test_dark_stream_frame_is_not_replaced_by_the_lean_path(self):
        h = Harness(self.folder, brightness=1.0)
        with self.assertRaises(cam.DarkFrameError):
            h.agile.capture(0)
        self.assertEqual(h.lean.captures, [])

    def test_list_is_the_lean_list(self):
        h = Harness(self.folder)
        self.assertEqual(h.agile.list(), [(0, 'cam 0')])

    def test_close_releases_the_camera(self):
        h = Harness(self.folder)
        h.agile.capture(0)
        h.agile.close()
        self.assertTrue(h.procs[0].killed)

    def test_orphan_stream_from_an_earlier_run_is_cleaned_up(self):
        pidfile = os.path.join(self.folder, 'agile.pid')
        with open(pidfile, 'w') as handle:
            handle.write('999999\n')           # no such process: only the file is removed
        Harness(self.folder)
        self.assertFalse(os.path.exists(pidfile))


if __name__ == '__main__':
    unittest.main()
