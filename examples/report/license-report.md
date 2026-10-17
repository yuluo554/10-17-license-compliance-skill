# 第三方开源清单（licaudit）

## 概述

- **规则包版本**：r0.1.0
- **依赖条目**：15 条
- **场景**：saas（交付 saas / 链接 none）
- **项目 outbound 许可证**：Elastic-2.0
- **阻断/隔离级条目**：4 条
- **待人工确认项**：7 条
- **处置级别 可直接使用**：8 条
- **处置级别 需补充声明**：1 条
- **处置级别 需隔离（进程分离 / 容器边界）**：0 条
- **处置级别 需替换或取得商业授权**：4 条

## 口径声明

- 判定链：依赖清单 → SPDX 归一化（四级可信度链）→ 许可证画像（五档 + 义务项）→ 使用场景（八场景 × 链接方式）→ 冲突与兼容性 → 四级处置建议。
- 档位、义务项、场景触发、冲突对、处置级别全部来自仓库内可审阅的规则包，并由生成器校验锚点可定位；引擎不新增义务项、不改档位。
- 未知即待确认：未覆盖档位、未回答的场景问题、未决定的 outbound 许可证一律输出「待人工确认」，不按最宽松默认放过。
- 档位级粗判：依赖 × 项目 outbound 的比较只到档位与义务层级，**未**按链接/分发边界聚合传染范围；已知偏差（例如弱传染档位高于宽松档位的依赖会被判不相容）在产物 notes 中登记。
- 许可证识别只认清单里显式写出的值，不按包名或生态惯例推断；缺失即降级并标待确认。

## 证据锚点

### com.example:example-pkg-m 13.0.0
- SPDX 标识：Python-2.0
- 声明位置：pom.xml :: <dependency> com.example:example-pkg-m（第 12 行）
- 依据条款：A-OK-001｜texts/0BSD.json#licenseText 许可段
- 处置规则：A-OK-001（核对日期 2026-10-17）
  > Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby granted.

### com.example:example-pkg-n 14.0.0
- SPDX 标识：0BSD
- 声明位置：pom.xml :: <dependency> com.example:example-pkg-n（第 18 行）
- 依据条款：A-OK-001｜texts/0BSD.json#licenseText 许可段
- 处置规则：A-OK-001（核对日期 2026-10-17）
  > Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby granted.

### example-pkg-a 1.0.0
- SPDX 标识：MIT
- 声明位置：package.json :: dependencies.example-pkg-a（第 6 行）
- 依据条款：A-OK-001｜texts/0BSD.json#licenseText 许可段
- 处置规则：A-OK-001（核对日期 2026-10-17）
  > Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby granted.

### example-pkg-b 2.0.0
- SPDX 标识：Apache-2.0
- 声明位置：package.json :: dependencies.example-pkg-b（第 10 行）
- 依据条款：A-REPL-002｜texts/Apache-2.0.json#licenseText §3
- 处置规则：A-REPL-002（核对日期 2026-10-17）
  > If You institute patent litigation against any entity (including a cross-claim or counterclaim in a lawsuit) alleging that the Work or a Contribution incorporated within the Work constitutes direct or contributory patent infringement, then any patent licenses granted to You under this License for that Work shall terminate as of the date such litigation is filed.

### example-pkg-c 3.0.0
- SPDX 标识：GPL-3.0-only
- 声明位置：package.json :: dependencies.example-pkg-c（第 16 行）
- 依据条款：A-REPL-002｜texts/Apache-2.0.json#licenseText §3
- 处置规则：A-REPL-002（核对日期 2026-10-17）
  > If You institute patent litigation against any entity (including a cross-claim or counterclaim in a lawsuit) alleging that the Work or a Contribution incorporated within the Work constitutes direct or contributory patent infringement, then any patent licenses granted to You under this License for that Work shall terminate as of the date such litigation is filed.

### example-pkg-d 4.0.0
- SPDX 标识：GPL-2.0-only
- 声明位置：package.json :: dependencies.example-pkg-d（第 20 行）
- 依据条款：A-REPL-002｜texts/Apache-2.0.json#licenseText §3
- 处置规则：A-REPL-002（核对日期 2026-10-17）
  > If You institute patent litigation against any entity (including a cross-claim or counterclaim in a lawsuit) alleging that the Work or a Contribution incorporated within the Work constitutes direct or contributory patent infringement, then any patent licenses granted to You under this License for that Work shall terminate as of the date such litigation is filed.

