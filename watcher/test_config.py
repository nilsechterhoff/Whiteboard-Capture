"""Tests for the config rules (BL-040): settings (values, defaults, conversion) and config checks.

Run: cd watcher && python3 -m unittest -v test_config
"""

import json
import os
import shutil
import unittest

import config as cfg
import settings as st
import testroot

EXAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.example.json')


def entry(value, default, allowed=None):
    item = {'value': value, 'default': default}
    if allowed is not None:
        item['allowed'] = allowed
    return item


class AllowedTests(unittest.TestCase):

    def test_range_is_whole_numbers_inclusive(self):
        self.assertTrue(st.check(2, '2-31'))
        self.assertTrue(st.check(31, '2-31'))
        for bad in (1, 32, 2.5, '2', True):
            self.assertFalse(st.check(bad, '2-31'), bad)

    def test_minimums(self):
        self.assertTrue(st.check(0, 'int>=0'))
        self.assertFalse(st.check(-1, 'int>=0'))
        self.assertFalse(st.check(1.5, 'int>=0'))
        self.assertTrue(st.check(0.1, 'number>=0'))
        self.assertFalse(st.check(-0.1, 'number>=0'))

    def test_lists_compare_as_text(self):
        self.assertTrue(st.check(90, '0|90|180|270'))
        self.assertFalse(st.check(45, '0|90|180|270'))
        self.assertTrue(st.check('yes', 'yes|no'))
        self.assertFalse(st.check('maybe', 'yes|no'))

    def test_dict_of_words(self):
        self.assertTrue(st.check({'request': 'yes'}, 'dict:yes|no'))
        self.assertFalse(st.check({'request': 'maybe'}, 'dict:yes|no'))

    def test_text_and_any(self):
        self.assertTrue(st.check('failed-photos', 'text'))
        self.assertFalse(st.check('', 'text'))
        self.assertTrue(st.check('anything at all', 'any'))
        self.assertTrue(st.check(None, None))


class ResolveTests(unittest.TestCase):

    def test_a_valid_value_is_used(self):
        settings, warnings = st.resolve({'jpeg_quality': entry(6, 4, '2-31')})
        self.assertEqual(settings['jpeg_quality'], 6)
        self.assertEqual(warnings, [])

    def test_an_invalid_value_falls_back_to_the_default_with_one_line(self):
        settings, warnings = st.resolve({'jpeg_quality': entry(40, 4, '2-31')})
        self.assertEqual(settings['jpeg_quality'], 4)
        self.assertEqual(len(warnings), 1)
        self.assertIn('jpeg_quality', warnings[0])
        self.assertIn('using the default 4', warnings[0])

    def test_an_empty_value_falls_back_to_the_default(self):
        settings, warnings = st.resolve({'retry_pause_seconds': entry(None, 1, 'number>=0')})
        self.assertEqual(settings['retry_pause_seconds'], 1)
        self.assertEqual(len(warnings), 1)

    def test_empty_value_equal_to_its_default_is_silent(self):
        settings, warnings = st.resolve({'camera_name': entry('', '', 'any')})
        self.assertEqual(settings['camera_name'], '')
        self.assertEqual(warnings, [])

    def test_plain_values_stay_as_they_are(self):
        settings, warnings = st.resolve({'app_key': 'K', 'models': {'haiku': 'x'}})
        self.assertEqual(settings, {'app_key': 'K', 'models': {'haiku': 'x'}})
        self.assertEqual(warnings, [])


