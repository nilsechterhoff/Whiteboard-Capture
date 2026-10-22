"""Tests for the camera function, with a fake imagesnap. No camera needed.

Run: cd watcher && python3 -m unittest -v test_camera
"""

import os
import subprocess
import unittest

import camera as cam
from whiteboard_watcher import CameraError

JPEG = b'\xff\xd8\xff\xe0' + b'data' * 10


class FakeRun(object):
    """Stands in for subprocess.run: writes the photo file named in the command."""

    def __init__(self, data=JPEG, returncode=0, stderr=b'', timeout=False, missing=False):
        self.data = data
        self.returncode = returncode
        self.stderr = stderr
        self.timeout = timeout
        self.missing = missing
        self.cmd = None
        self.limit = None

    def __call__(self, cmd, stdout=None, stderr=None, timeout=None):
        self.cmd = cmd
        self.limit = timeout
        if self.missing:
            raise FileNotFoundError(cmd[0])
        if self.timeout:
            raise subprocess.TimeoutExpired(cmd, timeout)
        if self.data is not None:
            with open(cmd[-1], 'wb') as handle:
                handle.write(self.data)
        return subprocess.CompletedProcess(cmd, self.returncode, b'', self.stderr)


class CameraTests(unittest.TestCase):

    def test_success_returns_the_jpeg(self):
        fake = FakeRun()
        self.assertEqual(cam.ImagesnapCamera(run=fake).take_photo(), JPEG)

    def test_command_selects_camera_by_name_not_serial(self):
        fake = FakeRun()
        cam.ImagesnapCamera(run=fake).take_photo()
        self.assertEqual(fake.cmd[:6], ['imagesnap', '-q', '-w', '1', '-d',
                                        'Logitech Webcam C930e'])
        self.assertNotIn('serial', ' '.join(fake.cmd))

    def test_hard_time_limit_is_passed_to_the_run(self):
        fake = FakeRun()
        cam.ImagesnapCamera(timeout=7, run=fake).take_photo()
        self.assertEqual(fake.limit, 7)

    def test_timeout_is_a_camera_error(self):
        with self.assertRaises(CameraError) as ctx:
            cam.ImagesnapCamera(timeout=5, run=FakeRun(timeout=True)).take_photo()
        self.assertIn('no photo within 5 s', str(ctx.exception))

    def test_nonzero_exit_is_a_camera_error_with_last_line(self):
        fake = FakeRun(data=None, returncode=1, stderr=b'warning\nimagesnap: no device\n')
        with self.assertRaises(CameraError) as ctx:
            cam.ImagesnapCamera(run=fake).take_photo()
        self.assertIn('exit 1', str(ctx.exception))
        self.assertIn('imagesnap: no device', str(ctx.exception))

    def test_missing_binary_is_a_camera_error(self):
        with self.assertRaises(CameraError):
            cam.ImagesnapCamera(run=FakeRun(missing=True)).take_photo()

    def test_no_file_written_is_a_camera_error(self):
        with self.assertRaises(CameraError):
            cam.ImagesnapCamera(run=FakeRun(data=None)).take_photo()

    def test_non_jpeg_output_is_rejected(self):
        with self.assertRaises(CameraError):
            cam.ImagesnapCamera(run=FakeRun(data=b'not a picture')).take_photo()

    def test_temporary_folder_is_removed(self):
        seen = []
        fake = FakeRun()

        def run(cmd, **kw):
            seen.append(os.path.dirname(cmd[-1]))
            return fake(cmd, **kw)

        cam.ImagesnapCamera(run=run).take_photo()
        self.assertTrue(seen)
        self.assertFalse(os.path.exists(seen[0]))


if __name__ == '__main__':
    unittest.main()