### example-pkg-e 5.0.0
- SPDX 标识：MPL-2.0
- 声明位置：package-lock.json :: packages.node_modules/example-pkg-e.license（第 10 行）
- 依据条款：A-OK-001｜texts/0BSD.json#licenseText 许可段
- 处置规则：A-OK-001（核对日期 2026-10-17）
  > Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby granted.

### example-pkg-f 6.0.0
- SPDX 标识：LGPL-2.1-only
- 声明位置：package-lock.json :: packages.node_modules/example-pkg-f.license（第 14 行）
- 依据条款：A-OK-001｜texts/0BSD.json#licenseText 许可段
- 处置规则：A-OK-001（核对日期 2026-10-17）
  > Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby granted.

### example-pkg-h 8.0.0
- SPDX 标识：AGPL-3.0-only
- 声明位置：requirements.txt :: line 2（第 2 行）
- 依据条款：A-REPL-002｜texts/Apache-2.0.json#licenseText §3
- 处置规则：A-REPL-002（核对日期 2026-10-17）
  > If You institute patent litigation against any entity (including a cross-claim or counterclaim in a lawsuit) alleging that the Work or a Contribution incorporated within the Work constitutes direct or contributory patent infringement, then any patent licenses granted to You under this License for that Work shall terminate as of the date such litigation is filed.

### example-pkg-i 9.0.0
- SPDX 标识：BSD-3-Clause
- 声明位置：requirements.txt :: line 3（第 3 行）
- 依据条款：A-OK-001｜texts/0BSD.json#licenseText 许可段
- 处置规则：A-OK-001（核对日期 2026-10-17）
  > Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby granted.

### example-pkg-j 10.0.0
- SPDX 标识：BUSL-1.1
- 声明位置：pyproject.toml :: project.dependencies.example-pkg-j
- 依据条款：A-DECL-001｜texts/MIT.json#licenseText 条件段
- 处置规则：A-DECL-001（核对日期 2026-10-17）
  > The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

### example-pkg-k 11.0.0
- SPDX 标识：MIT
- 声明位置：pyproject.toml :: project.dependencies.example-pkg-k
- 依据条款：A-OK-001｜texts/0BSD.json#licenseText 许可段
- 处置规则：A-OK-001（核对日期 2026-10-17）
  > Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby granted.

### example.com/example-pkg-l v12.0.0
- SPDX 标识：Unlicense
- 声明位置：go.mod :: require example.com/example-pkg-l（第 5 行）
- 依据条款：A-OK-001｜texts/0BSD.json#licenseText 许可段
- 处置规则：A-OK-001（核对日期 2026-10-17）
  > Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby granted.

> 依据条款的司法参照（不构成法律意见）：中国法院已有承认 GPL 类协议对衍生作品约束力的公开裁判（（2021）最高法知民终2063号，2023-05-05 终审）。本清单引用其方向性结论，不据此对具体项目下法律结论。

## 逐包明细

