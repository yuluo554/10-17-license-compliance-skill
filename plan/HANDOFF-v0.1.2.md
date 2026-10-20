# plan/HANDOFF-v0.1.2：M6 之后的元数据修补与发版（下一棒交接）

> 命名口径（`plan/05` §二之十）：里程碑 M0–M6 已收口，之后不再新增里程碑；发布留档与交接文档
> 按**版本**命名（`plan/RELEASE-v<version>.md` / `plan/HANDOFF-v<version>.md`）。

## 一、当前进度与证据

本轮做的事，一句话：**把 v0.1.1 发布后暴露的元数据 / 文档 / 门禁问题收干净，并以 `v0.1.2` 发版。**
判定面为零——`src/licaudit/` 只改了 `__init__.py` 的 `__version__`；规则包 `r0.1.0` 与
SPDX 3.29.0 快照、curated 表、`data/truth/` 的字节未动（七个生成器 `--check` 全绿即逐字节证明）。

### 已交付

| 项 | 内容 | 证据 |
| --- | --- | --- |
| 许可证元数据 | `license = "MIT"` + `license-files`（PEP 639），删 `License ::` classifier | `prepare_metadata_for_build_wheel` 的弃用警告 **3 → 0**；`METADATA` 2.4 带 `License-Expression: MIT` |
| Python floor | 3.8 → **3.12**（`requires-python` + classifiers 同步） | `py -3.12` 457 passed；3.8 通道本地仍绿但已退出承诺面 |
| CI | actions `checkout@v7` / `setup-python@v7`；矩阵 `3.12` × 双 OS（2 job） | 提交 `4a901bf` 两次 run 全 success（`39360702962` / `39360849976`），Node20 注解 0 条 |
| 发布门 | `tools/check_release.py` 按包版本发现留档（不再写死 `plan/RELEASE-M6.md`） | `--artifacts-dir dist --online` rc=0 |
| 文档事实 | `SKILL.md` 版本号 / 限制段、README 徽章与当前版本、`DEVELOPMENT.md`、`plan/00`·`02`·`05`·`06` | 见 `plan/05` §二之八 / §二之九 |
| 示例报告 | `examples/report/*.md` 按 `plan/04` 重生成 | 两份 CSV 逐字节不变；两份 MD 只差「工具版本」1 行 |
| 发布 | tag `v0.1.2`（附注，对象 `e2128fe9…`）→ 提交 `4a901bf`；Release（latest）3 附件 | `plan/RELEASE-v0.1.2.md` §二（含四方对撞与干净 clone 复核） |
| 仓库卫生 | `update/`（诊断交接目录，含本机绝对路径）加入 `.gitignore` | 脱敏自查从 27 命中降到 **26**，且「需人工判断的命中」= 0 |

### 关键数值（本轮实测）

- 测试：**457 passed, 0 skipped**（本机 3.12；干净 clone 3.12；CI ubuntu/windows 各一次）
- 基准：m1 59/59、m2 52/52、m3 231/231、m4 16/16、m5 196/196；`--only m6` 仍 rc=2（不装通过）
- 产物：wheel 789640 B / sdist 896954 B / `SHA256SUMS` 186 B
  - `ac5f9bd9826b4f9cf1d61690378b84e402b55b838e69b3f976c89e4b6069937f`（whl）
  - `728b9bdd2c4d7ac454094b6ebc3ad58c8c22a61529d76aef225b2cab123151e3`（sdist）
- wheel 构成：140 条目（`licaudit` 30 / `references` 65 / `data` 39）

## 二、下一棒待办

1. **PyPI 未同步**：PyPI 上 `licaudit` 仍是 `0.1.1`（`requires_python >=3.8`、无
   `license_expression`）。要对齐 `0.1.2` 的元数据必须**另行授权上传**（本机无 `twine`、
   无 `TWINE_*` / `PYPI_*` 凭证、无 `~/.pypirc`；上传需 token）。
2. **`tests/test_readme_surface.py` 不覆盖 `DEVELOPMENT.md`**：v0.1.1 把 README 改成产品页后，
   约 10 条命令迁到 `DEVELOPMENT.md`，而该测试只读 README.md / SKILL.md —— 这批命令目前
   **没有任何门禁**。修法是让测试也扫 `DEVELOPMENT.md`（属测试面扩大，需单独立项）。
