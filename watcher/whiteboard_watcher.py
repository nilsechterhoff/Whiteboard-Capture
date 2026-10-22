"""MVP B watcher core: read a request, take a photo, describe it, write the result.

No Dropbox, camera or Claude code here. Those are passed in (see the fakes in
test_whiteboard_watcher.py), so the logic is tested without network or hardware.
Python 3.9 standard library only.
"""

import re

REQUEST_NAME = re.compile(r'^request-(\d{4})\.yaml$')
FIELD_LINE = re.compile(r'^([a-z_]+):[ \t]+(.+)$')
ALLOWED = {
    'marker_color': ('black', 'red', 'green', 'blue'),
    'region_v': ('top', 'middle', 'bottom'),
    'region_h': ('left', 'center', 'right'),
    'mode': ('snapshot', 'diff'),
}


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


def publish(store, path, data):
    """Write to a hidden temporary name, then rename: readers never see a half file."""
    folder, name = path.rsplit('/', 1)
    temp = '%s/.%s.partial' % (folder, name)
    store.upload(temp, data)
    store.move(temp, path)


def one_line(text):
    return ' '.join(str(text).split())


def render_error(number, reason):
    return 'status: error\nrequest: "%s"\nreason: %s\n' % (number, one_line(reason))


def render_ok(number, fields, body):
    others = ', '.join('%s=%s' % (k, fields[k]) for k in sorted(fields) if k != 'request')
    lines = ['status: ok', 'request: "%s"' % number, 'fields: %s' % (others or 'none')]
    if fields.get('mode') == 'diff':
        lines.append('note: mode diff is not supported yet; this is a snapshot')
    return '\n'.join(lines) + '\n\n' + body.strip() + '\n'


def fail(store, number, reason):
    publish(store, description_path(number), render_error(number, reason).encode('utf-8'))


def handle_request(store, camera, describer, name):
    number = REQUEST_NAME.match(name).group(1)
    try:
        fields = parse_request(store.read_text(request_path(name)), number)
    except ValueError as err:
        fail(store, number, 'request: %s' % err)
        return
    try:
        photo = camera.take_photo()
    except CameraError as err:
        fail(store, number, 'camera: %s' % err)
        return
    publish(store, image_path(number), photo)
    try:
        body = describer.describe(photo, fields)
    except DescribeError as err:
        fail(store, number, 'describe: %s' % err)
        return
    if not body or not body.strip():
        fail(store, number, 'describe: empty description')
        return
    publish(store, description_path(number), render_ok(number, fields, body).encode('utf-8'))


def process_pending(store, camera, describer):
    """Handle every request that has no image and no description yet, oldest first.

    An upload that fails (network) leaves no final file behind, so the request
    is simply tried again on the next run.
    """
    handled = []
    names = sorted(n for n in store.list_names('/Requests') if REQUEST_NAME.match(n))
    for name in names:
        number = REQUEST_NAME.match(name).group(1)
        if store.exists(image_path(number)) or store.exists(description_path(number)):
            continue
        try:
            handle_request(store, camera, describer, name)
        except OSError:
            continue
        handled.append(number)
    return handled
