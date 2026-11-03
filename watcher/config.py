"""Config rules for the watcher. Defaults come from the config file (BL-040), see settings.py.

Standard library only, Python 3.9.
"""

IGNORED_KEYS = ('agile_enabled', 'mode')  # agile is always on (ADR-0012); the keys are ignored


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
    return config.get('agile_session') == 'yes'


def validate(config):
    """Checks that the file-level settings cannot express: a plain folder name and a known default model."""
    errors = []
    folder = config.get('failed_photos_folder', '')
    if not isinstance(folder, str) or not folder.strip() or '/' in folder or folder in ('.', '..'):
        errors.append('failed_photos_folder must be a plain folder name (got %r)' % (folder,))
    if config.get('default_model') not in config.get('models', {}):
        errors.append('default_model must be one of: %s' % ', '.join(sorted(config.get('models', {}))))
    return errors
