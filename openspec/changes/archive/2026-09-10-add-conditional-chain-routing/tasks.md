# Tasks: add-conditional-chain-routing

## 1. 引擎
- [x] 1.1 校验 when 与 skipOutputs 配置
- [x] 1.2 实现安全条件求值和连续自动跳过
- [x] 1.3 调整前置步骤与 requiredInputs 对 skipped 输出的识别
- [x] 1.4 保持旧 session 线性兼容

## 2. 链路与接口
- [x] 2.1 改造 alert-ticket 无相似工单分支
- [x] 2.2 status/context/complete 暴露 skipped_steps
- [x] 2.3 更新 Skill、capabilities、文档和版本

## 3. 验证
- [x] 3.1 增加条件命中、跳过、默认输出、配置错误与旧会话测试
- [x] 3.2 增加 Harness 黑盒分支场景并运行全量检查
- [x] 3.3 归档 OpenSpec、提交并合入 develop
