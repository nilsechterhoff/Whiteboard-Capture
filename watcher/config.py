"""Config checks for the watcher. Defaults live here, so every new setting has one place.

Standard library only, Python 3.9.
"""

import camera as cam

DEFAULTS = {
    'rotation_degrees': 0,
}


def apply_defaults(config):
    for key, value in DEFAULTS.items():
        config.setdefault(key, value)
    return config


def validate(config):
    """Return a list of error messages; an empty list means the config is valid."""
    errors = []
    try:
        cam.rotation_filters(config.get('rotation_degrees'))
    except ValueError as err:
        errors.append(str(err))
    return errors
