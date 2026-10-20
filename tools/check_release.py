#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""发布终态自检（M6）：tag / Release 附件 / 留档三件套是否真的成立。

这是**发布门**，不是生成器：它不改任何文件、不产生新事实，只回答
「仓库当前状态够不够格叫一次发布」。

离线检查（默认，不联网）
------------------------

1. 发布留档存在且含「tag 时点事实」「tag 后追加事实」两栏。留档按**包版本**发现：
   `plan/RELEASE-*.md` 里 `tag` 字段等于 `v<pyproject version>` 的那一份
   （M0–M6 收口后按版本命名，如 `plan/RELEASE-v0.1.2.md`；M6 留档 `tag: v0.1.0` 不再被误当当前版本）。
2. 留档里没有未填写的占位标记（``TODO`` / ``待追加`` / ``待首推`` 等）。
   发布终态必须无占位；这一条在发布前**故意**是红的。
3. 版本三方一致：``pyproject.toml`` 的 ``version`` == ``SKILL.md`` 前言的
   ``version`` == 留档 ``release`` 块里的 ``tag``（``v<version>``）。
4. 规则包版本一致：``references/ruleset/manifest.json`` 的 ``ruleset_version`` /
   ``license_list_version`` == 留档登记值。
5. sdist 自足：``MANIFEST.in`` 覆盖 ``references`` 与 ``data``
   （否则解包后 ``licaudit status`` 会 exit 3，源码包不算交付物）。
6. 口径已翻转：README / SKILL 的「当前状态」提到本版版本号；
   ``plan/00`` 的里程碑表 M6 行是 ✅。
7. 附件清单可机读：留档里有 ```sums 围栏块，每行 ``<sha256>  <文件名>``。

可选 ``--artifacts-dir DIR``：核对本地产物文件的 sha256 是否与留档一致。

联网检查（``--online``，走 ``gh``）
----------------------------------

8. 仓库存在且**公开**。
9. tag 已推送，且指向留档登记的 ``tag_commit``。
10. 该提交的 CI 运行全绿（四个矩阵 job 全部 success）。
11. Release 存在（非 draft），附件名集合 == 留档 `sums` 块的文件名集合。
12. 逐个把附件**下载回来**重算 sha256，与留档登记值逐一比对。

用法::

    py -3.12 -X utf8 tools/check_release.py
    py -3.12 -X utf8 tools/check_release.py --artifacts-dir dist
    py -3.12 -X utf8 tools/check_release.py --online

退出码：0 全部通过 / 1 有检查项失败 / 2 用法错误。
"""

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO_ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

RELEASE_DIR = os.path.join(REPO_ROOT, "plan")
RELEASE_PREFIX = "RELEASE-"
RELEASE_SUFFIX = ".md"
README_PATH = os.path.join(REPO_ROOT, "README.md")
SKILL_PATH = os.path.join(REPO_ROOT, "SKILL.md")
PYPROJECT_PATH = os.path.join(REPO_ROOT, "pyproject.toml")
MANIFEST_PATH = os.path.join(REPO_ROOT, "MANIFEST.in")
RULESET_MANIFEST = os.path.join(REPO_ROOT, "references", "ruleset", "manifest.json")
PLAN00_PATH = os.path.join(REPO_ROOT, "plan", "00-README总览.md")

REQUIRED_SECTIONS = ("tag 时点事实", "tag 后追加事实")

# 发布终态不许残留的占位标记。写进这里是刻意的：发布前这些词必须被真事实替换掉。
PLACEHOLDERS = (
    "TODO",
    "FIXME",
    "TBD",
    "待追加",
    "待填",
    "待补",
    "待首推",
    "待复核",
    "<sha256>",
    "<url>",
)

FENCE_RE = re.compile(r"^```([A-Za-z0-9_-]*)\s*$")
SUMS_LINE_RE = re.compile(r"^([0-9a-f]{64})\s{1,2}(\S+)\s*$")

# 附件里的校验和清单文件。```sums 块登记的是**被哈希的载荷文件**，这个文件是它们的
# 伴随清单（自身不进 ```sums 块），因此远端附件集合 = 登记的载荷 + 它。
SUMS_FILE = "SHA256SUMS"


def read_text(path):
    with io.open(path, encoding="utf-8") as stream:
        return stream.read()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fenced_blocks(text):
    """返回 [(info_string, [行])]；未闭合的围栏按到文件尾处理。"""
    blocks = []
    info = None
    body = []
    for line in text.split("\n"):
        match = FENCE_RE.match(line)
        if match and info is None:
            info = match.group(1)
            body = []
            continue
        if FENCE_RE.match(line) and info is not None:
            blocks.append((info, body))
            info = None
            body = []
            continue
        if info is not None:
            body.append(line)
    if info is not None:
        blocks.append((info, body))
    return blocks


