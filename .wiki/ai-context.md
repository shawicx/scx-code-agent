# AI Context

最小 token 理解整个 Agent 系统。

## Graph 结构

```
coordinator → [sec_expert, arch_expert, perf_expert] → reporter → END
```

3 专家并发，fan-out/fan-in 模式。DAG，无循环，无条件边。

## State

```python
SharedReviewState:
    mode: str              # all | diff | path
    target_files: List     # coordinator 填充
    raw_comments: List     # 3 专家累加 (operator.add)
    final_report: str      # reporter 填充
    diff_branch: str       # diff 模式基准分支
    target_path: str       # path 模式目标路径
    output_format: str     # markdown | json

AgentIssue:
    file_path: str
    line_number: int
    category: str          # Security | Architecture | Performance
    level: str             # Blocker | Warning | Info
    description: str
    suggestion: str
```

## Node 职责

| Node | 职责 | LLM 调用 |
|------|------|----------|
| coordinator | 扫描/收集代码文件 | 无 |
| sec_expert | 安全审查 | 有（并发5线程） |
| arch_expert | 架构审查 | 有（并发5线程） |
| perf_expert | 性能审查 | 有（并发5线程） |
| reporter | 去重+格式化报告 | 无 |

## Tool 映射

无外部 Tool。每个 expert 调用 `LLMClient.review_code(file)` 一次。

## Prompt 体系

```
system_message = base.md + role_prompt
user_message = "请审查以下代码文件：{path}\n```{lang}\n{code}\n```"
```

| Prompt | 角色 |
|--------|------|
| base.md | 输出格式约束（JSON 数组） |
| security.md | 安全专家 |
| architecture.md | 架构专家 |
| performance.md | 性能专家 |

## LLM 调用链

```
expert_node(state)
  → LLMClient()
  → load_prompt(role)
  → ThreadPoolExecutor(5): client.review_code(file)
      → _prepare_code_content(diff_lines)
      → chat_model.invoke([SystemMessage, HumanMessage])
      → _parse_response() → _extract_json() → _repair_json() → Pydantic 验证
  → {"raw_comments": issues}
```

## 重试

LLM 层：3 次，指数退避 2-10s，仅网络/超时错误。
Graph 层：无重试。

## 输出

Markdown 或 JSON 报告，可选 PR 评论。

## 关键注意

- 成本 = 文件数 × 3 次 LLM 调用
- 最大并发 15（3×5）
- JSON 解析依赖 `_repair_json()` 兜底
- diff 模式行号映射可能不准确
- 无 memory、无 checkpoint、无 human-in-the-loop
- 支持 anthropic/openai/deepseek/glm 四个 provider
