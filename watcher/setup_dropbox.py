"""One-time Dropbox authorization for the MVP B watcher.

Asks for the app key and app secret (hidden input), prints the authorization
link, takes the code you paste (hidden), exchanges it for a refresh token and
stores the three values in the config file, mode 600. Prints no secrets.
Standard library only, Python 3.9.

Run: python3 watcher/setup_dropbox.py          (add --replace to overwrite)
"""

import getpass
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

CONFIG_DIR = os.path.expanduser('~/Library/Application Support/whiteboard-watcher')
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.json')
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
    data = {'app_key': app_key, 'app_secret': app_secret, 'refresh_token': refresh_token}
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(data, handle, indent=2)
        handle.write('\n')
    os.replace(temp, path)
    os.chmod(path, 0o600)


def main(argv):
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
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
