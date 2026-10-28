"""One-time setup for the MVP B watcher.

1. Dropbox authorization: asks for the app key and app secret (hidden input), prints
   the authorization link, takes the code you paste (hidden), exchanges it for a refresh
   token and stores everything in the config file, mode 600. Prints no secrets.
2. Background service (launchd), only after you type yes: prints the exact paths, then
   writes the launchd plist and its log file.
3. Uninstall: removes the service and its two files (the config folder is kept).

Run:        python3 watcher/setup_dropbox.py                  (add --replace to overwrite)
Service:    python3 watcher/setup_dropbox.py --service        (needs the config)
Uninstall:  python3 watcher/setup_dropbox.py --uninstall
Standard library only, Python 3.9.
"""

import getpass
import json
import os
import plistlib
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

CONFIG_DIR = os.path.expanduser('~/Library/Application Support/whiteboard-watcher')
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.json')
LABEL = 'com.nilsechterhoff.whiteboard-watcher'
PLIST_PATH = os.path.expanduser('~/Library/LaunchAgents/%s.plist' % LABEL)
LAUNCHD_LOG = os.path.expanduser('~/Library/Logs/whiteboard-watcher.launchd.log')
# Starting values for config.json. Models live here, not in the watcher code.
# The defaults come from config.example.json (BL-040), not from this file.
EXAMPLE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.example.json')
AUTHORIZE_URL = 'https://www.dropbox.com/oauth2/authorize'
TOKEN_URL = 'https://api.dropboxapi.com/oauth2/token'
LIST_URL = 'https://api.dropboxapi.com/2/files/list_folder'


class SetupError(Exception):
    pass


def authorize_url(app_key):
    query = urllib.parse.urlencode({
        'client_id': app_key,
        'response_type': 'code',
        'token_access_type': 'offline',
    })
    return AUTHORIZE_URL + '?' + query


def post_form(url, fields):
    """POST form fields, return the JSON answer. Errors carry only Dropbox's summary."""
    data = urllib.parse.urlencode(fields).encode('utf-8')
    request = urllib.request.Request(url, data=data)
    return _send(request)


def post_json(url, token, body):
    request = urllib.request.Request(url, data=json.dumps(body).encode('utf-8'))
    request.add_header('Authorization', 'Bearer ' + token)
    request.add_header('Content-Type', 'application/json')
    return _send(request)


def _send(request):
    try:
        with urllib.request.urlopen(request, timeout=30) as answer:
            return json.loads(answer.read().decode('utf-8'))
    except urllib.error.HTTPError as err:
        summary = ''
        try:
            summary = json.loads(err.read().decode('utf-8')).get('error_summary', '')
        except (ValueError, AttributeError):
            pass
        raise SetupError('Dropbox answered HTTP %d %s' % (err.code, summary.strip()))
    except (urllib.error.URLError, OSError) as err:
        raise SetupError('no connection to Dropbox (%s)' % err.__class__.__name__)


def exchange_code(app_key, app_secret, code, post=post_form):
    answer = post(TOKEN_URL, {
        'code': code,
        'grant_type': 'authorization_code',
        'client_id': app_key,
        'client_secret': app_secret,
    })
    refresh_token = answer.get('refresh_token')
    if not refresh_token:
        raise SetupError('Dropbox gave no refresh token; check that token access is offline')
    return refresh_token


def access_token(app_key, app_secret, refresh_token, post=post_form):
    answer = post(TOKEN_URL, {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': app_key,
        'client_secret': app_secret,
    })
    if not answer.get('access_token'):
        raise SetupError('Dropbox gave no access token on refresh')
    return answer['access_token']


def list_app_root(token, post=post_json):
    """Names in the app folder root. Empty list is normal before the first move."""
    answer = post(LIST_URL, token, {'path': ''})
    return sorted(entry.get('name', '') for entry in answer.get('entries', []))


def write_config(path, app_key, app_secret, refresh_token):
    """Write the config atomically with mode 600 (folder 700)."""
    folder = os.path.dirname(path)
    os.makedirs(folder, mode=0o700, exist_ok=True)
    os.chmod(folder, 0o700)
    temp = path + '.tmp'
    with open(EXAMPLE_PATH) as handle:
        data = json.load(handle)
    data.update({'app_key': app_key, 'app_secret': app_secret, 'refresh_token': refresh_token})
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(data, handle, indent=2)
        handle.write('\n')
    os.replace(temp, path)
    os.chmod(path, 0o600)


def service_paths(script_dir=None, python=None):
    """Exact paths the service uses. Printed before anything is written."""
    here = script_dir or os.path.dirname(os.path.abspath(__file__))
    return {
        'plist': PLIST_PATH,
        'log': LAUNCHD_LOG,
        'script': os.path.join(here, 'watcher.py'),
        'python': python or sys.executable,
    }


