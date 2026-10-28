"""MVP B watcher: the program that runs on the Mac.

Usage:
    python3 watcher/watcher.py --once            one pass over pending requests, then exit
    python3 watcher/watcher.py --once --wait 60  wait up to 60 s for a request first
    python3 watcher/watcher.py                   loop (the launchd service, step D)

Config: config.json in the local folder named in paths.py (CONFIG_DIR)
  app_key, app_secret, refresh_token (from setup_dropbox.py)
  camera_name (optional, default all cameras), rotation_degrees (0, 90, 180 or 270; default 0), dark_below (default 20)
  models (short name -> model ID), default_model (a short name from models)
  min_board_fill_percent (0 = off; default 50)
All local files are in that one folder (BL-035), see README: config.json, last_camera.json, work/,
  results/, whiteboard-watcher.log (no secrets), whiteboard-watcher-timings.csv (one row per request, no
  whiteboard content), failed-photos/ (kept photos the board check refused)
Python 3.9 standard library only.
"""

import argparse
import atexit
import fcntl
import json
import logging
import signal
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import camera as cam                       # noqa: E402
import whiteboard_watcher as ww            # noqa: E402
from describe import Describer             # noqa: E402
import describe as describe_mod            # noqa: E402
from dropbox_store import DropboxStore     # noqa: E402
from stopwatch import Watch                # noqa: E402
from results import Results                # noqa: E402
import config as config_mod                # noqa: E402
import settings                            # noqa: E402
import selection as selection_mod          # noqa: E402

from paths import CONFIG_DIR               # noqa: E402
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.json')
LAST_CAMERA_PATH = os.path.join(CONFIG_DIR, 'last_camera.json')
EXAMPLE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.example.json')
WORK_DIR = os.path.join(CONFIG_DIR, 'work')
LOCK_PATH = os.path.join(CONFIG_DIR, 'watcher.lock')
LOG_PATH = os.path.join(CONFIG_DIR, 'whiteboard-watcher.log')
TIMINGS_PATH = os.path.join(CONFIG_DIR, 'whiteboard-watcher-timings.csv')
POLL_SECONDS = 1

log = logging.getLogger('whiteboard')
LEGACY_WARNINGS = []  # filled by load_config, logged once the log is set up


def setup_logging():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    handler = logging.FileHandler(LOG_PATH)
    handler.setFormatter(logging.Formatter('%(asctime)s %(message)s', '%Y-%m-%d %H:%M:%S'))
    log.addHandler(handler)
    log.addHandler(logging.StreamHandler(sys.stdout))
    log.setLevel(logging.INFO)


def load_config():
    """Reads the config file. Defaults come from the file itself (BL-040); a flat config is converted once."""
    with open(CONFIG_PATH) as handle:
        raw = json.load(handle)
    for warning in config_mod.normalize(raw):
        LEGACY_WARNINGS.append(warning)
    with open(EXAMPLE_PATH) as handle:
        example = json.load(handle)
    if settings.needs_conversion(raw, example):
        raw, backup = settings.convert(raw, example, CONFIG_PATH)
        settings.write(CONFIG_PATH, raw)
        LEGACY_WARNINGS.append('config converted to the value/default format; backup: %s' % backup)
    config, warnings = settings.resolve(raw)
    LEGACY_WARNINGS.extend(warnings)
    for key in ('app_key', 'app_secret', 'refresh_token', 'models'):
        if not config.get(key):
            raise SystemExit('config is missing %s; run setup_dropbox.py' % key)
    errors = config_mod.validate(config)
    if errors:
        raise SystemExit('config: ' + '; '.join(errors))
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
    for _ in handled:
        if hasattr(cameras.target if isinstance(cameras, Timed) else cameras, 'note_event'):
            cameras.note_event('request')
    if hasattr(cameras.target if isinstance(cameras, Timed) else cameras, 'tick'):
        cameras.tick()
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
    for warning in LEGACY_WARNINGS:
        log.warning(warning)
    os.makedirs(WORK_DIR, mode=0o700, exist_ok=True)
    lock = open(LOCK_PATH, 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log.info('another watcher is running; exiting')
        return 1

    store = Timed(DropboxStore(config['app_key'], config['app_secret'], config['refresh_token']), 'dropbox')
    lean = cam.Cameras(WORK_DIR, config['camera_name'], config['rotation_degrees'], config['dark_below'],
                       jpeg_quality=config['jpeg_quality'])
    parallel = selection_mod.ParallelCameras(
        WORK_DIR, lean, config['rotation_degrees'], config['dark_below'],
        config['agile_idle_timeout_seconds'], config['agile_timer_reset_events'],
        config['start_offset_seconds'], config['selection_frame_delay_seconds'],
        config['retry_pause_seconds'], config['capture_retries'], jpeg_quality=config['jpeg_quality'])
    atexit.register(parallel.close)
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
    cameras = Timed(parallel, 'camera')
    lean_describer = Describer(WORK_DIR, config['models'], min_fill=config['min_board_fill_percent'])
    if config_mod.session_on(config):
        describer = Timed(describe_mod.SessionDescriber(
            WORK_DIR, config['models'], lean_describer, config['agile_session_restart_after_requests'],
            min_fill=config['min_board_fill_percent']), 'describe')
    else:
        describer = Timed(lean_describer, 'describe')
    memory = Memory()
    watch = Watch(csv_path=TIMINGS_PATH)
    results = Results(os.path.join(CONFIG_DIR, 'results'))
    settings = {'models': config['models'], 'default_model': config['default_model'],
                'min_board_fill_percent': config['min_board_fill_percent'],
                'failed_photos_keep': config['failed_photos_keep'],
                'failed_photos_dir': os.path.join(CONFIG_DIR, config['failed_photos_folder'])}
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
