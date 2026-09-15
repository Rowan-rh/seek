# Tasks: fix-harness-readiness-followup

## 1. 错误路径修复

- [x] 1.1 `_check_version_change` 捕获版本目录和文件读写的 `OSError`，stderr 提示后继续执行
- [x] 1.2 `error_log.log_error` 写入失败时增加 stderr 降级提示
- [x] 1.3 补充不可写 `SEEK_HOME` 的 CLI 与单元测试

## 2. 文案与版本

- [x] 2.1 统一 capabilities/parser 中剩余的 `~/.seek` 路径文案
- [x] 2.2 升级补丁版本、同步 Skill 版本声明和 CHANGELOG

## 3. 验证与集成

- [x] 3.1 运行全量测试、Harness eval、OpenSpec strict 和 PR 检查
- [x] 3.2 归档 OpenSpec change、提交修复分支并合入 develop
