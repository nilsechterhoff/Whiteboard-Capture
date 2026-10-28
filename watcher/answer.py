"""The answer of the image agent: measured criteria, a conclusion, and the description (BL-034).

The agent answers with one line per criterion, then 'is_board_camera', then the description
(only if the conclusion is yes). The watcher re-checks the criteria itself: the conclusion is
not trusted, only logged next to the measured values. Standard library only, Python 3.9.
"""

import re

LINE = re.compile(r'^\s*(whiteboard_visible|board_fill_percent|is_board_camera)\s*:\s*(.*?)\s*$',
                  re.IGNORECASE)
YES_NO = {'yes': True, 'no': False}


class Answer(object):
    """The parsed answer. `visible` and `fill` are measured; `camera` is the agent's conclusion."""

    def __init__(self, visible, fill, camera, body):
        self.visible = visible  # bool
        self.fill = fill        # int 0 to 100, or None if missing or unparsable
        self.camera = camera    # bool, or None if the agent gave no conclusion
        self.body = body        # description; empty when the agent did not describe


def parse(text):
    """Parse the header lines (any order, case-insensitive), then the rest is the description.
    Raises ValueError if the whiteboard_visible line is missing or not yes or no."""
    values = {}
    lines = text.strip().splitlines()
    i = 0
    while i < len(lines):
        match = LINE.match(lines[i])
        if match:
            values[match.group(1).lower()] = match.group(2).lower()
        elif lines[i].strip() or not values:  # the first line that is not a header starts the body
            break
        i += 1
    if 'whiteboard_visible' not in values:
        raise ValueError('answer has no whiteboard_visible line')
    visible = YES_NO.get(values['whiteboard_visible'])
    if visible is None:
        raise ValueError('whiteboard_visible is not yes or no (got %r)' % values['whiteboard_visible'])
    fill = _fill(values.get('board_fill_percent'))
    camera = YES_NO.get(values.get('is_board_camera'))
    body = '\n'.join(lines[i:]).strip()
    return Answer(visible, fill, camera, body)


def _fill(value):
    if value is None:
        return None
    match = re.match(r'^(\d{1,3})\s*%?$', value)
    if not match or int(match.group(1)) > 100:
        return None
    return int(match.group(1))


def verdict(parsed, min_fill):
    """(passes, label) from the measured values. The watcher's own rule, not the agent's conclusion."""
    if not parsed.visible:
        return False, 'not a whiteboard'
    if min_fill and parsed.fill is None:
        return False, 'board fill missing'
    if min_fill and parsed.fill < min_fill:
        return False, 'board fill %d below %d' % (parsed.fill, min_fill)
    if not parsed.body:
        return False, 'describe: empty description'
    return True, 'ok'
