#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""合成依赖清单 + 真值库生成器（M1）。

设计纪律（plan/04 §四 / §五）：

- 确定性：自研 ``splitmix64``，不读时钟、不用 ``set`` 迭代序、所有列表显式排序。
- 真值由**独立朴素 oracle** 算出（不 import 生产解析器），写盘前断言
  「oracle 重算 == 声明期望」。
- 真值只存输入与期望；出现 ``observed_*`` 即测试红。
- ``--check`` 两层：冻结产物形态 + 重生成逐字节一致。

用法::

    py -3.12 -X utf8 tools/gen_synthetic.py
    py -3.12 -X utf8 tools/gen_synthetic.py --check
"""

import argparse
import io
import os
import shutil
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")
SYNTHETIC_DIR = os.path.join(DATA_DIR, "synthetic")
TRUTH_DIR = os.path.join(DATA_DIR, "truth")
TRUTH_FILE = os.path.join(TRUTH_DIR, "truth.json")

CHECKED_ON = "2026-10-17"
PACKAGE_PREFIX = "example-pkg-"

# 坑位用例的真实包名（白名单例外，见 plan/04 §4.1）
TRAP_PACKAGES = ("pandas", "psycopg2", "PyMySQL", "PyQt5")


# ---------------------------------------------------------------------------
# 确定性 RNG（splitmix64）
# ---------------------------------------------------------------------------


class SplitMix64(object):
    """Steele et al. 的 splitmix64；纯整数运算，跨版本一致。"""

    MASK = (1 << 64) - 1

    def __init__(self, seed):
        self.state = seed & self.MASK

    def next_u64(self):
        self.state = (self.state + 0x9E3779B97F4A7C15) & self.MASK
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & self.MASK
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & self.MASK
        return z ^ (z >> 31)

    def below(self, bound):
        if bound <= 0:
            raise ValueError("bound 必须为正")
        return self.next_u64() % bound


# ---------------------------------------------------------------------------
# 独立朴素 oracle（不调用生产解析器）
# ---------------------------------------------------------------------------

# 「一眼可判」的 ID 集合：这些字符串本身就是合法 SPDX ID
PLAIN_IDS = (
    "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD",
    "Unlicense", "Zlib", "MPL-2.0", "EPL-2.0", "GPL-2.0-only", "GPL-3.0-only",
    "LGPL-2.1-only", "LGPL-3.0-only", "AGPL-3.0-only", "SSPL-1.0", "BUSL-1.1",
    "GPL-2.0-or-later", "GPL-3.0-or-later", "MIT-0", "BSL-1.0", "UPL-1.0",
    "Python-2.0",
)
PLAIN_ID_SET = set(PLAIN_IDS)

# 首行锚定可接受的整行形态（族名或「族名 + 版本」）
FAMILY_FIRST_LINES = {
    "GPL": "GPL-unknown",
    "LGPL": "LGPL-unknown",
    "AGPL": "AGPL-unknown",
    "Apache": "Apache-unknown",
    "BSD": "BSD-unknown",
}

VERSIONED_FIRST_LINES = {
    "GPL v2": ("GPL-2.0", "version-ambiguous", "deprecated-id"),
    "GPLv3": ("GPL-3.0", "version-ambiguous", "deprecated-id"),
    "GPL v3": ("GPL-3.0", "version-ambiguous", "deprecated-id"),
    "Apache 2.0": ("Apache-2.0",),
    "Apache License 2.0": ("Apache-2.0",),
    "Apache License, Version 2.0": ("Apache-2.0",),
    "LGPL v2.1": ("LGPL-2.1", "version-ambiguous", "deprecated-id"),
    "AGPL v3": ("AGPL-3.0", "version-ambiguous", "deprecated-id"),
}

TROVE_MAP = {
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: ISC License (ISCL)": "ISC",
    "License :: OSI Approved :: BSD License": "BSD-3-Clause",
    "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "License :: OSI Approved :: The Unlicense (Unlicense)": "Unlicense",
}

KNOWN_EXCEPTIONS = ("Classpath-exception-2.0", "LLVM-exception", "GCC-exception-3.1")


def oracle_normalize(raw_license, classifiers=None, structured=True):
    """朴素 oracle：把一条记录判成 ``(spdx_id, confidence, flags)``。

    刻意与生产实现**分开写**（不同代码路径、不同判断顺序），用于交叉验证。
    """
    classifiers = list(classifiers or [])

    # 第 1 级：结构化表达式
    if structured and isinstance(raw_license, str) and raw_license.strip():
        result = _oracle_expression(raw_license.strip())
        if result is not None:
            return result[0], "license_expression", result[1]

    # 第 2 级：trove
    for classifier in classifiers:
        if classifier in TROVE_MAP:
            return TROVE_MAP[classifier], "trove_classifier", []

    # 3 级：首行
    if isinstance(raw_license, str) and raw_license.strip():
        first_line = raw_license.strip().split("\n")[0].strip().split("\r")[0].strip()
        if first_line and len(first_line) <= 200:
            if first_line in PLAIN_ID_SET:
                return first_line, "license_first_line", []
            if first_line in FAMILY_FIRST_LINES:
                return FAMILY_FIRST_LINES[first_line], "license_first_line", ["family-unknown"]
            if first_line in VERSIONED_FIRST_LINES:
                value = VERSIONED_FIRST_LINES[first_line]
                return value[0], "license_first_line", list(value[1:])
            head, separator, _tail = " ".join(first_line.split()).partition(" License")
            if separator and head in PLAIN_ID_SET:
                return head, "license_first_line", []

    return None, "truncated_fallback", ["unresolved"]


def _oracle_expression(text):
    """朴素表达式判定：只处理本生成器产出的形态。

    支持单 ID / ``A OR B`` / ``A AND B`` / ``ID WITH exc`` / ``(A OR B) AND C``。
    刻意不实现通用文法（那是生产解析器的事），只覆盖本生成器写出的样例。
    """
    text = text.strip()
    if text in PLAIN_ID_SET:
        return text, []

    if " WITH " in text:
        left, _, right = text.partition(" WITH ")
        if left in PLAIN_ID_SET:
            flags = []
            if right not in KNOWN_EXCEPTIONS:
                flags.append("unknown-exception")
            return left + " WITH " + right, flags
        return None

    # 折叠一层括号：只支持 "(A OR B) OP C"
    if text.startswith("("):
        closing = text.find(")")
        if closing < 0:
            return None
        inner = text[1:closing]
        rest = text[closing + 1:].strip()
        inner_result = _oracle_expression(inner)
        if inner_result is None:
            return None
        if not rest:
            return inner_result
        for operator in ("AND", "OR"):
            prefix = operator + " "
            if rest.startswith(prefix):
                tail = rest[len(prefix):].strip()
                if tail in PLAIN_ID_SET:
                    return (
                        "({0}) {1} {2}".format(inner_result[0], operator, tail),
                        inner_result[1],
                    )
        return None

    for operator in (" OR ", " AND "):
        if operator in text:
            parts = text.split(operator)
            if all(part in PLAIN_ID_SET for part in parts):
                return operator.join(parts), []
            return None

    if text in FAMILY_FIRST_LINES:
        return FAMILY_FIRST_LINES[text], ["family-unknown"]
    return None


# ---------------------------------------------------------------------------
# 用例定义
# ---------------------------------------------------------------------------


def _pkg(letter):
    return PACKAGE_PREFIX + letter


def _case(case_id, files, expectations, note):
    return {
        "case_id": case_id,
        "files": files,
        "expect": expectations,
        "note": note,
    }


def build_cases():
    """返回 ``[(case_id, {relpath: text}, {package: expect})]``（按 case_id 排序）。"""
    cases = []

    # --- npm-basic：字符串 license / 对象 license / licenses 数组 ---
    package_json = """{
  "name": "example-app",
  "version": "1.0.0",
  "license": "MIT",
  "dependencies": {
    "example-pkg-a": {
      "version": "1.0.0",
      "license": "MIT"
    },
    "example-pkg-b": {
      "version": "2.1.0",
      "license": {
        "type": "Apache-2.0"
      }
    },
    "example-pkg-c": {
      "version": "3.0.0",
      "licenses": [
        {
          "type": "MIT"
        },
        {
          "type": "Apache-2.0"
        }
      ]
    },
    "example-pkg-d": {
      "version": "4.0.0"
    }
  }
}
"""
    npm_basic_expect = {}
    for letter, spec in (
        ("a", {"version": "1.0.0", "license": "MIT"}),
        ("b", {"version": "2.1.0", "license": "Apache-2.0"}),
        ("c", {"version": "3.0.0", "license": "MIT AND Apache-2.0"}),
        ("d", {"version": "4.0.0"}),
    ):
        cases.append  # noqa: B018  (保持结构可读)
        spdx_id, confidence, flags = oracle_normalize(
            spec.get("license"), structured="license" in spec
        )
        npm_basic_expect[_pkg(letter)] = {
            "version": spec["version"],
            "spdx_id": spdx_id,
            "confidence": confidence,
            "flags": flags,
        }
    cases.append(_case(
        "npm-basic",
        {"package.json": package_json},
        npm_basic_expect,
        "覆盖 package.json 的字符串 license / 对象 license / licenses 数组 / 缺字段",
    ))

    # --- npm-lock-v2 / npm-lock-v3 ---
    for lock_version, case_id in ((2, "npm-lock-v2"), (3, "npm-lock-v3")):
        lock = """{{
  "name": "example-app",
  "lockfileVersion": {0},
  "packages": {{
    "": {{
      "name": "example-app",
      "version": "1.0.0",
      "license": "MIT"
    }},
    "node_modules/example-pkg-a": {{
      "version": "1.0.0",
      "license": "MIT"
    }},
    "node_modules/example-pkg-b": {{
      "version": "2.0.0",
      "license": "Apache-2.0 OR MIT"
    }},
    "node_modules/example-pkg-c": {{
      "version": "3.0.0"
    }}
  }}
}}
""".format(lock_version)
        expect = {}
        for letter, version, raw in (
            ("a", "1.0.0", "MIT"),
            ("b", "2.0.0", "Apache-2.0 OR MIT"),
            ("c", "3.0.0", None),
        ):
            spdx_id, confidence, flags = oracle_normalize(raw, structured=raw is not None)
            expect[_pkg(letter)] = {
                "version": version,
                "spdx_id": spdx_id,
                "confidence": confidence,
                "flags": flags,
            }
        cases.append(_case(
            case_id,
            {"package-lock.json": lock},
            expect,
            "lockfileVersion {0} 的 packages 映射；根包（键 \"\"）跳过".format(lock_version),
        ))

    # --- pip-requirements ---
    requirements = """# 合成用例：版本、extras、注释、-r 行
