"""Tests for the index-based camera module, with fake ffmpeg. No camera needed.

Run: cd watcher && python3 -m unittest -v test_camera
"""

import json
import os
import shutil
import subprocess
import testroot
import unittest

import camera as cam
from whiteboard_watcher import CameraError, DarkFrameError

LIST_TEXT = b"""[AVFoundation indev @ 0x1] AVFoundation video devices:
[AVFoundation indev @ 0x1] [0] Logitech Webcam C930e
[AVFoundation indev @ 0x1] [1] Logitech Webcam C930e
[AVFoundation indev @ 0x1] [2] FaceTime HD Camera
[AVFoundation indev @ 0x1] [3] Capture screen 0
[AVFoundation indev @ 0x1] AVFoundation audio devices:
[AVFoundation indev @ 0x1] [0] MacBook Air Microphone
"""


class FakeFfmpeg(object):
    """Stands in for subprocess.run. Routes by the command: listing, capture, brightness."""

    def __init__(self, listing=LIST_TEXT, brightness=None, frames=True, returncode=0,
                 stderr=b'', timeout=False, missing=False, brightness_text=None):
        self.listing = listing
        self.brightness = brightness or {}
        self.frames = frames
        self.returncode = returncode
        self.stderr = stderr
        self.timeout = timeout
        self.missing = missing
        self.brightness_text = brightness_text
        self.commands = []

    def __call__(self, cmd, stdout=None, stderr=None, timeout=None, **kwargs):
        self.commands.append(cmd)
        if self.missing:
            raise FileNotFoundError(cmd[0])
        if self.timeout:
            raise subprocess.TimeoutExpired(cmd, timeout)
        if '-list_devices' in cmd:
            return subprocess.CompletedProcess(cmd, 1, b'', self.listing)
        if '-frames:v' in cmd:
            if self.frames:
                with open(cmd[-1], 'wb') as handle:
                    handle.write(b'jpeg-1')
            return subprocess.CompletedProcess(cmd, self.returncode, b'', self.stderr)
        if 'signalstats,metadata=mode=print:file=-' in cmd:
            path = cmd[cmd.index('-i') + 1]
            value = self.brightness.get(os.path.basename(path), 100.0)
            text = self.brightness_text if self.brightness_text is not None else \
                'lavfi.signalstats.YAVG=%s\n' % value
            return subprocess.CompletedProcess(cmd, 0, text.encode('utf-8'), b'')
        raise AssertionError('unexpected command %r' % cmd)


class ListTests(unittest.TestCase):

    def test_parse_skips_audio_and_screen_capture(self):
        devices = cam.parse_video_devices(LIST_TEXT.decode('utf-8'))
        self.assertEqual(devices, [(0, 'Logitech Webcam C930e'),
                                   (1, 'Logitech Webcam C930e'),
                                   (2, 'FaceTime HD Camera')])

    def test_list_cameras_returns_devices(self):
        fake = FakeFfmpeg()
        self.assertEqual(len(cam.list_cameras(run=fake)), 3)

    def test_name_filter_is_the_exact_device_name(self):
        devices = cam.list_cameras('Logitech Webcam C930e', run=FakeFfmpeg())
        self.assertEqual([i for i, _ in devices], [0, 1])

    def test_substring_is_not_enough_and_the_error_lists_the_names(self):
        with self.assertRaises(CameraError) as ctx:
            cam.list_cameras('c930E', run=FakeFfmpeg())
        self.assertIn('0 "Logitech Webcam C930e"', str(ctx.exception))
        self.assertIn('2 "FaceTime HD Camera"', str(ctx.exception))

    def test_name_matching_nothing_is_an_error_with_the_names(self):
        with self.assertRaises(CameraError) as ctx:
            cam.list_cameras('Nope', run=FakeFfmpeg())
        self.assertIn('matches no device exactly', str(ctx.exception))

    def test_no_camera_listed_is_an_error(self):
        with self.assertRaises(CameraError):
            cam.list_cameras(run=FakeFfmpeg(listing=b'AVFoundation video devices:\n'))

    def test_missing_ffmpeg_is_an_error(self):
        with self.assertRaises(CameraError):
            cam.list_cameras(run=FakeFfmpeg(missing=True))

    def test_listing_timeout_is_an_error(self):
        with self.assertRaises(CameraError):
            cam.list_cameras(run=FakeFfmpeg(timeout=True))


