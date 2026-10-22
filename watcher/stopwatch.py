"""Stopwatch: times each step of one request.

The timing block goes at the end of every description, below MARKER. The final upload
of the description is not in the block (it is written to the CSV log only). The CSV has
no whiteboard content: machine name, step times, camera indices and results, model.
Standard library only, Python 3.9.
"""

import csv
import os
import socket
import time

MARKER = '--- timing, do not read aloud ---'
COLUMNS = ['when', 'request', 'machine', 'model', 'outcome', 'detect_s', 'camera_list_s',
           'tries', 'image_upload_s', 'describe_upload_s', 'total_s']


def machine_name():
    return socket.gethostname()


class Watch(object):
    """Collects the timings of one request at a time. csv_path None: keep them in memory only."""

    def __init__(self, machine=None, csv_path=None, clock=time.time):
        self.machine = machine or machine_name()
        self.csv_path = csv_path
        self.clock = clock
        self.rows = []  # finished rows, kept for tests and for the log
        self.begin('-', 0.0)

    def begin(self, request, detect_s):
        self.request = request
        self.detect_s = detect_s
        self.started = self.clock()
        self.model = ''
        self.camera_list_s = None
        self.tries = []          # (index, result, photo_s, brightness, describe_s)
        self.image_upload_s = None

    def camera_list(self, seconds):
        self.camera_list_s = seconds

    def camera_try(self, index, result, photo_s=None, brightness=None, describe_s=None):
        self.tries.append((index, one_line(result), photo_s, brightness, describe_s))

    def image_upload(self, seconds):
        self.image_upload_s = seconds

    def set_model(self, model):
        self.model = model

    def elapsed(self):
        return self.clock() - self.started

    def block(self):
        """Timing block for the end of the description (without the final description upload)."""
        lines = [MARKER, 'machine: %s' % self.machine, 'model: %s' % self.model,
                 'detect: %s' % secs(self.detect_s), 'camera list: %s' % secs(self.camera_list_s)]
        for index, result, photo_s, brightness, describe_s in self.tries:
            extra = ['photo %s' % secs(photo_s)]
            if brightness is not None:
                extra.append('brightness %.1f' % brightness)
            if describe_s is not None:
                extra.append('describe %s' % secs(describe_s))
            lines.append('camera %d: %s (%s)' % (index, result, ', '.join(extra)))
        lines.append('image upload: %s' % secs(self.image_upload_s))
        lines.append('total before description upload: %s' % secs(self.elapsed()))
        return '\n'.join(lines) + '\n'

    def finish(self, outcome, describe_upload_s):
        """Close the request: keep the row, append it to the CSV log if one is set."""
        tries = '; '.join('%d:%s:%s:%s:%s' % (i, r, secs(p, bare=True), b_text(b), secs(d, bare=True))
                          for i, r, p, b, d in self.tries)
        row = {
            'when': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.clock())),
            'request': self.request, 'machine': self.machine, 'model': self.model,
            'outcome': outcome, 'detect_s': secs(self.detect_s, bare=True),
            'camera_list_s': secs(self.camera_list_s, bare=True), 'tries': tries,
            'image_upload_s': secs(self.image_upload_s, bare=True),
            'describe_upload_s': secs(describe_upload_s, bare=True),
            'total_s': secs(self.elapsed(), bare=True),
        }
        self.rows.append(row)
        if self.csv_path:
            write_row(self.csv_path, row)
        return row


def secs(value, bare=False):
    if value is None:
        return '' if bare else '-'
    return ('%.2f' if bare else '%.1f s') % value


def b_text(value):
    return '' if value is None else '%.1f' % value


def one_line(text):
    return ' '.join(str(text).split())


def write_row(path, row):
    new = not os.path.exists(path)
    with open(path, 'a', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        if new:
            writer.writeheader()
        writer.writerow(row)
