# -*- coding: utf-8 -*-
"""M5：报告渲染。

骨架阶段只占位（M0）。落地时本子包必须满足三条 AST 守门（plan/06 D13）：

1. 不 import ``licaudit.inventory`` / ``licaudit.assess``；
2. 不出现算术 ``BinOp``（字符串拼接与格式化豁免）；
3. 不内联许可证 ID → 档位/处置的判定表。

渲染层只消费 ``actions.json`` / ``conflicts.json`` / ``scenario.json`` / ``inventory.json``
的既有字段，不重算任何判定。
"""

MILESTONE = "M5"

__all__ = ["MILESTONE"]
