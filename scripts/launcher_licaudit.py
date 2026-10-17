#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Skill 场景的薄启动器：编码守卫 + 转交包内 ``main``。

只做两件事：
1. 把仓库的 ``src`` 放进 ``sys.path``（未安装时也能跑）；
2. 安装编码守卫后调用 ``licaudit.cli.main``。

**不承担任何业务判断**。这样「装了包」与「直接跑启动器」是同一份逻辑。
"""

import os
import sys


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv=None):
    root = _repo_root()
    src = os.path.join(root, "src")
    if src not in sys.path:
        sys.path.insert(0, src)

    from licaudit.cli import main as cli_main
    from licaudit.encoding import ensure_utf8_stdio

    ensure_utf8_stdio()
    return cli_main(argv)


if __name__ == "__main__":
    sys.exit(main())
