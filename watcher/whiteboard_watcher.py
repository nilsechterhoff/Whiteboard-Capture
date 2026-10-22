"""MVP B watcher core: read a request, find the whiteboard camera, describe, write the result.

No Dropbox, camera or Claude code here. Those are passed in (see the fakes in
test_whiteboard_watcher.py), so the logic is tested without network or hardware.
Python 3.9 standard library only.
"""

import re

REQUEST_NAME = re.compile(r'^request-(\d{4})\.yaml$')
FIELD_LINE = re.compile(r'^([a-z_]+):[ \t]+(.+)$')
MAX_REQUEST_AGE = 120  # seconds; older requests are closed as "expired", no photo
ALLOWED = {
    'marker_color': ('black', 'red', 'green', 'blue'),
    'region_v': ('top', 'middle', 'bottom'),
    'region_h': ('left', 'center', 'right'),
    'mode': ('snapshot', 'diff'),
}
WHITEBOARD_YES = 'whiteboard: yes'
WHITEBOARD_NO = 'whiteboard: no'


class RequestError(ValueError):
    pass


class CameraError(Exception):
    pass


class DescribeError(Exception):
    pass


def request_path(name):
    return '/Requests/' + name


def image_path(number):
    return '/Images/image-%s.jpg' % number


def description_path(number):
    return '/Descriptions/description-%s.md' % number


def parse_request(text, number):
    """Parse the flat 'name: value' lines of a request. Reject anything else."""
    fields = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        match = FIELD_LINE.match(line)
        if not match:
            raise RequestError('not a "name: value" line: %s' % line)
        key, value = match.group(1), match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
            value = value[1:-1]
        if key in fields:
            raise RequestError('duplicate field: %s' % key)
        fields[key] = value
    unknown = sorted(set(fields) - set(ALLOWED) - set(['request']))
    if unknown:
        raise RequestError('unknown field: %s' % unknown[0])
    if fields.get('request') != number:
        raise RequestError('request field must be "%s"' % number)
    for key, allowed in sorted(ALLOWED.items()):
        if key in fields and fields[key] not in allowed:
            raise RequestError('%s: invalid value "%s"' % (key, fields[key]))
    return fields


def split_answer(text):
    """Split a describe answer whose first line is 'whiteboard: yes' or 'whiteboard: no'."""
    lines = text.strip().splitlines()
    if not lines:
        raise DescribeError('empty answer')
    first = lines[0].strip().lower()
    body = '\n'.join(lines[1:]).strip()
    if first == WHITEBOARD_YES:
        return True, body
    if first == WHITEBOARD_NO:
        return False, body
    raise DescribeError('answer did not start with a whiteboard line')


def camera_order(indices, remembered):
    """Remembered index first (only if listed), then the rest in listing order. No repeats."""
    order = list(indices)
    if remembered in order:
        order.remove(remembered)
        order.insert(0, remembered)
    return order


def publish(store, path, data):
    """Write to a hidden temporary name, then rename: readers never see a half file."""
    folder, name = path.rsplit('/', 1)
    temp = '%s/.%s.partial' % (folder, name)
    store.upload(temp, data)
    store.move(temp, path)


def one_line(text):
    return ' '.join(str(text).split())


def render_error(number, reasons):
    lines = ['status: error', 'request: "%s"' % number]
    lines += ['reason: %s' % one_line(reason) for reason in reasons]
    return '\n'.join(lines) + '\n'


def render_ok(number, fields, body):
    others = ', '.join('%s=%s' % (k, fields[k]) for k in sorted(fields) if k != 'request')
    lines = ['status: ok', 'request: "%s"' % number, 'fields: %s' % (others or 'none')]
    if fields.get('mode') == 'diff':
        lines.append('note: mode diff is not supported yet; this is a snapshot')
    return '\n'.join(lines) + '\n\n' + body.strip() + '\n'


def fail(store, number, reasons):
    publish(store, description_path(number), render_error(number, reasons).encode('utf-8'))


def handle_request(store, cameras, describer, memory, name):
    """Try the cameras one at a time (each at most once). Write the image and description
    of the first camera that shows a whiteboard, or one error description listing every try.
    """
    number = REQUEST_NAME.match(name).group(1)
    try:
        fields = parse_request(store.read_text(request_path(name)), number)
    except ValueError as err:
        fail(store, number, ['request: %s' % err])
        return
    try:
        devices = cameras.list()
    except CameraError as err:
        fail(store, number, ['camera: %s' % err])
        return
    reasons = []
    for index in camera_order([i for i, _ in devices], memory.index()):
        try:
            photo = cameras.capture(index)
        except CameraError as err:
            reasons.append('camera %d: %s' % (index, err))
            continue
        try:
            is_board, body = split_answer(describer.describe(photo, fields))
        except DescribeError as err:
            reasons.append('camera %d: describe: %s' % (index, err))
            continue
        if not is_board:
            reasons.append('camera %d: not a whiteboard' % index)
            continue
        if not body:
            reasons.append('camera %d: describe: empty description' % index)
            continue
        publish(store, image_path(number), photo)
        publish(store, description_path(number), render_ok(number, fields, body).encode('utf-8'))
        memory.remember(index)
        return
    fail(store, number, reasons or ['camera: no camera listed'])


def process_pending(store, cameras, describer, memory, now, max_age=MAX_REQUEST_AGE):
    """Close every request that has no description yet, oldest first.

    - description exists: nothing to do
    - image exists, no description: the run was interrupted; close with an error
    - request older than max_age (e.g. after a Mac sleep): close with "expired", no photo
    - otherwise: try the cameras and describe

    An upload that fails (network) leaves no final file behind, so the request
    is simply tried again on the next run.
    """
    handled = []
    names = sorted(n for n in store.list_names('/Requests') if REQUEST_NAME.match(n))
    for name in names:
        number = REQUEST_NAME.match(name).group(1)
        if store.exists(description_path(number)):
            continue
        try:
            if store.exists(image_path(number)):
                fail(store, number, ['interrupted before the description was written'])
            elif now - store.modified(request_path(name)) > max_age:
                fail(store, number, ['expired'])
            else:
                handle_request(store, cameras, describer, memory, name)
                handled.append(number)
        except OSError:
            continue
    return handled
