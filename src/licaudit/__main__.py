# -*- coding: utf-8 -*-
"""``python -m licaudit`` 入口。

包内需要 ``__main__.py``，否则 ``python -m licaudit`` 会报
``No module named licaudit.__main__`` —— 这是 README 指令面常见的空壳缺陷。
"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
