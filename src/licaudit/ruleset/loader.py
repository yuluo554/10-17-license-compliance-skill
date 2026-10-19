# -*- coding: utf-8 -*-
"""规则包加载与校验。

硬门（K10/K24）：
  - 定位顺序：显式参数 > ``LICAUDIT_RULES_DIR`` > 仓库推导 > wheel 安装推导 > 当前目录
  - manifest 缺失 / schema 版本不支持 / 文件哈希不符 → :class:`RulesetError`（exit 3）
  - ``verified != true`` 或锚点缺失的条目**拒绝加载**，进 ``disabled`` 并显式输出
  - 不提供任何内置默认规则
"""

import hashlib
import io
import json
import os

from ..errors import RulesetError

ENV_RULES_DIR = "LICAUDIT_RULES_DIR"
SUPPORTED_SCHEMA_VERSION = 1

# manifest.files 中允许登记的文件名（白名单，防把任意路径写进规则包）
ALLOWED_RULE_FILES = (
    "tiers.json",
    "obligations.json",
    "scenario-triggers.json",
    "conflict-pairs.json",
    "action-rules.json",
    "trove-map.json",
)

# 每份文件的硬门策略：
#   anchor —— 判定类规则，必须挂原文锚点 + verified + checked_on
#   source —— 映射类规则，必须挂来源 URL + checked_on（无原文锚点可言）
#   none   —— 定义文档（义务项命名与说明），不参与判定，只做结构校验
FILE_POLICIES = {
    "tiers.json": "anchor",
    "scenario-triggers.json": "anchor",
    "conflict-pairs.json": "anchor",
    "action-rules.json": "anchor",
    "trove-map.json": "source",
    "obligations.json": "none",
}

_REQUIRED_ANCHOR_KEYS = ("source", "ref")


def repo_root_from_package():
    """``src/licaudit/ruleset/loader.py`` → 仓库根（源码态）。"""
    return resource_roots()[0]