class CaptureTests(unittest.TestCase):

    def setUp(self):
        self.folder = testroot.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.folder)

    def test_capture_returns_last_frame_and_cleans_up(self):
        fake = FakeFfmpeg(brightness={'frame-1.jpg': 120.0})
        data = cam.capture(1, self.folder, run=fake)
        self.assertEqual(data, b'jpeg-1')
        self.assertEqual(os.listdir(self.folder), [])

    def test_command_uses_index_and_rotation(self):
        fake = FakeFfmpeg(brightness={'frame-1.jpg': 120.0})
        cam.capture(1, self.folder, rotation_degrees=180, run=fake)
        capture_cmd = [c for c in fake.commands if '-frames:v' in c][0]
        self.assertIn('1:none', capture_cmd)
        self.assertIn('hflip,vflip', capture_cmd)

    def test_rotation_off_has_no_flip(self):
        fake = FakeFfmpeg(brightness={'frame-0.jpg': 120.0})
        cam.capture(0, self.folder, rotation_degrees=0, run=fake)
        capture_cmd = [c for c in fake.commands if '-frames:v' in c][0]
        self.assertNotIn('-vf', capture_cmd)
        self.assertNotIn('hflip', capture_cmd)

    def test_first_frame_is_the_photo_without_warmup(self):
        fake = FakeFfmpeg(brightness={'frame-0.jpg': 90.0})
        self.assertEqual(cam.capture(0, self.folder, run=fake), b'jpeg-1')
        capture_cmd = [c for c in fake.commands if '-frames:v' in c][0]
        self.assertEqual(capture_cmd[capture_cmd.index('-frames:v') + 1], '1')
        self.assertNotIn('fps', ' '.join(capture_cmd))
        self.assertEqual(os.listdir(self.folder), [])

    def test_dark_frame_is_rejected(self):
        fake = FakeFfmpeg(brightness={'frame-2.jpg': 1.4})
        with self.assertRaises(DarkFrameError) as ctx:
            cam.capture(2, self.folder, run=fake)
        self.assertIn('dark, closed lid', str(ctx.exception))
        self.assertEqual(os.listdir(self.folder), [])

    def test_threshold_is_configurable(self):
        fake = FakeFfmpeg(brightness={'frame-0.jpg': 30.0})
        with self.assertRaises(CameraError):
            cam.capture(0, self.folder, dark_below=40, run=fake)

    def test_no_frame_written_is_an_error(self):
        with self.assertRaises(CameraError) as ctx:
            cam.capture(0, self.folder, run=FakeFfmpeg(frames=False, returncode=1,
                                                        stderr=b'Video device not found\n'))
        self.assertIn('Video device not found', str(ctx.exception))

    def test_capture_timeout_is_an_error(self):
        with self.assertRaises(CameraError) as ctx:
            cam.capture(0, self.folder, run=FakeFfmpeg(timeout=True))
        self.assertIn('no photo within', str(ctx.exception))

    def test_brightness_without_value_is_an_error(self):
        with self.assertRaises(CameraError):
            cam.capture(0, self.folder, run=FakeFfmpeg(brightness_text='nothing here'))

    def test_cameras_class_passes_settings_through(self):
        fake = FakeFfmpeg(brightness={'frame-4.jpg': 90.0})
        cameras = cam.Cameras(self.folder, 'Logitech Webcam C930e', rotation_degrees=0, dark_below=10, run=fake)
        self.assertEqual(cameras.capture(4), b'jpeg-1')
        self.assertEqual(cameras.list(), [(0, 'Logitech Webcam C930e'),
                                          (1, 'Logitech Webcam C930e')])


class StateTests(unittest.TestCase):

    def setUp(self):
        self.folder = testroot.mkdtemp()
        self.path = os.path.join(self.folder, 'last_camera.json')

    def tearDown(self):
        shutil.rmtree(self.folder)

    def test_missing_file_gives_none(self):
        self.assertIsNone(cam.load_last(self.path))

    def test_corrupt_file_gives_none(self):
        with open(self.path, 'w') as handle:
            handle.write('{not json')
        self.assertIsNone(cam.load_last(self.path))

    def test_wrong_type_gives_none(self):
        with open(self.path, 'w') as handle:
            json.dump({'index': 'one'}, handle)
        self.assertIsNone(cam.load_last(self.path))

    def test_save_then_load(self):
        cam.save_last(self.path, 1, 'Logitech Webcam C930e')
        self.assertEqual(cam.load_last(self.path), 1)
        self.assertFalse(os.path.exists(self.path + '.tmp'))


class JpegQualityTests(unittest.TestCase):

    def setUp(self):
        self.folder = testroot.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.folder)

    def quality_of(self, cmd):
        return cmd[cmd.index('-q:v') + 1]

    def test_stream_command_default_is_quality_2_before_the_output(self):
        cmd, out = cam.stream_command(0, self.folder, 0)
        self.assertEqual(self.quality_of(cmd), '2')
        self.assertLess(cmd.index('-q:v'), cmd.index('-y'))
        self.assertEqual(cmd[-1], out)

    def test_stream_command_uses_the_configured_quality(self):
        cmd, _ = cam.stream_command(0, self.folder, 0, jpeg_quality=10)
        self.assertEqual(self.quality_of(cmd), '10')

    def test_single_capture_uses_the_quality_too(self):
        fake = FakeFfmpeg(brightness={'frame-0.jpg': 90.0})
        cam.capture(0, self.folder, run=fake)
        capture_cmd = [c for c in fake.commands if '-frames:v' in c][0]
        self.assertEqual(self.quality_of(capture_cmd), '2')

    def test_cameras_class_passes_the_configured_quality(self):
        fake = FakeFfmpeg(brightness={'frame-4.jpg': 90.0})
        cameras = cam.Cameras(self.folder, 'Logitech Webcam C930e', run=fake, jpeg_quality=7)
        cameras.capture(4)
        capture_cmd = [c for c in fake.commands if '-frames:v' in c][0]
        self.assertEqual(self.quality_of(capture_cmd), '7')

if __name__ == '__main__':
    unittest.main()
