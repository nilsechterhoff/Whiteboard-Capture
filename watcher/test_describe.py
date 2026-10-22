"""Tests for the describe step with a fake claude. No API, no network.

Run: cd watcher && python3 -m unittest -v test_describe
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

import describe as desc
from whiteboard_watcher import DescribeError


class FakeClaude(object):
    """Stands in for subprocess.run. Records the call; photo must exist during the call."""

    def __init__(self, result='whiteboard: yes\nbody', is_error=False, returncode=0,
                 stdout=None, timeout=False, missing=False):
        self.result = result
        self.is_error = is_error
        self.returncode = returncode
        self.stdout = stdout
        self.timeout = timeout
        self.missing = missing
        self.cmd = None
        self.env = None
        self.cwd = None
        self.photo_seen = None

    def __call__(self, cmd, cwd=None, env=None, stdout=None, stderr=None, timeout=None):
        self.cmd, self.env, self.cwd = cmd, env, cwd
        if self.missing:
            raise FileNotFoundError(cmd[0])
        if self.timeout:
            raise subprocess.TimeoutExpired(cmd, timeout)
        self.photo_seen = os.path.exists(os.path.join(cwd, desc.PHOTO_NAME))
        out = self.stdout if self.stdout is not None else json.dumps({
            'is_error': self.is_error, 'result': self.result})
        return subprocess.CompletedProcess(cmd, self.returncode, out.encode('utf-8'), b'')


class DescribeTests(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.folder)

    def describer(self, fake, environ=None):
        return desc.Describer(self.folder, run=fake, environ=environ or {})

    def test_returns_the_result_text(self):
        fake = FakeClaude(result='whiteboard: no')
        self.assertEqual(self.describer(fake).describe(b'jpg', {'request': '0003'}), 'whiteboard: no')

    def test_photo_is_in_the_work_folder_during_the_call_and_removed_after(self):
        fake = FakeClaude()
        self.describer(fake).describe(b'jpg', {'request': '0003'})
        self.assertTrue(fake.photo_seen)
        self.assertEqual(os.listdir(self.folder), [])

    def test_command_is_read_only_and_uses_sonnet(self):
        fake = FakeClaude()
        self.describer(fake).describe(b'jpg', {'request': '0003'})
        self.assertIn('--model', fake.cmd)
        self.assertEqual(fake.cmd[fake.cmd.index('--model') + 1], 'sonnet')
        self.assertEqual(fake.cmd[fake.cmd.index('--allowedTools') + 1], 'Read')
        self.assertEqual(fake.cwd, self.folder)

    def test_prompt_asks_for_the_whiteboard_line_first(self):
        prompt = desc.build_prompt({'request': '0003', 'marker_color': 'red'})
        self.assertIn("exactly 'whiteboard: yes'", prompt)
        self.assertIn("exactly 'whiteboard: no'", prompt)
        self.assertIn('marker_color=red', prompt)

    def test_api_key_in_environment_is_refused(self):
        fake = FakeClaude()
        with self.assertRaises(DescribeError) as ctx:
            self.describer(fake, environ={'ANTHROPIC_API_KEY': 'x'}).describe(b'jpg', {})
        self.assertIn('ANTHROPIC_API_KEY', str(ctx.exception))
        self.assertIsNone(fake.cmd)

    def test_api_key_is_removed_from_the_child_environment(self):
        fake = FakeClaude()
        self.describer(fake, environ={'PATH': '/bin'}).describe(b'jpg', {})
        self.assertNotIn('ANTHROPIC_API_KEY', fake.env)
        self.assertEqual(fake.env['PATH'], '/bin')

    def test_timeout_is_a_describe_error(self):
        with self.assertRaises(DescribeError) as ctx:
            self.describer(FakeClaude(timeout=True)).describe(b'jpg', {})
        self.assertIn('timed out', str(ctx.exception))
        self.assertEqual(os.listdir(self.folder), [])

    def test_missing_claude_is_a_describe_error(self):
        with self.assertRaises(DescribeError):
            self.describer(FakeClaude(missing=True)).describe(b'jpg', {})

    def test_nonzero_exit_is_a_describe_error(self):
        with self.assertRaises(DescribeError):
            self.describer(FakeClaude(returncode=1, stdout='')).describe(b'jpg', {})

    def test_non_json_answer_is_a_describe_error(self):
        with self.assertRaises(DescribeError):
            self.describer(FakeClaude(stdout='not json')).describe(b'jpg', {})

    def test_claude_reported_error_is_a_describe_error(self):
        with self.assertRaises(DescribeError):
            self.describer(FakeClaude(is_error=True)).describe(b'jpg', {})


if __name__ == '__main__':
    unittest.main()
