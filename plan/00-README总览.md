# 10-17-license-compliance-skill 总览（plan/00）

- **项目**：开源许可证合规审查 Skill（Agent Skill：`SKILL.md` + 确定性 CLI 引擎 + 可版本化规则包）
- **性质**：不参赛项目题（模拟项目），发布 GitHub **公开仓库**，署名 `yuluo554`
- **版本**：v1（2026-10-17 定稿）
- **当前里程碑**：**M0 / M1 / M2 / M3 / M4 / M5 / M6 已完成（2026-10-17）**；已发布 `v0.1.0`（tag + Release 附产物 + 留档）。
- **定位**：现有工具出事实（syft / scancode / ORT），本题做**判定层**——把"场景 × 传染 × 冲突 × 中文处置"串成可回归测试的判定链。

## 一、文档索引

| 文档 | 内容 | 状态 |
| --- | --- | --- |
| `plan/00-README总览.md` | 本文档：索引、决策记录、承诺-证据台账、里程碑 | ✅ 已建立 |
| `plan/01-题目文档.md` | 十段式题目定稿（**定稿不改写**；后续勘误走新版本号 + 版本史行） | ✅ 已建立 |
| `plan/02-架构与技术选型.md` | 交付形态、分层架构、目录结构、退出码契约、技术选型 | ✅ M0 |
| `plan/03-模块详设.md` | M1–M5 实现级设计、判定语义总纲、失败路径 | ✅ M0；M1 落地补充（D19/D22）；M2 落地补充（§2.5）；M3 落地补充（§3.4）；M4 落地补充（§4.7）；M5 落地补充（§5.6，D35/D36） |
| `plan/04-数据计划.md` | SPDX 快照、规则包生成、合成清单与真值、冻结纪律 | ✅ M0；M1 执行完毕；M2–M5 真值就位 |
| `plan/05-里程碑.md` | M0–M6 DoD、K 清单（唯一一份） | ✅ M0–M5 DoD |
| `plan/06-交付对标与决策记录.md` | 评分对标、决策记录（D1–D36）、待定决策表、风险 | ✅ M0–M5 |
| `plan/HANDOFF-M1.md` | M0→M1 交接（六节） | ✅ 已完成其内容 |
| `plan/HANDOFF-M2.md` | M1→M2 交接（六节） | ✅ 已完成其内容 |
| `plan/HANDOFF-M3.md` | M2→M3 交接（六节） | ✅ 已完成其内容 |
| `plan/HANDOFF-M4.md` | M3→M4 交接（六节） | ✅ 已完成其内容 |
| `plan/HANDOFF-M5.md` | M4→M5 交接（六节） | ✅ 已完成其内容 |
| `plan/HANDOFF-M6.md` | M5→M6 交接（六节） | ✅ M5 |
| `plan/RELEASE-M6.md` | 发布留档：tag 时点事实 / tag 后追加事实两栏 + tag / Release 附件 / 校验和 | ✅ M6（tag 前入库） |
| `tools/check_release.py` | 发布终态自检门（离线 + `--online`） | ✅ M6 |
| `data/README.md` | 依据查证记录（三态）、数据源可获取性、合成数据纪律、数值口径 | ✅ 已建立 + M5 实测 |
| `data/synthetic/README.md` | 合成数据与真值库说明 | ✅ M1 + M5 |
| `references/README.md` | 规则包结构与生成纪律 + M1/M3/M4/M5 实测数字 | ✅ M1 + M3 + M4 + M5 |
| `tools/README.md` | 生成器清单与纪律 + M1–M5 实测 | ✅ M1 + M3 + M4 + M5 |
| `examples/README.md` | 示例报告生成与断言 | ✅ M5 |
| `SKILL.md` | Skill 主入口（含机器可解析契约块） | ✅ M0–M5 |
| `README.md` | 仓库说明、快速开始、退出码、限制 | ✅ M0–M5 |

## 二、决策记录

