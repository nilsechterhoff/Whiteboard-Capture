"""MVP B watcher core: read a request, find the whiteboard camera, describe, write the result.

No Dropbox, camera or Claude code here. Those are passed in (see the fakes in
test_whiteboard_watcher.py), so the logic is tested without network or hardware.
Python 3.9 standard library only.
"""

import logging
import re

import failed_photos
import time

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


def split_fill(body):
    """Take the 'fill: NN' line out of the describe body (it must be among the first two lines).
    Returns (fill as int 0 to 100, or None if missing or unparsable; body without that line).
    A missing or unparsable value is None: with the check on, it counts as a failed check."""
    lines = body.splitlines()
    for i, line in enumerate(lines[:2]):
        match = re.match(r'^\s*fill\s*:\s*(\d{1,3})\s*%?\s*$', line, re.IGNORECASE)
        if match:
            value = int(match.group(1))
            rest = '\n'.join(lines[:i] + lines[i + 1:]).strip()
            return (value if value <= 100 else None), rest
    return None, body


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
    lines += ['reason: %s' % ' '.join(str(reason).split()) for reason in reasons]
    return '\n'.join(lines) + '\n'


def render_ok(number, fields, body):
    others = ', '.join('%s=%s' % (k, fields[k]) for k in sorted(fields) if k != 'request')
    lines = ['status: ok', 'request: "%s"' % number, 'fields: %s' % (others or 'none')]
    if fields.get('mode') == 'diff':
        lines.append('note: mode diff is not supported yet; this is a snapshot')
    return '\n'.join(lines) + '\n\n' + body.strip() + '\n'


STATUS_PATH = '/status.md'
CODES = ('IMAGE_UPLOAD_FAILED', 'DESCRIPTION_UPLOAD_FAILED', 'CAMERA_FAILED', 'DESCRIBE_FAILED',
         'UNKNOWN_ERROR')
MESSAGES = {
    'IMAGE_UPLOAD_FAILED': 'The description is delivered, but the photo could not be uploaded; the local copy is kept.',
    'DESCRIPTION_UPLOAD_FAILED': 'The description could not be uploaded yet; it will be retried from the local copy.',
    'CAMERA_FAILED': 'No camera gave a usable photo of the whiteboard.',
    'DESCRIBE_FAILED': 'The photo was taken, but the describe step did not confirm a whiteboard.',
    'UNKNOWN_ERROR': 'An unexpected error stopped this request; the local files are kept.',
}


def write_description(store, watch, number, text):
    """Upload the description. Returns the upload time (CSV log only, not in the block)."""
    started = watch.clock()
    publish(store, description_path(number), text.encode('utf-8'))
    return watch.clock() - started


def upload_image(store, watch, number, photo, attempts):
    """Upload the photo, up to `attempts` times. Returns True if it is in Dropbox."""
    for _ in range(attempts):
        started = watch.clock()
        try:
            publish(store, image_path(number), photo)
        except OSError:
            continue
        watch.image_upload(watch.clock() - started)
        return True
    return False


def write_status(store, watch, number, ok, delivered, saved, code=None, message=None):
    """status.md in the app folder root, rewritten at the end of every request.
    A failure to write it is not raised: the voice agent then sees the previous status."""
    lines = ['status: %s' % ('ok' if ok else 'error'),
             'time: %s' % time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(watch.clock())),
             'last request: %s' % number,
             'description delivered: %s' % ('yes' if delivered else 'no'),
             'image saved: %s' % ('yes' if saved else 'no')]
    if code:
        lines += ['code: %s' % code, 'message: %s' % one_line(message or MESSAGES[code])]
    try:
        # Uploaded straight to the final name: Dropbox replaces the file atomically, so a reader
        # sees the old or the new status, never a half file. (move would refuse an existing file.)
        store.upload(STATUS_PATH, ('\n'.join(lines) + '\n').encode('utf-8'))
    except OSError:
        pass