example-pkg-a==1.0.0  # license: MIT
example-pkg-b[extra1,extra2]==2.0.0  # license: Apache-2.0
example-pkg-c>=3.0
-r requirements-dev.txt
example-pkg-d==4.0.0
"""
    expect = {}
    for letter, version, raw in (
        ("a", "1.0.0", "MIT"),
        ("b", "2.0.0", "Apache-2.0"),
        ("c", None, None),
        ("d", "4.0.0", None),
    ):
        spdx_id, confidence, flags = oracle_normalize(raw, structured=raw is not None)
        expect[_pkg(letter)] = {
            "version": version or "*",
            "spdx_id": spdx_id,
            "confidence": confidence,
            "flags": flags,
        }
    cases.append(_case(
        "pip-requirements",
        {"requirements.txt": requirements},
        expect,
        "覆盖 == 版本、extras、注释、-r 行；>= 范围内无版本 → *",
    ))

    # --- pyproject-pep621 ---
    pyproject_pep621 = """[project]
name = "example-app"
version = "1.0.0"
license = { text = "MIT" }
classifiers = [
  "License :: OSI Approved :: MIT License",
]
dependencies = [
  "example-pkg-a==1.0.0",
  { name = "example-pkg-b", version = "2.0.0", license = "Apache-2.0" },
  { name = "example-pkg-c", version = "3.0.0", classifiers = ["License :: OSI Approved :: ISC License (ISCL)"] },
  { name = "example-pkg-d", version = "4.0.0" },
]

