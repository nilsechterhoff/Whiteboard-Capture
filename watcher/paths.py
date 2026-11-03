"""The one place where the watcher's local folder is named (BL-035, item 5 of batch 1 fix-up).

Every local file (config, state, work and result copies, logs, failed-request photos) lives in
CONFIG_DIR. The name is a working name; the rename of the brand is BL-046. Standard library only.
"""

import os

CONFIG_DIR = os.path.expanduser('~/Library/Application Support/aiaiboard')
