"""Tests for keeping the photos of failed requests: keep the newest N requests. Files in scratch/.

Run: cd watcher && python3 -m unittest -v test_failed_photos
"""

import os
import shutil
import unittest

import failed_photos as fp
import testroot


class KeepTests(unittest.TestCase):

    def setUp(self):
        self.folder = os.path.join(testroot.mkdtemp(), 'failed-photos')

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self.folder))

    def names(self):
        return sorted(os.listdir(self.folder))

    def test_file_names_per_request_and_camera(self):
        fp.save_failed(self.folder, '0021', [(1, b'a'), (0, b'b')], 5)
        self.assertEqual(self.names(), ['request-0021-cam00.jpg', 'request-0021-cam01.jpg'])

    def test_keeps_only_the_newest_five_requests(self):
        for n in range(16, 23):          # 7 requests, two cameras each
            fp.save_failed(self.folder, '%04d' % n, [(0, b'x'), (1, b'y')], 5)
        kept = sorted({name[8:12] for name in self.names()})
        self.assertEqual(kept, ['0018', '0019', '0020', '0021', '0022'])
        self.assertEqual(len(self.names()), 10)

    def test_keep_zero_writes_nothing(self):
        self.assertEqual(fp.save_failed(self.folder, '0021', [(0, b'x')], 0), [])
        self.assertFalse(os.path.exists(self.folder))

    def test_no_photos_writes_nothing(self):
        self.assertEqual(fp.save_failed(self.folder, '0021', [], 5), [])

    def test_prune_ignores_other_files(self):
        os.makedirs(self.folder)
        open(os.path.join(self.folder, 'notes.txt'), 'w').close()
        for n in range(1, 4):
            fp.save_failed(self.folder, '%04d' % n, [(0, b'x')], 2)
        self.assertIn('notes.txt', self.names())
        self.assertNotIn('request-0001-cam00.jpg', self.names())


if __name__ == '__main__':
    unittest.main()