3. **`check_status_flipped` 里的里程碑检查仍是 M6 硬编码**：门禁现在按包版本发现留档，但
   「README/SKILL 必须提到 M6」「plan/00 的 M6 行必须 ✅」两条仍是里程碑硬编码。它当前**通过**
   （M6 是最后一个里程碑，提它是合理的），但若将来真起 M7，需要一并泛化。
4. **v0.1.1 的 Release 附件命名不符门禁契约**：`v0.1.1` 挂的是 `SHA256SUMS.txt`，而
   `SUMS_FILE = "SHA256SUMS"`。本轮不动已发布物（`v0.1.2` 用无扩展名对齐）。
5. **传染范围聚合（D36）** 仍是明文登记的未做项。

## 三、既定口径清单（动了会打挂测试的，本轮相关部分）

- **报告里打印的「工具版本」必须等于产出它的版本**：`examples/report/*.md` 逐字节锁定，
  因此**每次抬版本号都要重生成这两份 MD**（`tests/test_report.py::test_example_reports_are_reproducible`）。
  这不是缺陷，见 `plan/06` §五。
- **`addopts = "-q"`**：命令行再叠 `-q` 会变 `-qq` 吞掉汇总行；要计数就写 `-o addopts=`。
- **报告层零判定（D13 / K23）**：`report` 只读四份产物；三条 AST 守门（不 import 判定模块 /
  无算术拼接 / 无内联判定表）在 `tests/test_report.py` 里。
- **退出码语义**：`assess` / `report` 有阻断级或待确认项 → `1`（既定语义，不是故障）；
  用法错误 `2`；规则包缺失/校验失败 `3`；`bench --only m6` 刻意 `2`。
- **`-only` / `-or-later` 原样保留**（D7）；**显式 `--rules-dir` 无效不回退**（D21）。
- **发布留档只写已发生的事实**，两栏（tag 时点 / tag 后追加）；tag 之后只允许追加类提交
  （`plan/RELEASE-M6.md` §一 的口径，`v0.1.2` 沿用）。
- **产物不能登记自身的 sha256**：`plan/*.md` 与 `CHANGELOG.md` 都随 sdist 分发，权威校验和
  放 §二 与 Release 附件 `SHA256SUMS`；随包分发的那份是登记之前的版本（刻意，不是遗漏）。

## 四、本机环境坑（本轮踩到 / 复用的）

- **本机解释器**：只有 `py -3.8` 与 `py -3.12`（`py -0p` 可查）；`python` 指向 Store stub，
  跑工具链一律 `py -3.12 -X utf8`。
- **`pip` / `build` 必须走代理**：`export HTTPS_PROXY=http://127.0.0.1:7897
  HTTP_PROXY=http://127.0.0.1:7897`，否则隔离构建（`python -m build` 要装 `setuptools>=77`）会挂；
  pip 索引已配置为清华镜像（`pip config list` 可见）。
- **`setuptools>=77` 与 Python 3.8 不可兼得**：3.8 可装的最新 setuptools 是 **75.3.0**
  （75.4.0 起 `requires_python >= 3.9`）。在 3.8 + 75.3.0 下 `license = "MIT"` 直接
  `ValueError: invalid pyproject.toml config`。这就是 floor 必须抬到 ≥3.9 的原因（本仓取 3.12）。
- **构建到临时目录再拷进 `dist/`**：`python -m build --outdir <tmp>` 避免在仓库里堆中间产物
  （`dist/`、`out/`、`build/`、`*.egg-info` 都已在 `.gitignore` 里）。
- **`git push` 走 SSH**：`origin` 是 `git@github.com:...`（本机到 `github.com:443` 的 HTTPS
  推流不稳）；`gh` 已登录（`repo` / `read:org` / `gist` / `user`）。
- **`gh release create` 的附件名要与门禁契约一致**：`SUMS_FILE = "SHA256SUMS"`（无扩展名）。
- **`update/` 必须不入库**：它是「诊断对话」的交接目录，里面会写本机绝对路径；
  已加进 `.gitignore`，提交时用显式路径 `git add`，不要 `git add -A`。

## 五、DoD 逐项 checklist（v0.1.2）

