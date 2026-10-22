"""Cameras through ffmpeg avfoundation, by index only (no serial or ID lookup).

list_cameras() gives the video devices, capture() takes one photo from one index
and rejects it when it is near-black (closed lid). Rotation and brightness use
ffmpeg filters (hflip, vflip, signalstats). Standard library only, Python 3.9.
"""

import json
import os
import re
import subprocess
import time

from whiteboard_watcher import CameraError, DarkFrameError

FFMPEG = 'ffmpeg'
LIST_TIMEOUT = 15
CAPTURE_TIMEOUT = 25
BRIGHTNESS_TIMEOUT = 10
FRAMERATE = '30'    # the default (29.97) is refused by the Logitech C930e
SIZE = '1920x1080'
FPS = 2             # frames per second while warming up
WARMUP_FRAMES = 3   # first 1.5 s at 2 fps: discarded (exposure settles, black first frames)
FRAMES = WARMUP_FRAMES + 1  # the next frame (about 2 s after start) is the photo
DARK_BELOW = 20     # mean brightness 0 to 255 under this counts as closed lid
DEVICE = re.compile(r'\[(\d+)\] (.+)$')
NOT_CAMERAS = ('Capture screen',)  # screen recording is not a camera
BRIGHTNESS = re.compile(r'lavfi\.signalstats\.YAVG=([0-9.]+)')


def parse_video_devices(text):
    """Return [(index, name)] from the video section of ffmpeg's device listing."""
    devices = []
    in_video = False
    for line in text.splitlines():
        if 'AVFoundation video devices' in line:
            in_video = True
        elif 'AVFoundation audio devices' in line:
            break
        elif in_video:
            match = DEVICE.search(line)
            if match and not match.group(2).startswith(NOT_CAMERAS):
                devices.append((int(match.group(1)), match.group(2).strip()))
    return devices


def list_cameras(name_filter='', run=subprocess.run):
    """Video devices as [(index, name)]. Optional name filter (case-insensitive substring)."""
    cmd = [FFMPEG, '-hide_banner', '-f', 'avfoundation', '-list_devices', 'true', '-i', '']
    try:
        done = run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=LIST_TIMEOUT)
    except FileNotFoundError:
        raise CameraError('ffmpeg not found')
    except subprocess.TimeoutExpired:
        raise CameraError('ffmpeg listing timed out')
    devices = parse_video_devices(done.stderr.decode('utf-8', 'replace'))
    if name_filter:
        devices = [d for d in devices if name_filter.lower() in d[1].lower()]
    if not devices:
        raise CameraError('ffmpeg lists no camera')
    return devices


def mean_brightness(path, run=subprocess.run):
    """Mean brightness (0 to 255) of one image, from ffmpeg signalstats."""
    cmd = [FFMPEG, '-hide_banner', '-loglevel', 'info', '-i', path,
           '-vf', 'signalstats,metadata=mode=print:file=-', '-f', 'null', '-']
    try:
        done = run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=BRIGHTNESS_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise CameraError('brightness check timed out')
    match = BRIGHTNESS.search(done.stdout.decode('utf-8', 'replace'))
    if not match:
        raise CameraError('no brightness value')
    return float(match.group(1))


def capture(index, folder, rotate=True, dark_below=DARK_BELOW, run=subprocess.run, timing=None):
    """One photo from camera `index` as JPEG bytes. Raises CameraError.

    Frames go to `folder` (created by the caller) and are deleted again.
    `timing` (a dict, optional) gets photo_s, brightness_s and brightness, also when
    the frame is rejected.
    """
    timing = {} if timing is None else timing
    pattern = os.path.join(folder, 'frame-%d-%%d.jpg' % index)
    filters = ['hflip', 'vflip'] if rotate else []
    filters.append('fps=%d' % FPS)
    cmd = [FFMPEG, '-hide_banner', '-loglevel', 'error', '-f', 'avfoundation',
           '-framerate', FRAMERATE, '-video_size', SIZE,
           '-i', '%d:none' % index, '-vf', ','.join(filters),
           '-frames:v', str(FRAMES), '-y', pattern]
    last = pattern % FRAMES
    try:
        started = time.time()
        try:
            done = run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=CAPTURE_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise CameraError('no photo within %d s' % CAPTURE_TIMEOUT)
        finally:
            timing['photo_s'] = time.time() - started
        if done.returncode != 0 or not os.path.exists(last):
            lines = done.stderr.decode('utf-8', 'replace').strip().splitlines()
            raise CameraError('no frame (%s)' % (lines[-1] if lines else 'no message'))
        started = time.time()
        brightness = mean_brightness(last, run)
        timing['brightness_s'] = time.time() - started
        timing['brightness'] = brightness
        if brightness < dark_below:
            raise DarkFrameError('dark, closed lid (mean %d)' % brightness)
        with open(last, 'rb') as handle:
            return handle.read()
    finally:
        for frame in range(1, FRAMES + 1):
            try:
                os.remove(pattern % frame)
            except OSError:
                pass


def load_last(path):
    """Index of the last working camera from the state file, or None if missing or corrupt."""
    try:
        with open(path) as handle:
            index = json.load(handle).get('index')
    except (OSError, ValueError, AttributeError):
        return None
    return index if isinstance(index, int) else None


def save_last(path, index, name):
    """Write the state file atomically. It is only a hint, see camera_order()."""
    temp = path + '.tmp'
    with open(temp, 'w') as handle:
        json.dump({'index': index, 'name': name}, handle)
        handle.write('\n')
    os.replace(temp, path)


class Cameras(object):
    """What handle_request() needs: list() and capture(index)."""

    def __init__(self, folder, name_filter='', rotate=True, dark_below=DARK_BELOW,
                 run=subprocess.run):
        self.folder = folder
        self.name_filter = name_filter
        self.rotate = rotate
        self.dark_below = dark_below
        self.run = run
        self.last = {}  # timing of the last capture, see capture()

    def list(self):
        return list_cameras(self.name_filter, self.run)

    def capture(self, index):
        self.last = {}
        return capture(index, self.folder, self.rotate, self.dark_below, self.run, self.last)
