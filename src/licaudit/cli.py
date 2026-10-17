# -*- coding: utf-8 -*-
"""唯一入口：参数解析、异常映射、退出码。

本模块不做任何判定。所有业务结论都来自 ``pipeline`` 之后的引擎层。
"""

import argparse
import sys

from . import __version__, contract, pipeline
from .encoding import ensure_utf8_stdio
from .errors import RulesetError, UsageError
from .exit_codes import (
    EXIT_FINDINGS,
    EXIT_OK,
    EXIT_RULESET,
    EXIT_USAGE,
)
from .selftest import format_checks, run_selftest

PROG = "licaudit"


def build_parser():
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="开源许可证合规审查：依赖清单 → SPDX 归一化 → 场景/冲突判定 → 中文清单",
        epilog="退出码：0 完成无阻断 / 1 检出阻断级 / 2 用法或输入错误 / 3 规则包问题",
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    parser.add_argument(
        "--rules-dir",
        default=None,
        help="规则包目录（含 manifest.json）；默认按 references/ruleset 定位",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    status = subparsers.add_parser("status", help="报告规则包加载状态与版本")
    status.add_argument("--out-dir", default=pipeline.DEFAULT_OUT_DIR, help="产物目录")
    status.set_defaults(handler=pipeline.run_status, needs_out_dir=True)

    scan = subparsers.add_parser("scan", help="解析依赖清单，产出 inventory.json")
    scan.add_argument("manifests", nargs="+", help="清单文件（package.json 等）")
    scan.add_argument("--out-dir", default=pipeline.DEFAULT_OUT_DIR, help="产物目录")
    scan.set_defaults(handler=pipeline.run_scan)

    assess = subparsers.add_parser("assess", help="画像、场景与冲突判定")
    assess.add_argument("--inventory", required=True, help="scan 产出的 inventory.json")
    assess.add_argument(
        "--profile-only",
        action="store_true",
        help="只产许可证画像矩阵 profile.json（M2）；不要求场景与 outbound 许可证",
    )
    assess.add_argument(
        "--scenario",
        default=None,
        choices=contract.SCENARIO_IDS,
        help="八场景之一：internal / distribute-binary / distribute-source / saas / "
        "static-link / dynamic-link / separate-process / container-image；全量模式必填",
    )
    assess.add_argument(
        "--delivery",
        default=None,
        choices=contract.DELIVERIES,
        help="交付形态（内部使用/二进制/源码/SaaS/容器镜像）；链接方式轴场景必填",
    )
    assess.add_argument(
        "--linking",
        default=None,
        choices=contract.LINK_MODES,
        help="链接方式（默认由场景推导）",
    )
    assess.add_argument(
        "--network-interaction",
        default=None,
        choices=("yes", "no"),
        help="用户是否通过网络与程序交互（saas 必答；container-image 可选）",
    )
    assess.add_argument(
        "--outbound-license",
        default=None,
        help="项目自身 outbound 许可证的 SPDX 表达式；尚未决定时写 pending；全量模式必填",
    )
    assess.add_argument("--scenario-note", default="", help="用户原始回答，原样落盘")
    assess.add_argument(
        "--spdx-dir",
        default=None,
        help="SPDX 快照目录；默认按 references/spdx 定位",
    )
    assess.add_argument("--out-dir", default=pipeline.DEFAULT_OUT_DIR, help="产物目录")
    assess.set_defaults(handler=pipeline.run_assess)

    report = subparsers.add_parser("report", help="渲染中文《第三方开源清单》")
    report.add_argument("--out-dir", default=pipeline.DEFAULT_OUT_DIR, help="产物目录")
    report.add_argument(
        "--format",
        default="md",
        choices=("md", "csv"),
        help="输出格式（md 或 csv）",
    )
    report.set_defaults(handler=pipeline.run_report)

    verify = subparsers.add_parser("verify-data", help="用参照实现对账冻结真值库")
    verify.add_argument("--data-dir", default="data", help="数据目录")
    verify.set_defaults(handler=pipeline.run_verify_data)

    bench = subparsers.add_parser("bench", help="运行内置基准")
    bench.add_argument("--only", default=None, help="只跑指定套件（未知名 → exit 2）")
    bench.add_argument("--data-dir", default="data", help="数据目录")
    bench.set_defaults(handler=pipeline.run_bench)

    selftest = subparsers.add_parser("selftest", help="可证伪自检")
    selftest.add_argument("--core", action="store_true", help="只跑纯内部不变量")
    selftest.set_defaults(handler=None)

    return parser


def _print(message):
    sys.stdout.write(message + "\n")


def _print_err(message):
    sys.stderr.write(message + "\n")


def _dispatch(args):
    if args.command == "selftest":
        checks, ok = run_selftest(core_only=args.core, rules_dir=args.rules_dir)
        _print(format_checks(checks))
        return EXIT_OK if ok else EXIT_FINDINGS

    handler = getattr(args, "handler", None)
    if handler is None:
        _print_err("缺少子命令；用 {0} --help 查看可用命令".format(PROG))
        return EXIT_USAGE

    result, code = handler(args)
    if getattr(args, "needs_out_dir", False) and isinstance(result, dict):
        path = pipeline.write_status_artifact(result, args.out_dir)
        _print("规则包: {0}".format(result.get("rules_dir")))
        _print("ruleset_version: {0}".format(result.get("ruleset_version")))
        _print("license_list_version: {0}".format(result.get("license_list_version")))
        _print("启用条目: {0}".format(result.get("enabled", {})))
        _print("被拒绝条目: {0}".format(result.get("disabled", 0)))
        _print("产物: {0}".format(path))
    return code


def main(argv=None):
    ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except UsageError as exc:
        _print_err("输入或用法错误：{0}".format(exc))
        return EXIT_USAGE
    except RulesetError as exc:
        _print_err("规则包错误：{0}".format(exc))
        return EXIT_RULESET
    except NotImplementedError as exc:
        # 骨架阶段不应走到这里（pipeline 先过规则包硬门），留作防御而非成功路径。
        _print_err("该能力尚未实现：{0}".format(exc))
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
