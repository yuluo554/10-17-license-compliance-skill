# data/ — 数据台账与纪律

> **查证基准日：2026-10-17**。本文档所有 URL 与计数均为该日实测/检索快照；会随时间漂移的数据一律与基准日成对出现。
> 三态标记：`✅ 已核对`（可直连、可解析）/ `⬜ 待核对`（路径已登记但未取得或不可用）/ 不可获取的源**不得作规则来源**。

## 一、依据查证记录（规则素材）

| # | 素材 | 状态 | 实测 / 核对结果 | 来源 |
| --- | --- | --- | --- | --- |
| S1 | SPDX 许可证清单 | ✅ 已核对 | 直连成功；`licenseListVersion` = **3.29.0**；字段含 `licenseId` / `name` / `isOsiApproved` / `isFsfLibre` / `seeAlso` / `detailsUrl` | <https://spdx.org/licenses/licenses.json> |
| S2 | SPDX 例外清单 | ✅ 已核对 | 直连成功；3.29.0（**2026-09-16**）；含 `GPL-CC-1.0`、`WxWindows-exception-3.1` 等 | <https://spdx.org/licenses/exceptions.json> |
| S3 | 单许可证全文 | ✅ 已核对 | 直连成功；`GPL-3.0-only.json` 的 `licenseText` 约 **3.5 万字符**，可作条款节号/段落锚点来源 | <https://spdx.org/licenses/GPL-3.0-only.json> |
| S4 | AGPL §13 网络交互 | ✅ 已核对 | 直连成功；Version 3 / 2007-11-19；原文要求"远程网络交互须向用户提供对应源码" | <https://www.gnu.org/licenses/agpl-3.0.en.html> |
| S5 | GB/T 44272-2024《信息技术 开源 开源许可证框架》 | ⬜ 待核对（**只作框架对齐**） | 元数据可查：2024-08-23 发布 / 2025-03-01 实施；全文需另购或仅预览，**不可逐条核对 → 不作规则来源** | 国家标准全文公开系统元数据 |
| S6 | OSADL 兼容矩阵 | ⬜ 待核对（**不作唯一来源**） | 官方 CSV 端点实测 **404 / ECONNRESET**；镜像 `priv-kweihmann/osadl-matrix`（18★）可用但需从包内提取 | 镜像见 GitHub；冲突对以 curated JSON 为主 |
| S7 | 中国司法锚点：罗盒案 | ✅ 已核对 | 最高人民法院知识产权法庭（2021）最高法知民终2063号，**2023-05-05 终审**；认定 GPL3.0 具合同性质、违约则授权自动终止，判赔 **50 万元** | <https://enipc.court.gov.cn/zh-cn/news/view-3655.html> |
| S8 | 需求证据（V2EX 原帖） | ✅ 已核对 | AGPL 能否商用 `/t/492190`；MinIO AGPL 传染 `/t/871132`；商用边界 `/t/769017`；OnlyOffice 网页编辑 `/t/957890`；双授权 `/t/888552`；被抄袭反诉 `/t/754170`；TPLINK 固件 GPL `/t/824253` | `https://www.v2ex.com` + 路径 |
| S9 | 开源空白检索 | ⬜ 软论据 | `gh api` 检索：`开源许可证 合规` total=2；`开源许可证 skill` total=1（`WANGKenwill/license-check`，0★，2026-10-08，README 自我限缩为取证层）；`license audit agent skill` total=8（最高 31★，无关）；`agent skill license compliance` total=8（`dungnotnull` 4★ 以 CVE 为主、`ajwann/license-compliance` 0★） | `gh api`，基准日 2026-10-17 |

> **软论据纪律**："开源空白"类结论**只作辅助论据**，不得与 S1–S4、S7 这类可直连原文核对的事实并列作硬锚点。检索式、计数与基准日必须成对出现，便于回溯复跑。

## 二、数据源可获取性记录

| 数据源 | 三态 | 获取方式 | 阻断原因 / 降级处置 |
| --- | --- | --- | --- |
| SPDX `licenses.json` | ✅ 已获取 | 直连下载 → 快照入 `data/spdx/` | — |
| SPDX `exceptions.json` | ✅ 已获取 | 直连下载 → 快照入 `data/spdx/` | — |
| SPDX 单许可证 JSON（按需） | ✅ 已获取 | 按 `detailsUrl` 取指定许可证 | 全文不整体入包，只抽条款锚点 |
| AGPL 官方文本页 | ✅ 已获取 | 直连 HTML → 抽 §13 锚点 | — |
| GB/T 44272-2024 全文 | ⬜ 待获取 | 需另购/预览 | **只作框架对齐引用**，不进规则包 |
| OSADL 官方兼容矩阵 CSV | ⬜ 待获取 | 官方端点 | 404 / ECONNRESET → 改 curated JSON；镜像仅交叉验证 |
| 罗盒案裁判信息 | ✅ 已获取 | 最高法知产法庭官网页面 | 作报告脚注引用，不作规则来源 |