- [x] 全量测试：本机 3.12 **457 passed**；干净 clone（tag 本体）**457 passed**
- [x] `licaudit status` / `selftest` / `selftest --core` / `verify-data` / `bench` 全 rc=0
- [x] 七个生成器 `--check` 7 × rc=0（冻结数据位级一致）
- [x] `python -m build` 零 `SetuptoolsDeprecationWarning`
- [x] wheel 自带 `references/`（65）与 `data/`（39）；装态 `status` / `selftest` rc=0
- [x] 示例报告可逐字节复现（CSV 不变、MD 只差版本行）
- [x] 脱敏自查：本轮改动文件零命中；`update/` 不再进扫描面
- [x] 留档先于 tag 入库（`plan/RELEASE-v0.1.2.md` §一）
- [x] tag `v0.1.2` + Release（3 附件，latest）+ 附件真下载 sha256 三方对撞
- [x] 远端 CI 两次 run 全绿（含 tag 推送那次）
- [x] `tools/check_release.py --artifacts-dir dist --online` rc=0
- [x] 回写 `plan/00` §三/§五、`plan/05` §二之九/§二之十、`plan/06` §五
- [x] 本文件（`plan/HANDOFF-v0.1.2.md`）
- [ ] PyPI 上传 `0.1.2`（**未授权，未做**）

## 六、关键命令速查

```bash
# 环境（Windows / Git Bash）
export HTTPS_PROXY=http://127.0.0.1:7897 HTTP_PROXY=http://127.0.0.1:7897

# 全量测试（本机两通道）
py -3.12 -X utf8 -m pytest -o addopts= -q
py -3.8  -X utf8 -m pytest -o addopts= -q

# 交付态入口与基准
py -3.12 -X utf8 -m licaudit status
py -3.12 -X utf8 -m licaudit selftest --core
py -3.12 -X utf8 -m licaudit verify-data
py -3.12 -X utf8 -m licaudit bench

# 生成物自检（改 curated 表之后必跑）
py -3.12 -X utf8 tools/fetch_spdx.py --check --out references/spdx
py -3.12 -X utf8 tools/gen_ruleset.py --check
py -3.12 -X utf8 tools/gen_synthetic.py --check
py -3.12 -X utf8 tools/gen_profile_truth.py --check
py -3.12 -X utf8 tools/gen_scenario_truth.py --check
py -3.12 -X utf8 tools/gen_conflict_truth.py --check
py -3.12 -X utf8 tools/gen_action_truth.py --check

# 脱敏自查（public 硬门）
py -3.12 -X utf8 tools/_scan_desensitize.py

# 发布留档 / 发布终态门
py -3.12 -X utf8 tools/check_release.py                                  # 离线
py -3.12 -X utf8 tools/check_release.py --artifacts-dir dist             # 离线 + 本地产物
py -3.12 -X utf8 tools/check_release.py --artifacts-dir dist --online    # 含远端

# 构建与打包核验
py -3.12 -m build --outdir "$TEMP/b"

# 示例报告重生成（**抬版本号之后必做**，两份运行）
M="data/synthetic/example-project/package.json data/synthetic/example-project/package-lock.json data/synthetic/example-project/requirements.txt data/synthetic/example-project/pyproject.toml data/synthetic/example-project/go.mod data/synthetic/example-project/pom.xml"
py -3.12 -X utf8 -m licaudit scan $M --out-dir out/license-report
py -3.12 -X utf8 -m licaudit assess --inventory out/license-report/inventory.json --scenario saas \
  --network-interaction yes --outbound-license Elastic-2.0 \
  --scenario-note "示例项目以 SaaS 形式对外提供服务" --out-dir out/license-report
py -3.12 -X utf8 -m licaudit report --out-dir out/license-report --format md
py -3.12 -X utf8 -m licaudit report --out-dir out/license-report --format csv
# （第二份运行：--scenario distribute-binary --outbound-license MIT，无 --network-interaction，
#   note 用「示例项目分发二进制产物」；产物名 license-report-distribute.*）
# 与 tests/test_report.py 的 EXAMPLE_RUNS 完全一致，参数错一个字符就会逐字节比对失败。

# 远端
gh run list --repo yuluo554/10-17-license-compliance-skill --limit 5
gh release view v0.1.2 --repo yuluo554/10-17-license-compliance-skill --json assets
```