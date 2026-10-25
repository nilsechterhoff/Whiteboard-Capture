"""MVP B watcher: the program that runs on the Mac.

Usage:
    python3 watcher/watcher.py --once            one pass over pending requests, then exit
    python3 watcher/watcher.py --once --wait 60  wait up to 60 s for a request first
    python3 watcher/watcher.py                   loop (the launchd service, step D)

Config: ~/Library/Application Support/whiteboard-watcher/config.json
  app_key, app_secret, refresh_token (from setup_dropbox.py)
  camera_name (optional, default all cameras), rotation_degrees (0, 90, 180 or 270; default 0), dark_below (default 20)
  models (short name -> model ID), default_model (a short name from models)
Logs:   ~/Library/Logs/whiteboard-watcher.log (no secrets)
        ~/Library/Logs/whiteboard-watcher-timings.csv (one row per request, no whiteboard content)
Python 3.9 standard library only.
"""

import argparse
import fcntl
import json
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import camera as cam                       # noqa: E402
import whiteboard_watcher as ww            # noqa: E402
from describe import Describer             # noqa: E402
from dropbox_store import DropboxStore     # noqa: E402
from stopwatch import Watch                # noqa: E402
from results import Results                # noqa: E402
import config as config_mod                # noqa: E402

CONFIG_DIR = os.path.expanduser('~/Library/Application Support/whiteboard-watcher')
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.json')
LAST_CAMERA_PATH = os.path.join(CONFIG_DIR, 'last_camera.json')
WORK_DIR = os.path.join(CONFIG_DIR, 'work')
LOCK_PATH = os.path.join(CONFIG_DIR, 'watcher.lock')
LOG_PATH = os.path.expanduser('~/Library/Logs/whiteboard-watcher.log')
TIMINGS_PATH = os.path.expanduser('~/Library/Logs/whiteboard-watcher-timings.csv')
POLL_SECONDS = 1

log = logging.getLogger('whiteboard')


def setup_logging():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    handler = logging.FileHandler(LOG_PATH)
    handler.setFormatter(logging.Formatter('%(asctime)s %(message)s', '%Y-%m-%d %H:%M:%S'))
    log.addHandler(handler)
    log.addHandler(logging.StreamHandler(sys.stdout))
    log.setLevel(logging.INFO)


def load_config():
    with open(CONFIG_PATH) as handle:
        config = json.load(handle)
    config_mod.apply_defaults(config)
    for key in ('app_key', 'app_secret', 'refresh_token', 'models', 'default_model'):
        if not config.get(key):
            raise SystemExit('config is missing %s; run setup_dropbox.py' % key)
    errors = config_mod.validate(config)
    if errors:
        raise SystemExit('config: ' + '; '.join(errors))
    if config['default_model'] not in config['models']:
        raise SystemExit('default_model must be one of: %s' % ', '.join(sorted(config['models'])))
    config.setdefault('camera_name', '')
    config.setdefault('dark_below', cam.DARK_BELOW)
    return config


class Memory(object):
    """Last working camera index. A hint only: see camera_order()."""

    def index(self):
        return cam.load_last(LAST_CAMERA_PATH)

    def remember(self, index):
        cam.save_last(LAST_CAMERA_PATH, index, None)
        log.info('last working camera: index %d' % index)


class Timed(object):
    """Wraps an object and logs how long each call took."""

    def __init__(self, target, label):
        self.target = target
        self.label = label

    def __getattr__(self, name):
        attr = getattr(self.target, name)
        if not callable(attr):
            return attr

        def timed(*args, **kwargs):
            started = time.time()
            try:
                return attr(*args, **kwargs)
            finally:
                log.info('%s.%s %.2f s' % (self.label, name, time.time() - started))
        return timed


def pass_once(store, cameras, describer, memory, watch, results, settings):
    started = time.time()
    handled = ww.process_pending(store, cameras, describer, memory, watch, results, time.time(), settings)
    if handled:
        log.info('pass done: handled %s in %.2f s' % (', '.join(handled), time.time() - started))
    return handled


def wait_for_request(store, limit):
    """Poll /Requests until a request without a description shows up (or the limit passes)."""
    deadline = time.time() + limit
    while time.time() < deadline:
        names = [n for n in store.list_names('/Requests') if ww.REQUEST_NAME.match(n)]
        pending = [n for n in names if not store.exists(ww.description_path(ww.REQUEST_NAME.match(n).group(1)))]
        if pending:
            return True
        time.sleep(POLL_SECONDS)
    return False


def main(argv):
    parser = argparse.ArgumentParser(description='MVP B whiteboard watcher')
    parser.add_argument('--once', action='store_true', help='one pass, then exit')
    parser.add_argument('--wait', type=float, default=0, help='with --once: wait this many s for a request')
    args = parser.parse_args(argv)
    setup_logging()
    config = load_config()
    os.makedirs(WORK_DIR, mode=0o700, exist_ok=True)
    lock = open(LOCK_PATH, 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log.info('another watcher is running; exiting')
        return 1

    store = Timed(DropboxStore(config['app_key'], config['app_secret'], config['refresh_token']), 'dropbox')
    cameras = Timed(cam.Cameras(WORK_DIR, config['camera_name'], config['rotation_degrees'],
                                config['dark_below']), 'camera')
    describer = Timed(Describer(WORK_DIR, config['models']), 'describe')
    memory = Memory()
    watch = Watch(csv_path=TIMINGS_PATH)
    results = Results(os.path.join(CONFIG_DIR, 'results'))
    settings = {'models': config['models'], 'default_model': config['default_model']}
    log.info('watcher start (%s)' % ('once' if args.once else 'loop'))

    if args.once:
        if args.wait and not wait_for_request(store, args.wait):
            log.info('no request within %.0f s' % args.wait)
            return 0
        pass_once(store, cameras, describer, memory, watch, results, settings)
        return 0
    while True:
        pass_once(store, cameras, describer, memory, watch, results, settings)
        time.sleep(POLL_SECONDS)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
