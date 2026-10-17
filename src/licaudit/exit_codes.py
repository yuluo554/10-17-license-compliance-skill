# -*- coding: utf-8 -*-
"""退出码语义。

四个常量是契约的一部分：``SKILL.md`` 的退出码表、本模块、测试三处必须一致。
不得新增第五个退出码；确需新增时同步改三处并登记决策记录。
"""

EXIT_OK = 0
"""分析完成且无阻断项。"""

EXIT_FINDINGS = 1
"""分析完成，检出阻断/隔离级项；或 selftest 未通过。"""

EXIT_USAGE = 2
"""用法错误、输入不可用、未知许可证 ID。"""

EXIT_RULESET = 3
"""规则包缺失、schema 校验失败或版本不可识别。"""

EXIT_CODES = {
    EXIT_OK: "分析完成且无阻断项",
    EXIT_FINDINGS: "分析完成并检出阻断/隔离级项，或自检未通过",
    EXIT_USAGE: "用法错误、输入不可用或未知许可证 ID",
    EXIT_RULESET: "规则包缺失或校验失败",
}
