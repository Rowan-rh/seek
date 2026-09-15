# Evidence 契约

需要外部取证的 Chain 步骤必须提交：

```json
{
  "status": "FOUND",
  "sources": [
    {"tool": "provider logs query", "reference": "query-id-or-document-link"}
  ],
  "boundary": "覆盖的时间窗口、资源范围和权限边界"
}
```

支持的状态：

- `FOUND`：找到支持结论的证据。
- `NO_DATA`：查询已执行但没有结果；必须说明查询范围。
- `NOT_APPLICABLE`：该来源不适用于当前问题；必须说明原因。
- `TOOL_ERROR`：工具调用失败；必须说明错误和恢复路径。

证据只能支撑其来源和边界内的结论。报告应把观测事实、推断、反证和未决事项分开记录。
