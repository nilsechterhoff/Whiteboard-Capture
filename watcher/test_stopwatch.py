"""Tests for the stopwatch: the timing block and the CSV log. Files only in scratch/.

Run: cd watcher && python3 -m unittest -v test_stopwatch
"""

import csv
import os
import shutil
import unittest

import testroot
import stopwatch as sw


class Clock(object):
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class StopwatchTests(unittest.TestCase):

    def setUp(self):
        self.folder = testroot.mkdtemp()
        self.csv = os.path.join(self.folder, 'timings.csv')
        self.clock = Clock()
        self.watch = sw.Watch(machine='test-mac', csv_path=self.csv, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self.folder)

    def test_marker_is_exact(self):
        self.assertEqual(sw.MARKER, '--- timing, do not read aloud ---')

    def test_block_lists_steps_and_camera_tries(self):
        self.watch.begin('0004', 1.2)
        self.watch.set_model('haiku')
        self.watch.camera_list(0.36)
        self.watch.camera_try(0, 'dark, closed lid', photo_s=4.9, brightness=1.4)
        self.watch.camera_try(1, 'ok', photo_s=4.8, brightness=124.6, describe_s=11.9)
        self.watch.image_upload(2.9)
        self.clock.now += 25
        block = self.watch.block()
        self.assertTrue(block.startswith(sw.MARKER + '\n'))
        for line in ['machine: test-mac', 'model: haiku', 'detect: 1.2 s', 'camera list: 0.4 s',
                     'camera 0: dark, closed lid (photo 4.9 s, brightness 1.4)',
                     'camera 1: ok (photo 4.8 s, brightness 124.6, describe 11.9 s)',
                     'total before description upload: 25.0 s']:
            self.assertIn(line, block)

    def test_block_has_no_description_text(self):
        self.watch.begin('0004', 0)
        self.watch.camera_try(0, 'ok', describe_s=1)
        self.assertNotIn('HELLO', self.watch.block())

    def test_finish_writes_one_csv_row_with_header(self):
        self.watch.begin('0004', 1.0)
        self.watch.set_model('sonnet')
        self.watch.camera_list(0.3)
        self.watch.camera_try(1, 'ok', photo_s=4.0, brightness=100.0, describe_s=10.0)
        self.watch.image_upload(1.5)
        self.clock.now += 20
        self.watch.finish('ok', 1.1)
        with open(self.csv) as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(list(row.keys()), sw.COLUMNS)
        self.assertEqual(row['request'], '0004')
        self.assertEqual(row['machine'], 'test-mac')
        self.assertEqual(row['model'], 'sonnet')
        self.assertEqual(row['outcome'], 'ok')
        self.assertEqual(row['describe_upload_s'], '1.10')
        self.assertEqual(row['total_s'], '20.00')

    def test_second_request_appends_without_second_header(self):
        for number in ('0004', '0005'):
            self.watch.begin(number, 0)
            self.watch.finish('error', 0.5)
        with open(self.csv) as handle:
            lines = handle.read().splitlines()
        self.assertEqual(len(lines), 3)  # header plus two rows
        self.assertEqual(lines[0].split(',')[0], 'when')

    def test_csv_holds_no_whiteboard_text(self):
        self.watch.begin('0004', 0)
        self.watch.camera_try(0, 'ok', describe_s=1)
        self.watch.finish('ok', 0.2)
        with open(self.csv) as handle:
            self.assertNotIn('HELLO', handle.read())

    def test_no_csv_path_keeps_rows_in_memory(self):
        watch = sw.Watch(machine='m', clock=self.clock)
        watch.begin('0004', 0)
        watch.finish('ok', 0.1)
        self.assertEqual(len(watch.rows), 1)
        self.assertFalse(os.path.exists(self.csv))

    def test_image_upload_is_not_in_the_block_only_in_the_csv(self):
        self.watch.begin('0004', 0)
        self.watch.image_upload(2.5)
        self.assertNotIn('image upload', self.watch.block())
        self.watch.finish('ok', 0.4)
        self.assertEqual(self.watch.rows[0]['image_upload_s'], '2.50')


if __name__ == '__main__':
    unittest.main()
