"""Describe step: headless Claude Code (claude -p) reads one photo and answers.

The answer starts with the measured criteria (answer.py), then the description if the agent
concludes it is the board camera. Only Read is allowed. Refuses to run if
ANTHROPIC_API_KEY is set, so nothing is billed to an API key. Standard library only.
"""

import base64
import json
import os
import select
import subprocess
import time

import logging

from whiteboard_watcher import DescribeError

LOG = logging.getLogger('whiteboard')

CLAUDE = 'claude'
TIMEOUT = 120         # hard limit per run, seconds
PHOTO_NAME = 'describe-photo.jpg'


def build_prompt(fields, photo_ref=None, min_fill=0):
    """photo_ref None: the lean call reads PHOTO_NAME in the work folder; a session passes the
    attached image instead. min_fill: the board fill the watcher requires (0 = no requirement)."""
    others = ', '.join('%s=%s' % (k, fields[k]) for k in sorted(fields) if k != 'request')
    start = ("Read the image file %s in this folder. " % PHOTO_NAME if photo_ref is None
             else 'Look at the attached image. ')
    fill_rule = 'at least %d' % min_fill if min_fill else 'none'
    return (
        start +
        "Answer with one line per criterion, in this order, nothing before them. "
        "'whiteboard_visible: yes' if the image shows a whiteboard with handwriting, otherwise "
        "'whiteboard_visible: no' (required: yes). "
        "'board_fill_percent: NN', where NN is a whole number from 0 to 100: the percentage of the "
        "whole frame covered by the real whiteboard surface. Count only the board itself: not "
        "reflections in mirrors, screens, posters, windows or walls. Write 0 if no board is visible "
        "(required: %s). "
        "'challenges_if_any': list only real obstacles that limited the picture or the description "
        "(for example glare, a hand in the frame, text cut off at an edge): one short line each, as "
        "'- what; where; minor or critical'. If there are none, write exactly 'challenges_if_any: none'. "
        "'is_board_camera: yes' if every required criterion is met, otherwise 'is_board_camera: no'. "
        "If is_board_camera is no, stop after that line. "
        "If yes, leave one blank line, then describe only, do not interpret: "
        "(1) the text, grouped by region; "
        "(2) the shapes, arrows and what connects to what; "
        "(3) a short summary. "
        "Request fields: %s. Honour marker_color and region fields if given. "
        "Plain text, no tool use other than reading the image."
    ) % (fill_rule, others or 'none')


class Describer(object):

    def __init__(self, folder, models, timeout=TIMEOUT, run=subprocess.run, environ=None, min_fill=0):
        """`models` maps the short names from the config file to model IDs."""
        self.folder = folder
        self.models = models
        self.timeout = timeout
        self.run = run
        self.environ = dict(os.environ if environ is None else environ)
        self.min_fill = min_fill

    def describe(self, photo, fields):
        if self.environ.get('ANTHROPIC_API_KEY'):
            raise DescribeError('ANTHROPIC_API_KEY is set; refusing to bill an API key')
        path = os.path.join(self.folder, PHOTO_NAME)
        with open(path, 'wb') as handle:
            handle.write(photo)
        env = dict(self.environ)
        env.pop('ANTHROPIC_API_KEY', None)
        model = self.models[fields['model']]
        cmd = [CLAUDE, '-p', build_prompt(fields, min_fill=self.min_fill), '--model', model,
               '--allowedTools', 'Read', '--add-dir', self.folder,
               '--output-format', 'json']
        try:
            done = self.run(cmd, cwd=self.folder, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=self.timeout)
        except FileNotFoundError:
            raise DescribeError('claude not found')
        except subprocess.TimeoutExpired:
            raise DescribeError('claude timed out after %d s' % self.timeout)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        if done.returncode != 0:
            raise DescribeError('claude exit %d' % done.returncode)
        try:
            answer = json.loads(done.stdout.decode('utf-8', 'replace'))
        except ValueError:
            raise DescribeError('no JSON answer from claude')
        if answer.get('is_error'):
            raise DescribeError('claude reported an error')
        return answer.get('result', '')


