# 合成数据与真值库

> 本目录在 **M1** 起存放程序化生成的合成依赖清单与真值。M0 骨架阶段只有本说明。
> 纪律见 `plan/04-数据计划.md`：真值只存输入与期望，观测由运行时实算。

## 目录（M1 起）

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

## 说明

本文件在 M1 之前保持现状；M1 完成后由 `plan/04` 的启动清单驱动填充。