def resource_roots():
    """随包资源根候选，按优先级：**源码态仓库根 → 安装态 site-packages**。

    源码态：``src/licaudit/ruleset/loader.py`` 上溯三级 = 仓库根；
    安装态：``<site-packages>/licaudit/ruleset/loader.py`` 上溯两级 = ``<site-packages>``
    （wheel 里 ``references/`` 与 ``data/`` 是顶层数据包，见 pyproject 的 package-dir 映射）。
    两处都返回，由调用方按「文件是否真的在」挑选。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    return [
        os.path.dirname(os.path.dirname(os.path.dirname(here))),
        os.path.dirname(os.path.dirname(here)),
    ]


def candidate_dirs(explicit=None):
    """返回按优先级排列的候选规则包目录（去重，保持顺序）。"""
    candidates = []
    if explicit:
        candidates.append(os.path.abspath(explicit))
    env_value = os.environ.get(ENV_RULES_DIR)
    if env_value:
        candidates.append(os.path.abspath(env_value))
    for root in resource_roots():
        candidates.append(os.path.join(root, "references", "ruleset"))
    candidates.append(os.path.abspath(os.path.join(os.getcwd(), "references", "ruleset")))
    seen = []
    for candidate in candidates:
        if candidate not in seen:
            seen.append(candidate)
    return seen


def locate_ruleset(explicit=None):
    """按优先级找到第一个含 manifest.json 的目录；都没有则抛错。

    显式 ``--rules-dir`` 若是无效目录，**不回退**到环境变量/仓库推导——
    否则 ``--rules-dir /empty`` 会静默用上另一份规则，等于让调用方误以为在验证它指定的那份。
    """
    if explicit:
        explicit_path = os.path.abspath(explicit)
        manifest_path = os.path.join(explicit_path, "manifest.json")
        if os.path.isfile(manifest_path):
            return explicit_path
        raise RulesetError(
            "显式指定的规则包目录中没有 manifest.json",
            path=explicit_path,
            tried=explicit_path,
            hint="--rules-dir 指向的目录必须含 manifest.json；不会回退到其他来源",
        )

    tried = candidate_dirs(None)
    for candidate in tried:
        manifest_path = os.path.join(candidate, "manifest.json")
        if os.path.isfile(manifest_path):
            return candidate
    raise RulesetError(
        "未找到规则包（references/ruleset/manifest.json）",
        tried=" | ".join(tried),
        hint="先运行 tools/gen_ruleset.py 生成规则包，或用 --rules-dir 指定目录",
    )


def _read_json(path, what):
    try:
        with io.open(path, "r", encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise RulesetError("规则包文件不可读", file=what, reason=str(exc))


def sha256_file(path):
    digest = hashlib.sha256()
    with io.open(path, "rb") as stream:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


class Ruleset(object):
    """已加载并校验通过的规则包。

    ``entries`` 是各文件里通过硬门的条目；``disabled`` 是被拒绝条目的说明列表。
    """

    def __init__(self, root, manifest, documents, enabled, disabled):
        self.root = root
        self.manifest = manifest
        self.documents = documents
        self.enabled = enabled
        self.disabled = disabled

    @property
    def version(self):
        return self.manifest.get("ruleset_version")

    @property
    def license_list_version(self):
        return self.manifest.get("license_list_version")

    def entries(self, name):
        return self.enabled.get(name, [])

    def summary(self):
        counts = {}
        for name in ALLOWED_RULE_FILES:
            counts[name] = len(self.enabled.get(name, []))
        return {
            "ruleset_version": self.version,
            "license_list_version": self.license_list_version,
            "enabled": counts,
            "disabled": len(self.disabled),
        }


def _looks_like_anchor(anchor):
    if not isinstance(anchor, dict):
        return False
    for key in _REQUIRED_ANCHOR_KEYS:
        value = anchor.get(key)
        if not isinstance(value, str) or not value.strip():
            return False
    return True


def _partition_entries(name, payload):
    """把一份规则文件分成「通过硬门」与「被拒绝」两组。"""
    if not isinstance(payload, dict):
        raise RulesetError("规则文件顶层必须是对象", file=name)
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise RulesetError("规则文件缺少 entries 数组", file=name)

    policy = FILE_POLICIES.get(name, "anchor")
    enabled = []
    disabled = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            disabled.append(
                {"file": name, "index": index, "reason": "entry_not_object"}
            )
            continue
        reasons = []
        # 定义文档（义务项命名与说明）不参与判定，不要求核对日期
        if policy != "none" and not entry.get("checked_on"):
            reasons.append("checked_on_missing")
        if policy == "anchor":
            if entry.get("verified") is not True:
                reasons.append("not_verified")
            if not _looks_like_anchor(entry.get("anchor")):
                reasons.append("anchor_missing")
        elif policy == "source":
            source_url = entry.get("source_url")
            if not isinstance(source_url, str) or not source_url.strip():
                reasons.append("source_url_missing")
        if reasons:
            disabled.append(
                {
                    "file": name,
                    "index": index,
                    "id": entry.get("id")
                    or entry.get("license_id")
                    or entry.get("pair_id")
                    or entry.get("classifier"),
                    "reasons": reasons,
                }
            )
            continue
        enabled.append(entry)
    return enabled, disabled


def load_ruleset(explicit=None, verify_hashes=True):
    """加载规则包；任何硬门失败都抛 :class:`RulesetError`。"""
    root = locate_ruleset(explicit)
    manifest_path = os.path.join(root, "manifest.json")
    manifest = _read_json(manifest_path, "manifest.json")

    if not isinstance(manifest, dict):
        raise RulesetError("manifest 顶层必须是对象", file="manifest.json")
    if manifest.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise RulesetError(
            "规则包 schema 版本不受支持",
            got=manifest.get("schema_version"),
            supported=SUPPORTED_SCHEMA_VERSION,
        )
    if not manifest.get("ruleset_version"):
        raise RulesetError("manifest 缺少 ruleset_version", file="manifest.json")
    if not manifest.get("license_list_version"):
        raise RulesetError("manifest 缺少 license_list_version", file="manifest.json")

    declared = manifest.get("files")
    if not isinstance(declared, dict) or not declared:
        raise RulesetError("manifest 缺少 files 清单", file="manifest.json")

    documents = {}
    for name in sorted(declared):
        if name not in ALLOWED_RULE_FILES:
            raise RulesetError(
                "manifest 登记了白名单外的文件", file=name, allowed=", ".join(ALLOWED_RULE_FILES)
            )
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            raise RulesetError("manifest 登记的文件不存在", file=name)
        expected = declared[name]
        if verify_hashes:
            if not isinstance(expected, str) or len(expected) != 64:
                raise RulesetError("manifest 中的 sha256 形态不合法", file=name, got=expected)
            actual = sha256_file(path)
            if actual != expected:
                raise RulesetError(
                    "规则包文件与 manifest 哈希不一致（可能被手改或生成器漂移）",
                    file=name,
                    expected=expected,
                    actual=actual,
                )
        documents[name] = _read_json(path, name)

    enabled = {}
    disabled = []
    for name in sorted(documents):
        file_enabled, file_disabled = _partition_entries(name, documents[name])
        enabled[name] = file_enabled
        disabled.extend(file_disabled)

    return Ruleset(root=root, manifest=manifest, documents=documents,
                   enabled=enabled, disabled=disabled)
