# Tasks: add-chain-evidence-and-token-telemetry

## 1. 证据 Schema
- [x] 1.1 实现 evidence 校验与错误类型
- [x] 1.2 complete/amend 支持 evidence 持久化和当前视图
- [x] 1.3 内置链路查询步骤声明 evidenceRequired 并同步镜像

## 2. Token 统计
- [x] 2.1 complete 支持可选 token usage 校验与持久化
- [x] 2.2 实现会话 token 汇总和 `chain usage` 命令
- [x] 2.3 明确 token 仅统计、不参与评分或流程判断

## 3. 契约与验证
- [x] 3.1 更新 parser、capabilities、Skill、命令文档和 CHANGELOG
- [x] 3.2 增加单测及 Harness 黑盒场景
- [x] 3.3 运行全量检查、归档 OpenSpec、提交并合入 develop
