# Tasks: fix-agent-evaluation-validation

## 1. 输入校验
- [x] 1.1 校验 defaults.expected 与 scenario.expected
- [x] 1.2 校验三层 expected 子字段类型
- [x] 1.3 保证独立 runner 意外错误仍输出 JSON

## 2. Live 隔离与指标
- [x] 2.1 live payload 使用执行字段白名单并剥离评分标准
- [x] 2.2 增加 scenario_failure_rate 与 violations_per_scenario
- [x] 2.3 保留并标记旧指标兼容别名

## 3. 验证
- [x] 3.1 增加 CR 复现与回归测试
- [x] 3.2 更新版本和文档
- [x] 3.3 全量验证、归档、提交并合入 develop
