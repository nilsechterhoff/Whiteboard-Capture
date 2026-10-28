"""The answer of the image agent: measured criteria, a conclusion, and the description (BL-034).

The agent answers with one line per criterion, then 'is_board_camera', then the description
(only if the conclusion is yes). The watcher re-checks the criteria itself: the conclusion is
not trusted, only logged next to the measured values. Standard library only, Python 3.9.
"""

import re

LINE = re.compile(r'^\s*(whiteboard_visible|board_fill_percent|is_board_camera|challenges_if_any)\s*:\s*(.*?)\s*$',
                  re.IGNORECASE)
YES_NO = {'yes': True, 'no': False}


class Answer(object):
    """The parsed answer. `visible` and `fill` are measured; `camera` is the agent's conclusion."""

    def __init__(self, visible, fill, camera, body, challenges=None):
        self.visible = visible  # bool
        self.fill = fill        # int 0 to 100, or None if missing or unparsable
        self.camera = camera    # bool, or None if the agent gave no conclusion
        self.body = body        # description; empty when the agent did not describe
        self.challenges = challenges or []  # obstacles, one short text each; [] for none


def parse(text):
    """Parse the header lines (any order, case-insensitive), then the rest is the description.
    Raises ValueError if the whiteboard_visible line is missing or not yes or no."""
    values = {}
    challenges = []
    listing = False  # after 'challenges_if_any:' come the '- ' lines
    lines = text.strip().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        match = LINE.match(line)
        if match and match.group(1).lower() == 'challenges_if_any':
            listing = True
            if match.group(2).lower() not in ('', 'none'):
                challenges.append(match.group(2))
        elif match:
            values[match.group(1).lower()] = match.group(2).lower()
            listing = False
        elif listing and line.strip().startswith('-'):
            challenges.append(line.strip()[1:].strip())
        elif line.strip() or not (values or listing):  # the first line that is not a header starts the body
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
    return Answer(visible, fill, camera, body, [c for c in challenges if c])


def challenges_section(challenges):
    """The challenges_if_any part of the description: 'none', or one '- ' line per obstacle."""
    if not challenges:
        return 'challenges_if_any: none'
    return 'challenges_if_any:\n' + '\n'.join('- %s' % item for item in challenges)


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
