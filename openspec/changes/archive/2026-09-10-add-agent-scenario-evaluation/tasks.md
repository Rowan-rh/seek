# Tasks: add-agent-scenario-evaluation

## 1. 评测核心
- [x] 1.1 定义版本化场景和 Agent 结果 Schema 校验
- [x] 1.2 实现 protocol、trajectory、report 三层评分与稳定违规码
- [x] 1.3 实现 replay 与外部命令 live runner

## 2. 场景与入口
- [x] 2.1 增加 20～30 个脱敏基线场景
- [x] 2.2 增加独立 runner、CLI 能力声明和 JSON 汇总指标
- [x] 2.3 将 replay 评测接入 run_checks.sh

## 3. 验证与交付
- [x] 3.1 增加通过、违规、非法输出、live runner 单测
- [x] 3.2 更新 Harness 文档和版本声明
- [x] 3.3 全量验证、归档、提交并合入 develop