class ConversionTests(unittest.TestCase):

    def setUp(self):
        self.folder = testroot.mkdtemp()
        self.path = os.path.join(self.folder, 'config.json')
        self.example = json.load(open(EXAMPLE))

    def tearDown(self):
        shutil.rmtree(self.folder)

    def test_flat_config_needs_conversion(self):
        self.assertTrue(st.needs_conversion({'jpeg_quality': 2}, self.example))

    def test_entry_config_does_not_need_conversion(self):
        self.assertFalse(st.needs_conversion({'jpeg_quality': entry(2, 4, '2-31')}, self.example))

    def test_conversion_keeps_the_old_value_and_takes_the_default_from_the_example(self):
        raw = {'app_key': 'K', 'camera_name': 'Logitech Webcam C930e', 'jpeg_quality': 2}
        with open(self.path, 'w') as handle:
            json.dump(raw, handle)
        converted, _ = st.convert(raw, self.example, self.path, now=1793200000)
        self.assertEqual(converted['camera_name']['value'], 'Logitech Webcam C930e')
        self.assertEqual(converted['jpeg_quality'], entry(2, 4, '2-31'))
        self.assertEqual(converted['app_key'], 'K')

    def test_conversion_writes_a_timestamped_backup_next_to_the_file(self):
        raw = {'jpeg_quality': 2}
        with open(self.path, 'w') as handle:
            json.dump(raw, handle)
        _, backup = st.convert(raw, self.example, self.path, now=1793200000)
        self.assertTrue(os.path.exists(backup))
        self.assertEqual(os.path.dirname(backup), self.folder)
        self.assertIn('backup-', os.path.basename(backup))
        self.assertEqual(json.load(open(backup)), raw)

    def test_missing_keys_get_the_example_entry(self):
        with open(self.path, 'w') as handle:
            json.dump({'app_key': 'K'}, handle)
        converted, _ = st.convert({'app_key': 'K'}, self.example, self.path, now=1793200000)
        self.assertEqual(converted['capture_retries'], entry(2, 2, 'int>=0'))

    def test_write_keeps_the_file_private(self):
        st.write(self.path, {'a': 1})
        self.assertEqual(oct(os.stat(self.path).st_mode & 0o777), '0o600')


class ExampleFileTests(unittest.TestCase):

    def test_every_default_is_an_entry_with_an_allowed_rule_and_resolves_cleanly(self):
        example = json.load(open(EXAMPLE))
        settings, warnings = st.resolve(example)
        self.assertEqual(warnings, [])
        self.assertEqual(settings['jpeg_quality'], 4)
        self.assertEqual(settings['rotation_degrees'], 0)
        self.assertEqual(settings['agile_timer_reset_events'], {'request': 'yes'})

    def test_example_secrets_stay_plain(self):
        example = json.load(open(EXAMPLE))
        for key in ('app_key', 'app_secret', 'refresh_token', 'models'):
            self.assertFalse(st.is_entry(example[key]), key)


class ConfigRuleTests(unittest.TestCase):

    def test_agile_enabled_and_mode_are_removed_with_one_warning(self):
        c = {'agile_enabled': 'yes', 'camera_name': 'x'}
        warnings = cfg.normalize(c)
        self.assertNotIn('agile_enabled', c)
        self.assertEqual(len(warnings), 1)
        self.assertIn('ignored', warnings[0])

    def test_old_mode_key_is_removed(self):
        c = {'mode': 'agile'}
        self.assertEqual(len(cfg.normalize(c)), 1)
        self.assertNotIn('mode', c)

    def test_both_keys_still_give_one_warning(self):
        c = {'mode': 'agile', 'agile_enabled': 'no'}
        self.assertEqual(len(cfg.normalize(c)), 1)
        self.assertEqual(c, {})

    def test_no_such_key_means_no_warning(self):
        self.assertEqual(cfg.normalize({'camera_name': 'x'}), [])

    def test_session_is_on_only_with_session_yes(self):
        self.assertFalse(cfg.session_on({'agile_session': 'no'}))
        self.assertTrue(cfg.session_on({'agile_session': 'yes'}))

    def test_validate_checks_the_folder_name_and_the_default_model(self):
        ok = {'failed_photos_folder': 'failed-photos', 'default_model': 'haiku', 'models': {'haiku': 'x'}}
        self.assertEqual(cfg.validate(ok), [])
        self.assertEqual(len(cfg.validate(dict(ok, failed_photos_folder='../x'))), 1)
        self.assertEqual(len(cfg.validate(dict(ok, default_model='nope'))), 1)


if __name__ == '__main__':
    unittest.main()