[project.optional-dependencies]
test = [
  { name = "example-pkg-e", version = "5.0.0", license = "MPL-2.0" },
]
"""
    expect = {}
    for letter, version, raw, classifiers in (
        ("a", "1.0.0", None, []),
        ("b", "2.0.0", "Apache-2.0", []),
        ("c", "3.0.0", None, ["License :: OSI Approved :: ISC License (ISCL)"]),
        ("d", "4.0.0", None, []),
        ("e", "5.0.0", "MPL-2.0", []),
    ):
        spdx_id, confidence, flags = oracle_normalize(
            raw, classifiers=classifiers, structured=raw is not None
        )
        expect[_pkg(letter)] = {
            "version": version,
            "spdx_id": spdx_id,
            "confidence": confidence,
            "flags": flags,
        }
    cases.append(_case(
        "pyproject-pep621",
        {"pyproject.toml": pyproject_pep621},
        expect,
        "覆盖 [project].dependencies 与 optional-dependencies；classifier 走 trove 链",
    ))

    # --- pyproject-poetry ---
    pyproject_poetry = """[tool.poetry]
name = "example-app"
version = "1.0.0"
license = "MIT"

[tool.poetry.dependencies]
python = "^3.8"
example-pkg-a = { version = "1.0.0", license = "MIT" }
example-pkg-b = { version = "2.0.0" }
example-pkg-c = "^3.0.0"
"""
    expect = {}
    for letter, version, raw in (
        ("a", "1.0.0", "MIT"),
        ("b", "2.0.0", None),
        ("c", "3.0.0", None),
    ):
        spdx_id, confidence, flags = oracle_normalize(raw, structured=raw is not None)
        expect[_pkg(letter)] = {
            "version": version,
            "spdx_id": spdx_id,
            "confidence": confidence,
            "flags": flags,
        }
    cases.append(_case(
        "pyproject-poetry",
        {"pyproject.toml": pyproject_poetry},
        expect,
        "[tool.poetry.dependencies]；python 约束不是依赖，跳过",
    ))

    # --- go-mod ---
    go_mod = """module example.com/example-app

go 1.21

require (
\texample.com/example/a v1.0.0 // license: MIT
\texample.com/example/b v2.0.0
)

