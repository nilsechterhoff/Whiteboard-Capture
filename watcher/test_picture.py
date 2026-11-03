"""Tests for picture facts: size and dimensions from the JPEG header, no subprocess, under 10 ms.

Run: cd watcher && python3 -m unittest -v test_picture
"""

import struct
import subprocess
import time
import unittest
from unittest import mock

import picture


def jpeg(width, height, body=b'', sof=0xC0):
    """A minimal JPEG header: SOI, an APP0 segment, a frame header, then a scan with `body`."""
    app0 = b'\xff\xe0' + struct.pack('>H', 16) + b'JFIF\x00' + b'\x01\x01\x00\x00\x01\x00\x01\x00\x00'
    frame = b'\xff' + bytes([sof]) + struct.pack('>HBHHB', 17, 8, height, width, 3) + b'\x00' * 9
    scan = b'\xff\xda' + struct.pack('>H', 2) + body + b'\xff\xd9'
    return b'\xff\xd8' + app0 + frame + scan


class DimensionTests(unittest.TestCase):

    def test_reads_width_and_height_from_the_frame_header(self):
        self.assertEqual(picture.dimensions(jpeg(1920, 1080)), (1920, 1080))

    def test_progressive_frame_header_is_read_too(self):
        self.assertEqual(picture.dimensions(jpeg(640, 480, sof=0xC2)), (640, 480))

    def test_not_a_jpeg_gives_none(self):
        self.assertIsNone(picture.dimensions(b'saved-photo'))
        self.assertIsNone(picture.dimensions(b''))

    def test_no_frame_header_before_the_scan_gives_none(self):
        self.assertIsNone(picture.dimensions(b'\xff\xd8' + b'\xff\xda\x00\x02' + b'\x00' * 20))

    def test_a_truncated_frame_header_gives_none(self):
        self.assertIsNone(picture.dimensions(b'\xff\xd8\xff\xc0\x00\x11\x08'))

    def test_huffman_table_is_not_taken_for_a_frame_header(self):
        dht = b'\xff\xc4' + struct.pack('>H', 4) + b'\x00\x00'
        self.assertEqual(picture.dimensions(b'\xff\xd8' + dht + jpeg(800, 600)[2:]), (800, 600))


class LineTests(unittest.TestCase):

    def test_line_has_dimensions_and_size_in_kilobytes(self):
        photo = jpeg(1920, 1080, body=b'\x00' * (158 * 1024))
        text, ms = picture.line(photo)
        self.assertEqual(text, 'picture: 1920x1080, %d KB' % round(len(photo) / 1024))
        self.assertGreaterEqual(ms, 0)

    def test_unknown_size_still_gives_a_line(self):
        text, _ = picture.line(b'saved-photo')
        self.assertEqual(text, 'picture: size unknown, 0 KB')

    def test_starts_no_subprocess(self):
        with mock.patch.object(subprocess, 'Popen', side_effect=AssertionError('subprocess started')), \
                mock.patch.object(subprocess, 'run', side_effect=AssertionError('subprocess started')):
            text, _ = picture.line(jpeg(1920, 1080))
        self.assertIn('1920x1080', text)

    def test_module_does_not_import_subprocess(self):
        self.assertNotIn('subprocess', vars(picture))

    def test_takes_under_10_ms_for_a_photo_sized_buffer(self):
        photo = jpeg(1920, 1080, body=b'\x12' * (160 * 1024))
        started = time.perf_counter()
        for _ in range(10):
            picture.line(photo)
        per_call_ms = (time.perf_counter() - started) * 1000.0 / 10
        self.assertLess(per_call_ms, 10.0)


if __name__ == '__main__':
    unittest.main()
