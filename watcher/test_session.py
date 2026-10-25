"""Tests for the long-lived describe session (agile phase 2), with a fake process. No API.

Run: cd watcher && python3 -m unittest -v test_session
"""

import json
import unittest

import describe as desc
from whiteboard_watcher import DescribeError

MODELS = {'haiku': 'claude-haiku-5-5', 'sonnet': 'claude-sonnet-5-5'}
FIELDS = {'request': '0040', 'model': 'haiku'}


class FakeStdin(object):
    def __init__(self):
        self.sent = []

    def write(self, data):
        self.sent.append(json.loads(data.decode('utf-8')))

    def flush(self):
        pass


class FakeProc(object):
    def __init__(self, cmd, **kwargs):
        self.cmd = cmd
        self.stdin = FakeStdin()
        self.killed = False
        self.dead = False

    def poll(self):
        return 1 if self.dead else None

    def kill(self):
        self.killed = True


class Lean(object):
    def __init__(self, answer='whiteboard: no'):
        self.calls = 0
        self.answer = answer

    def describe(self, photo, fields):
        self.calls += 1
        return self.answer


def answer_events(text):
    return {'type': 'result', 'is_error': False, 'result': text}


class SessionTests(unittest.TestCase):

    def make(self, events, lean=None, restart_after=20):
        self.procs = []
        queue = list(events)

        def popen(cmd, **kwargs):
            p = FakeProc(cmd, **kwargs)
            self.procs.append(p)
            return p

        def read_event(proc, timeout):
            if not queue:
                return None
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        self.lean = lean or Lean()
        return desc.SessionDescriber('/tmp-not-used', MODELS, self.lean, restart_after=restart_after,
                                     popen=popen, read_event=read_event, environ={})

    def test_photo_is_sent_as_a_message_and_answer_returned(self):
        s = self.make([answer_events('whiteboard: yes\nbody')])
        self.assertEqual(s.describe(b'jpg', FIELDS), 'whiteboard: yes\nbody')
        msg = self.procs[0].stdin.sent[0]['message']['content']
        self.assertEqual(msg[0]['type'], 'image')
        self.assertEqual(msg[0]['source']['media_type'], 'image/jpeg')
        self.assertIn('--input-format', self.procs[0].cmd)
        self.assertNotIn('--resume', self.procs[0].cmd)

    def test_second_photo_goes_into_the_same_session(self):
        s = self.make([answer_events('whiteboard: yes'), answer_events('whiteboard: no')])
        s.describe(b'a', FIELDS)
        s.describe(b'b', FIELDS)
        self.assertEqual(len(self.procs), 1)
        self.assertEqual(len(self.procs[0].stdin.sent), 2)

    def test_session_restarts_after_the_limit(self):
        s = self.make([answer_events('whiteboard: yes')] * 3, restart_after=2)
        for _ in range(3):
            s.describe(b'x', FIELDS)
        self.assertEqual(len(self.procs), 2)

    def test_model_change_starts_a_new_session(self):
        s = self.make([answer_events('whiteboard: yes')] * 2)
        s.describe(b'x', FIELDS)
        s.describe(b'x', dict(FIELDS, model='sonnet'))
        self.assertEqual(len(self.procs), 2)

    def test_session_failure_runs_lean_once_and_closes_the_session(self):
        s = self.make([DescribeError('session reported an error')], lean=Lean('whiteboard: yes\nlean'))
        self.assertEqual(s.describe(b'x', FIELDS), 'whiteboard: yes\nlean')
        self.assertEqual(self.lean.calls, 1)
        self.assertTrue(self.procs[0].killed)

    def test_next_request_after_a_failure_starts_a_new_session(self):
        s = self.make([DescribeError('closed'), answer_events('whiteboard: yes')])
        s.describe(b'x', FIELDS)
        s.describe(b'y', FIELDS)
        self.assertEqual(len(self.procs), 2)

    def test_session_closed_is_a_failure(self):
        s = self.make([])          # read_event returns None: the process closed
        self.assertEqual(s.describe(b'x', FIELDS), 'whiteboard: no')
        self.assertEqual(self.lean.calls, 1)

    def test_api_key_refuses_before_any_process(self):
        s = self.make([answer_events('x')])
        s.environ = {'ANTHROPIC_API_KEY': 'k'}
        with self.assertRaises(DescribeError):
            s.describe(b'x', FIELDS)
        self.assertEqual(self.procs, [])

    def test_prompt_for_session_refers_to_the_attached_image(self):
        prompt = desc.build_prompt(FIELDS, photo_ref='attached')
        self.assertIn('attached image', prompt)
        self.assertIn("exactly 'whiteboard: yes'", prompt)


if __name__ == '__main__':
    unittest.main()
