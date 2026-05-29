# Memory

## 结论

**本项目无 Memory 机制。**

## 详细分析

| 类型 | 是否存在 |
|------|----------|
| Short-term memory | 无 |
| Long-term memory | 无 |
| Vector memory | 无 |
| Checkpoint | 无 |
| Conversation memory | 无 |
| Session state | 无 |

## State 生命周期

State 只在单次 `graph.invoke()` 调用期间存在：

```
graph.invoke(initial_state) → result → 结束
```

无持久化，无跨会话记忆。

## raw_comments 累加机制

`SharedReviewState.raw_comments` 使用 `Annotated[List[AgentIssue], operator.add]`。

LangGraph 在多个节点返回 `{"raw_comments": issues}` 时自动 `operator.add`（列表拼接）。

这不是 memory，只是 State 的合并策略。

## 配置缓存

`load_prompt()` 使用 `@lru_cache(maxsize=8)` 缓存 prompt 文件内容。

`detect_repo_info()` 使用模块级字典 `_repo_info_cache` 缓存仓库信息。

这些是性能优化，非 Agent memory。

## Token 膨胀风险

**不存在**。每次 LLM 调用是独立的，不累积 context。

每个文件每次调用发送的消息：

```
[SystemMessage(base_prompt + role_prompt), HumanMessage(code)]
```

消息长度 = prompt 长度 + 文件内容长度。不随审查轮次增长。

## Memory 污染风险

**不存在**。无持久化 state。

## Checkpoint 恢复

**不支持**。`graph.compile()` 未配置 checkpointer。

审查中途失败需重新运行整个 Graph。