### 成熟工具星数快照（基准日 2026-10-17，`gh api`）

| 工具 | 星数 | 定位 |
| --- | --- | --- |
| anchore/syft | 9692★ | SBOM 生成 |
| aboutcode-org/scancode-toolkit | 2645★ | 源码许可头扫描 / 许可证识别 |
| oss-review-toolkit/ort | 2104★ | 依赖与许可证编排、策略引擎 |
| davglass/license-checker | 1679★ | npm 依赖许可证枚举 |
| XmirrorSecurity/OpenSCA-cli | 1136★ | 组件成分分析 |
| licensee | 915★ | 单仓库许可证文件识别 |
| reuse-tool | 594★ | REUSE 规范合规 |
| pilosus/pip-license-checker | 78★ | pip 依赖许可证枚举 |

> 星数只用于证明"扫描/取证层已成熟且被占"，是**会漂移的软论据**：题面与文档中一律与基准日成对出现，不得单独引用为能力结论。

## 三、合成数据纪律

### 3.1 合成依赖清单

- 基准与示例**不使用任何真实项目的依赖清单**。全部使用合成清单，覆盖六种输入形态：`package.json`、`package-lock.json`（v2 / v3）、`requirements.txt`、`pyproject.toml`、`go.mod`、`pom.xml`。
- 合成清单中的包名必须来自**假包名白名单**：`example-pkg-a`、`example-pkg-b`、`example-pkg-c`……（前缀 `example-pkg-`，后缀为小写字母）。**禁止**使用真实 npm / PyPI / Go / Maven 包名来构造测试用例（坑位回归用例例外，见 3.2）。
- 许可证字段必须覆盖：SPDX 表达式（`MIT`、`Apache-2.0 OR MIT`、`GPL-2.0-only WITH Classpath-exception-2.0`）、trove classifier、非 SPDX 自由文本（含超长全文）、缺失字段。

### 3.2 真值植入与坑位回归

- **真值由生成器程序化输出**：生成合成清单的脚本同时输出 `truth.json`（每个包的期望 `spdx_id`、`confidence`、五档、触发条件、处置级别）。**严禁手抄数字**。
- **已知坑位回归用例**（允许使用真实包名，仅用于解析器回归，不进入示例报告）：
  - `pandas`：`license` 字段为超长全文（实测约 61K 字符）——用于证明"禁用全文关键词匹配"；
  - `psycopg2`：`license` 字段为自由文本形态；
  - `PyMySQL`：classifier 与表达式并存的形态；
  - `PyQt5`：多许可证 / 特殊条款形态。
  这四条用例的**期望输出由人工核对后写入真值文件并标注核对日期**，不得由解析器自身输出回填真值。
- **冲突对真值（M4）**：`data/truth/conflicts.json` 由 `tools/gen_conflict_truth.py` 从
  `references/curated/conflict-pairs.json` + `references/curated/tiers.json` **直接推导**，
  生成器不 import 生产冲突引擎；表达式求值用生成器内自带的迷你文法独立实现。
  三侧覆盖：① 已知冲突对全命中（含 `GPL-2.0-only` × `Apache-2.0`）与未登记组合；
  ② `OR` 最宽松 / `AND` 最严格（含嵌套与 `WITH`、未覆盖档位 → `resolved = false`）；
  ③ `outbound = pending` → 全部条目 `pending` 且文案固定。实测：4 条冲突对 / 2 对未登记组合 / 6 条求值样例。
- **场景真值**：八场景 × 链接方式的触发表由规则包给出，基准只引用不另写一份。
- **画像真值（M2）**：`data/truth/profile.json` 由 `tools/gen_profile_truth.py` 从
  `references/curated/tiers.json` **直接推导**，生成器不 import 生产画像引擎；锚点可定位性
  用文件内的朴素实现独立校验。真值必须同时登记「有档位」与「`tier: null`」两侧，
  否则未覆盖分支无人守。实测：52 个输入 ID → 48 条覆盖 + 4 条未覆盖。

- **场景真值（M3）**：`data/truth/scenario.json` 由 `tools/gen_scenario_truth.py` 从
  `references/curated/scenario-triggers.json` **直接推导**，生成器不 import 生产场景引擎。
  真值同时登记 `expect.matrix`（八场景 × 链接方式 × 档位 × 网络交互 = 230 行）与
  `expect.pending`（`tier: null` 分支）；链接方式轴场景的匹配用代表性交付形态（见 `inputs.link_scenario_delivery`）。