| 编号 | 决策 | 弃选项 | 弃因 |
| --- | --- | --- | --- |
| D1 | 交付形态收敛为**唯一 Agent Skill**（`SKILL.md` + CLI + `references/`） | GUI / 桌面 exe / "CLI 或桌面任选其一" | 形态留后门会给空壳通行证；本题核心是规则包与判定链，不需要图形形态 |
| D2 | 只做**判定层**（场景 × 传染 × 冲突 × 中文处置） | 源码头扫描 + SBOM 生成入首期 | 重依赖且 syft / scancode / ORT / reuse-tool 已成熟覆盖；重复造轮子且拖垮首期 |
| D3 | 冲突对以 **curated JSON** 为主、OSADL 镜像仅交叉验证 | 依赖 OSADL 官方 CSV 端点作唯一来源 | 官方端点 404 / ECONNRESET，不可作为可复现来源（预检②） |
| D4 | 规则来源只用 **SPDX 机器可读 JSON + curated 条款锚点** | 以 GB/T 44272-2024 作规则来源 | 全文需另购/预览，不可逐条核对；**仅作框架对齐引用**（预检②⑥） |
| D5 | 许可证识别走**四级可信度链 + 首行锚定** | 全文关键词匹配 | pandas 等包的 license 字段极长，全文匹配必然误命中（经典陷阱） |
| D6 | 不做 CVE / 供应链安全评分 | 把 CVE 维度并入首期 | 偏离许可证主线，且与安全类 skill 定位撞车 |
| D7 | `-only` / `-or-later` 原样保留，族系不明归 `<族>-unknown` | 归一化为不带后缀的族名或默认最新版 | 会改变可升级性判定，属于实质性判定错误 |
| D8 | 纯本地处理，SPDX 快照随包冻结，联网刷新为可选增强 | 运行时强制联网查 npm / PyPI | 清单本地可解；联网引入不可复现与隐私风险 |
| D9 | 品牌隔离：本题只做开源软件许可证 | 与其他项目共用文档模板、素材或交叉引用 | 领域不同，交叉引用会污染定位与检索 |
| D10 | Python **3.12+** 纯标准库，src 布局 + setuptools（2026-10-20 由 plan/06 D39 从 3.8+ 抬升） | Node / Go / poetry / hatch | 零安装成本；pytest 仅在 dev extra |
| D11 | **完全不使用 LLM** | LLM 抽取兜底 / 复核 | 判定必须确定可复现；无解析兜底需求；免去 API 依赖与脱敏面 |
| D12 | 规则包放仓库 `references/`，~~不打进 wheel~~；发布形态为源码包 + editable —— **2026-10-19 由 plan/06 D38 修正：规则包与真值同时打进 wheel** | 规则包收进包内 | 首期发布物是 git clone / 源码包；规则包需人工审阅与 `--check`。D38 起 wheel 开箱可用 |
| D13 | 报告层零判定用 AST 三条守门 | 只靠代码评审 | 「不 import」只证明通道不证明内容 |
| D14 | TOML 用受限子集自写解析器（原口径：3.8 无 `tomllib`；floor 抬到 3.12 后该库可用，解析器仍保留自写，见 plan/06 D39） | 引入 `tomli` 运行时依赖 | 保持零依赖；超集显式 `toml_unsupported`，不静默跳过 |
| D15 | 骨架阶段 `scan/assess/report` 因规则包缺失**真实返回 exit 3** | 返回空结果 exit 0 / 伪造占位数据 | 「零依赖、无风险」的 exit 0 是最危险的假成功 |
| D16 | M3 对外八场景 ID 与 `(delivery, link_mode)` 双轴映射 | 只用 delivery 五值 | 题面要求八场景；链接方式本身是判定输入 |
| D17 | CI 矩阵 windows/ubuntu × **3.12**（2 个 job；2026-10-20 由 plan/06 D39 从 × 3.8/3.12 收窄），`PYTHONUTF8=1` | 单平台单版本 | 本机可做本地等价校验；跨平台只能靠 CI |
| D18 | 仓库公开、署名 `yuluo554` | 私有仓库 | 题目要求公开发布 |
| D19 | 依赖级许可证只认清单显式写出的值，绝不按包名/生态推断 | 按包名查 npm/PyPI 或按生态默认 | 推断即猜测；清单没写就是不知道 |
| D20 | 规则包锚点必须带可在原文逐字定位的 `quote` | 只记节号 / 只记文件名 | 节号会随版本漂移且无法机器校验 |
| D21 | 显式 `--rules-dir` 无效时不回退 | 回退到环境变量/仓库推导 | 静默回退会让调用方以为在验证自己指定的那份规则 |
| D22 | 真值是「两个非互斥列表」：`dependencies` + `pending_confirmation` | 单一列表 + 布尔标记 | 一条记录可以既可用又待确认；互斥列表会丢掉这层语义 |
| D23 | 画像**按原子 ID** 出，表达式在 M2 只拆不求值；`WITH` 只拆出许可证 ID | 直接对整条表达式出档位 / 自行组合 `AND`-`OR` | 求值规则（`OR` 最宽松 / `AND` 最严格）属 M4；M2 自行组合等于提前定死 M4 口径 |
| D24 | 无规则时条款 `present = null`（不知道），`false` 只表示「该许可证没有此条款」 | 一律填 `false` | 把「不知道」写成 `false` 会把未核验项说成「无专利条款」，是实质性误判 |
| D25 | 画像退出码：有待确认项 → `1`；全部覆盖 → `0` | 一律 `0` | 与 `plan/03` §六失败路径表一致；「零依赖、无风险」式 exit 0 不得复用到未覆盖场景 |
| D26 | 画像真值由 `tools/gen_profile_truth.py` 从 curated 规则表**直接推导**，生成器不 import 生产引擎 | 跑一遍引擎再把输出写成真值 | 回填等于用实现证明实现；锚点可定位性必须独立校验 |
| D32 | M4 用求值结果**回填 scenario 判定**；`expression_unresolved` 收窄为「求值不出」 | 维持 M3 的「原子结论不一致即待确认」 | 两个产物对同一表达式给不同结论会让报告自相矛盾；求值口径 D31 已交给 M4 |
| D33 | `same-license` 判据加档位护栏（outbound 档位不高于依赖才判不兼容） | 许可证不同即不兼容 | GPLv3 合并进 AGPLv3 由 AGPL §13 允许；判不兼容会与原文冲突 |
| D34 | M4 不做传染范围聚合，只做档位级比较并在产物里显式登记 | 本轮就做 `linkage-boundary.json` | 聚合尚无消费方（属 M5 处置分级）；半成品聚合表比诚实的粗判更危险 |
| D35 | `actions.json` 由 `assess` 全量模式产出（第四份产物），`report` 只读产物不重算 | `report` 自己跑判定 / 单独加 `licaudit action` 子命令 | 报告层零判定（K23）；产物链每步可单独复查（K29）；少一条等价通路 |
| D36 | 处置分级用「义务轴 + 冲突结论 + 依赖间冲突 + 链接方式」查有序决策表；「边界可分离」由 `link_mode` 维度承担，聚合仍不实现 | 按 `tier` 直接映射四级 / 本轮补聚合表 | 档位直接映射等于把枚举搬进代码（违 K4），且无法表达同档位内差别；聚合表无独立证据源 |