def plist_bytes(paths):
    """The launchd job: run the watcher at login and keep it running. PATH includes the
    Homebrew folder (ffmpeg) and ~/.local/bin (claude)."""
    job = {
        'Label': LABEL,
        'ProgramArguments': [paths['python'], paths['script']],
        'EnvironmentVariables': {
            'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:%s'
                    % os.path.expanduser('~/.local/bin'),
        },
        'RunAtLoad': True,
        'KeepAlive': True,
        'ThrottleInterval': 60,
        'StandardOutPath': paths['log'],
        'StandardErrorPath': paths['log'],
    }
    return plistlib.dumps(job)


def launchctl(runner, *args):
    return runner(['launchctl'] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def install_service(paths, runner=subprocess.run, uid=None):
    """Write the plist and its log file, then start the job (launchctl bootstrap)."""
    uid = os.getuid() if uid is None else uid
    os.makedirs(os.path.dirname(paths['plist']), exist_ok=True)
    os.makedirs(os.path.dirname(paths['log']), exist_ok=True)
    with open(paths['plist'], 'wb') as handle:
        handle.write(plist_bytes(paths))
    with open(paths['log'], 'a'):
        pass
    launchctl(runner, 'bootout', 'gui/%d/%s' % (uid, LABEL))  # ok if it was not running
    done = launchctl(runner, 'bootstrap', 'gui/%d' % uid, paths['plist'])
    if done.returncode != 0:
        raise SetupError('launchctl bootstrap failed (exit %d)' % done.returncode)


def uninstall_service(paths, runner=subprocess.run, uid=None):
    """Stop the job and remove the plist and the launchd log. The config folder is kept."""
    uid = os.getuid() if uid is None else uid
    launchctl(runner, 'bootout', 'gui/%d/%s' % (uid, LABEL))
    removed = []
    for key in ('plist', 'log'):
        if os.path.exists(paths[key]):
            os.remove(paths[key])
            removed.append(paths[key])
    return removed


def confirm(question):
    return input('%s (type yes to continue): ' % question).strip() == 'yes'


def offer_service():
    paths = service_paths()
    print()
    print('Background service (starts the watcher at login and keeps it running).')
    print('This creates:')
    print('  %s' % paths['plist'])
    print('  %s' % paths['log'])
    print('It runs: %s %s' % (paths['python'], paths['script']))
    if not confirm('Create these files and start the service now?'):
        print('Service not installed. Run with --service later.')
        return 0
    try:
        install_service(paths)
    except (OSError, SetupError) as err:
        print('Failed: %s' % err)
        return 1
    print('Service installed and started. Log: %s' % paths['log'])
    return 0


def uninstall(argv):
    paths = service_paths()
    print('This removes the service and these two files:')
    print('  %s' % paths['plist'])
    print('  %s' % paths['log'])
    print('The config folder (keys, settings) is kept.')
    if not confirm('Remove them now?'):
        print('Nothing removed.')
        return 0
    removed = uninstall_service(paths)
    print('Removed: %s' % (', '.join(removed) if removed else 'nothing (already gone)'))
    return 0


def main(argv):
    if '--uninstall' in argv:
        return uninstall(argv)
    if '--service' in argv:
        if not os.path.exists(CONFIG_PATH):
            print('No config yet; run setup_dropbox.py first.')
            return 1
        return offer_service()
    if os.path.exists(CONFIG_PATH) and '--replace' not in argv:
        print('A config already exists: %s' % CONFIG_PATH)
        print('Run with --replace to overwrite it.')
        return 1

    print('Dropbox authorization for Whiteboard-Capture.')
    print('Input is hidden. Paste; do not type secrets into chat.')
    app_key = getpass.getpass('App key: ').strip()
    app_secret = getpass.getpass('App secret: ').strip()
    if not app_key or not app_secret:
        print('Empty app key or secret; nothing written.')
        return 1

    print()
    print('Open this link in your browser, allow access, then copy the code:')
    print(authorize_url(app_key))
    code = getpass.getpass('Code (hidden): ').strip()
    if not code:
        print('Empty code; nothing written.')
        return 1

    try:
        refresh_token = exchange_code(app_key, app_secret, code)
        write_config(CONFIG_PATH, app_key, app_secret, refresh_token)
        names = list_app_root(access_token(app_key, app_secret, refresh_token))
    except SetupError as err:
        print('Failed: %s' % err)
        return 1

    print('Saved config (mode 600): %s' % CONFIG_PATH)
    print('App folder root has %d entries%s' % (
        len(names), ': ' + ', '.join(names) if names else ' (empty)'))
    return offer_service()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
