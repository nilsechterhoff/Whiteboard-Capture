"""Agile mode, phase 1: the camera stays open while Nils brainstorms.

A request takes the newest frame from the open stream. A request wakes the stream up if it
is closed. Idle for agile_idle_timeout_seconds (only reset events count) closes it. Any failure
closes the stream and runs that request once through the lean path; a successful lean run
starts a new stream. The stream's pid is kept in a file, so a restart cleans up an orphan.

Standard library only, Python 3.9.
"""

import os
import subprocess
import time

import logging

import camera as cam
from whiteboard_watcher import CameraError, DarkFrameError

LOG = logging.getLogger('whiteboard')

START_WAIT = 6.0  # seconds to wait for the first frame after a wake-up


class AgileCameras(object):

    def __init__(self, folder, lean, rotation_degrees=0, dark_below=cam.DARK_BELOW,
                 idle_timeout=600, reset_events=None, popen=subprocess.Popen, clock=time.time,
                 run=subprocess.run):
        self.folder = folder
        self.lean = lean            # the lean path: a cam.Cameras object (list, capture)
        self.rotation_degrees = rotation_degrees
        self.dark_below = dark_below
        self.idle_timeout = idle_timeout
        self.reset_events = reset_events or {'request': 'yes'}
        self.popen = popen
        self.clock = clock
        self.run = run
        self.proc = None
        self.index = None
        self.path = None
        self.last_event = None
        self.last = {}
        self.pidfile = os.path.join(folder, 'agile.pid')
        self._kill_orphan()

    # listing is the same as the lean path
    def list(self):
        return self.lean.list()

    def capture(self, index):
        try:
            if self.proc is None or self.index != index or self.proc.poll() is not None:
                LOG.info('agile: stream started for camera %d (wake-up)' % index)
                self._start(index)
                self._wait_for_first_frame()
            else:
                LOG.info('agile: reused open stream for camera %d' % index)
            photo, brightness = cam.get_newest_frame(self.path, self.clock(), dark_below=self.dark_below,
                                                     run=self.run)
            self.last = {'brightness': brightness}
            return photo
        except DarkFrameError:
            raise
        except CameraError as err:
            LOG.info('agile: check failed (%s); lean path once' % err)
            self._stop()
            photo = self.lean.capture(index)      # fallback: the lean path, once
            self.last = dict(getattr(self.lean, 'last', {}))
            self._start(index)                    # a successful lean run starts a new stream
            return photo

    def note_event(self, name):
        if self.reset_events.get(name) == 'yes':
            self.last_event = self.clock()

    def tick(self):
        """Called from the main loop: close the stream after the idle timeout."""
        if self.proc is None:
            return
        if self.last_event is not None and self.clock() - self.last_event > self.idle_timeout:
            self._stop()

    def close(self):
        self._stop()

    def _start(self, index):
        self._stop()
        cmd, path = cam.stream_command(index, self.folder, self.rotation_degrees)
        try:
            os.remove(path)            # never answer from an old frame
        except OSError:
            pass
        self.proc = self.popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.index, self.path = index, path
        self.last_event = self.clock()
        with open(self.pidfile, 'w') as handle:
            handle.write('%d\n' % self.proc.pid)

    def _wait_for_first_frame(self):
        deadline = time.time() + START_WAIT
        while time.time() < deadline:
            if os.path.exists(self.path):
                return
            time.sleep(0.1)
        raise CameraError('the open stream gave no frame in %d s' % START_WAIT)

    def _stop(self):
        if self.proc is not None:
            if self.proc.poll() is None:
                self.proc.kill()
                self.proc.wait()
            self.proc = None
        for path in (self.path,):
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass
        self.index = self.path = None
        try:
            os.remove(self.pidfile)
        except OSError:
            pass

    def _kill_orphan(self):
        """A stream left by an earlier service instance (if it is still an ffmpeg process) is stopped."""
        try:
            with open(self.pidfile) as handle:
                pid = int(handle.read().strip())
        except (OSError, ValueError):
            return
        try:
            comm = subprocess.run(['ps', '-p', str(pid), '-o', 'comm='], stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE).stdout.decode().strip()
            if 'ffmpeg' in comm:
                os.kill(pid, 9)
        except OSError:
            pass
        try:
            os.remove(self.pidfile)
        except OSError:
            pass
