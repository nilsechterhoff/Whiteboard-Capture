"""Settings: the config file is the only source of defaults (BL-040).

A setting with a default is stored as {"value": ..., "default": ..., "allowed": "..."}; "allowed" is
optional. An empty or invalid "value" falls back to "default" and one line is logged. Secrets and
paths without a default stay plain values. An old flat config (values only) is converted once: a
timestamped backup is written next to it, and the defaults come from config.example.json.

"allowed" forms: "a-b" (whole numbers a to b), "int>=n", "number>=n", "a|b|c" (one of these words),
"dict:a|b" (a dict of names to one of these words), "text" (any non-empty text), "any".

Standard library only, Python 3.9.
"""

import json
import os
import re
import shutil
import time

RANGE = re.compile(r'^(-?\d+)-(-?\d+)$')
INT_MIN = re.compile(r'^int>=(-?\d+)$')
NUMBER_MIN = re.compile(r'^number>=(-?\d+(\.\d+)?)$')


def is_entry(value):
    return isinstance(value, dict) and 'value' in value and 'default' in value


def check(value, allowed):
    """True if `value` is allowed by the `allowed` text. A missing rule allows anything."""
    if allowed is None or allowed == 'any':
        return True
    if isinstance(value, bool):
        return False
    match = RANGE.match(allowed)
    if match:
        return isinstance(value, int) and int(match.group(1)) <= value <= int(match.group(2))
    match = INT_MIN.match(allowed)
    if match:
        return isinstance(value, int) and value >= int(match.group(1))
    match = NUMBER_MIN.match(allowed)
    if match:
        return isinstance(value, (int, float)) and value >= float(match.group(1))
    if allowed == 'text':
        return isinstance(value, str) and value.strip() != ''
    if allowed.startswith('dict:'):
        words = allowed[len('dict:'):].split('|')
        return isinstance(value, dict) and all(v in words for v in value.values())
    if '|' in allowed:
        return str(value) in allowed.split('|')
    return False


def is_empty(value):
    return value is None or value == '' or value == {}


def resolve(raw):
    """Return (settings, warnings): plain values, with every entry replaced by its value or default."""
    settings = {}
    warnings = []
    for key, item in raw.items():
        if not is_entry(item):
            settings[key] = item
            continue
        value, default, allowed = item['value'], item['default'], item.get('allowed')
        if is_empty(value) or not check(value, allowed):
            if value != default:
                warnings.append('config %s: value %r is empty or not allowed (%s); using the default %r'
                                % (key, value, allowed or 'any', default))
            value = default
        settings[key] = value
    return settings, warnings


def needs_conversion(raw, example):
    """True if the config still has flat values for keys that have a default in the example."""
    return any(key in raw and not is_entry(raw[key]) and is_entry(example[key])
               for key in example)


def convert(raw, example, path, now=None):
    """Write a timestamped backup next to `path`, then return the config in the value/default format."""
    stamp = time.strftime('%Y%m%d-%H%M%S', time.localtime(now if now is not None else time.time()))
    backup = '%s.backup-%s' % (path, stamp)
    shutil.copy2(path, backup)
    converted = {}
    for key, item in example.items():
        if not is_entry(item):
            if key in raw:
                converted[key] = raw[key]
            continue
        value = raw[key] if key in raw and not is_entry(raw[key]) else item['default']
        entry = {'value': value, 'default': item['default']}
        if 'allowed' in item:
            entry['allowed'] = item['allowed']
        converted[key] = entry
    for key, item in raw.items():
        if key not in converted:
            converted[key] = item
    return converted, backup


def write(path, raw):
    temp = path + '.tmp'
    with open(temp, 'w') as handle:
        json.dump(raw, handle, indent=2)
        handle.write('\n')
    os.chmod(temp, 0o600)
    os.replace(temp, path)