def deliver(store, watch, results, number, photo, text):
    """Description first, then the image. Always ends with a status file.

    A failed description upload keeps the local copy and is retried on the next pass
    (no new photo). A failed image upload gets one retry; then the request is done
    with status error, and the local photo is kept.
    """
    try:
        upload_s = write_description(store, watch, number, text)
    except OSError:
        watch.finish('description_upload_failed', None)
        write_status(store, watch, number, False, False, False, 'DESCRIPTION_UPLOAD_FAILED')
        return
    saved = upload_image(store, watch, number, photo, attempts=2)
    results.mark_done(number)
    if not saved:
        watch.finish('image_upload_failed', upload_s)
        write_status(store, watch, number, False, True, False, 'IMAGE_UPLOAD_FAILED')
        return
    watch.finish('ok', upload_s)
    write_status(store, watch, number, True, True, True)


def resume_image(store, watch, results, number):
    """Description is in Dropbox but the image is not: one more upload from the local copy.
    The photo is never taken again."""
    local = results.load(number)
    saved = local is not None and upload_image(store, watch, number, local[0], attempts=1)
    results.mark_done(number)
    if saved:
        write_status(store, watch, number, True, True, True)
    else:
        write_status(store, watch, number, False, True, False, 'IMAGE_UPLOAD_FAILED')


def fail(store, watch, results, number, reasons, code, message=None):
    """One error description for this request (the reasons, then the timing block),
    and a status with the code. The request is done."""
    text = render_error(number, reasons) + '\n' + watch.block()
    try:
        upload_s = write_description(store, watch, number, text)
    except OSError:
        upload_s = None
        code = 'DESCRIPTION_UPLOAD_FAILED'
    results.mark_done(number)
    watch.finish('error', upload_s)
    write_status(store, watch, number, False, upload_s is not None, False, code, message)


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


LOG = logging.getLogger('whiteboard')


def board_passes(is_board, fill, min_fill):
    """A camera passes only with a yes answer and, if the check is on, a fill at or above the setting."""
    if not is_board:
        return False
    return min_fill == 0 or (fill is not None and fill >= min_fill)


def handle_request(store, cameras, describer, memory, watch, results, settings, name):
    """Photo and describe for one request. The result is kept locally before any upload."""
    number = REQUEST_NAME.match(name).group(1)
    try:
        fields = parse_request(store.read_text(request_path(name)), number,
                               settings['models'], settings['default_model'])
    except ValueError as err:
        fail(store, watch, results, number, ['request: %s' % err], 'UNKNOWN_ERROR',
             'The request file is not valid: %s' % one_line(err))
        return
    watch.set_model(fields['model'])
    started = watch.clock()
    try:
        devices = cameras.list()
    except CameraError as err:
        watch.camera_list(watch.clock() - started)
        fail(store, watch, results, number, ['camera: %s' % err], 'CAMERA_FAILED')
        return
    watch.camera_list(watch.clock() - started)
    reasons = []
    rejected = []  # (camera, photo) of every try that was refused: kept for diagnosis
    described = False
    for index in camera_order([i for i, _ in devices], memory.index()):
        photo, error = capture_once_or_retry_dark(cameras, watch, index)
        if photo is None:
            reasons.append('camera %d: %s' % (index, error))
            continue
        info = dict(getattr(cameras, 'last', {}))
        started = watch.clock()
        described = True
        try:
            raw = describer.describe(photo, fields)
            is_board, body = split_answer(raw)
            fill, body = split_fill(body)
        except DescribeError as err:
            describe_s = watch.clock() - started
            watch.camera_try(index, 'describe error: %s' % err, info.get('photo_s'),
                             info.get('brightness'), describe_s)
            reasons.append('camera %d: describe: %s' % (index, err))
            continue
        describe_s = watch.clock() - started
        min_fill = settings.get('min_board_fill_percent', 0)
        LOG.info('request %s camera %d raw answer: %r; fill %s; check %s'
                 % (number, index, raw, fill, min_fill or 'off'))
        if not board_passes(is_board, fill, min_fill):
            label = 'not a whiteboard' if not is_board else (
                'board fill %s below %d' % (fill, min_fill) if fill is not None
                else 'board fill missing')
            watch.camera_try(index, label, info.get('photo_s'), info.get('brightness'), describe_s)
            reasons.append('camera %d: %s' % (index, label))
            rejected.append((index, photo))
            continue
        if not body:
            watch.camera_try(index, 'describe: empty description', info.get('photo_s'),
                             info.get('brightness'), describe_s)
            reasons.append('camera %d: describe: empty description' % index)
            rejected.append((index, photo))
            continue
        watch.camera_try(index, 'ok', info.get('photo_s'), info.get('brightness'), describe_s)
        text = render_ok(number, fields, body) + '\n' + watch.block()
        results.save(number, photo, text)  # local copy first: a restart never takes a new photo
        memory.remember(index)
        deliver(store, watch, results, number, photo, text)
        return
    if rejected:
        try:
            failed_photos.save_failed(settings.get('failed_photos_dir', ''), number, rejected,
                                      settings.get('failed_photos_keep', 0))
        except OSError as err:
            LOG.info('request %s: could not keep the failed photos: %s' % (number, err))
    code = 'DESCRIBE_FAILED' if described else 'CAMERA_FAILED'
    fail(store, watch, results, number, reasons or ['camera: no camera listed'], code)


