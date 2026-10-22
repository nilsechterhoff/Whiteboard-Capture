"""Temporary folders for tests: always inside the repo's scratch/ (never /var/folders or /tmp)."""

import os
import tempfile

SCRATCH_TESTS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scratch', 'tests'))


def mkdtemp():
    os.makedirs(SCRATCH_TESTS, exist_ok=True)
    return tempfile.mkdtemp(dir=SCRATCH_TESTS)
