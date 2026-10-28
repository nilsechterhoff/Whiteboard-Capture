"""Picture facts: width, height and size of one photo, for the top line of each description.

The size is read from the header and the byte count, no subprocess and no extra file. The byte
count is the size os.path.getsize gives for the saved image. Standard library only, Python 3.9.
"""

import struct
import time

SOF_MARKERS = frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}  # start-of-frame, not DHT/JPG/DAC
STANDALONE = frozenset([0x01] + list(range(0xD0, 0xD8)))        # markers without a length


def dimensions(data):
    """(width, height) from the JPEG header, or None if there is no frame header before the scan."""
    if data[:2] != b'\xff\xd8':
        return None
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte before a marker
            i += 1
        elif marker in SOF_MARKERS:
            if i + 9 > len(data):
                return None
            height, width = struct.unpack('>HH', data[i + 5:i + 9])
            return width, height
        elif marker == 0xDA:  # start of scan: the frame header has come before it
            return None
        elif marker in STANDALONE:
            i += 2
        else:
            i += 2 + struct.unpack('>H', data[i + 2:i + 4])[0]
    return None


def line(photo):
    """(one line for the top of the description, duration in ms). Pure Python, no subprocess."""
    started = time.perf_counter()
    size = dimensions(photo)
    text = 'picture: %dx%d, %d KB' % (size[0], size[1], round(len(photo) / 1024)) if size \
        else 'picture: size unknown, %d KB' % round(len(photo) / 1024)
    return text, (time.perf_counter() - started) * 1000.0
