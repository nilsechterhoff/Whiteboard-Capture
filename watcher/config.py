"""Config checks for the watcher. Defaults live here, so every new setting has one place.

Standard library only, Python 3.9.
"""

import camera as cam

DEFAULTS = {
    'rotation_degrees': 0,
    'min_board_fill_percent': 50,  # 0 = off
    'jpeg_quality': 4,             # ffmpeg -q:v for every JPEG the watcher writes: 2 (best) to 31
    'start_offset_seconds': 0.1,            # between the stream starts of one selection
    'selection_frame_delay_seconds': 2,     # frame checked this long after its stream started
    'retry_pause_seconds': 1,               # pause between two selections
    'capture_retries': 2,                   # selections after the first one, when no frame passes
    'agile_idle_timeout_seconds': 600,
    'agile_timer_reset_events': {'request': 'yes'},
    'agile_session': 'no',                  # yes | no: long-lived describe session
    'agile_session_restart_after_requests': 20,
    'failed_photos_keep': 5,            # 0 = off
    'failed_photos_folder': 'failed-photos',  # inside the log folder
}

IGNORED_KEYS = ('agile_enabled', 'mode')  # agile is always on (ADR-0012); the keys are ignored


def apply_defaults(config):
    for key, value in DEFAULTS.items():
        config.setdefault(key, value)
    return config


def normalize(config):
    """Removes the keys that no longer do anything (IGNORED_KEYS). Returns one warning if any was present."""
    present = [key for key in IGNORED_KEYS if key in config]
    for key in present:
        config.pop(key, None)
    if not present:
        return []
    return ['config keys %s are ignored: agile is always on (ADR-0012); remove them from config.json'
            % ', '.join(present)]


def session_on(config):
    """The long-lived describe session (used together with the always-on streams)."""
    return config.get('agile_session', DEFAULTS['agile_session']) == 'yes'


def validate(config):
    """Return a list of error messages; an empty list means the config is valid."""
    errors = []
    try:
        cam.rotation_filters(config.get('rotation_degrees', DEFAULTS['rotation_degrees']))
    except ValueError as err:
        errors.append(str(err))
    fill = config.get('min_board_fill_percent', DEFAULTS['min_board_fill_percent'])
    if not isinstance(fill, int) or isinstance(fill, bool) or not 0 <= fill <= 100:
        errors.append('min_board_fill_percent must be a whole number from 0 to 100 (got %r)' % (fill,))
    for key in ('start_offset_seconds', 'selection_frame_delay_seconds', 'retry_pause_seconds'):
        value = config.get(key, DEFAULTS[key])
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            errors.append('%s must be a number, 0 or more (got %r)' % (key, value))
    quality = config.get('jpeg_quality', DEFAULTS['jpeg_quality'])
    if not isinstance(quality, int) or isinstance(quality, bool) or not 2 <= quality <= 31:
        errors.append('jpeg_quality must be a whole number from 2 to 31 (got %r)' % (quality,))
    retries = config.get('capture_retries', DEFAULTS['capture_retries'])
    if not isinstance(retries, int) or isinstance(retries, bool) or retries < 0:
        errors.append('capture_retries must be a whole number, 0 or more (got %r)' % (retries,))
    timeout = config.get('agile_idle_timeout_seconds', DEFAULTS['agile_idle_timeout_seconds'])
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
        errors.append('agile_idle_timeout_seconds must be a whole number above 0 (got %r)' % (timeout,))
    events = config.get('agile_timer_reset_events', DEFAULTS['agile_timer_reset_events'])
    if not isinstance(events, dict) or any(v not in ('yes', 'no') for v in events.values()):
        errors.append('agile_timer_reset_events must map event names to yes or no')
    session = config.get('agile_session', DEFAULTS['agile_session'])
    if session not in ('yes', 'no'):
        errors.append('agile_session must be yes or no (got %r)' % (session,))
    restart = config.get('agile_session_restart_after_requests', DEFAULTS['agile_session_restart_after_requests'])
    if not isinstance(restart, int) or isinstance(restart, bool) or restart <= 0:
        errors.append('agile_session_restart_after_requests must be a whole number above 0 (got %r)' % (restart,))
    keep = config.get('failed_photos_keep', DEFAULTS['failed_photos_keep'])
    if not isinstance(keep, int) or isinstance(keep, bool) or keep < 0:
        errors.append('failed_photos_keep must be a whole number, 0 or more (got %r)' % (keep,))
    folder = config.get('failed_photos_folder', DEFAULTS['failed_photos_folder'])
    if not isinstance(folder, str) or not folder.strip() or '/' in folder or folder in ('.', '..'):
        errors.append('failed_photos_folder must be a plain folder name (got %r)' % (folder,))
    return errors
