"""Config checks for the watcher. Defaults live here, so every new setting has one place.

Standard library only, Python 3.9.
"""

import camera as cam

DEFAULTS = {
    'rotation_degrees': 0,
    'min_board_fill_percent': 0,  # 0 = off
}


def apply_defaults(config):
    for key, value in DEFAULTS.items():
        config.setdefault(key, value)
    return config


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
    return errors
