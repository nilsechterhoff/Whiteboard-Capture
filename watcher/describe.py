"""Describe step: headless Claude Code (claude -p) reads one photo and answers.

The first line of the answer is 'whiteboard: yes' or 'whiteboard: no' (checked by
whiteboard_watcher.split_answer). Only Read is allowed. Refuses to run if
ANTHROPIC_API_KEY is set, so nothing is billed to an API key. Standard library only.
"""

import json
import os
import subprocess

from whiteboard_watcher import DescribeError

CLAUDE = 'claude'
MODEL = 'sonnet'      # fastest model that read the board correctly (scratch test)
TIMEOUT = 120         # hard limit per run, seconds
PHOTO_NAME = 'describe-photo.jpg'


def build_prompt(fields):
    others = ', '.join('%s=%s' % (k, fields[k]) for k in sorted(fields) if k != 'request')
    return (
        "Read the image file %s in this folder. "
        "The first line of your answer must be exactly 'whiteboard: yes' if the image shows "
        "a whiteboard with handwriting, otherwise exactly 'whiteboard: no'. "
        "If the answer is no, stop after that line. "
        "If yes, then describe only, do not interpret: "
        "(1) the text, grouped by region; "
        "(2) the shapes, arrows and what connects to what; "
        "(3) a short summary. "
        "Request fields: %s. Honour marker_color and region fields if given. "
        "Plain text, no tool use other than reading the image."
    ) % (PHOTO_NAME, others or 'none')


class Describer(object):

    def __init__(self, folder, model=MODEL, timeout=TIMEOUT, run=subprocess.run,
                 environ=None):
        self.folder = folder
        self.model = model
        self.timeout = timeout
        self.run = run
        self.environ = dict(os.environ if environ is None else environ)

    def describe(self, photo, fields):
        if self.environ.get('ANTHROPIC_API_KEY'):
            raise DescribeError('ANTHROPIC_API_KEY is set; refusing to bill an API key')
        path = os.path.join(self.folder, PHOTO_NAME)
        with open(path, 'wb') as handle:
            handle.write(photo)
        env = dict(self.environ)
        env.pop('ANTHROPIC_API_KEY', None)
        cmd = [CLAUDE, '-p', build_prompt(fields), '--model', self.model,
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
