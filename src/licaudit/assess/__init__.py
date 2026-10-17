# -*- coding: utf-8 -*-
"""M2–M4：画像、场景判定、冲突分析。

骨架阶段只占位（M0）。M1–M4 落地时在此实现，判定数据全部来自 ``ruleset``，
引擎不得内置档位/义务/触发/冲突对。

- ``build_profile(inventory, ruleset, spdx)`` → ``profile.json``（M2）
- ``assess_scenario(inventory, profile, scenario_input, ruleset)`` → ``scenario.json``（M3）
- ``assess_conflicts(inventory, profile, scenario, outbound, ruleset)`` → ``conflicts.json``（M4）
"""

MILESTONE = "M2-M4"

__all__ = ["MILESTONE"]
