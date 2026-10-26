"""Config checks for the watcher. Defaults live here, so every new setting has one place.

Standard library only, Python 3.9.
"""

import camera as cam

DEFAULTS = {
    'rotation_degrees': 0,
    'min_board_fill_percent': 0,  # 0 = off
    'agile_enabled': 'no',        # yes: a request may start or reuse agile mode; no: always lean
    'agile_idle_timeout_seconds': 600,
    'agile_timer_reset_events': {'request': 'yes'},
    'agile_session': 'no',                  # phase 2: yes | no
    'agile_session_restart_after_requests': 20,
    'failed_photos_keep': 5,            # 0 = off
    'failed_photos_folder': 'failed-photos',  # inside the log folder
}


def apply_defaults(config):
    for key, value in DEFAULTS.items():
        config.setdefault(key, value)
    return config


def normalize(config):
    """Old key `mode`: `mode: agile` becomes agile_enabled yes, anything else no.
    Returns the warnings to log (one per use of the old key). Never raises."""
    warnings = []
    if 'mode' in config:
        if 'agile_enabled' not in config:
            config['agile_enabled'] = 'yes' if config.get('mode') == 'agile' else 'no'
        warnings.append('config key mode is replaced by agile_enabled (set to %s); remove mode'
                        % config['agile_enabled'])
        config.pop('mode', None)
    return warnings


def agile_on(config):
    """A request may start or reuse agile mode. Lean is the base; this is only the upgrade."""
    return config.get('agile_enabled', DEFAULTS['agile_enabled']) == 'yes'


def session_on(config):
    """The long-lived describe session, only ever used while agile is allowed."""
    return agile_on(config) and config.get('agile_session', DEFAULTS['agile_session']) == 'yes'


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
    enabled = config.get('agile_enabled', DEFAULTS['agile_enabled'])
    if enabled not in ('yes', 'no'):
        errors.append('agile_enabled must be yes or no (got %r)' % (enabled,))
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