- **处置真值（M5）**：`data/truth/actions.json` 由 `tools/gen_action_truth.py` 从
  `references/curated/action-rules.json` + `references/curated/scenario-triggers.json`
  **直接推导**，生成器不 import 生产处置引擎；谓词匹配用文件内的独立朴素实现。
  真值登记**可达事实域**（6 组可达义务轴 × 确定冲突结论 × 依赖间冲突 × 链接方式 × 场景结论 = 192 组）
  与每级处置的植入样本（`expect.levels`，四级各一条），并要求「零未覆盖 + 零死规则」。

### 3.3 冻结纪律

- SPDX 快照、规则包、合成清单与真值在 M1 冻结入 `data/`，此后只读；需变更时另立版本号并重跑全部断言。
- **M1 实测（2026-10-17）**：11 个合成用例 / 44 条真值期望；`verify-data` 全命中；解析 F1 = 1.0。
  坑位素材存于 `references/curated/trap-packages.json`（照实录入的 PyPI 元数据）。
- 冻结物必须可 `--check` 位级复现：生成脚本 + 输入快照 → 生成物哈希与 manifest 一致。
- **M2 实测（2026-10-17）**：`tools/gen_profile_truth.py --check` rc=0；
  `licaudit bench --only m2` 52/52 命中。
- **M3 实测（2026-10-17）**：`tools/gen_scenario_truth.py --check` rc=0；
  `licaudit bench --only m3` 231/231 命中（6 条可用触发规则）。
- **M4 实测（2026-10-17）**：`tools/gen_conflict_truth.py --check` rc=0；
  `licaudit bench --only m4` 16/16 命中（4 条可用冲突对 + 2 对未登记组合 + 1 次无向复查 + 6 条求值样例 + 4 条待定条目）。
- **M5 实测（2026-10-17）**：`tools/gen_action_truth.py --check` rc=0；
  `licaudit bench --only m5` 196/196 命中（192 组确定输入 + 四级样本）；
  合成用例增至 12 个 / 59 条真值期望（新增 `example-project`：15 个依赖、六种清单形态、全合成包名），
  `verify-data` 全命中、解析 F1 = 1.0。

## 四、数值口径纪律

> **一处定义**：以下口径只在规则包（`references/ruleset/*.json`）中定义一次；题面、报告、注记只引用，不手写第二份表述。

1. **传染强度五档**（唯一枚举）：`permissive`（宽松）/ `weak-copyleft`（弱传染：LGPL、MPL、EPL）/ `strong-copyleft`（强传染：GPL）/ `network-copyleft`（网络传染：AGPL、SSPL）/ `source-available`（源可用：BUSL、Elastic）。
   - 档位判定只依据规则包的 `licenseId → tier` 映射；同一许可证不得在不同文档出现两个档位。
2. **可信度四级**（唯一枚举）：`license_expression` > `trove_classifier` > `license_first_line` > `truncated_fallback`。
   - 逐级命中即停，不跨级合并；`truncated_fallback` 的 `confidence` 恒为最低档且必须标"待人工确认"。
3. **版本语义**：`-only` / `-or-later` 原样保留；族系不明 → `<族>-unknown`；包版本不明 → `*`。三者都强制"待人工确认"。
4. **冲突求值**：`OR` 取最宽松（按五档从 `permissive` 到 `source-available` 排序）；`AND` 取最严格；项目 outbound 许可未提供 → `pending`（待定），不猜测。
5. **触发判定**：分发、网络交互（AGPL §13）、链接方式三者分别求值后取并集；**"商用"本身不是触发条件**，不得作为判定输入。
6. **处置四级**（唯一枚举）：`ok`（可直接用）/ `declare`（需补声明）/ `isolate`（需隔离：进程分离·容器边界）/ `replace_or_license`（需替换或取得商业授权）。
7. **证据锚点五项**：包名、版本、声明位置（文件 + 字段/行号）、SPDX ID、依据条款。任一缺失 → 条目降级为"待人工确认"，不得进处置结论。
8. **报告固定免责声明**（原样输出，不得改写）：
   > 本清单由自动化工具生成，不构成法律意见（非法律意见）。涉及商业分发、诉讼或高价值交易时，请咨询执业律师。

## 五、隐私与品牌

- 纯本地处理，用户依赖清单与项目信息**不上传**；示例与测试数据全部为合成清单。
- 本题是**开源软件许可证合规**方向；文档、仓库名、Skill 名不引用其他项目的名称、素材或文档模板。
