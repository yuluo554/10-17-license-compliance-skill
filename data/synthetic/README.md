# 合成数据与真值库

> **M1 已生成入仓、M5 扩充**：12 个用例目录，每个含清单文件 + `README.md`（说明覆盖点）。
> 纪律见 `plan/04-数据计划.md`：真值只存输入与期望，观测由运行时实算。

## 目录（M1 已就位）

```
data/
  synthetic/
    npm-basic/package.json
    npm-lock-v2/package-lock.json
    npm-lock-v3/package-lock.json
    pip-requirements/requirements.txt
    pyproject-pep621/pyproject.toml
    pyproject-poetry/pyproject.toml
    go-mod/go.mod
    maven-pom/pom.xml
    expr-complex/package.json
    unknown-and-missing/package.json
    known-traps/            # pandas / psycopg2 / PyMySQL / PyQt5（允许真实包名）
    example-project/        # 示例报告输入
  truth/
    truth.json              # M1：解析真值
    profile.json            # M2
    scenario.json           # M3
    conflicts.json          # M4
    actions.json            # M5
```

## 生成

```bash
py -3.12 -X utf8 tools/gen_synthetic.py --out data
py -3.12 -X utf8 tools/gen_synthetic.py --check
```

- 固定 seed、自研确定性 RNG（splitmix64）、无时钟、无集合迭代序。
- 生成后整目录入仓，禁手改；改生成器 → 整目录重生成并提交。
- `--check` 两层：冻结产物形态正确 + 重生成逐字节一致。

## 包名白名单

- 普通用例：`example-pkg-<小写字母>`。
- 真实包名只允许出现在 `synthetic/known-traps/`，且**不进示例报告**。

## 真值纪律

- 只存输入与期望（`id` / `inputs` / `expect`）；出现 `observed_*` 字段即测试红。
- 期望值由生成器内的独立朴素 oracle 计算，不调用生产解析器。
- 人工核对项（坑位用例）挂 `checked_on`，不得用解析器输出回填。

## M1 实测（2026-10-17）

| 用例 | 覆盖点 |
| --- | --- |
| `npm-basic` | 字符串 license / 对象 license / `licenses` 数组 / 缺失字段 |
| `npm-lock-v2` / `npm-lock-v3` | `packages` 映射；根包（键 `""`）跳过 |
| `pip-requirements` | `==` 版本、extras、注释、`-r` 行；无版本 → `*` |
| `pyproject-pep621` | `[project]` 依赖 + optional-dependencies；classifier 走 trove 链 |
| `pyproject-poetry` | `[tool.poetry.dependencies]`；`python` 约束不是依赖 |
| `go-mod` | require 块 + 单行 require；`// license:` 注记 |
| `maven-pom` | 项目 `<licenses>` 不传给依赖；依赖级 `<license>` 生效 |
| `expr-complex` | `OR` / `AND` / `WITH`（已知与未知例外）/ 括号 |
| `unknown-and-missing` | 族名 → `<族>-unknown`；缺 license → 兜底；自由文本不被猜 |
| `known-traps` | pandas / psycopg2 / PyMySQL / PyQt5（真实包名，不进示例报告） |
| `example-project` | **M5 示例项目**：六种清单形态（package.json / package-lock.json / requirements.txt / pyproject.toml / go.mod / pom.xml），15 个依赖，全合成包名；`examples/report/` 的输入 |

共 12 用例 / 59 条真值期望（M5 新增 `example-project` 的 15 条）。
`py -3.12 tools/gen_synthetic.py --check` 通过。