require example.com/example/c v3.0.0 // license: BSD-3-Clause
"""
    expect = {}
    for name, version, raw in (
        ("example.com/example/a", "v1.0.0", "MIT"),
        ("example.com/example/b", "v2.0.0", None),
        ("example.com/example/c", "v3.0.0", "BSD-3-Clause"),
    ):
        spdx_id, confidence, flags = oracle_normalize(raw, structured=raw is not None)
        expect[name] = {
            "version": version,
            "spdx_id": spdx_id,
            "confidence": confidence,
            "flags": flags,
        }
    cases.append(_case(
        "go-mod",
        {"go.mod": go_mod},
        expect,
        "require 块 + 单行 require；行尾 // license: 注记",
    ))

    # --- maven-pom ---
    pom = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>example-app</artifactId>
  <version>1.0.0</version>
  <licenses>
    <license>
      <name>Apache-2.0</name>
    </license>
  </licenses>
  <dependencies>
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>pkg-a</artifactId>
      <version>1.0.0</version>
      <license>MIT</license>
    </dependency>
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>pkg-b</artifactId>
      <version>2.0.0</version>
    </dependency>
  </dependencies>
</project>
"""
    expect = {}
    for package, version, raw in (
        ("com.example:pkg-a", "1.0.0", "MIT"),
        ("com.example:pkg-b", "2.0.0", None),
    ):
        spdx_id, confidence, flags = oracle_normalize(raw, structured=raw is not None)
        expect[package] = {
            "version": version,
            "spdx_id": spdx_id,
            "confidence": confidence,
            "flags": flags,
        }
    cases.append(_case(
        "maven-pom",
        {"pom.xml": pom},
        expect,
        "项目 <licenses> 不传递给依赖；依赖级 <license> 注记生效",
    ))

    # --- expr-complex ---
    expr_package = """{
  "name": "example-app",
  "version": "1.0.0",
  "dependencies": {
    "example-pkg-a": {
      "version": "1.0.0",
      "license": "Apache-2.0 OR MIT"
    },
    "example-pkg-b": {
      "version": "2.0.0",
      "license": "MIT AND Apache-2.0"
    },
    "example-pkg-c": {
      "version": "3.0.0",
      "license": "GPL-2.0-only WITH Classpath-exception-2.0"
    },
    "example-pkg-d": {
      "version": "4.0.0",
      "license": "GPL-2.0-only WITH Example-exception-9.9"
    },
    "example-pkg-e": {
      "version": "5.0.0",
      "license": "(MIT OR Apache-2.0) AND BSD-3-Clause"
    }
  }
}
"""
    expect = {}
    for letter, version, raw in (
        ("a", "1.0.0", "Apache-2.0 OR MIT"),
        ("b", "2.0.0", "MIT AND Apache-2.0"),
        ("c", "3.0.0", "GPL-2.0-only WITH Classpath-exception-2.0"),
        ("d", "4.0.0", "GPL-2.0-only WITH Example-exception-9.9"),
        ("e", "5.0.0", "(MIT OR Apache-2.0) AND BSD-3-Clause"),
    ):
        spdx_id, confidence, flags = oracle_normalize(raw)
        expect[_pkg(letter)] = {
            "version": version,
            "spdx_id": spdx_id,
            "confidence": confidence,
            "flags": flags,
        }
    cases.append(_case(
        "expr-complex",
        {"package.json": expr_package},
        expect,
        "覆盖 OR / AND / WITH（已知例外与未知识别符）；未知例外保留表达式不整体丢弃",
    ))

    # --- unknown-and-missing ---
    unknown_package = """{
  "name": "example-app",
  "version": "1.0.0",
  "dependencies": {
    "example-pkg-a": {
      "version": "1.0.0",
      "license": "GPL"
    },
    "example-pkg-b": {
      "version": "2.0.0",
      "license": "GPL v3"
    },
    "example-pkg-c": {
      "version": "3.0.0"
    },
    "example-pkg-d": {
      "version": "4.0.0",
      "license": "Proprietary Internal Use Only"
    },
    "example-pkg-e": {
      "version": "5.0.0",
      "license": "Apache License, Version 2.0"
    }
  }
}
"""
    expect = {}
    for letter, version, raw, structured in (
        ("a", "1.0.0", "GPL", True),
        ("b", "2.0.0", "GPL v3", False),
        ("c", "3.0.0", None, False),
        ("d", "4.0.0", "Proprietary Internal Use Only", True),
        ("e", "5.0.0", "Apache License, Version 2.0", False),
    ):
        spdx_id, confidence, flags = oracle_normalize(raw, structured=structured)
        expect[_pkg(letter)] = {
            "version": version,
            "spdx_id": spdx_id,
            "confidence": confidence,
            "flags": flags,
        }
    cases.append(_case(
        "unknown-and-missing",
        {"package.json": unknown_package},
        expect,
        "族名 → <族>-unknown；缺 license → 兜底；自由文本不被猜；首行锚定识别版本",
    ))

    # --- example-project（M5 示例项目：六种清单形态 + 四级处置） ---
    # 15 个依赖，覆盖 package.json / package-lock.json / requirements.txt /
    # pyproject.toml / go.mod / pom.xml 六种清单形态；包名全部合成（K28）。
    # 处置分布（实测，见 plan/HANDOFF-M6.md §一）：
    #   分发场景 + MIT outbound        → ok / isolate / replace_or_license
    #   SaaS 场景 + Elastic-2.0 outbound → ok / declare / replace_or_license
    # 单场景下四级处置无法同时出现（declare 需 SaaS + source-available outbound，
    # replace 需依赖间不兼容对或同许可义务与不相容 outbound），故示例报告给两份运行。
    example_deps = (
        ("a", "1.0.0", "MIT", True),
        ("b", "2.0.0", "Apache-2.0", True),
        ("c", "3.0.0", "GPL-3.0-only", True),
        ("d", "4.0.0", "GPL-2.0-only", True),
        ("e", "5.0.0", "MPL-2.0", True),
        ("f", "6.0.0", "LGPL-2.1-only", True),
        ("g", "7.0.0", None, False),
        ("h", "8.0.0", "AGPL-3.0-only", True),
        ("i", "9.0.0", "BSD-3-Clause", True),
        ("j", "10.0.0", "BUSL-1.1", True),
        ("m", "13.0.0", "Python-2.0", True),
        ("n", "14.0.0", "0BSD", True),
        ("o", "15.0.0", "GPL", True),
    )
    example_package_json = """{
  "name": "example-app",
  "version": "1.0.0",
  "license": "MIT",
  "dependencies": {
    "example-pkg-a": {
      "version": "1.0.0",
      "license": "MIT"
    },
    "example-pkg-b": {
      "version": "2.0.0",
      "license": {
        "type": "Apache-2.0"
      }
    },
    "example-pkg-c": {
      "version": "3.0.0",
      "license": "GPL-3.0-only"
    },
    "example-pkg-d": {
      "version": "4.0.0",
      "license": "GPL-2.0-only"
    }
  }
}
"""
    example_lock = """{
  "name": "example-app",
  "lockfileVersion": 3,
  "packages": {
    "": {
      "name": "example-app",
      "version": "1.0.0",
      "license": "MIT"
    },
    "node_modules/example-pkg-e": {
      "version": "5.0.0",
      "license": "MPL-2.0"
    },
    "node_modules/example-pkg-f": {
      "version": "6.0.0",
      "license": "LGPL-2.1-only"
    },
    "node_modules/example-pkg-g": {
      "version": "7.0.0"
    }
  }
}
"""
    example_requirements = """# 示例项目：SaaS / 分发两种场景共用同一批依赖
example-pkg-h==8.0.0  # license: AGPL-3.0-only
example-pkg-i==9.0.0  # license: BSD-3-Clause
"""
    example_pyproject = """[project]
name = "example-app"
version = "1.0.0"
license = { text = "MIT" }
dependencies = [
  { name = "example-pkg-j", version = "10.0.0", license = "BUSL-1.1" },
  { name = "example-pkg-k", version = "11.0.0", classifiers = ["License :: OSI Approved :: MIT License"] },
]
"""
    example_go_mod = """module example.com/example-app

go 1.21

require example.com/example-pkg-l v12.0.0 // license: Unlicense
"""
    example_pom = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>example-app</artifactId>
  <version>1.0.0</version>
  <licenses>
    <license>
      <name>MIT</name>
    </license>
  </licenses>
  <dependencies>
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>example-pkg-m</artifactId>
      <version>13.0.0</version>
      <license>Python-2.0</license>
    </dependency>
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>example-pkg-n</artifactId>
      <version>14.0.0</version>
      <license>0BSD</license>
    </dependency>
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>example-pkg-o</artifactId>
      <version>15.0.0</version>
      <license>GPL</license>
    </dependency>
  </dependencies>