> D1–D9 原载于出题阶段；D10–D18 于 M0 新增；D19–D22 于 M1 新增；D23–D26 于 M2 新增；
> D27–D31 于 M3 新增；D32–D34 于 M4 新增；D35–D36 于 M5 新增；D37 于 M6 新增。编号只增不改。

## 三、承诺-证据台账（全项目唯一一份）

> 状态列随里程碑同步翻转；其他文档只可引用本表，不得复制第二份。
> `⬜` 表示尚未兑现的承诺，**不得在任何文档里写成已完成**。

| 承诺项 | 素材来源 | 交付物内可达性 | 核验方式 | 状态 |
| --- | --- | --- | --- | --- |
| SPDX 许可证清单可用作规则来源 | <https://spdx.org/licenses/licenses.json>（3.29.0） | 快照入 `references/spdx/`，随仓冻结 | manifest 记录 `license_list_version` + `--check` 位级一致 | ✅ M1 |
| SPDX 例外清单可用于 `WITH` 解析 | <https://spdx.org/licenses/exceptions.json>（3.29.0） | 同上 | 例外 ID 命中率基准 | ✅ M1（`WITH` 命中/未命中双向用例） |
| 单许可证全文可作条款锚点 | <https://spdx.org/licenses/GPL-3.0-only.json> | 按需取子集入仓（48 份），全文不入包 | 锚点抽检：quote 可在 text 中逐字定位 | ✅ M1（`test_tier_anchors_are_locatable_in_snapshots`） |
| AGPL §13 网络交互为独立触发点 | <https://www.gnu.org/licenses/agpl-3.0.en.html> | 规则包场景触发表 | 基准用例：SaaS + 未分发 → 触发 | ✅ M3 |
| 中国司法锚点（罗盒案） | （2021）最高法知民终2063号，2023-05-05 终审 | 报告"证据锚点"章节固定引用 | `test_report_cites_the_judicial_anchor` + 入仓示例报告逐字可查 | ✅ M5 |
| M1 四级可信度链 | 六种清单形态的真实结构 | 解析器纯函数，随包 | 坑位回归：pandas / psycopg2 / PyMySQL / PyQt5；F1 = 1.0 | ✅ M1 |
| M2 传染五档 + 义务矩阵 | SPDX 字段 + curated 条款锚点 | `references/ruleset/` | 每个 SPDX ID 的真值表断言 | ✅ M2（`bench --only m2`，52 个 ID / 命中 52） |
| M3 场景判定（八场景） | AGPL §13 + curated 触发表 | `assess` 命令 | 八场景 × 链接方式判定表 | ✅ M3（`bench --only m3`，231/231） |
| M4 冲突与兼容性 | curated `conflict-pairs.json` + OSADL 镜像交叉验证 | `assess` 命令 | `GPL-2.0-only × Apache-2.0` 等已知对 | ✅ M4（`bench --only m4`，16/16） |
| M5 中文清单 + 四级处置 + 五锚点 | 引擎输出 + curated 处置决策表 | `report` 命令（MD/CSV） | 锚点完整性 + 八章节顺序 + 免责声明 + AST 三条守门 + `bench --only m5`（196/196） | ✅ M5 |
| 契约块与代码双向一致 | `SKILL.md` + `contract.py` | 交付态入口 | 集合相等 + 顺序相等 + 实际字段序 | ✅ M0（`tests/test_skill_contract.py`） |
| 退出码四语义 | `exit_codes.py` | CLI | 0/1/2/3 逐码测试；`1` 由 M5 处置分级真实产出 | ✅ M5 |
| 规则包加载硬门 | `ruleset/loader.py` | CLI 每次运行 | 未核验/缺锚点/缺核对日期/哈希不符/缺文件 → exit 3 | ✅ M0 |
| 自检可证伪 | `selftest.py` | `licaudit selftest` | 空规则包 → exit 1；6 项核心 check 各有变异用例 | ✅ M0 |
| 纯本地 / 零上传（源码层） | 架构 | 运行时无出站请求 | AST 扫描禁止网络模块 import | ✅ M0（产物层：报告与产物只写 `--out-dir`，M6 复核） |
| 发布三件套：tag / Release 附产物 / 留档 | GitHub 公开仓库 | Release 页面 + `plan/RELEASE-M6.md` | `gh release view` + 附件**真下载**后重算 sha256 + `tools/check_release.py --online` | ✅ M6 |
| CI 全绿（M6 时点为四矩阵） | `.github/workflows/ci.yml` | 每次 push 自动跑 | `gh run view`：M6 时点 windows/ubuntu × 3.8/3.12 四个 job 全 success，日志含 `selftest` / 七个 `--check` / `verify-data` / `bench`。**2026-10-20 起矩阵收为 3.12 × 双 OS（2 个 job），改动未推送、未跑远端**（见 §五 v0.1.1 条） | ✅ M6（首推提交 `5e7ad6f`；新矩阵待推送验证） |
| 「源码包」发布形态自足 | `MANIFEST.in` | sdist 自带 `references/` 规则包与 SPDX 快照 | 解包 → `pip install -e .` → `licaudit status` 不再 exit 3 | ✅ M6 |
| 三条调用通路等价 | `cli.py` / `__main__.py` / `scripts/launcher_licaudit.py` | — | 子进程实跑 + 退出码一致 | ✅ M0 |
| 合成数据白名单 | `data/synthetic/` | 随包 | `test_synthetic_packages_are_whitelisted` | ✅ M1 |
| 中文合规 skill 形态空白 | `gh api` 检索，基准日 2026-10-17 | — | 软论据，记录检索式与基准日 | ⬜ 软论据（不可硬化为结论） |

