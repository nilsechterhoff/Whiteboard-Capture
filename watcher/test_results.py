"""Tests for the local results store. Files only in the repo's scratch/ folder.

Run: cd watcher && python3 -m unittest -v test_results
"""

import shutil
import unittest

import results as rs
import testroot


class ResultsTests(unittest.TestCase):

    def setUp(self):
        self.folder = testroot.mkdtemp()
        self.results = rs.Results(self.folder)

    def tearDown(self):
        shutil.rmtree(self.folder)

    def test_save_then_load_returns_photo_and_text(self):
        self.results.save('0003', b'jpeg', 'text')
        self.assertEqual(self.results.load('0003'), (b'jpeg', 'text'))

    def test_nothing_saved_loads_as_none(self):
        self.assertIsNone(self.results.load('0009'))

    def test_done_marker(self):
        self.assertFalse(self.results.is_done('0003'))
        self.results.mark_done('0003')
        self.assertTrue(self.results.is_done('0003'))

    def test_no_temporary_files_left(self):
        self.results.save('0003', b'jpeg', 'text')
        import os
        names = os.listdir(os.path.join(self.folder, 'request-0003'))
        self.assertEqual(sorted(names), ['description.md', 'image.jpg'])


if __name__ == '__main__':
    unittest.main()