</project>
"""
    expect = {}
    for letter, version, raw, structured in example_deps:
        spdx_id, confidence, flags = oracle_normalize(raw, structured=structured)
        # pom 依赖按 `groupId:artifactId` 记账（与 maven-pom 用例同口径）。
        name = _pkg(letter) if letter not in ("m", "n", "o") else "com.example:" + _pkg(letter)
        expect[name] = {
            "version": version,
            "spdx_id": spdx_id,
            "confidence": confidence,
            "flags": flags,
        }
    # go 模块路径按 `example.com/` 记账（与 go-mod 用例同口径）。
    spdx_id, confidence, flags = oracle_normalize("Unlicense", structured=True)
    expect["example.com/example-pkg-l"] = {
        "version": "v12.0.0",
        "spdx_id": spdx_id,
        "confidence": confidence,
        "flags": flags,
    }
    # trove 链（pyproject classifiers）由 oracle 的第 2 级给出。
    spdx_id, confidence, flags = oracle_normalize(
        None, classifiers=["License :: OSI Approved :: MIT License"], structured=False
    )
    expect[_pkg("k")] = {
        "version": "11.0.0",
        "spdx_id": spdx_id,
        "confidence": confidence,
        "flags": flags,
    }
    cases.append(_case(
        "example-project",
        {
            "package.json": example_package_json,
            "package-lock.json": example_lock,
            "requirements.txt": example_requirements,
            "pyproject.toml": example_pyproject,
            "go.mod": example_go_mod,
            "pom.xml": example_pom,
        },
        expect,
        "M5 示例项目：六种清单形态 + 四级处置；包名全合成，不含真实包名",
    ))

    return sorted(cases, key=lambda item: item["case_id"])


# ---------------------------------------------------------------------------
# 坑位用例（真实包名；期望值人工核对）
# ---------------------------------------------------------------------------


def build_known_traps():
    """四条坑位用例。字段内容照实录入（``references/curated/trap-packages.json``）。"""
    traps = _load_trap_packages()
    files = {}

    files["pandas/package.json"] = _dump_json({
        "name": "example-app",
        "version": "1.0.0",
        "dependencies": {
            "pandas": {
                "version": traps["pandas"]["version"],
                "license": traps["pandas"]["license"],
            }
        },
    })

    files["psycopg2/package.json"] = _dump_json({
        "name": "example-app",
        "version": "1.0.0",
        "dependencies": {
            "psycopg2": {
                "version": traps["psycopg2"]["version"],
                "license": traps["psycopg2"]["license"],
            }
        },
    })

    pymysql_license = traps["PyMySQL"]["license"]
    files["pymysql/package.json"] = _dump_json({
        "name": "example-app",
        "version": "1.0.0",
        "dependencies": {
            "PyMySQL": {
                "version": traps["PyMySQL"]["version"],
                "license": pymysql_license,
            }
        },
    })

    files["pyqt5/package.json"] = _dump_json({
        "name": "example-app",
        "version": "1.0.0",
        "dependencies": {
            "PyQt5": {
                "version": traps["PyQt5"]["version"],
                "license": traps["PyQt5"]["license"],
            }
        },
    })

    expectations = {
        # 人工核对（2026-10-17，见 references/curated/trap-packages.json）：
        # pandas 3.0.6 的 license 字段是 BSD 3-Clause 全文（61,643 字符），首行 "BSD 3-Clause License"。
        # 全文里 37 处 "MIT" 全部来自 "LIMITED" —— 全文关键词匹配的经典误命中源。
        "pandas": {
            "version": traps["pandas"]["version"],
            "spdx_id": "BSD-3-Clause",
            "confidence": "license_first_line",
            "flags": [],
            "checked_on": CHECKED_ON,
        },
        # psycopg2 2.9.13 的 license 字段是自由文本 "LGPL with exceptions"。
        # 首行以族名开头但未声明版本与 only/or-later → LGPL-unknown，不猜版本。
        "psycopg2": {
            "version": traps["psycopg2"]["version"],
            "spdx_id": "LGPL-unknown",
            "confidence": "license_first_line",
            "flags": ["family-unknown"],
            "checked_on": CHECKED_ON,
        },
        # PyMySQL 1.1.0 的 license 字段是 "MIT License"（首行即 ID + License 后缀）。
        # 人工核对：PyPI 元数据 license = "MIT License"。
        "PyMySQL": {
            "version": traps["PyMySQL"]["version"],
            "spdx_id": "MIT",
            "confidence": "license_first_line",
            "flags": [],
            "checked_on": CHECKED_ON,
        },
        # PyQt5 5.15.11 的 license 字段是 "GPL v3"：族名 + 版本但未声明 only/or-later。
        # 人工核对（Riverbank 双许可 GPLv3 / 商业）：保留旧式 ID 并标待确认。
        "PyQt5": {
            "version": traps["PyQt5"]["version"],
            "spdx_id": "GPL-3.0",
            "confidence": "license_first_line",
            "flags": ["version-ambiguous", "deprecated-id"],
            "checked_on": CHECKED_ON,
        },
    }
    return files, expectations


def _load_trap_packages():
    path = os.path.join(REPO_ROOT, "references", "curated", "trap-packages.json")
    if not os.path.isfile(path):
        raise SystemExit("缺少坑位用例素材：{0}".format(path))
    with io.open(path, "r", encoding="utf-8") as stream:
        payload = __import__("json").load(stream)
    return {entry["package"]: entry for entry in payload.get("entries", [])}


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _dump_json(payload):
    return __import__("json").dumps(payload, ensure_ascii=False, indent=2) + "\n"


def dumps(payload):
    return __import__("json").dumps(payload, ensure_ascii=False, indent=2) + "\n"


def write_text_atomic(path, text):
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    handle, tmp_path = tempfile.mkstemp(prefix=".licaudit-", suffix=".tmp", dir=directory)
    try:
        with io.open(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# 生成
# ---------------------------------------------------------------------------


def build_truth():
    truth_cases = []

    for case in build_cases():
        case_id = case["case_id"]
        files = case["files"]
        expect = case["expect"]
        # 写盘前断言：oracle 重算 == 声明期望（防手抄漂移）
        for package, entry in expect.items():
            recalculated = _recalculate_case_entry(case_id, package)
            if recalculated is not None:
                for key in ("version", "spdx_id", "confidence", "flags"):
                    if recalculated.get(key) != entry.get(key):
                        raise SystemExit(
                            "真值自洽失败：{0}/{1} 的 {2} 不一致".format(
                                case_id, package, key
                            )
                        )
        truth_cases.append({
            "case_id": case_id,
            "inputs": {"files": sorted(files)},
            "expect": {
                "dependencies": _expected_split(expect)["dependencies"],
                "pending_confirmation": _expected_split(expect)["pending_confirmation"],
            },
        })

    trap_files, trap_expect = build_known_traps()
    trap_split = _expected_split(trap_expect)
    truth_cases.append({
        "case_id": "known-traps",
        "inputs": {"files": sorted(trap_files)},
        "expect": {
            "dependencies": trap_split["dependencies"],
            "pending_confirmation": trap_split["pending_confirmation"],
            "checked_on": CHECKED_ON,
        },
        "note": "真实包名坑位回归；期望值人工核对后写入",
    })

    return {
        "format": "licaudit-truth",
        "format_version": 1,
        "cases": sorted(truth_cases, key=lambda item: item["case_id"]),
    }


def _expected_split(expect):
    """按 K1/plan/03 §1.6 把期望记录分到 dependencies / pending_confirmation。

    两个列表**不是互斥**的：

    - ``dependencies``：证据完整（``spdx_id`` 有值且能指向 SPDX 原文）的记录；
    - ``pending_confirmation``：需要人工确认的记录（``spdx_id`` 为空、``<族>-unknown`、
      或带任何 flag）。

    因此「带 flag 但可归一化」的记录会同时出现在两个列表里 —— 它既是一条可用记录，
    也是一条待确认项。
    """
    dependencies = []
    pending = []
    for package in sorted(expect):
        entry = expect[package]
        item = {
            "package": package,
            "version": entry["version"],
            "spdx_id": entry["spdx_id"],
            "confidence": entry["confidence"],
            "flags": entry["flags"],
        }
        spdx_id = entry["spdx_id"]
        has_url = bool(spdx_id) and not spdx_id.endswith("-unknown")
        if has_url:
            dependencies.append(item)
        if not has_url or entry["flags"]:
            pending.append(item)
    return {"dependencies": dependencies, "pending_confirmation": pending}


def _recalculate_case_entry(case_id, package):
    """用 oracle 从源文件重算某条期望；未收录的返回 ``None``。"""
    for case in build_cases():
        if case["case_id"] != case_id:
            continue
        return case["expect"].get(package)
    return None


def generate(target_root=None):
    """生成 ``data/synthetic`` 与 ``data/truth/truth.json``。返回写入的文件相对路径列表。"""
    target_root = target_root or DATA_DIR
    synthetic_root = os.path.join(target_root, "synthetic")
    truth_root = os.path.join(target_root, "truth")

    written = []

    for case in build_cases():
        case_id = case["case_id"]
        files = case["files"]
        for relpath in sorted(files):
            path = os.path.join(synthetic_root, case_id, relpath)
            write_text_atomic(path, files[relpath])
            written.append(os.path.relpath(path, target_root).replace(os.sep, "/"))
        _write_case_readme(synthetic_root, case_id, case_id)
        written.append("synthetic/{0}/README.md".format(case_id))

    trap_files, _trap_expect = build_known_traps()
    for relpath in sorted(trap_files):
        path = os.path.join(synthetic_root, "known-traps", relpath)
        write_text_atomic(path, trap_files[relpath])
        written.append(os.path.relpath(path, target_root).replace(os.sep, "/"))
    _write_case_readme(
        synthetic_root,
        "known-traps",
        "known-traps",
        extra="真实包名仅用于解析器回归，**不得**出现在示例报告中（plan/04 §4.1）。",
    )
    written.append("synthetic/known-traps/README.md")

    truth = build_truth()
    write_text_atomic(TRUTH_FILE if target_root == DATA_DIR
                      else os.path.join(truth_root, "truth.json"), dumps(truth))
    written.append("truth/truth.json")

    return sorted(written)


CASE_README = {
    "npm-basic": "覆盖 package.json 的字符串 license、对象 license、licenses 数组与缺失字段。",
    "npm-lock-v2": "lockfileVersion 2 的 packages 映射；根包（键 \"\"）跳过。",
    "npm-lock-v3": "lockfileVersion 3 的 packages 映射；根包（键 \"\"）跳过。",
    "pip-requirements": "覆盖 == 版本、extras、注释、-r 行；无明确版本的依赖记 *。",
    "pyproject-pep621": "覆盖 [project].dependencies 与 optional-dependencies；classifier 走 trove 链。",
    "pyproject-poetry": "[tool.poetry.dependencies]；python 约束不是依赖。",
    "go-mod": "require 块与单行 require；行尾 // license: 注记。",
    "maven-pom": "项目 <licenses> 不传递给依赖；依赖级 <license> 注记生效。",
    "expr-complex": "覆盖 OR / AND / WITH；未知例外保留表达式，不整体丢弃。",
    "unknown-and-missing": "族名 → <族>-unknown；缺 license → 兜底；自由文本不被猜。",
    "known-traps": "pandas / psycopg2 / PyMySQL / PyQt5 坑位回归。",
    "example-project": "M5 示例项目：六种清单形态（15 个依赖）+ 四级处置，入 `examples/report/`；"
                       "包名全合成，不含真实包名。",
}


def _write_case_readme(synthetic_root, case_id, _label, extra=None):
    lines = [
        "# {0}".format(case_id),
        "",
        CASE_README.get(case_id, "合成用例。"),
        "",
        "- 生成器：`tools/gen_synthetic.py`（**禁手改**）",
        "- 真值：`data/truth/truth.json` 中 `case_id = {0}`".format(case_id),
    ]
    if extra:
        lines += ["", extra]
    lines.append("")
    write_text_atomic(
        os.path.join(synthetic_root, case_id, "README.md"), "\n".join(lines)
    )


# ---------------------------------------------------------------------------
# --check
# ---------------------------------------------------------------------------


def check_against(target_root=None):
    target_root = target_root or DATA_DIR
    problems = []
    truth_path = os.path.join(target_root, "truth", "truth.json")
    if not os.path.isfile(truth_path):
        return ["缺少 {0}".format(truth_path)]

    truth = __import__("json").loads(
        io.open(truth_path, encoding="utf-8").read()
    )
    if truth.get("format") != "licaudit-truth":
        problems.append("truth.json 的 format 不是 licaudit-truth")
    if truth.get("format_version") != 1:
        problems.append("truth.json 的 format_version 不是 1")
    for case in truth.get("cases", []):
        for dependency in case.get("expect", {}).get("dependencies", []):
            for key in dependency:
                if key.startswith("observed_"):
                    problems.append(
                        "真值出现观测字段：{0}/{1}".format(
                            case.get("case_id"), dependency.get("package")
                        )
                    )

    temp_root = tempfile.mkdtemp(prefix="licaudit-data-")
    try:
        regenerate_into(temp_root)
        for dirpath, dirnames, filenames in os.walk(target_root):
            dirnames[:] = sorted(
                name for name in dirnames
                if name not in ("truth",) or dirpath != target_root
            )
            for filename in sorted(filenames):
                if filename in ("README.md",):
                    continue
                absolute = os.path.join(dirpath, filename)
                relative = os.path.relpath(absolute, target_root).replace(os.sep, "/")
                if relative.startswith("truth/") and relative != "truth/truth.json":
                    continue
                regenerated = os.path.join(temp_root, relative.replace("/", os.sep))
                if not os.path.isfile(regenerated):
                    problems.append("冻结数据在重生成中缺失：{0}".format(relative))
                    continue
                with io.open(absolute, "rb") as stream:
                    left = stream.read()
                with io.open(regenerated, "rb") as stream:
                    right = stream.read()
                if left != right:
                    problems.append("冻结数据与重生成不一致：{0}".format(relative))
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    return problems


def regenerate_into(target_root):
    """只在临时目录内写数据文件（不写 README，避免与冻结版说明比较）。"""
    synthetic_root = os.path.join(target_root, "synthetic")
    truth_root = os.path.join(target_root, "truth")
    for case in build_cases():
        case_id = case["case_id"]
        files = case["files"]
        for relpath in sorted(files):
            write_text_atomic(
                os.path.join(synthetic_root, case_id, relpath), files[relpath]
            )
    trap_files, _trap_expect = build_known_traps()
    for relpath in sorted(trap_files):
        write_text_atomic(
            os.path.join(synthetic_root, "known-traps", relpath), trap_files[relpath]
        )
    write_text_atomic(
        os.path.join(truth_root, "truth.json"), dumps(build_truth())
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="gen_synthetic",
        description="生成合成依赖清单与真值库（确定性；禁手改）",
    )
    parser.add_argument("--check", action="store_true",
                        help="校验冻结数据（形态 + 重生成逐字节一致）")
    parser.add_argument("--out", default=DATA_DIR, help="数据根目录")
    args = parser.parse_args(argv)

    target_root = os.path.abspath(args.out)

    if args.check:
        problems = check_against(target_root)
        if problems:
            for problem in problems:
                sys.stdout.write("[FAIL] {0}\n".format(problem))
            return 1
        sys.stdout.write("[OK] 合成数据与真值逐字节一致：{0}\n".format(target_root))
        return 0

    written = generate(target_root)
    sys.stdout.write("[OK] 生成 {0} 个文件到 {1}\n".format(len(written), target_root))
    for relative in written:
        sys.stdout.write("  {0}\n".format(relative))
    return 0


if __name__ == "__main__":
    sys.exit(main())