## 四、里程碑

| 里程碑 | 内容 | DoD | 状态 |
| --- | --- | --- | --- |
| **M0 计划与骨架** | plan/00–06；CLI 契约与退出码；规则包加载硬门；可证伪自检；三条调用通路；CI 配置 | 双解释器 pytest 全绿（137 项）；退出码 0/2/3 锁进测试；README 命令实跑；CI 属「本地等价校验，未接远端」 | ✅ 2026-10-17 |
| **M1 数据先行 + M1 解析** | SPDX 快照；规则包 v0；合成清单与真值；M1 解析器；`scan` 命令 | 快照/规则包/真值入仓且 `--check` 位级一致；四条坑位全部有断言；`verify-data` 读冻结件；解析 F1 = 1.0 | ✅ 2026-10-17 |
| **M2 画像矩阵** | 传染五档、义务项、OSI/FSF、专利/商标条款；`assess --profile-only` | 每个采样 ID 有档位+义务+锚点；无锚点不生效；FSF 不参与判定 | ✅ 2026-10-17 |
| **M3 场景判定** | 八场景 × 链接方式触发表；用户回答落盘 | 判定表全绿；SaaS 未分发但网络交互 → 触发；「商用」不在输入 | ✅ 2026-10-17 |
| **M4 冲突分析** | `conflict-pairs.json`（4 条已核验冲突对）；`OR`/`AND` 求值；outbound 判定；`conflicts.json` | 已知冲突对全命中（含 GPL-2.0-only × Apache-2.0）；冲突对无向匹配；outbound 未知 → 全部待定 | ✅ 2026-10-17 |
| **M5 输出与基准** | `scan → assess → report`；MD/CSV；四级处置；五锚点；`bench --only m5` | 交付态全链；契约三方断言；AST 零判定守门；锚点完整性 | ✅ 2026-10-17 |
| **M6 发布** | GitHub 公开仓库 `yuluo554/10-17-license-compliance-skill` | 三件套：tag `v0.1.0` / Release 附件（真实产物）/ `plan/RELEASE-M6.md`（tag 前入库）；干净 clone 复核；CI 首推四矩阵全绿 | ✅ 2026-10-17 |

