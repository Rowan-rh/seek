# Delta: chain-session-persistence

## Purpose

定义 chain 会话状态文件（~/.seek/sessions/{session_id}.json）的写原子性规范：所有变更会话状态的引擎入口 MUST 在文件锁的保护下完成完整的「读-改-写」周期，防止并发 CLI 进程操作同一会话时丢失更新。

## ADDED Requirements

### Requirement: 会话写入口的读-改-写原子性
`complete_step`、`amend_step`、`provide_inputs` 等变更会话状态的引擎入口 SHALL 在该会话的文件锁（`{session_id}.lock`）内完成读取、修改与写入全流程；锁内 MUST NOT 再调用会获取同一把锁的写入路径（flock 以 open file description 为持有单位，同进程新 fd 二次排他会死锁）。`start_session` 等无外部锁调用方 SHALL 使用自带锁的保存入口。

#### Scenario: 并发补注入不丢键
- **WHEN** 多个进程/线程并发对同一会话 `provide_inputs` 注入不同的键
- **THEN** 所有键都出现在最终落盘的会话 context 中，无相互覆盖

#### Scenario: 并发完成步骤不丢记录
- **WHEN** 两个进程同时尝试对同一会话完成步骤
- **THEN** 两次操作串行化执行，completed_steps 不丢失其中任何一次的记录

### Requirement: 原子写入与降级保护
会话文件写入 SHALL 采用 mkstemp → write → fsync → os.replace 原子替换；写入异常 MUST 清理临时文件并上抛。锁在 fcntl 不可用的平台上 SHALL 降级为无锁（行为与现状一致），锁文件路径 MUST 保持 `{session_id}.lock` 以兼容新旧版本进程互斥。

#### Scenario: 写入中断不损坏既有文件
- **WHEN** 会话文件写入过程中断
- **THEN** 磁盘上保留写入前的完整会话文件（或原子替换后的新文件），不存在半写状态
