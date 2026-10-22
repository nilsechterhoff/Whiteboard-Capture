"""One photo on demand from the camera, with a hard time limit (Mac: imagesnap).

Each call opens the camera, takes one photo and closes it again. Selected by
the listed name, not by serial number. Standard library only, Python 3.9.

Test (5 photos, a few seconds apart, saved outside the repo):
    python3 watcher/camera.py --photos 5 --dir <folder>
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

from whiteboard_watcher import CameraError

CAMERA_NAME = 'Logitech Webcam C930e'  # as listed by: imagesnap -l
IMAGESNAP = 'imagesnap'
WARMUP = 1      # seconds imagesnap waits before the shot
TIMEOUT = 20    # hard limit for one photo, seconds
JPEG_START = b'\xff\xd8\xff'


class ImagesnapCamera(object):

    def __init__(self, name=CAMERA_NAME, timeout=TIMEOUT, run=subprocess.run):
        self.name = name
        self.timeout = timeout
        self.run = run

    def take_photo(self):
        folder = tempfile.mkdtemp(prefix='wbw-')
        out = os.path.join(folder, 'photo.jpg')
        try:
            cmd = [IMAGESNAP, '-q', '-w', str(WARMUP), '-d', self.name, out]
            try:
                done = self.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=self.timeout)
            except FileNotFoundError:
                raise CameraError('imagesnap not found')
            except subprocess.TimeoutExpired:
                raise CameraError('no photo within %d s' % self.timeout)
            if done.returncode != 0:
                lines = done.stderr.decode('utf-8', 'replace').strip().splitlines()
                last = lines[-1] if lines else 'no message'
                raise CameraError('imagesnap exit %d: %s' % (done.returncode, last))
            try:
                with open(out, 'rb') as handle:
                    data = handle.read()
            except OSError:
                raise CameraError('no photo file written')
            if not data.startswith(JPEG_START):
                raise CameraError('output is not a JPEG')
            return data
        finally:
            shutil.rmtree(folder, ignore_errors=True)


def main(argv):
    parser = argparse.ArgumentParser(description='Take photos for a camera test.')
    parser.add_argument('--photos', type=int, default=5)
    parser.add_argument('--gap', type=float, default=3.0, help='seconds between photos')
    parser.add_argument('--dir', required=True, help='folder for the test photos (not in the repo)')
    args = parser.parse_args(argv)
    os.makedirs(args.dir, exist_ok=True)
    camera = ImagesnapCamera()
    failures = 0
    for i in range(1, args.photos + 1):
        started = time.time()
        try:
            data = camera.take_photo()
        except CameraError as err:
            failures += 1
            print('photo %d: FAILED after %.1f s: %s' % (i, time.time() - started, err))
        else:
            path = os.path.join(args.dir, 'test-%d.jpg' % i)
            with open(path, 'wb') as handle:
                handle.write(data)
            print('photo %d: ok, %d bytes, %.1f s -> %s' % (
                i, len(data), time.time() - started, path))
        if i < args.photos:
            time.sleep(args.gap)
    print('done: %d of %d ok' % (args.photos - failures, args.photos))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
