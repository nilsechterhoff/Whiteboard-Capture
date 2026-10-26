"""Keep the photos of requests where no camera showed the board (for diagnosis).

Files: <folder>/request-NNNN-camNN.jpg, one per rejected camera try. Only the photos of the
newest `keep` requests stay; older ones are deleted. keep 0 turns this off. Standard library only.
"""

import os
import re

NAME = re.compile(r'^request-(\d{4})-cam(\d{2})\.jpg$')


def save_failed(folder, number, photos, keep):
    """photos: list of (camera index, JPEG bytes). Returns the paths written."""
    if keep <= 0 or not photos:
        return []
    os.makedirs(folder, mode=0o700, exist_ok=True)
    written = []
    for index, data in photos:
        path = os.path.join(folder, 'request-%s-cam%02d.jpg' % (number, index))
        temp = path + '.tmp'
        with open(temp, 'wb') as handle:
            handle.write(data)
        os.replace(temp, path)
        written.append(path)
    prune(folder, keep)
    return written


def prune(folder, keep):
    """Delete the files of all but the newest `keep` request numbers."""
    if keep <= 0 or not os.path.isdir(folder):
        return []
    numbers = sorted({m.group(1) for m in (NAME.match(n) for n in os.listdir(folder)) if m})
    removed = []
    for number in numbers[:-keep] if len(numbers) > keep else []:
        for name in os.listdir(folder):
            match = NAME.match(name)
            if match and match.group(1) == number:
                os.remove(os.path.join(folder, name))
                removed.append(name)
    return removed
