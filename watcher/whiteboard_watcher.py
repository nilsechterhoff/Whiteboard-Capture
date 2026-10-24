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


class DarkFrameError(CameraError):
    """Near-black frame (closed lid, or not warmed up yet). The camera is retried once."""
    pass


class DescribeError(Exception):
    pass


def request_path(name):
    return '/Requests/' + name


def image_path(number):
    return '/Images/image-%s.jpg' % number


def description_path(number):
    return '/Descriptions/description-%s.md' % number


def parse_request(text, number, models, default_model):
    """Parse the flat 'name: value' lines of a request. Reject anything else.

    `models` maps the allowed short names (from the config file) to model IDs.
    A request without a model field gets `default_model`.
    """
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
    unknown = sorted(set(fields) - set(ALLOWED) - set(['request', 'model']))
    if unknown:
        raise RequestError('unknown field: %s' % unknown[0])
    if fields.get('request') != number:
        raise RequestError('request field must be "%s"' % number)
    for key, allowed in sorted(ALLOWED.items()):
        if key in fields and fields[key] not in allowed:
            raise RequestError('%s: invalid value "%s"' % (key, fields[key]))
    if 'model' not in fields:
        fields['model'] = default_model
    elif fields['model'] not in models:
        raise RequestError('model: invalid value "%s"; allowed: %s' % (
            fields['model'], ', '.join(sorted(models))))
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


def render_error(number, reasons):
    lines = ['status: error', 'request: "%s"' % number]
    lines += ['reason: %s' % ' '.join(str(reason).split()) for reason in reasons]
    return '\n'.join(lines) + '\n'


def render_ok(number, fields, body):
    others = ', '.join('%s=%s' % (k, fields[k]) for k in sorted(fields) if k != 'request')
    lines = ['status: ok', 'request: "%s"' % number, 'fields: %s' % (others or 'none')]
    if fields.get('mode') == 'diff':
        lines.append('note: mode diff is not supported yet; this is a snapshot')
    return '\n'.join(lines) + '\n\n' + body.strip() + '\n'


def write_description(store, watch, number, text):
    """Upload the description last. Returns the upload time (CSV log only, not in the block)."""
    started = watch.clock()
    publish(store, description_path(number), text.encode('utf-8'))
    return watch.clock() - started


def fail(store, watch, number, reasons):
    """One error description for this request: the reasons, then the timing block."""
    text = render_error(number, reasons) + '\n' + watch.block()
    upload_s = write_description(store, watch, number, text)
    watch.finish('error', upload_s)


REOPENS = 2  # after a dark frame: close, reopen at once, up to this many times


def capture_once_or_retry_dark(cameras, watch, index):
    """One photo from `index`. A dark frame makes the camera be reopened at once, up to
    REOPENS times. Returns (photo, None) or (None, error). Every try goes to the timing block.
    """
    error = None
    for attempt in range(REOPENS + 1):
        try:
            return cameras.capture(index), None
        except CameraError as err:
            info = dict(getattr(cameras, 'last', {}))
            label = err if attempt == 0 else 'reopen %d: %s' % (attempt, err)
            watch.camera_try(index, label, info.get('photo_s'), info.get('brightness'))
            error = err
            if not isinstance(err, DarkFrameError):
                break
    return None, error


def handle_request(store, cameras, describer, memory, watch, settings, name):
    """Try the cameras one at a time (each at most once). Write the image and description
    of the first camera that shows a whiteboard, or one error description listing every try.
    """
    number = REQUEST_NAME.match(name).group(1)
    try:
        fields = parse_request(store.read_text(request_path(name)), number,
                               settings['models'], settings['default_model'])
    except ValueError as err:
        fail(store, watch, number, ['request: %s' % err])
        return
    watch.set_model(fields['model'])
    started = watch.clock()
    try:
        devices = cameras.list()
    except CameraError as err:
        watch.camera_list(watch.clock() - started)
        fail(store, watch, number, ['camera: %s' % err])
        return
    watch.camera_list(watch.clock() - started)
    reasons = []
    for index in camera_order([i for i, _ in devices], memory.index()):
        photo, error = capture_once_or_retry_dark(cameras, watch, index)
        if photo is None:
            reasons.append('camera %d: %s' % (index, error))
            continue
        info = dict(getattr(cameras, 'last', {}))
        started = watch.clock()
        try:
            is_board, body = split_answer(describer.describe(photo, fields))
        except DescribeError as err:
            describe_s = watch.clock() - started
            watch.camera_try(index, 'describe error: %s' % err, info.get('photo_s'),
                             info.get('brightness'), describe_s)
            reasons.append('camera %d: describe: %s' % (index, err))
            continue
        describe_s = watch.clock() - started
        if not is_board:
            watch.camera_try(index, 'not a whiteboard', info.get('photo_s'),
                             info.get('brightness'), describe_s)
            reasons.append('camera %d: not a whiteboard' % index)
            continue
        if not body:
            watch.camera_try(index, 'describe: empty description', info.get('photo_s'),
                             info.get('brightness'), describe_s)
            reasons.append('camera %d: describe: empty description' % index)
            continue
        watch.camera_try(index, 'ok', info.get('photo_s'), info.get('brightness'), describe_s)
        started = watch.clock()
        publish(store, image_path(number), photo)
        watch.image_upload(watch.clock() - started)
        text = render_ok(number, fields, body) + '\n' + watch.block()
        upload_s = write_description(store, watch, number, text)
        memory.remember(index)
        watch.finish('ok', upload_s)
        return
    fail(store, watch, number, reasons or ['camera: no camera listed'])


def process_pending(store, cameras, describer, memory, watch, now, settings,
                    max_age=MAX_REQUEST_AGE):
    """Close every request that has no description yet, oldest first.

    - description exists: nothing to do
    - image exists, no description: the run was interrupted; close with an error
    - request older than max_age (e.g. after a Mac sleep): close with "expired", no photo
    - otherwise: try the cameras and describe

    An upload that fails (network) leaves no final file behind, so the request
    is simply tried again on the next run.
    """
    handled = []
    try:
        names = sorted(n for n in store.list_names('/Requests') if REQUEST_NAME.match(n))
    except OSError:
        return handled  # no network: try again on the next pass, the service keeps running
    for name in names:
        number = REQUEST_NAME.match(name).group(1)
        if store.exists(description_path(number)):
            continue
        try:
            modified = store.modified(request_path(name))
            watch.begin(number, now - modified)
            if store.exists(image_path(number)):
                fail(store, watch, number, ['interrupted before the description was written'])
            elif now - modified > max_age:
                fail(store, watch, number, ['expired'])
            else:
                handle_request(store, cameras, describer, memory, watch, settings, name)
                handled.append(number)
        except OSError:
            continue
    return handled
