"""Local copy of each request's result, under the config folder: the photo and the
description text, written before any upload. A marker file says the request is done.
Standard library only, Python 3.9."""

import os


class Results(object):

    def __init__(self, folder):
        self.folder = folder

    def _dir(self, number):
        return os.path.join(self.folder, 'request-%s' % number)

    def _write(self, path, data):
        temp = path + '.tmp'
        with open(temp, 'wb') as handle:
            handle.write(data)
        os.replace(temp, path)

    def save(self, number, photo, text):
        folder = self._dir(number)
        os.makedirs(folder, mode=0o700, exist_ok=True)
        self._write(os.path.join(folder, 'image.jpg'), photo)
        self._write(os.path.join(folder, 'description.md'), text.encode('utf-8'))

    def load(self, number):
        """(photo or None, description text) if a description was saved, else None."""
        folder = self._dir(number)
        try:
            with open(os.path.join(folder, 'description.md'), 'rb') as handle:
                text = handle.read().decode('utf-8')
        except OSError:
            return None
        try:
            with open(os.path.join(folder, 'image.jpg'), 'rb') as handle:
                photo = handle.read()
        except OSError:
            photo = None
        return photo, text

    def mark_done(self, number):
        folder = self._dir(number)
        os.makedirs(folder, mode=0o700, exist_ok=True)
        self._write(os.path.join(folder, 'done'), b'')

    def is_done(self, number):
        return os.path.exists(os.path.join(self._dir(number), 'done'))
