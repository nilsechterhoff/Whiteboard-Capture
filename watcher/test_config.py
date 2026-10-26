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


class AgileConfigTests(unittest.TestCase):

    def test_defaults_are_off_and_ten_minutes(self):
        d = cfg.apply_defaults({})
        self.assertEqual(d['agile_enabled'], 'no')
        self.assertEqual(d['agile_idle_timeout_seconds'], 600)
        self.assertEqual(d['agile_timer_reset_events'], {'request': 'yes'})
        self.assertFalse(cfg.agile_on(d))
        self.assertFalse(cfg.session_on(d))

    def test_values_are_checked(self):
        self.assertEqual(cfg.validate({'agile_enabled': 'yes'}), [])
        self.assertEqual(len(cfg.validate({'agile_enabled': 'maybe'})), 1)
        self.assertEqual(len(cfg.validate({'agile_enabled': True})), 1)
        self.assertEqual(len(cfg.validate({'agile_idle_timeout_seconds': 0})), 1)
        self.assertEqual(len(cfg.validate({'agile_timer_reset_events': {'request': 'maybe'}})), 1)

    def test_disabled_means_lean_even_with_session_on(self):
        c = cfg.apply_defaults({'agile_enabled': 'no', 'agile_session': 'yes'})
        self.assertFalse(cfg.agile_on(c))
        self.assertFalse(cfg.session_on(c))

    def test_enabled_turns_agile_on_and_session_only_with_it(self):
        self.assertTrue(cfg.agile_on({'agile_enabled': 'yes'}))
        self.assertFalse(cfg.session_on({'agile_enabled': 'yes'}))
        self.assertTrue(cfg.session_on({'agile_enabled': 'yes', 'agile_session': 'yes'}))


class LegacyModeTests(unittest.TestCase):

    def test_mode_agile_becomes_enabled_with_a_warning(self):
        c = {'mode': 'agile'}
        warnings = cfg.normalize(c)
        self.assertEqual(c['agile_enabled'], 'yes')
        self.assertNotIn('mode', c)
        self.assertEqual(len(warnings), 1)
        self.assertIn('agile_enabled', warnings[0])

    def test_any_other_mode_becomes_disabled(self):
        for old in ('lean', 'turbo', None):
            c = {'mode': old}
            cfg.normalize(c)
            self.assertEqual(c['agile_enabled'], 'no')

    def test_explicit_agile_enabled_wins_over_mode(self):
        c = {'mode': 'agile', 'agile_enabled': 'no'}
        cfg.normalize(c)
        self.assertEqual(c['agile_enabled'], 'no')

    def test_no_mode_key_means_no_warning(self):
        self.assertEqual(cfg.normalize({'agile_enabled': 'yes'}), [])


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


if __name__ == '__main__':
    unittest.main()
