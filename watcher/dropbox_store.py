"""Dropbox HTTP API for the watcher, inside the app folder only.

Paths are relative to the app folder root (/Requests/..., /Images/..., /Descriptions/...).
Calls: list, get metadata, download, upload (overwrite a temporary name), move.
Nothing is deleted. Standard library only, Python 3.9.
"""

import calendar
import json
import time
import urllib.error
import urllib.parse
import urllib.request

API = 'https://api.dropboxapi.com/2/'
CONTENT = 'https://content.dropboxapi.com/2/'
TOKEN_URL = 'https://api.dropboxapi.com/oauth2/token'


class StoreError(OSError):
    """Network or API trouble. An OSError, so the watcher retries on the next pass."""


class NotFound(StoreError):
    pass


class DropboxStore(object):

    def __init__(self, app_key, app_secret, refresh_token, opener=urllib.request.urlopen):
        self.app_key = app_key
        self.app_secret = app_secret
        self.refresh_token = refresh_token
        self.opener = opener
        self.token = None

    def _refresh(self):
        data = urllib.parse.urlencode({
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token,
            'client_id': self.app_key,
            'client_secret': self.app_secret,
        }).encode('utf-8')
        answer = json.loads(self._send(urllib.request.Request(TOKEN_URL, data=data)).decode('utf-8'))
        self.token = answer.get('access_token')
        if not self.token:
            raise StoreError('Dropbox gave no access token')

    def _send(self, request):
        try:
            with self.opener(request, timeout=30) as answer:
                return answer.read()
        except urllib.error.HTTPError as err:
            summary = err.read().decode('utf-8', 'replace')
            if err.code == 409 and 'path/not_found' in summary:
                raise NotFound('not found')
            raise StoreError('Dropbox HTTP %d: %s' % (err.code, summary[:200]))
        except OSError as err:
            raise StoreError('no connection to Dropbox (%s)' % err.__class__.__name__)

    def _api(self, endpoint, body):
        if self.token is None:
            self._refresh()
        data = json.dumps(body).encode('utf-8')
        for attempt in (1, 2):
            request = urllib.request.Request(API + endpoint, data=data, headers={
                'Authorization': 'Bearer ' + self.token,
                'Content-Type': 'application/json',
            })
            try:
                return json.loads(self._send(request).decode('utf-8'))
            except StoreError as err:
                if attempt == 1 and 'expired_access_token' in str(err):
                    self._refresh()
                    continue
                raise

    def list_names(self, folder):
        """File names directly in `folder`. A missing folder counts as empty."""
        try:
            answer = self._api('files/list_folder', {'path': folder})
        except NotFound:
            return []
        names = [e['name'] for e in answer['entries'] if e.get('.tag') == 'file']
        while answer.get('has_more'):
            answer = self._api('files/list_folder/continue', {'cursor': answer['cursor']})
            names += [e['name'] for e in answer['entries'] if e.get('.tag') == 'file']
        return names

    def _metadata(self, path):
        return self._api('files/get_metadata', {'path': path})

    def exists(self, path):
        try:
            self._metadata(path)
        except NotFound:
            return False
        return True

    def modified(self, path):
        """Dropbox server time of the file, as epoch seconds (UTC, one-second resolution)."""
        stamp = self._metadata(path)['server_modified']
        return calendar.timegm(time.strptime(stamp, '%Y-%m-%dT%H:%M:%SZ'))

    def read_text(self, path):
        return self.read(path).decode('utf-8')

    def read(self, path):
        arg = json.dumps({'path': path})
        request = urllib.request.Request(CONTENT + 'files/download', data=b'', headers={
            'Authorization': 'Bearer ' + self._access(),
            'Dropbox-API-Arg': arg,
        })
        return self._send(request)

    def upload(self, path, data):
        arg = json.dumps({'path': path, 'mode': 'overwrite', 'autorename': False, 'mute': True})
        request = urllib.request.Request(CONTENT + 'files/upload', data=data, headers={
            'Authorization': 'Bearer ' + self._access(),
            'Dropbox-API-Arg': arg,
            'Content-Type': 'application/octet-stream',
        })
        self._send(request)

    def move(self, src, dst):
        self._api('files/move_v2', {'from_path': src, 'to_path': dst, 'autorename': False})

    def _access(self):
        if self.token is None:
            self._refresh()
        return self.token