def parse_release_block(text, problems):
    """取所有 ```release 块里的 ``key: value``，按文档顺序后者覆盖前者。

    两栏各放一块：第一节只写 tag 时点字段，第二节追加 tag 后字段。
    """
    seen = False
    fields = {}
    for info, body in fenced_blocks(text):
        if info != "release":
            continue
        seen = True
        for line in body:
            if not line.strip():
                continue
            if ":" not in line:
                problems.append("release 块里有非 ``key: value`` 行：{0}".format(line))
                continue
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    if not seen:
        problems.append("留档里没有 ```release 键值块（tag / 版本 / 仓库地址的机读来源）")
    return fields


def parse_sums_block(text, problems):
    """取所有 ```sums 块里的 ``sha256 文件名`` 清单，按文档顺序拼接。"""
    seen = False
    sums = []
    for info, body in fenced_blocks(text):
        if info != "sums":
            continue
        seen = True
        for line in body:
            if not line.strip():
                continue
            match = SUMS_LINE_RE.match(line)
            if not match:
                problems.append("sums 块里有无法解析的行：{0}".format(line))
                continue
            sums.append((match.group(1), match.group(2)))
    if not seen:
        problems.append("留档里没有 ```sums 围栏块（附件校验和的机读来源）")
    elif not sums:
        problems.append("sums 块为空；附产物发布必须登记 sha256")
    return sums


def parse_pyproject_version(problems):
    text = read_text(PYPROJECT_PATH)
    match = re.search(r'^version\s*=\s*"([^"]+)"\s*$', text, re.MULTILINE)
    if not match:
        problems.append("pyproject.toml 里找不到 version")
        return None
    return match.group(1)


def parse_skill_version(problems):
    text = read_text(SKILL_PATH)
    match = re.search(r"^\s+version:\s*(\S+)\s*$", text, re.MULTILINE)
    if not match:
        problems.append("SKILL.md 前言里找不到 metadata.version")
        return None
    return match.group(1)