> M6 口径采用 "Release 附产物"，不采用"源码 zipball 即产物"。发布留档文件必须在 tag **之前**入库；
> tag 之后只允许追加类提交，并在留档里分栏写"tag 时点事实 / tag 后追加事实"。

## 五、当前状态

- **M0 已完成（2026-10-17）**：计划文档 00–06 齐备；骨架可安装、三条通路实跑；退出码四语义锁进测试；
  规则包加载硬门与可证伪自检就位；CI 配置就位但**未接远端**。
- **M1 已完成（2026-10-17）**：SPDX 3.29.0 快照（740 许可 / 86 例外 / 48 份全文）冻结；
  curated 人工表（48 条档位规则、7 条 trove 映射、4 条坑位元数据）；规则包 r0.1.0 生成且 `--check` 位级一致；
  11 个合成用例 + 44 条真值期望；M1 解析器（六形态 / 四级链 / SPDX 表达式）；`scan` / `verify-data` /
  `bench --only m1` 打通；双解释器 **247 passed, 1 skipped**；F1 = 1.0；7 组变异验证。
- **M2 已完成（2026-10-17）**：`assess --profile-only` 产出 `profile.json`（52 个原子 ID：
  48 条有档位 + 4 条未覆盖 → `tier: null` + 待确认）；档位/义务/条款只查规则包，
  OSI/FSF 只从 SPDX 快照取且 FSF 不参与判定；`data/truth/profile.json` 由 curated 规则表
  直接推导并 `--check` 位级一致；`bench --only m2` 52/52 命中；双解释器 **288 passed, 1 skipped**；
  9 组变异验证。