| package | version | spdx_id | tier | scenario | verdict | action_level | basis_clause | declaration_location | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| com.example:example-pkg-m | 13.0.0 | Python-2.0 | permissive | saas | not_triggered | ok | A-OK-001｜texts/0BSD.json#licenseText 许可段 | pom.xml :: <dependency> com.example:example-pkg-m（第 12 行） | 当前场景与链接方式下未触发任何需要行动的义务，且与项目 outbound 相容：依赖可直接使用，无附加动作。 |
| com.example:example-pkg-n | 14.0.0 | 0BSD | permissive | saas | not_triggered | ok | A-OK-001｜texts/0BSD.json#licenseText 许可段 | pom.xml :: <dependency> com.example:example-pkg-n（第 18 行） | 当前场景与链接方式下未触发任何需要行动的义务，且与项目 outbound 相容：依赖可直接使用，无附加动作。 |
| com.example:example-pkg-o | 15.0.0 | GPL-unknown |  | saas | pending_confirmation |  |  | pom.xml :: <dependency> com.example:example-pkg-o（第 24 行） | 场景结论为待确认，未触发义务集合未知；兼容性结论为待定，与项目 outbound 是否相容未知；原因码：conflict_pending、scenario_pending_confirmation |
| example-pkg-a | 1.0.0 | MIT | permissive | saas | not_triggered | ok | A-OK-001｜texts/0BSD.json#licenseText 许可段 | package.json :: dependencies.example-pkg-a（第 6 行） | 当前场景与链接方式下未触发任何需要行动的义务，且与项目 outbound 相容：依赖可直接使用，无附加动作。 |
| example-pkg-b | 2.0.0 | Apache-2.0 | permissive | saas | not_triggered | replace_or_license | A-REPL-002｜texts/Apache-2.0.json#licenseText §3 | package.json :: dependencies.example-pkg-b（第 10 行） | 清单内两条依赖的许可证组合已被规则包登记为 incompatible（依赖间冲突），且当前链接方式（无边界隔离 / 静态合并）使两者进入同一作品，无法通过进程或容器边界分开。 |
| example-pkg-c | 3.0.0 | GPL-3.0-only | strong-copyleft | saas | not_triggered | replace_or_license | A-REPL-002｜texts/Apache-2.0.json#licenseText §3 | package.json :: dependencies.example-pkg-c（第 16 行） | 清单内两条依赖的许可证组合已被规则包登记为 incompatible（依赖间冲突），且当前链接方式（无边界隔离 / 静态合并）使两者进入同一作品，无法通过进程或容器边界分开。 |
| example-pkg-d | 4.0.0 | GPL-2.0-only | strong-copyleft | saas | not_triggered | replace_or_license | A-REPL-002｜texts/Apache-2.0.json#licenseText §3 | package.json :: dependencies.example-pkg-d（第 20 行） | 清单内两条依赖的许可证组合已被规则包登记为 incompatible（依赖间冲突），且当前链接方式（无边界隔离 / 静态合并）使两者进入同一作品，无法通过进程或容器边界分开。 |
| example-pkg-e | 5.0.0 | MPL-2.0 | weak-copyleft | saas | not_triggered | ok | A-OK-001｜texts/0BSD.json#licenseText 许可段 | package-lock.json :: packages.node_modules/example-pkg-e.license（第 10 行） | 当前场景与链接方式下未触发任何需要行动的义务，且与项目 outbound 相容：依赖可直接使用，无附加动作。 |
| example-pkg-f | 6.0.0 | LGPL-2.1-only | weak-copyleft | saas | not_triggered | ok | A-OK-001｜texts/0BSD.json#licenseText 许可段 | package-lock.json :: packages.node_modules/example-pkg-f.license（第 14 行） | 当前场景与链接方式下未触发任何需要行动的义务，且与项目 outbound 相容：依赖可直接使用，无附加动作。 |
| example-pkg-g | 7.0.0 |  |  | saas | pending_confirmation |  |  | package-lock.json :: packages.node_modules/example-pkg-g.license（第 18 行） | 缺少 SPDX 标识，无法确定许可证义务；场景结论为待确认，未触发义务集合未知；兼容性结论为待定，与项目 outbound 是否相容未知；原因码：conflict_pending、scenario_pending_confirmation、spdx_id_missing |
| example-pkg-h | 8.0.0 | AGPL-3.0-only | network-copyleft | saas | triggered | replace_or_license | A-REPL-002｜texts/Apache-2.0.json#licenseText §3 | requirements.txt :: line 2（第 2 行） | 清单内两条依赖的许可证组合已被规则包登记为 incompatible（依赖间冲突），且当前链接方式（无边界隔离 / 静态合并）使两者进入同一作品，无法通过进程或容器边界分开。 |
| example-pkg-i | 9.0.0 | BSD-3-Clause | permissive | saas | not_triggered | ok | A-OK-001｜texts/0BSD.json#licenseText 许可段 | requirements.txt :: line 3（第 3 行） | 当前场景与链接方式下未触发任何需要行动的义务，且与项目 outbound 相容：依赖可直接使用，无附加动作。 |
| example-pkg-j | 10.0.0 | BUSL-1.1 | source-available | saas | triggered | declare | A-DECL-001｜texts/MIT.json#licenseText 条件段 | pyproject.toml :: project.dependencies.example-pkg-j | 只触发了声明类义务（保留版权与许可声明、标注修改、商标/专利提示），且与项目 outbound 相容：把许可全文与版权声明随交付物一并提供即可，不需要改变架构。 |
| example-pkg-k | 11.0.0 | MIT | permissive | saas | not_triggered | ok | A-OK-001｜texts/0BSD.json#licenseText 许可段 | pyproject.toml :: project.dependencies.example-pkg-k | 当前场景与链接方式下未触发任何需要行动的义务，且与项目 outbound 相容：依赖可直接使用，无附加动作。 |
| example.com/example-pkg-l | v12.0.0 | Unlicense | permissive | saas | not_triggered | ok | A-OK-001｜texts/0BSD.json#licenseText 许可段 | go.mod :: require example.com/example-pkg-l（第 5 行） | 当前场景与链接方式下未触发任何需要行动的义务，且与项目 outbound 相容：依赖可直接使用，无附加动作。 |

