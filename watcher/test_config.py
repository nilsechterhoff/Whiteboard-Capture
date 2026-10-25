"""Tests for the rotation setting and config validation. No camera, no network.

Run: cd watcher && python3 -m unittest -v test_config
"""

import unittest

import camera as cam
from whiteboard_watcher import CameraError
import config as cfg


class RotationTests(unittest.TestCase):

    def test_mapping(self):
        self.assertEqual(cam.rotation_filters(0), [])
        self.assertEqual(cam.rotation_filters(90), ['transpose=1'])
        self.assertEqual(cam.rotation_filters(180), ['hflip', 'vflip'])
        self.assertEqual(cam.rotation_filters(270), ['transpose=2'])

    def test_other_values_are_refused(self):
        for bad in (45, 360, -90, '180', None):
            with self.assertRaises(ValueError):
                cam.rotation_filters(bad)

    def test_capture_command_uses_the_mapping(self):
        import os
        import tempfile
        seen = []

        def run(cmd, **kwargs):
            seen.append(cmd)
            raise FileNotFoundError('record only')
        folder = tempfile.mkdtemp()
        try:
            cam.capture(1, folder, 90, run=run)
        except CameraError:
            pass
        except FileNotFoundError:
            pass
        os.rmdir(folder)
        self.assertIn('transpose=1', seen[0])
        self.assertNotIn('hflip', ' '.join(seen[0]))


class ConfigTests(unittest.TestCase):

    def test_default_rotation_is_zero(self):
        self.assertEqual(cfg.apply_defaults({})['rotation_degrees'], 0)

    def test_valid_config_has_no_errors(self):
        self.assertEqual(cfg.validate({'rotation_degrees': 180}), [])

    def test_invalid_rotation_is_reported(self):
        errors = cfg.validate({'rotation_degrees': 45})
        self.assertEqual(len(errors), 1)
        self.assertIn('0, 90, 180, 270', errors[0])


class BoardFillConfigTests(unittest.TestCase):

    def test_default_is_off(self):
        self.assertEqual(cfg.apply_defaults({})['min_board_fill_percent'], 0)

    def test_range_0_to_100(self):
        self.assertEqual(cfg.validate({'min_board_fill_percent': 80}), [])
        self.assertEqual(cfg.validate({'min_board_fill_percent': 0}), [])
        self.assertEqual(cfg.validate({'min_board_fill_percent': 100}), [])
        for bad in (-1, 101, 80.5, '80', True):
            self.assertEqual(len(cfg.validate({'min_board_fill_percent': bad})), 1, bad)


if __name__ == '__main__':
    unittest.main()
