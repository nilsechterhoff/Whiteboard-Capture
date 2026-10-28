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
DARK_BELOW = 20     # mean brightness 0 to 255 under this counts as closed lid
JPEG_QUALITY = 2   # ffmpeg -q:v for every JPEG the watcher writes (lower is better, 2 to 31); H23
# rotation_degrees (config) -> ffmpeg filters; 0 = none
ROTATION_FILTERS = {0: [], 90: ['transpose=1'], 180: ['hflip', 'vflip'], 270: ['transpose=2']}
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
    """Video devices as [(index, name)]. The optional name filter must equal the device name exactly.

    If nothing matches exactly, the error names every device found (so the config can be fixed).
    """
    cmd = [FFMPEG, '-hide_banner', '-f', 'avfoundation', '-list_devices', 'true', '-i', '']
    try:
        done = run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=LIST_TIMEOUT)
    except FileNotFoundError:
        raise CameraError('ffmpeg not found')
    except subprocess.TimeoutExpired:
        raise CameraError('ffmpeg listing timed out')
    devices = parse_video_devices(done.stderr.decode('utf-8', 'replace'))
    if name_filter:
        matches = [d for d in devices if d[1] == name_filter]
        if not matches:
            found = '; '.join('%d "%s"' % (index, name) for index, name in devices) or 'none'
            raise CameraError('camera_name "%s" matches no device exactly; devices found: %s'
                              % (name_filter, found))
        devices = matches
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


def rotation_filters(degrees):
    """ffmpeg filters for a rotation in degrees. Any other value is refused."""
    if degrees not in ROTATION_FILTERS:
        raise ValueError('rotation_degrees must be one of 0, 90, 180, 270 (got %r)' % (degrees,))
    return list(ROTATION_FILTERS[degrees])


def capture(index, folder, rotation_degrees=0, dark_below=DARK_BELOW, run=subprocess.run, timing=None,
            jpeg_quality=JPEG_QUALITY):
    """One photo from camera `index` as JPEG bytes. Raises CameraError.

    The first frame is the photo (no warm-up: a working camera is bright from the start).
    The frame goes to `folder` (created by the caller) and is deleted again.
    `timing` (a dict, optional) gets photo_s, brightness_s and brightness, also when
    the frame is rejected.
    """
    timing = {} if timing is None else timing
    last = os.path.join(folder, 'frame-%d.jpg' % index)
    cmd = [FFMPEG, '-hide_banner', '-loglevel', 'error', '-f', 'avfoundation',
           '-framerate', FRAMERATE, '-video_size', SIZE, '-i', '%d:none' % index]
    filters = rotation_filters(rotation_degrees)
    if filters:
        cmd += ['-vf', ','.join(filters)]
    cmd += ['-q:v', str(jpeg_quality), '-frames:v', '1', '-y', last]
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
        try:
            os.remove(last)
        except OSError:
            pass


def stream_command(index, folder, rotation_degrees=0, jpeg_quality=JPEG_QUALITY):
    """ffmpeg command that keeps one camera open and rewrites its newest frame (about 2 per second).
    Returns (command, path of the newest frame)."""
    out = os.path.join(folder, 'agile-%d.jpg' % index)
    filters = rotation_filters(rotation_degrees) + ['fps=2']
    cmd = [FFMPEG, '-hide_banner', '-loglevel', 'error', '-f', 'avfoundation',
           '-framerate', FRAMERATE, '-video_size', SIZE, '-i', '%d:none' % index,
           '-vf', ','.join(filters), '-update', '1', '-atomic_writing', '1',
           '-q:v', str(jpeg_quality), '-y', out]
    return cmd, out


def get_newest_frame(path, now, max_age=3.0, dark_below=DARK_BELOW, run=subprocess.run):
    """The single access point to an open stream: the newest frame, if it is fresh and not dark.
    Returns (JPEG bytes, brightness). Raises CameraError (no fresh frame) or DarkFrameError."""
    if not os.path.exists(path) or now - os.stat(path).st_mtime > max_age:
        raise CameraError('no fresh frame from the open stream')
    brightness = mean_brightness(path, run)
    if brightness < dark_below:
        raise DarkFrameError('dark, closed lid (mean %d)' % brightness)
    with open(path, 'rb') as handle:
        return handle.read(), brightness


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

    def __init__(self, folder, name_filter='', rotation_degrees=0, dark_below=DARK_BELOW,
                 run=subprocess.run, jpeg_quality=JPEG_QUALITY):
        self.folder = folder
        self.name_filter = name_filter
        self.rotation_degrees = rotation_degrees
        self.dark_below = dark_below
        self.run = run
        self.jpeg_quality = jpeg_quality
        self.last = {}  # timing of the last capture, see capture()

    def list(self):
        return list_cameras(self.name_filter, self.run)

    def capture(self, index):
        self.last = {}
        return capture(index, self.folder, self.rotation_degrees, self.dark_below, self.run, self.last,
                       self.jpeg_quality)
