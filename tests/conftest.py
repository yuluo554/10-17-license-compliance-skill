# -*- coding: utf-8 -*-
"""pytest 桩：把 ``src`` 与 ``tests`` 放进 ``sys.path``。"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(REPO_ROOT, "src")

for path in (SRC_DIR, TESTS_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)