## 风险分级

### 宽松许可（permissive）
- com.example:example-pkg-m 13.0.0（Python-2.0）
- com.example:example-pkg-n 14.0.0（0BSD）
- example-pkg-a 1.0.0（MIT）
- example-pkg-b 2.0.0（Apache-2.0）
- example-pkg-i 9.0.0（BSD-3-Clause）
- example-pkg-k 11.0.0（MIT）
- example.com/example-pkg-l v12.0.0（Unlicense）

### 弱传染（文件/库级）（weak-copyleft）
- example-pkg-e 5.0.0（MPL-2.0）
- example-pkg-f 6.0.0（LGPL-2.1-only）

### 强传染（同一作品）（strong-copyleft）
- example-pkg-c 3.0.0（GPL-3.0-only）
- example-pkg-d 4.0.0（GPL-2.0-only）

### 网络传染（对外提供服务即触发）（network-copyleft）
- example-pkg-h 8.0.0（AGPL-3.0-only）

### 源码可见（非开源许可）（source-available）
- example-pkg-j 10.0.0（BUSL-1.1）

### 档位未覆盖（待人工确认）
- com.example:example-pkg-o 15.0.0
- example-pkg-g 7.0.0


## 处置建议

### 可直接使用
#### com.example:example-pkg-m 13.0.0（Python-2.0）
- 当前场景与链接方式下未触发任何需要行动的义务，且与项目 outbound 相容：依赖可直接使用，无附加动作。
- 依据条款：A-OK-001｜texts/0BSD.json#licenseText 许可段
- 声明位置：pom.xml :: <dependency> com.example:example-pkg-m（第 12 行）

#### com.example:example-pkg-n 14.0.0（0BSD）
- 当前场景与链接方式下未触发任何需要行动的义务，且与项目 outbound 相容：依赖可直接使用，无附加动作。
- 依据条款：A-OK-001｜texts/0BSD.json#licenseText 许可段
- 声明位置：pom.xml :: <dependency> com.example:example-pkg-n（第 18 行）

#### example-pkg-a 1.0.0（MIT）
- 当前场景与链接方式下未触发任何需要行动的义务，且与项目 outbound 相容：依赖可直接使用，无附加动作。
- 依据条款：A-OK-001｜texts/0BSD.json#licenseText 许可段
- 声明位置：package.json :: dependencies.example-pkg-a（第 6 行）

#### example-pkg-e 5.0.0（MPL-2.0）
- 当前场景与链接方式下未触发任何需要行动的义务，且与项目 outbound 相容：依赖可直接使用，无附加动作。
- 依据条款：A-OK-001｜texts/0BSD.json#licenseText 许可段
- 声明位置：package-lock.json :: packages.node_modules/example-pkg-e.license（第 10 行）

#### example-pkg-f 6.0.0（LGPL-2.1-only）
- 当前场景与链接方式下未触发任何需要行动的义务，且与项目 outbound 相容：依赖可直接使用，无附加动作。
- 依据条款：A-OK-001｜texts/0BSD.json#licenseText 许可段
- 声明位置：package-lock.json :: packages.node_modules/example-pkg-f.license（第 14 行）

#### example-pkg-i 9.0.0（BSD-3-Clause）
- 当前场景与链接方式下未触发任何需要行动的义务，且与项目 outbound 相容：依赖可直接使用，无附加动作。
- 依据条款：A-OK-001｜texts/0BSD.json#licenseText 许可段
- 声明位置：requirements.txt :: line 3（第 3 行）

