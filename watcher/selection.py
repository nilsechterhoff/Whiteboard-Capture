"""Parallel camera selection (ADR-0012): one stream per camera, the first board frame wins.

At stream start every matching camera gets its own ffmpeg stream, each one start_offset
seconds after the previous one (the lab showed that two starts at the same instant often
land on the same camera). Each stream is checked once selection_frame_delay seconds after
its own start, so autofocus and exposure have settled. Frames are checked in check_order;
the first board frame wins, the other streams close at once. A request reads the newest
frame of the open stream; if that fails the check, the streams are closed and selection
runs again, at most `retries` times.

The lean path (one ffmpeg per index, one frame) stays as the fall back when the streams
cannot start at all. Standard library only, Python 3.9.
"""

import logging
import os
import subprocess
import time

import camera as cam
from whiteboard_watcher import CameraError, DarkFrameError, DescribeError

LOG = logging.getLogger('whiteboard')
FRAME_MAX_AGE = 3.0          # seconds: an older stream frame counts as no frame
FRAME_WAIT = 6.0             # seconds: the first frame may come 2 to 4 s after the start (h17)
SHARP_WIDTH = 480            # the sharpness score is taken on a 480 x 270 grayscale copy
SHARP_HEIGHT = 270


def check_order(indices, last_board):
    """The order in which the streams are checked.

    With exactly two cameras and the board last seen on one of them, the other one goes
    first. Otherwise the last index in the listing goes first; the rest keep listing order.
    """
    indices = list(indices)
    if not indices:
        return []
    if len(indices) == 2 and last_board in indices:
        return [i for i in indices if i != last_board] + [last_board]
    return [indices[-1]] + indices[:-1]


def laplacian_variance(gray, width, height):
    """Variance of the 3x3 Laplacian of a grayscale image (raw bytes, row by row)."""
    total = 0
    squares = 0
    count = 0
    for y in range(1, height - 1):
        up = gray[(y - 1) * width:y * width]
        cur = gray[y * width:(y + 1) * width]
        down = gray[(y + 1) * width:(y + 2) * width]
        for x in range(1, width - 1):
            value = up[x] + down[x] + cur[x - 1] + cur[x + 1] - 4 * cur[x]
            total += value
            squares += value * value
            count += 1
    mean = total / count
    return squares / count - mean * mean


def stamp(moment):
    return time.strftime('%H:%M:%S', time.localtime(moment)) + '.%03d' % int((moment % 1) * 1000)


class Stream(object):
    def __init__(self, index, proc, path, started):
        self.index = index
        self.proc = proc
        self.path = path
        self.started = started


class Outcome(object):
    """What one request got from the cameras."""

    def __init__(self):
        self.ok = False
        self.index = None
        self.photo = None
        self.body = ''
        self.rejected = []    # (index, photo) of every frame that failed the check
        self.reasons = []     # one line per camera that did not give the board
        self.described = False


