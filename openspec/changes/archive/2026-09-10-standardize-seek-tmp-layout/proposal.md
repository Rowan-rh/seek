# Proposal: standardize-seek-tmp-layout

## Why

仓库级分析、评审、调试和媒体生成会产生报告、日志、截图及中间数据；缺少统一约束时，这些临时产物会平铺在仓库根目录或集中堆放在单一临时目录中，难以判断归属、阶段和是否可清理。需要把一次任务的临时产物作为独立运行单元管理，并让 Agent 和开发脚本使用同一套可验证的目录与命名规则。

## What Changes

- 新增仓库临时工作区规范，统一使用 `.seek-tmp/runs/YYYY-MM-DD/<run-id>/`，禁止直接向 `.seek-tmp` 根目录写入临时文件。
- 每个运行目录固定包含 `inputs/`、`work/`、`outputs/`、`logs/` 和 `manifest.json`，以任务为单位隔离产物。
- 新增仓库级 helper，用固定规则创建运行目录并输出机器可读结果，避免每个 Agent 自行拼接路径。
- 在 `AGENT.md` 和根 README 中明确临时产物、正式交付物、缓存及原子写临时文件的边界。
- 将 `.seek-tmp/` 纳入 Git 忽略规则，并新增一致性测试防止目录规范和工具实现漂移。

## Capabilities

### New Capabilities

- `repository-temporary-workspace`: 定义仓库内 Agent/开发任务临时产物的隔离目录、命名、元数据和边界规则。

### Modified Capabilities

无。

## Impact

影响仓库开发工作流、`AGENT.md`、根 README、`.gitignore`、仓库级临时目录 helper 及其测试；不改变 seek CLI 的用户命令、JSON API、`SEEK_HOME` 运行时状态布局或原子写实现。