- **M3 已完成（2026-10-17）**：场景触发表补齐为 6 条已核验条目（分发 / AGPL §13 网络交互 /
  静态链接 / 托管服务限制，锚点均可在 SPDX 全文逐字定位）；`assess --scenario ... --outbound-license ...`
  产出 `profile.json` + `scenario.json`；`data/truth/scenario.json`（230 行判定表 + 1 条 `tier: null`）
  由 curated 触发表直接推导且 `--check` 位级一致；`bench --only m3` 231/231 命中；
  双解释器 **342 passed, 1 skipped**；9 组变异验证。
- **M4 已完成（2026-10-17）**：curated 冲突对表补齐为 4 条已核验条目（锚点可在 SPDX 全文逐字定位，
  另加「left/right 必须在快照内」「无向组合不得重复」两道生成器门）；`assess` 全量模式追加
  `conflicts.json`（依赖间冲突 + 依赖 × outbound + 表达式求值记录 + 未登记组合覆盖度）；
  `data/truth/conflicts.json` 由 curated 冲突对表直接推导且 `--check` 位级一致；
  `bench --only m4` 16/16 命中；双解释器 **401 passed, 1 skipped**；12 组变异验证
  （`_mutate_m2/m3` 复跑仍全绿）。**D32 起表达式求值回填 scenario 判定**，全量模式退出码把冲突
  待定/不兼容并进聚合（`--outbound-license pending` 一律 exit 1）。
- **M5 已完成（2026-10-17）**：curated 处置决策表 8 条已核验规则（义务轴映射 + 有序 when 谓词，
  生成器另加「覆盖完备 / 无死规则」两道门，192 组确定输入零未覆盖）；`assess` 全量模式追加
  `actions.json`（四级处置 + 五锚点门 + 待确认投影）；`report` 渲染八章节中文清单（MD/CSV 同源、
  CSV 无 BOM、免责声明逐字、司法参照固定引用）；报告层三条 AST 守门落进测试；
  `data/truth/actions.json` 由 curated 决策表直接推导且 `--check` 位级一致；
  `bench --only m5` 196/196 命中；示例项目（15 依赖 / 六种清单形态）与两份示例报告入仓并可逐字节复现；
  双解释器 **467 passed, 0 skipped**；13 组变异验证（`_mutate_m2/m3/m4` 复跑仍全绿）。
  **D35/D36** 登记了「actions.json 由 assess 产出」与「分级查表 + 聚合仍不做」两条口径。
- **M6 已完成（2026-10-17）**：发布动作全部落地——脱敏自查（绝对路径 / 凭证 / 跨项目引用 / 模板占位
  全部为 0）、`MANIFEST.in` 让 sdist 自带 `references/` 规则包（「源码包」形态自足）、
  `tools/check_release.py` 发布终态自检门；GitHub **公开仓库**创建并**首推**，
  CI 四矩阵（windows/ubuntu × 3.8/3.12）**全绿**；打 tag `v0.1.0` 并建 Release
  （附真实产物，非「源码 zipball 即产物」），附件**下载回来逐个重算 sha256** 与留档一致；
  干净 clone 复核通过。`plan/RELEASE-M6.md` 在 tag **之前**入库，按
  「tag 时点事实 / tag 后追加事实」两栏记录，不预填。M6 **未新增任何判定能力**
  （`src/licaudit/` 判定链一行未改）；新增口径 D37（`MANIFEST.in` 让 sdist 自带规则包）。