class ParallelCameras(object):

    def __init__(self, folder, lean, rotation_degrees, dark_below, idle_timeout,
                 reset_events, start_offset, frame_delay, retry_pause, retries, jpeg_quality,
                 popen=subprocess.Popen, clock=time.time, sleep=time.sleep,
                 run=subprocess.run):
        self.folder = folder
        self.lean = lean                      # the lean path: a cam.Cameras object (list, capture)
        self.rotation_degrees = rotation_degrees
        self.dark_below = dark_below
        self.idle_timeout = idle_timeout
        self.reset_events = reset_events
        self.start_offset = start_offset
        self.frame_delay = frame_delay
        self.retry_pause = retry_pause
        self.retries = retries
        self.jpeg_quality = jpeg_quality
        self.popen = popen
        self.clock = clock
        self.sleep = sleep
        self.run = run
        self.streams = {}                     # index -> Stream
        self.open_index = None                # the stream that passed the board check
        self.last_event = None
        self.last = {}
        self.pidfile = os.path.join(folder, 'streams.pid')
        self._kill_orphans()

    def list(self):
        return self.lean.list()

    def capture(self, index):
        """The lean path: one photo from one index. Used only when the streams cannot start."""
        photo = self.lean.capture(index)
        self.last = dict(getattr(self.lean, 'last', {}))
        return photo

    def select_board(self, indices, check, watch, last_board):
        """Return an Outcome. `check(index, photo)` gives (passes, body, label) for one frame.

        Raises OSError if ffmpeg cannot be started; the caller then uses the lean path.
        """
        if self.open_index is not None and self.open_index in self.streams:
            outcome = self._check_open(check, watch)
            if outcome is not None:
                return outcome
        result = Outcome()
        for attempt in range(self.retries + 1):
            if attempt:
                self._close_all()
                LOG.info('selection: no board frame; retry %d of %d after %.1f s pause'
                         % (attempt, self.retries, self.retry_pause))
                self.sleep(self.retry_pause)
            one = self._select_once(indices, check, watch, last_board, attempt + 1)
            result.rejected += one.rejected
            result.reasons += one.reasons
            result.described = result.described or one.described
            if one.ok:
                return one
        self._close_all()
        return result

    def warm(self, indices, last_board):
        """Headstart (BL-037): open the stream of the likely board camera (the remembered one, else
        the first listed) and keep it as the open camera. Nothing is checked or described; the next
        request checks this stream first. Returns the index, or None if no camera is listed.
        Raises OSError if ffmpeg cannot be started."""
        if not indices:
            return None
        index = last_board if last_board in indices else indices[0]
        self._close_all()
        self._start(index)
        self.open_index = index
        LOG.info('headstart: stream on camera %d opened, not checked' % index)
        return index

    def note_event(self, name):
        if self.reset_events.get(name) == 'yes':
            self.last_event = self.clock()

    def tick(self):
        """Called from the main loop: close the streams after the idle timeout."""
        if not self.streams:
            return
        if self.last_event is not None and self.clock() - self.last_event > self.idle_timeout:
            self._close_all()

    def close(self):
        self._close_all()

    # --- one request on the open stream -------------------------------------------------

    def _check_open(self, check, watch):
        index = self.open_index
        stream = self.streams[index]
        started = self.clock()
        try:
            photo, brightness = cam.get_newest_frame(stream.path, self.clock(), max_age=FRAME_MAX_AGE,
                                                     dark_below=self.dark_below, run=self.run)
        except CameraError as err:
            LOG.info('open stream on camera %d gave no usable frame (%s); selecting again' % (index, err))
            self._close_all()
            return None
        photo_s = self.clock() - started
        passes, body, label, describe_s = self._check(check, index, photo)
        watch.camera_try(index, 'ok' if passes else label, photo_s, brightness, describe_s)
        if not passes:
            LOG.info('open stream on camera %d failed the board check (%s); selecting again' % (index, label))
            self._close_all()
            return None
        outcome = Outcome()
        outcome.ok, outcome.index, outcome.photo, outcome.body = True, index, photo, body
        outcome.described = True
        return outcome

    # --- one selection ------------------------------------------------------------------

    def _select_once(self, indices, check, watch, last_board, number):
        out = Outcome()
        order = check_order(indices, last_board)
        guess = order[0] if order else None
        LOG.info('selection %d: cameras %s, check order %s, last board camera %s'
                 % (number, list(indices), order, last_board))
        self._open_all(indices)
        winner = None
        for index in order:
            stream = self.streams[index]
            wait = stream.started + self.frame_delay - self.clock()
            if wait > 0:
                self.sleep(wait)
            started = self.clock()
            try:
                photo, brightness = self._wait_frame(stream)
            except DarkFrameError as err:
                LOG.info('selection %d: camera %d dark, skipped without describe (%s)' % (number, index, err))
                watch.camera_try(index, 'dark', self.clock() - started, None)
                out.reasons.append('camera %d: dark' % index)
                continue
            except CameraError as err:
                LOG.info('selection %d: camera %d gave no frame (%s)' % (number, index, err))
                watch.camera_try(index, 'no frame', self.clock() - started, None)
                out.reasons.append('camera %d: no frame (%s)' % (index, err))
                continue
            photo_s = self.clock() - started
            sharp = self._sharpness(index, photo)
            LOG.info('selection %d: camera %d frame brightness %.1f sharpness %s'
                     % (number, index, brightness, 'n/a' if sharp is None else '%.1f' % sharp))
            passes, body, label, describe_s = self._check(check, index, photo)
            out.described = True
            watch.camera_try(index, 'ok' if passes else label, photo_s, brightness, describe_s)
            if passes:
                winner = index
                out.ok, out.index, out.photo, out.body = True, index, photo, body
                break
            out.rejected.append((index, photo))
            out.reasons.append('camera %d: %s' % (index, label))
        self._close_except(winner)
        if winner is None:
            LOG.info('selection %d: no board frame; guess %s not confirmed' % (number, guess))
        else:
            self.open_index = winner
            LOG.info('selection %d: board on camera %d; guess %s was %s'
                     % (number, winner, guess, 'right' if winner == guess else 'wrong'))
        return out

    def _wait_frame(self, stream):
        """The newest frame of the stream; waits up to FRAME_WAIT for the first one to appear."""
        deadline = self.clock() + FRAME_WAIT
        while True:
            try:
                return cam.get_newest_frame(stream.path, self.clock(), max_age=FRAME_MAX_AGE,
                                            dark_below=self.dark_below, run=self.run)
            except DarkFrameError:
                raise
            except CameraError:
                if self.clock() >= deadline:
                    raise
                self.sleep(0.2)

    def _check(self, check, index, photo):
        started = self.clock()
        try:
            passes, body, label = check(index, photo)
        except DescribeError as err:
            passes, body, label = False, '', 'describe error: %s' % err
        return passes, body, label, self.clock() - started

    def _sharpness(self, index, photo):
        path = os.path.join(self.folder, 'check-%d.jpg' % index)
        try:
            with open(path, 'wb') as handle:
                handle.write(photo)
            cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', path,
                   '-vf', 'scale=%d:%d,format=gray' % (SHARP_WIDTH, SHARP_HEIGHT),
                   '-f', 'rawvideo', '-pix_fmt', 'gray', '-']
            done = self.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            if done.returncode != 0 or len(done.stdout) != SHARP_WIDTH * SHARP_HEIGHT:
                return None
            return laplacian_variance(done.stdout, SHARP_WIDTH, SHARP_HEIGHT)
        except (OSError, subprocess.TimeoutExpired):
            return None
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    # --- streams ------------------------------------------------------------------------

    def _open_all(self, indices):
        self._close_all()
        for number, index in enumerate(indices):
            if number:
                self.sleep(self.start_offset)
            self._start(index)
            LOG.info('stream on camera %d started at %s' % (index, stamp(self.streams[index].started)))

    def _start(self, index):
        cmd, path = cam.stream_command(index, self.folder, self.rotation_degrees, self.jpeg_quality)
        try:
            os.remove(path)            # never answer from an old frame
        except OSError:
            pass
        proc = self.popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.streams[index] = Stream(index, proc, path, self.clock())
        self._write_pidfile()

    def _close_except(self, keep):
        for index in list(self.streams):
            if index != keep:
                self._stop(index)
        if keep is None:
            self.open_index = None

    def _close_all(self):
        for index in list(self.streams):
            self._stop(index)
        self.open_index = None

    def _stop(self, index):
        stream = self.streams.pop(index, None)
        if stream is None:
            return
        if stream.proc.poll() is None:
            stream.proc.kill()
            stream.proc.wait()
        try:
            os.remove(stream.path)
        except OSError:
            pass
        self._write_pidfile()

    def _write_pidfile(self):
        if not self.streams:
            try:
                os.remove(self.pidfile)
            except OSError:
                pass
            return
        with open(self.pidfile, 'w') as handle:
            for stream in self.streams.values():
                handle.write('%d\n' % stream.proc.pid)

    def _kill_orphans(self):
        """Streams left by an earlier service instance (if still ffmpeg processes) are stopped."""
        try:
            with open(self.pidfile) as handle:
                pids = [int(line) for line in handle.read().split()]
        except (OSError, ValueError):
            return
        for pid in pids:
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
