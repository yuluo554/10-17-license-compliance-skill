# -*- coding: utf-8 -*-
"""M2–M5：画像、场景判定、冲突分析、处置分级。

判定数据全部来自 ``ruleset``，引擎不得内置档位/义务/触发名/冲突对/处置级别。

- ``profile.build_profile(inventory, ruleset, spdx_dir=...)`` → ``profile.json``（M2 ✅）
- ``scenario.build_scenario(...)`` → ``scenario.json``（M3 ✅）
- ``conflict.build_conflicts(...)`` → ``conflicts.json``（M4 ✅）
- ``action.build_actions(...)`` → ``actions.json``（M5 ✅，只查 ``action-rules.json`` 决策表）

求值口径只有一份实现：``conflict.evaluate_expression``（K16）；场景引擎直接引用它，
把表达式依赖的结论一并回填（决策 D32）。

处置分级只读上游产物字段（inventory / profile / scenario / conflicts），不重新判定；
五锚点门与「输入不确定即待确认」都在 ``action`` 内完成（K20 / K7）。
"""

MILESTONE = "M2-M5"
IMPLEMENTED = ("profile", "scenario", "conflict", "action")

__all__ = ["IMPLEMENTED", "MILESTONE"]