- **v0.1.1 已完成（2026-10-19）**：M6 之后的小版本（DoD 见 `plan/05-里程碑.md` §二之七）——
  wheel 首次自带规则包与真值（修正 D12，见 D38）；随包资源定位统一为「源码态仓库根 + 安装态
  site-packages」两处都找（修掉安装态 `assess` / `report` 报「SPDX 快照不可读」的 exit 2）；
  规则集 `meta.review` 复核元数据入库（复核日 / 周期 / 下次到期 / 复核人 / `standards[]`）；
  `licaudit report` 概述区新增工具版本与 SPDX 许可证清单两行；PyPI 上架 `licaudit 0.1.1`。
  **实测 457 passed**（3.8 / 3.12 各一次；基线时点 `8173867` = tag `v0.1.1`）。
  干净 venv 装 wheel 后 `licaudit status` / `licaudit selftest` 均 rc=0。
  > 457 比 M5/M6 的 467 少 20 项，原因是 README 改产品页后 `test_readme_surface.py` 的
  > 参数化样本减少（不是删断言），成因与代价记在 `plan/06` §五。
  > `plan/05`、`plan/RELEASE-M6.md`、`plan/HANDOFF-M6.md` 里的 467 **保持不动**——那是 M5/M6
  > （= `v0.1.0` 时点）的实测值，已与 `gh run view 39034225029` 的日志对齐。
- **v0.1.2 已发布（2026-10-20）**：`license` 改 PEP 639 形式（`license = "MIT"` +
  `license-files`）、`build-system` 抬到 `setuptools>=77`、Python floor **3.8 → 3.12**、
  CI 矩阵收为 `3.12` × 双 OS（2 个 job）、actions 升 `checkout@v7` / `setup-python@v7`
  （口径与实测见 `plan/06` D39）；同时修掉 v0.1.1 遗留的陈旧口径（`SKILL.md` 的
  `metadata.version` 停在 `0.1.0`、README 不提 M6、SKILL 限制段仍写「不支持 wheel 安装后直接使用」）。
  判定面为零（`src/licaudit/` 只改 `__version__`，规则包/快照字节未动）。
  发布事实（tag / Release 附件 / sha256 / 远端 CI）见 `plan/RELEASE-v0.1.2.md`。
- **本轮收尾动作**：`tools/check_release.py` 的发布留档不再写死 `plan/RELEASE-M6.md`，改为按包
  版本匹配 `plan/RELEASE-*.md` 的 `tag`（旧的写死路径让包版本一抬就永远红）；`examples/report/`
  的两份 MD 因报告内嵌工具版本而按 `plan/04` 重生成（**只差版本号一行**，CSV 逐字节不变）；
  `update/`（诊断交接目录，含绝对路径）加入 `.gitignore`。
- **未做**：传染范围聚合（D36，明文登记）；`v0.1.1` 的发布留档（同名文件 `plan/RELEASE-v0.1.1.md`
  从未建立，本轮按版本补齐的是 `v0.1.2` 那一份；`v0.1.1` 的发布事实仍以 `plan/05` §二之七 与
  `plan/RELEASE-M6.md` 的体例承载）。
- **下一棒**：里程碑表 M0–M6 全部 ✅，无强制项。若要继续，优先：
  ① 让 `tests/test_readme_surface.py` 也覆盖 `DEVELOPMENT.md`（v0.1.1 精简 README 时约 10 条命令
  迁走且失去门禁）；② PyPI 上 `licaudit` 仍是 `0.1.1`（`requires_python >=3.8`），若要同步元数据
  需另行授权上传 `0.1.2`；③ 传染病范围聚合（D36）。收尾固定动作见 `plan/05` §四。
- **诚实口径**：M6 轮的 CI 表述从「本地等价校验，未接远端」改为**实测四矩阵全绿**
  （首推提交 `5e7ad6f`，run `39033849070`）；`check_release.py` **刻意不进 CI**，
  因为它是发布终态门、发布之前必然红（理由记在 `plan/RELEASE-M6.md` §1.5）。
  2026-10-20 起 CI 矩阵是 **2 个 job**（`3.12` × 双 OS），四矩阵的表述只属于 M6 那一段历史。