def process_pending(store, cameras, describer, memory, watch, results, now, settings,
                    max_age=MAX_REQUEST_AGE):
    """Close every open request, oldest first. Each request ends with a status file.

    - done (local marker): nothing to do
    - description in Dropbox, image missing: one image upload from the local copy
    - local copy but no description (crash after describe): upload the description from it
    - image in Dropbox but no description (older run, before the new order): error
    - request older than max_age (e.g. after a Mac sleep): error "expired", no photo
    - otherwise: photo, describe, then deliver

    A network error (OSError) is not an outcome: the request stays open and is tried again.
    Any other unexpected exception ends the request with UNKNOWN_ERROR, so it is never
    processed twice and always gets a status.
    """
    handled = []
    try:
        names = sorted(n for n in store.list_names('/Requests') if REQUEST_NAME.match(n))
    except OSError:
        return handled  # no network: try again on the next pass, the service keeps running
    for name in names:
        number = REQUEST_NAME.match(name).group(1)
        try:
            if results.is_done(number):
                continue
            if store.exists(description_path(number)):
                if store.exists(image_path(number)):
                    results.mark_done(number)  # already complete (older run): no status needed
                else:
                    resume_image(store, watch, results, number)
                continue
            modified = store.modified(request_path(name))
            watch.begin(number, now - modified)
            local = results.load(number)
            if local is not None and local[0] is None:
                results.mark_done(number)
                write_status(store, watch, number, False, False, False, 'UNKNOWN_ERROR',
                             'The local photo is missing, so the request cannot be finished.')
                continue
            if local is not None:
                deliver(store, watch, results, number, local[0], local[1])
                continue
            if store.exists(image_path(number)):
                fail(store, watch, results, number,
                     ['interrupted before the description was written'], 'UNKNOWN_ERROR',
                     'An earlier run stopped before the description was written.')
            elif now - modified > max_age:
                fail(store, watch, results, number, ['expired'], 'UNKNOWN_ERROR',
                     'The request was too old when the watcher saw it, so no photo was taken.')
            else:
                handle_request(store, cameras, describer, memory, watch, results, settings, name)
                handled.append(number)
        except OSError:
            continue
        except Exception as err:
            results.mark_done(number)
            write_status(store, watch, number, False, False, False, 'UNKNOWN_ERROR',
                         'An unexpected error stopped this request (%s); the local files are kept.'
                         % err.__class__.__name__)
    return handled
