#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""M6 变异验证（一次性脚本，不入发布面）。

发布门最大的风险是「永远绿」：一个只会打印 [OK] 的 `check_release.py` 比没有门更糟。
本脚本对**发布态本身**做「弄坏 → 变红 → 恢复 → 变绿」，逐条证明门真的在看东西。

- 离线组（不联网）：留档缺栏目 / 留档里出现占位标记 / 校验和行不是 sha256 /
  规则包版本与留档不一致 / `plan/00` 状态表没翻转 / `MANIFEST.in` 不再打包规则包 /
  包版本与 SKILL 版本不一致 / 留档 tag 与包版本不匹配。
- 联网组（`--online`，会真下载附件，较慢）：tag 指向的提交与留档不符 /
  登记的附件名远端不存在 / 校验和是合法 sha256 但值不对。

用法::

    py -3.12 -X utf8 tools/_mutate_m6.py
    py -3.12 -X utf8 tools/_mutate_m6.py --offline-only
"""

import argparse
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NOTE = os.path.join("plan", "RELEASE-M6.md")
PLAN00 = os.path.join("plan", "00-README总览.md")
MANIFEST = "MANIFEST.in"
PYPROJECT = "pyproject.toml"

TAG_COMMIT = "4f4951c3dfe038a5c2b11e3cf95e2390d950e2cd"
GOOD_SHA = "aab14a19b749568f2523995d24cbabc3aeea764b4299412fbf4dd651ba9812ac"


def gate(online):
    argv = [sys.executable, "-X", "utf8", os.path.join("tools", "check_release.py")]
    if online:
        argv.append("--online")
    proc = subprocess.run(argv, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def apply(relpath, old, new):
    """写坏一处；返回 (path, 原字节)。锚点出现次数 != 1 直接报错（锚点漂移要立刻暴露）。"""
    path = os.path.join(REPO_ROOT, relpath)
    with open(path, "rb") as stream:
        original = stream.read()
    text = original.decode("utf-8")
    count = text.count(old)
    if count != 1:
        raise AssertionError("锚点在 {0} 里出现 {1} 次（应为 1 次）：{2!r}".format(relpath, count, old[:60]))
    with open(path, "wb") as stream:
        stream.write(text.replace(old, new).encode("utf-8"))
    return path, original


def mutate(name, relpath, old, new, online):
    path, original = apply(relpath, old, new)
    try:
        rc, out = gate(online)
        if rc == 0:
            print("[FAIL] {0}：弄坏后门仍然绿（门没在看这里）".format(name))
            return False
        first = [line for line in out.split("\n") if line.startswith("[FAIL]")]
        print("[OK]   {0}：" .format(name))
        print("         弄坏 -> 变红（rc={0}）｜{1}".format(rc, first[0][:130] if first else ""))
    finally:
        with open(path, "wb") as stream:
            stream.write(original)
    rc, out = gate(online)
    if rc != 0:
        print("[FAIL] {0}：恢复后门仍然红（恢复不干净）\n{1}".format(name, out[-300:]))
        return False
    print("         恢复 -> 变绿")
    return True


OFFLINE_CASES = [
    ("M1  留档缺「tag 后追加事实」一栏", NOTE, "## 二、tag 后追加事实", "## 二、补充记录"),
    ("M2  留档里残留占位标记", NOTE, "## 二、tag 后追加事实\n", "## 二、tag 后追加事实\n\n待追加\n"),
    ("M3  校验和行不是 sha256（截断成 40 位）", NOTE, GOOD_SHA, GOOD_SHA[:40]),
    ("M4  规则包版本与留档登记不一致", NOTE, "ruleset_version: r0.1.0", "ruleset_version: r0.9.9"),
    ("M5  plan/00 的 M6 行没翻转",
     PLAN00, "CI 首推四矩阵全绿 | ✅ 2026-10-17 |", "CI 首推四矩阵全绿 | ⬜ 2026-10-17 |"),
    ("M6  MANIFEST.in 不再把规则包打进 sdist",
     MANIFEST, "recursive-include references *.json *.md", "recursive-include references *.md"),
    ("M7  包版本与 SKILL 版本不一致", PYPROJECT, 'version = "0.1.0"', 'version = "0.2.0"'),
    ("M8  留档 tag 与包版本不匹配", NOTE, "tag: v0.1.0", "tag: v9.9.9"),
]

ONLINE_CASES = [
    ("M9  tag 指向的提交与留档登记不符", NOTE,
     "tag_commit: " + TAG_COMMIT, "tag_commit: " + "0" * 40),
    ("M10 登记的附件名在远端不存在", NOTE,
     "  licaudit-0.1.0.tar.gz", "  licaudit-9.9.9-nope.tar.gz"),
    ("M11 校验和是合法 sha256 但值不对", NOTE, GOOD_SHA, "f" * 64),
]


def main(argv=None):
    parser = argparse.ArgumentParser(prog="_mutate_m6", description="M6 发布门变异验证")
    parser.add_argument("--offline-only", action="store_true", help="跳过联网组（真下载附件，慢）")
    args = parser.parse_args(argv)

    rc, _ = gate(False)
    if rc != 0:
        print("[FAIL] 基线不绿，先修好再谈变异验证")
        return 1

    cases = list(OFFLINE_CASES)
    if not args.offline_only:
        cases.extend(ONLINE_CASES)

    ok = True
    for index, (name, relpath, old, new) in enumerate(cases):
        online = index >= len(OFFLINE_CASES)
        try:
            ok = mutate(name, relpath, old, new, online) and ok
        except AssertionError as exc:
            print("[FAIL] {0}：{1}".format(name, exc))
            ok = False

    print("")
    if ok:
        print("[OK] 变异验证通过：{0} 组「弄坏 → 变红 → 恢复 → 变绿」".format(len(cases)))
        return 0
    print("[FAIL] 变异验证有未通过项")
    return 1


if __name__ == "__main__":
    sys.exit(main())
