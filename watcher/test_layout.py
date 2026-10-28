"""Tests for the one folder for all watcher local files (BL-035).

Run: cd watcher && python3 -m unittest -v test_layout
"""

import glob
import os
import unittest

import setup_dropbox
import watcher

HERE = os.path.dirname(os.path.abspath(__file__))


class OneFolderTests(unittest.TestCase):

    def test_config_state_work_logs_and_failed_photos_are_under_one_folder(self):
        folder = watcher.CONFIG_DIR
        for path in (watcher.CONFIG_PATH, watcher.LAST_CAMERA_PATH, watcher.WORK_DIR, watcher.LOCK_PATH,
                     watcher.LOG_PATH, watcher.TIMINGS_PATH, setup_dropbox.LAUNCHD_LOG):
            self.assertEqual(os.path.dirname(path), folder, path)

    def test_failed_photos_default_folder_is_inside_it(self):
        failed = os.path.join(watcher.CONFIG_DIR, 'failed-photos')
        self.assertEqual(os.path.dirname(failed), watcher.CONFIG_DIR)

    def test_the_watcher_code_names_no_other_log_folder(self):
        for name in glob.glob(os.path.join(HERE, '*.py')):
            if os.path.basename(name).startswith('test_'):
                continue
            with open(name) as handle:
                self.assertNotIn('Library/Logs', handle.read(), name)


if __name__ == '__main__':
    unittest.main()