class SessionDescriber(object):
    """Agile phase 2: one long-lived `claude -p` session (stream-json in and out). Each photo is
    sent as a new message into the open session. The session restarts after `restart_after`
    requests, when the model changes, or when it is gone. Any session failure closes it and runs
    that request once through the lean describe; the next request starts a new session.
    """

    def __init__(self, folder, models, lean, restart_after=20, timeout=TIMEOUT,
                 popen=subprocess.Popen, read_event=None, environ=None, min_fill=0):
        self.folder = folder
        self.models = models
        self.lean = lean
        self.restart_after = restart_after
        self.timeout = timeout
        self.popen = popen
        self.read_event = read_event or _read_event
        self.environ = dict(os.environ if environ is None else environ)
        self.min_fill = min_fill
        self.proc = None
        self.model = None
        self.count = 0

    def _env(self):
        if self.environ.get('ANTHROPIC_API_KEY'):
            raise DescribeError('ANTHROPIC_API_KEY is set; refusing to bill an API key')
        env = dict(self.environ)
        env.pop('ANTHROPIC_API_KEY', None)
        return env

    def _start(self, model):
        self._stop()
        cmd = [CLAUDE, '-p', '--input-format', 'stream-json', '--output-format', 'stream-json',
               '--verbose', '--model', self.models[model], '--allowedTools', '']
        self.proc = self.popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, cwd=self.folder, env=self._env())
        self.model = model
        self.count = 0

    def _stop(self):
        if self.proc is not None:
            try:
                self.proc.kill()
            except OSError:
                pass
            self.proc = None
            self.model = None

    def _ask(self, photo, fields):
        message = {'type': 'user', 'message': {'role': 'user', 'content': [
            {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg',
                                         'data': base64.b64encode(photo).decode('ascii')}},
            {'type': 'text', 'text': build_prompt(fields, photo_ref='attached', min_fill=self.min_fill)}]}}
        self.proc.stdin.write((json.dumps(message) + '\n').encode('utf-8'))
        self.proc.stdin.flush()
        deadline = time.time() + self.timeout
        while True:
            left = deadline - time.time()
            if left <= 0:
                raise DescribeError('session timed out after %d s' % self.timeout)
            event = self.read_event(self.proc, left)
            if event is None:
                raise DescribeError('session closed')
            if event.get('type') == 'result':
                if event.get('is_error'):
                    raise DescribeError('session reported an error')
                return event.get('result', '')

    def warm(self, model):
        """Headstart (BL-037): start the session now, without a photo. A failure is logged; the next
        describe starts the session again."""
        try:
            self._env()
            if self.proc is None or self.model != model or self.proc.poll() is not None:
                LOG.info('session: started by headstart (model %s)' % model)
                self._start(model)
        except (DescribeError, OSError) as err:
            LOG.info('session: headstart could not start (%s)' % err)
            self._stop()

    def describe(self, photo, fields):
        self._env()  # refuses if the key is set
        try:
            if (self.proc is None or self.model != fields['model'] or self.count >= self.restart_after
                    or self.proc.poll() is not None):
                LOG.info('session: started (model %s)' % fields['model'])
                self._start(fields['model'])
            else:
                LOG.info('session: reused (request %d in this session)' % (self.count + 1))
            text = self._ask(photo, fields)
            self.count += 1
            return text
        except (DescribeError, OSError, ValueError) as err:
            LOG.info('session: check failed (%s); lean describe once' % err)
            self._stop()
            return self.lean.describe(photo, fields)


def _read_event(proc, timeout):
    """One JSON event from the session's stdout, or None if it closed. Raises DescribeError on timeout."""
    ready, _, _ = select.select([proc.stdout], [], [], timeout)
    if not ready:
        raise DescribeError('session timed out')
    line = proc.stdout.readline()
    if not line:
        return None
    return json.loads(line.decode('utf-8'))