#### example-pkg-k 11.0.0（MIT）
- 当前场景与链接方式下未触发任何需要行动的义务，且与项目 outbound 相容：依赖可直接使用，无附加动作。
- 依据条款：A-OK-001｜texts/0BSD.json#licenseText 许可段
- 声明位置：pyproject.toml :: project.dependencies.example-pkg-k

#### example.com/example-pkg-l v12.0.0（Unlicense）
- 当前场景与链接方式下未触发任何需要行动的义务，且与项目 outbound 相容：依赖可直接使用，无附加动作。
- 依据条款：A-OK-001｜texts/0BSD.json#licenseText 许可段
- 声明位置：go.mod :: require example.com/example-pkg-l（第 5 行）

### 需补充声明
#### example-pkg-j 10.0.0（BUSL-1.1）
- 只触发了声明类义务（保留版权与许可声明、标注修改、商标/专利提示），且与项目 outbound 相容：把许可全文与版权声明随交付物一并提供即可，不需要改变架构。
- 依据条款：A-DECL-001｜texts/MIT.json#licenseText 条件段
- 声明位置：pyproject.toml :: project.dependencies.example-pkg-j

### 需替换或取得商业授权
#### example-pkg-b 2.0.0（Apache-2.0）
- 清单内两条依赖的许可证组合已被规则包登记为 incompatible（依赖间冲突），且当前链接方式（无边界隔离 / 静态合并）使两者进入同一作品，无法通过进程或容器边界分开。
- 依据条款：A-REPL-002｜texts/Apache-2.0.json#licenseText §3
- 声明位置：package.json :: dependencies.example-pkg-b（第 10 行）

#### example-pkg-c 3.0.0（GPL-3.0-only）
- 清单内两条依赖的许可证组合已被规则包登记为 incompatible（依赖间冲突），且当前链接方式（无边界隔离 / 静态合并）使两者进入同一作品，无法通过进程或容器边界分开。
- 依据条款：A-REPL-002｜texts/Apache-2.0.json#licenseText §3
- 声明位置：package.json :: dependencies.example-pkg-c（第 16 行）

#### example-pkg-d 4.0.0（GPL-2.0-only）
- 清单内两条依赖的许可证组合已被规则包登记为 incompatible（依赖间冲突），且当前链接方式（无边界隔离 / 静态合并）使两者进入同一作品，无法通过进程或容器边界分开。
- 依据条款：A-REPL-002｜texts/Apache-2.0.json#licenseText §3
- 声明位置：package.json :: dependencies.example-pkg-d（第 20 行）

#### example-pkg-h 8.0.0（AGPL-3.0-only）
- 清单内两条依赖的许可证组合已被规则包登记为 incompatible（依赖间冲突），且当前链接方式（无边界隔离 / 静态合并）使两者进入同一作品，无法通过进程或容器边界分开。
- 依据条款：A-REPL-002｜texts/Apache-2.0.json#licenseText §3
- 声明位置：requirements.txt :: line 2（第 2 行）


## 待人工确认项

- [处置] com.example:example-pkg-o（SPDX 标识：GPL-unknown）— 原因码：conflict_pending、scenario_pending_confirmation
- [处置] example-pkg-g（SPDX 标识：未识别）— 原因码：conflict_pending、scenario_pending_confirmation、spdx_id_missing
- [冲突] OB-GPL-unknown-Elastic-2.0（SPDX 标识：未识别）— 原因码：tier_unavailable
- [冲突] OB-unidentified-Elastic-2.0（SPDX 标识：未识别）— 原因码：spdx_id_missing
- [画像] GPL-unknown（SPDX 标识：GPL-unknown）— 原因码：tier_uncovered、unknown_family
- [场景] com.example:example-pkg-o（SPDX 标识：GPL-unknown）— 原因码：tier_unavailable
- [场景] example-pkg-g（SPDX 标识：未识别）— 原因码：spdx_id_missing

## 免责声明

> 本清单由自动化工具生成，不构成法律意见（非法律意见）。涉及商业分发、诉讼或高价值交易时，请咨询执业律师。

