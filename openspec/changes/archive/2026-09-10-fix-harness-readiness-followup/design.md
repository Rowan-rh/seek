# Design: fix-harness-readiness-followup

## Context

`_check_version_change()` 位于命令函数调用之前，其目录创建和版本文件读写未捕获 `OSError`。当 seek home 不可写时，`harness check` 尚未执行即崩溃。错误日志虽然已降级为 best-effort，但当前静默吞掉写入错误。

## Goals / Non-Goals

**Goals:** 保证版本提示和诊断日志永远不覆盖原始命令结果；真实覆盖不可写 seek home；统一用户可见路径文案。

**Non-Goals:** 不改变 readiness 的检查分级，不实现自动修复目录权限，不改变默认目录。

## Decisions

- `_check_version_change()` 整体捕获 `OSError`，向 stderr 输出单行提示后返回。
- `error_log.log_error()` 捕获 `OSError` 后也写 stderr；stdout 保持纯 JSON。
- 黑盒用例使用一个普通文件作为 `SEEK_HOME`，稳定触发 `mkdir` 的 `FileExistsError`，避免依赖 root 用户或 chmod 语义。
- 文案统一使用 `${SEEK_HOME:-~/.seek}`，明确环境变量覆盖关系。

## Risks / Trade-offs

- stderr 会多一条降级提示 → 仅异常路径出现，不影响 stdout 协议。
- 文件形式的 `SEEK_HOME` 不是最常见故障 → 可跨平台稳定模拟不可创建目录，覆盖同一 OSError 控制流。
