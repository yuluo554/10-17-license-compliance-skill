#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""M6 脱敏自查（一次性脚本，不入发布面）。

公开仓库之前的硬门，查三类东西（模式本身刻意不在本文档里逐字抄写，否则扫描器会命中自己的说明）：

1. **本机绝对路径**——盘符路径的几种写法（反斜杠与正斜杠两种分隔符）、
   类 Unix 家目录前缀、Git Bash 的盘符写法、UNC 路径。
2. **凭证**——token 形态（GitHub 的几种前缀、`sk-` 打头的密钥串）、PEM 私钥头、
   赋值式口令/密钥字段。
3. **模板脚手架残留**——全大写花括号占位、常见的占位人名变量、脚手架遗留的
   改动提示词（英文），以及尖括号里的全大写项目名占位。
   （**不收** `${{ ... }}` 与 Python 的 `{{` 转义：它们是 Actions 表达式与格式化语法，不是占位。）

`git ls-files -co --exclude-standard` 取面（含未跟踪但未被 ignore 的文件），二进制跳过，逐行匹配。

**`references/spdx/` 单独归类为上游冻结数据**（许可证原文里本来就有反斜杠、人名、邮箱、地址），
命中的是原文内容而不是本仓引入的东西，因此与「本仓命中」分开计数，不混进结论。

它是**模式扫描**：结论是「按这些模式没命中」，不是「必然不含任何敏感信息」。
命中明细逐条打印，便于人工复核。退出码 0 表示「本仓没有需要人工判断的命中」。

用法::

    py -3.12 -X utf8 tools/_scan_desensitize.py
    py -3.12 -X utf8 tools/_scan_desensitize.py --quiet
"""

import argparse
import collections
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

SLASH = re.escape("\\")
UPSTREAM_PREFIX = "references/spdx/"

PATTERNS = (
    # 1. 本机绝对路径
    ("win-drive", re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/](?![\\/])")),
    ("posix-home", re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+")),
    ("gitbash-drive", re.compile(r"(?<![A-Za-z0-9])/[a-z]/(?:Program|Users|home|tmp|mnt)[/\\]")),
    ("unc", re.compile(SLASH + r"{2}[A-Za-z0-9._-]+" + SLASH)),

    # 2. 凭证
    ("token-ish", re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,})\b")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("password-assign", re.compile(
        r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*[\"'][^\"']{4,}[\"']")),

    # 3. 模板脚手架残留
    ("template", re.compile(
        r"\{\{\s*[A-Z_]+\s*\}\}|\bYOUR[_ -]?NAME\b|\bchangeme\b|\blorem ipsum\b|<\s*PROJECT[_ ]?NAME\s*>")),

    # 附：邮箱（VCS 远端写法不算，见 VCS_USERS）
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
)

# VCS 远端的 `user@host` 写法不是邮箱地址。
VCS_USERS = frozenset(("git", "hg", "svn", "bzr"))

# 这三类「本仓引入」才叫问题；邮箱到处都是（上游原文、版权声明、NOTICE 条款），单独列。
VERDICT_TYPES = ("win-drive", "posix-home", "gitbash-drive", "unc",
                 "token-ish", "private-key", "password-assign", "template")


def listed():
    out = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=str(REPO), capture_output=True, text=True, check=True,
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def scan():
    """返回 [(相对路径, 行号, 类型, 命中片段, 整行)]。"""
    hits = []
    for rel in listed():
        path = REPO / rel
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw[:8000]:
            continue
        for lineno, line in enumerate(raw.decode("utf-8", "replace").splitlines(), 1):
            for name, rx in PATTERNS:
                match = rx.search(line)
                if not match:
                    continue
                if name == "email" and match.group(0).split("@")[0].lower() in VCS_USERS:
                    continue
                hits.append((rel, lineno, name, match.group(0), line.strip()))
    return hits


def main(argv=None):
    parser = argparse.ArgumentParser(prog="_scan_desensitize", description="M6 脱敏自查")
    parser.add_argument("--quiet", action="store_true", help="只打印结论与类型分布")
    args = parser.parse_args(argv)

    hits = scan()
    upstream = [h for h in hits if h[0].startswith(UPSTREAM_PREFIX)]
    own = [h for h in hits if not h[0].startswith(UPSTREAM_PREFIX)]

    if not args.quiet:
        for rel, lineno, name, snippet, line in hits:
            sys.stdout.write("%s:%d\t[%s]\t%s\t%s\n" % (rel, lineno, name, snippet[:60], line[:110]))
        sys.stdout.write("\n")

    by_type = collections.Counter(name for _, _, name, _, _ in own)
    verdict = [h for h in own if h[2] in VERDICT_TYPES]
    sys.stdout.write("扫描面（git ls-files -co --exclude-standard）: %d 个文件\n" % len(listed()))
    sys.stdout.write("本仓命中类型分布: %s\n" % dict(sorted(by_type.items())))
    sys.stdout.write("本仓需人工判断的命中（路径/凭证/模板）: %d\n" % len(verdict))
    for rel, lineno, name, _snippet, line in verdict:
        sys.stdout.write("    %s:%d [%s] %s\n" % (rel, lineno, name, line[:100]))
    sys.stdout.write("上游冻结数据（references/spdx/）命中: %d（许可证原文内容，非本仓引入）\n" % len(upstream))
    sys.stdout.write("TOTAL HITS: %d\n" % len(hits))
    return 1 if verdict else 0


if __name__ == "__main__":
    sys.exit(main())