def gh(args, problems=None, check=True):
    """调用 gh；返回 (rc, stdout)。缺失 gh 时给出可读原因，不抛栈。"""
    try:
        proc = subprocess.Popen(
            ["gh"] + list(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        message = "无法执行 gh（{0}）；联网检查需要 GitHub CLI 且已登录".format(exc)
        if problems is not None:
            problems.append(message)
        return 127, ""
    out, err = proc.communicate()
    text = out.decode("utf-8", "replace")
    if proc.returncode != 0 and problems is not None:
        problems.append(
            "gh {0} 失败（rc={1}）：{2}".format(
                " ".join(args), proc.returncode, err.decode("utf-8", "replace").strip()
            )
        )
    if check and proc.returncode != 0:
        return proc.returncode, text
    return proc.returncode, text


def gh_json(args, problems):
    rc, out = gh(args, problems)
    if rc != 0:
        return None
    try:
        return json.loads(out)
    except ValueError:
        problems.append("gh {0} 的返回不是 JSON".format(" ".join(args)))
        return None


# --------------------------------------------------------------------------
# 离线检查
# --------------------------------------------------------------------------


def release_note_candidates():
    """`plan/RELEASE-*.md` 的全部候选（字典序）。"""
    if not os.path.isdir(RELEASE_DIR):
        return []
    return sorted(
        os.path.join(RELEASE_DIR, name)
        for name in os.listdir(RELEASE_DIR)
        if name.startswith(RELEASE_PREFIX) and name.endswith(RELEASE_SUFFIX)
    )


def release_note_tag(path):
    """取某个留档的 ```release 块里的 ``tag``；读不到返回 None。"""
    try:
        text = read_text(path)
    except OSError:
        return None
    for info, body in fenced_blocks(text):
        if info != "release":
            continue
        for line in body:
            if line.strip().startswith("tag:"):
                return line.split(":", 1)[1].strip()
    return None


def resolve_release_note(version, problems):
    """按包版本挑发布留档：``tag`` 字段 == ``v<version>`` 的那一份。

    旧版把路径写死成 `plan/RELEASE-M6.md`，包版本一抬（0.1.1）就永远红——
    那会把「门禁红」变成噪音。里程碑 M0–M6 收口后留档按版本命名，
    因此这里用「留档自己登记的 tag」配对，而不是靠文件名或时间排序。
    """
    candidates = release_note_candidates()
    if not candidates:
        problems.append(
            "plan/ 下没有 {0}*{1} 发布留档（发布留档必须在 tag 之前入库）".format(
                RELEASE_PREFIX, RELEASE_SUFFIX
            )
        )
        return None
    if not version:
        return None
    wanted = "v" + version
    matched = [path for path in candidates if release_note_tag(path) == wanted]
    if not matched:
        problems.append(
            "plan/ 下没有 tag 为 {0} 的发布留档（现有留档：{1}）；"
            "发布留档必须在 tag 之前入库".format(
                wanted, "、".join(os.path.basename(p) for p in candidates)
            )
        )
        return None
    if len(matched) > 1:
        problems.append(
            "plan/ 下有多份 tag 为 {0} 的留档：{1}".format(
                wanted, "、".join(os.path.basename(p) for p in matched)
            )
        )
    return matched[0]


def check_release_note_exists(note_path, problems):
    if not os.path.isfile(note_path):
        problems.append(
            "缺少 {0}（发布留档必须在 tag 之前入库）".format(
                os.path.relpath(note_path, REPO_ROOT).replace(os.sep, "/")
            )
        )
        return None
    text = read_text(note_path)
    # 必须是真的**标题行**，不能靠正文里提到过这两个词就算数。
    headings = [line.strip() for line in text.split("\n") if line.startswith("## ")]
    missing = [
        name for name in REQUIRED_SECTIONS if not any(name in heading for heading in headings)
    ]
    if missing:
        problems.append(
            "留档缺少必需的栏目标题：{0}（口径：tag 时点事实 / tag 后追加事实两栏）".format(
                "、".join(missing)
            )
        )
    return text


def check_no_placeholders(text, problems):
    found = []
    for lineno, line in enumerate(text.split("\n"), 1):
        for marker in PLACEHOLDERS:
            if marker in line:
                found.append("第 {0} 行残留占位标记 {1}".format(lineno, marker))
    if found:
        problems.append(
            "留档还有未填写的占位标记（发布终态必须无占位）：{0}".format("；".join(found))
        )


def check_version_consistency(fields, online, problems):
    version = parse_pyproject_version(problems)
    skill_version = parse_skill_version(problems)
    tag = fields.get("tag")

    if version and skill_version and version != skill_version:
        problems.append(
            "版本不一致：pyproject.toml={0} 而 SKILL.md={1}".format(version, skill_version)
        )
    if version and tag and tag != "v" + version:
        problems.append("留档 tag={0} 与包版本 {1} 不匹配（应为 v{1}）".format(tag, version))

    recorded = fields.get("tag_commit")
    if not recorded:
        # tag 提交 sha 只能在提交之后得知，因此只在联网核对时当作硬要求。
        if online:
            problems.append("留档 release 块缺少 tag_commit（联网核对需要它）")
    elif not re.match(r"^[0-9a-f]{40}$", recorded):
        problems.append("留档 tag_commit 不是 40 位 sha：{0}".format(recorded))
    return version, tag


def check_ruleset_versions(fields, problems):
    try:
        manifest = json.loads(read_text(RULESET_MANIFEST))
    except (OSError, ValueError) as exc:
        problems.append("读不到规则包 manifest：{0}".format(exc))
        return
    for field, key in (("ruleset_version", "ruleset_version"),
                       ("license_list_version", "license_list_version")):
        actual = manifest.get(key)
        recorded = fields.get(field)
        if not recorded:
            problems.append("留档 release 块缺少 {0}".format(field))
        elif actual != recorded:
            problems.append(
                "规则包 {0} 与留档不一致：manifest={1} 留档={2}".format(key, actual, recorded)
            )


def recursive_includes(text):
    """把 MANIFEST.in 的 ``recursive-include <dir> <pattern...>`` 解析成 {目录: [pattern]}。"""
    table = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line.startswith("recursive-include"):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        table.setdefault(parts[1], []).extend(parts[2:])
    return table


def check_sdist_self_sufficient(problems):
    """sdist 必须带上规则包与真值，否则「源码包」解包即 exit 3。

    权威证明是**真去解包构建出来的 sdist** 跑一遍 `licaudit status`
    （记录在 `plan/RELEASE-M6.md` §2.5）；这里守的是清单本身别退化——
    只要求「有 recursive-include references」太松，得要求它确实覆盖 `.json`。
    """
    if not os.path.isfile(MANIFEST_PATH):
        problems.append("缺少 MANIFEST.in；sdist 会丢掉 references/ 规则包，源码包不自足")
        return
    table = recursive_includes(read_text(MANIFEST_PATH))
    for needed in ("references", "data"):
        patterns = table.get(needed)
        if not patterns:
            problems.append("MANIFEST.in 没有 recursive-include {0}/".format(needed))
        elif "*.json" not in patterns:
            problems.append(
                "MANIFEST.in 的 recursive-include {0} 不覆盖 *.json（规则包/快照/真值都是 JSON）：{1}".format(
                    needed, patterns
                )
            )


def check_status_flipped(version, problems):
    if version:
        for label, path in (("README.md", README_PATH), ("SKILL.md", SKILL_PATH)):
            text = read_text(path)
            if version not in text:
                problems.append("{0} 的「当前状态」没有提到本版版本号 {1}".format(label, version))
            if "M6" not in text:
                problems.append("{0} 没有提到 M6（发布里程碑）".format(label))

    plan00 = read_text(PLAN00_PATH)
    row = [line for line in plan00.split("\n") if line.startswith("| **M6 发布**")]
    if not row:
        problems.append("plan/00 的里程碑表里找不到 M6 行")
    elif "✅" not in row[0]:
        problems.append("plan/00 的 M6 行仍是 ⬜（未翻转）")


def check_artifacts_local(sums, artifacts_dir, problems):
    if artifacts_dir is None:
        return
    for digest, name in sums:
        path = os.path.join(artifacts_dir, name)
        if not os.path.isfile(path):
            problems.append("--artifacts-dir 下缺附件：{0}".format(name))
            continue
        actual = sha256_file(path)
        if actual != digest:
            problems.append(
                "本地产物 {0} 的 sha256 与留档不一致：{1} != {2}".format(name, actual, digest)
            )


# --------------------------------------------------------------------------
# 联网检查
# --------------------------------------------------------------------------


def repo_slug(fields, problems):
    url = fields.get("repository", "")
    match = re.search(r"github\.com[:/]+([^/]+)/([^/\s]+?)(?:\.git)?$", url)
    if not match:
        problems.append("留档 repository 不是可解析的 GitHub 地址：{0}".format(url))
        return None
    return "{0}/{1}".format(match.group(1), match.group(2))


def resolve_tag_commit(slug, tag, problems):
    data = gh_json(["api", "repos/{0}/git/ref/tags/{1}".format(slug, tag)], problems)
    if data is None:
        problems.append("tag {0} 未推送（远端查不到）".format(tag))
        return None
    obj = data.get("object") or {}
    if obj.get("type") == "tag":
        tag_obj = gh_json(["api", "repos/{0}/git/tags/{1}".format(slug, obj.get("sha"))], problems)
        if tag_obj is None:
            return None
        return (tag_obj.get("object") or {}).get("sha")
    return obj.get("sha")


def check_online(fields, sums, problems):
    slug = repo_slug(fields, problems)
    if slug is None:
        return
    tag = fields.get("tag")

    repo = gh_json(["repo", "view", slug, "--json", "isPrivate,url"], problems)
    if repo is None:
        problems.append("仓库 {0} 不可见（未创建 / 无权访问）".format(slug))
        return
    if repo.get("isPrivate"):
        problems.append("仓库 {0} 不是公开仓库（D18 要求公开）".format(slug))

    commit = resolve_tag_commit(slug, tag, problems)
    recorded = fields.get("tag_commit")
    if commit and recorded and commit != recorded:
        problems.append(
            "tag {0} 指向 {1}，与留档登记的 {2} 不一致".format(tag, commit, recorded)
        )

    if commit:
        check_ci_green(slug, commit, problems)

    release = gh_json(
        ["release", "view", tag, "--repo", slug, "--json", "tagName,url,isDraft,isPrerelease,assets"],
        problems,
    )
    if release is None:
        problems.append("Release {0} 不存在（tag 不足以构成「附产物」的发布）".format(tag))
        return
    if release.get("isDraft"):
        problems.append("Release {0} 仍是 draft".format(tag))

    remote = sorted(asset.get("name") for asset in release.get("assets") or [])
    expected = sorted(set(name for _, name in sums) | {SUMS_FILE})
    if remote != expected:
        problems.append(
            "Release 附件与留档登记不一致：远端={0} 期望={1}（登记的载荷 + {2}）".format(
                remote, expected, SUMS_FILE
            )
        )

    check_downloaded_sums(slug, tag, sums, problems)


def check_ci_green(slug, commit, problems):
    runs = gh_json(
        [
            "run",
            "list",
            "--repo",
            slug,
            "--commit",
            commit,
            "--limit",
            "10",
            "--json",
            "databaseId,name,status,conclusion,headSha",
        ],
        problems,
    )
    if runs is None:
        return
    if not runs:
        problems.append("提交 {0} 没有 CI 运行记录（首推未触发）".format(commit[:12]))
        return
    for run in runs:
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            problems.append(
                "CI 运行未全绿：{0}（status={1} conclusion={2}）".format(
                    run.get("name"), run.get("status"), run.get("conclusion")
                )
            )
            continue
        jobs = gh_json(
            ["run", "view", str(run.get("databaseId")), "--repo", slug, "--json", "jobs"],
            problems,
        )
        if jobs is None:
            continue
        for job in jobs.get("jobs") or []:
            if job.get("conclusion") != "success":
                problems.append(
                    "CI job 未通过：{0}（conclusion={1}）".format(
                        job.get("name"), job.get("conclusion")
                    )
                )


def check_downloaded_sums(slug, tag, sums, problems):
    with tempfile.TemporaryDirectory(prefix="licaudit-release-") as tmp:
        for digest, name in sums:
            rc, _ = gh(
                ["release", "download", tag, "--repo", slug, "--pattern", name, "--dir", tmp],
                problems,
            )
            if rc != 0:
                continue
            path = os.path.join(tmp, name)
            if not os.path.isfile(path):
                problems.append("下载回来的附件里找不到 {0}".format(name))
                continue
            actual = sha256_file(path)
            if actual != digest:
                problems.append(
                    "下载回来的 {0} sha256 与留档不一致：{1} != {2}".format(
                        name, actual, digest
                    )
                )

        # 伴随清单自身也要核对：它必须恰好登记同一批载荷（否则「校验和文件」可以撒谎）。
        rc, _ = gh(
            ["release", "download", tag, "--repo", slug, "--pattern", SUMS_FILE, "--dir", tmp],
            problems,
        )
        if rc != 0:
            return
        path = os.path.join(tmp, SUMS_FILE)
        if not os.path.isfile(path):
            problems.append("Release 附件里缺少 {0}".format(SUMS_FILE))
            return
        listed = []
        for line in read_text(path).split("\n"):
            if not line.strip():
                continue
            match = SUMS_LINE_RE.match(line)
            if not match:
                problems.append("{0} 里有无法解析的行：{1}".format(SUMS_FILE, line))
                continue
            listed.append((match.group(1), match.group(2)))
        if sorted(listed) != sorted(sums):
            problems.append(
                "下载回来的 {0} 与留档 ```sums 块登记的不是同一批：{1} vs {2}".format(
                    SUMS_FILE, sorted(listed), sorted(sums)
                )
            )


# --------------------------------------------------------------------------


def run(args):
    problems = []

    version = parse_pyproject_version(problems)
    note_path = resolve_release_note(version, problems)
    if note_path is None:
        return problems
    note = check_release_note_exists(note_path, problems)
    if note is None:
        return problems

    check_no_placeholders(note, problems)
    fields = parse_release_block(note, problems)
    sums = parse_sums_block(note, problems)

    version, _tag = check_version_consistency(fields, args.online, problems)
    check_ruleset_versions(fields, problems)
    check_sdist_self_sufficient(problems)
    check_status_flipped(version, problems)
    check_artifacts_local(sums, args.artifacts_dir, problems)

    if args.online and not problems:
        check_online(fields, sums, problems)
    elif args.online:
        sys.stdout.write("[SKIP] 离线检查未通过，跳过联网检查（先修离线项）\n")

    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="check_release",
        description="发布终态自检：tag / Release 附件 / 留档三件套（留档按包版本发现）",
    )
    parser.add_argument("--online", action="store_true",
                        help="额外核对远端：仓库公开、tag 指向、CI 全绿、Release 附件与 sha256")
    parser.add_argument("--artifacts-dir", default=None,
                        help="本地产物目录；核对文件 sha256 是否与留档登记一致")
    args = parser.parse_args(argv)

    problems = run(args)
    if problems:
        for problem in problems:
            sys.stdout.write("[FAIL] {0}\n".format(problem))
        sys.stdout.write("[FAIL] 发布终态自检未通过：{0} 项\n".format(len(problems)))
        return 1

    mode = "离线 + 联网" if args.online else "离线"
    sys.stdout.write("[OK] 发布终态自检通过（{0}）：留档两栏 / 版本三方一致 / "
                     "sdist 自足 / 口径已翻转 / 附件校验和可机读\n".format(mode))
    return 0


if __name__ == "__main__":
    sys.exit(main())
