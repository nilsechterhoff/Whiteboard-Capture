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

    def test_default_is_50_and_0_is_off(self):
        self.assertEqual(cfg.apply_defaults({})['min_board_fill_percent'], 50)
        self.assertEqual(cfg.validate({'min_board_fill_percent': 0}), [])

    def test_range_0_to_100(self):
        self.assertEqual(cfg.validate({'min_board_fill_percent': 80}), [])
        self.assertEqual(cfg.validate({'min_board_fill_percent': 0}), [])
        self.assertEqual(cfg.validate({'min_board_fill_percent': 100}), [])
        for bad in (-1, 101, 80.5, '80', True):
            self.assertEqual(len(cfg.validate({'min_board_fill_percent': bad})), 1, bad)


class AgileConfigTests(unittest.TestCase):

    def test_defaults_are_ten_minutes_session_off_and_selection_settings(self):
        d = cfg.apply_defaults({})
        self.assertEqual(d['agile_idle_timeout_seconds'], 600)
        self.assertEqual(d['agile_timer_reset_events'], {'request': 'yes'})
        self.assertEqual(d['start_offset_seconds'], 0.1)
        self.assertEqual(d['selection_frame_delay_seconds'], 2)
        self.assertEqual(d['retry_pause_seconds'], 1)
        self.assertEqual(d['capture_retries'], 2)
        self.assertFalse(cfg.session_on(d))
        self.assertNotIn('agile_enabled', d)

    def test_values_are_checked(self):
        self.assertEqual(len(cfg.validate({'agile_idle_timeout_seconds': 0})), 1)
        self.assertEqual(len(cfg.validate({'agile_timer_reset_events': {'request': 'maybe'}})), 1)
        self.assertEqual(len(cfg.validate({'agile_session': 'maybe'})), 1)

    def test_selection_values_are_checked(self):
        self.assertEqual(cfg.validate({'start_offset_seconds': 0, 'selection_frame_delay_seconds': 2.5,
                                       'retry_pause_seconds': 0, 'capture_retries': 0}), [])
        self.assertEqual(len(cfg.validate({'start_offset_seconds': -0.1})), 1)
        self.assertEqual(len(cfg.validate({'selection_frame_delay_seconds': '2'})), 1)
        self.assertEqual(len(cfg.validate({'retry_pause_seconds': True})), 1)
        self.assertEqual(len(cfg.validate({'capture_retries': -1})), 1)
        self.assertEqual(len(cfg.validate({'capture_retries': 1.5})), 1)

    def test_session_needs_session_yes(self):
        self.assertFalse(cfg.session_on({}))
        self.assertTrue(cfg.session_on({'agile_session': 'yes'}))


class IgnoredKeysTests(unittest.TestCase):

    def test_agile_enabled_is_removed_with_one_warning(self):
        c = {'agile_enabled': 'yes', 'camera_name': 'x'}
        warnings = cfg.normalize(c)
        self.assertNotIn('agile_enabled', c)
        self.assertEqual(len(warnings), 1)
        self.assertIn('agile_enabled', warnings[0])
        self.assertIn('ignored', warnings[0])

    def test_old_mode_key_is_removed_with_one_warning(self):
        c = {'mode': 'agile'}
        warnings = cfg.normalize(c)
        self.assertNotIn('mode', c)
        self.assertEqual(len(warnings), 1)
        self.assertIn('mode', warnings[0])

    def test_both_keys_still_give_one_warning(self):
        c = {'mode': 'agile', 'agile_enabled': 'no'}
        self.assertEqual(len(cfg.normalize(c)), 1)
        self.assertEqual(c, {})

    def test_no_such_key_means_no_warning(self):
        self.assertEqual(cfg.normalize({'camera_name': 'x'}), [])


class FailedPhotosConfigTests(unittest.TestCase):

    def test_defaults(self):
        d = cfg.apply_defaults({})
        self.assertEqual(d['failed_photos_keep'], 5)
        self.assertEqual(d['failed_photos_folder'], 'failed-photos')

    def test_keep_and_folder_are_checked(self):
        self.assertEqual(cfg.validate({'failed_photos_keep': 0}), [])
        self.assertEqual(len(cfg.validate({'failed_photos_keep': -1})), 1)
        self.assertEqual(len(cfg.validate({'failed_photos_keep': '5'})), 1)
        self.assertEqual(len(cfg.validate({'failed_photos_folder': '../x'})), 1)
        self.assertEqual(len(cfg.validate({'failed_photos_folder': ''})), 1)


class JpegQualityConfigTests(unittest.TestCase):

    def test_default_is_2(self):
        self.assertEqual(cfg.apply_defaults({})['jpeg_quality'], 2)

    def test_range_2_to_31_is_accepted(self):
        self.assertEqual(cfg.validate({'jpeg_quality': 2}), [])
        self.assertEqual(cfg.validate({'jpeg_quality': 31}), [])

    def test_bad_values_are_refused_with_a_message(self):
        for bad in (1, 0, 32, -1, 2.5, '2', True, None):
            errors = cfg.validate({'jpeg_quality': bad})
            self.assertEqual(len(errors), 1, bad)
            self.assertIn('jpeg_quality must be a whole number from 2 to 31', errors[0])

if __name__ == '__main__':
    unittest.main()
