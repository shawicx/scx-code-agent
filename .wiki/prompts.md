# Prompts

## Prompt 体系

每个 expert 节点使用两个 prompt 拼接：

```
system_message = base_prompt + "\n\n" + role_prompt
```

## Prompt 列表

### base.md — 输出格式规范

| 属性 | 值 |
|------|-----|
| 文件 | `prompts/base.md` |
| 作用 | 约束 LLM 输出为合法 JSON 数组 |
| 使用者 | 所有 3 个 expert 节点 |
| 关键性 | **最高** — 直接决定解析成功率 |

**核心约束**:
- 只返回 JSON 数组，禁止 Markdown 代码块
- `line_number` 从 1 开始
- `level` 只能是 Blocker / Warning / Info
- 空结果返回 `[]`

**风险**: LLM 仍可能返回 Markdown 代码块或非 JSON 文本，需要 `_parse_response()` 兜底

---

### architecture.md — 架构专家 Prompt

| 属性 | 值 |
|------|-----|
| 文件 | `prompts/architecture.md` |
| 作用 | 定义架构审查角色和审查重点 |
| 使用者 | `arch_expert_node` |
| category | `"Architecture"` |

**审查重点**: 代码结构、设计模式、耦合度、可扩展性、命名规范、注释文档

---

### security.md — 安全专家 Prompt

| 属性 | 值 |
|------|-----|
| 文件 | `prompts/security.md` |
| 作用 | 定义安全审查角色和审查重点 |
| 使用者 | `sec_expert_node` |
| category | `"Security"` |

**审查重点**: 注入漏洞、认证授权、数据保护、输入验证、加密问题、依赖安全

---

### performance.md — 性能专家 Prompt

| 属性 | 值 |
|------|-----|
| 文件 | `prompts/performance.md` |
| 作用 | 定义性能审查角色和审查重点 |
| 使用者 | `perf_expert_node` |
| category | `"Performance"` |

**审查重点**: 算法复杂度、数据库操作、资源管理、并发问题、缓存策略、I/O 操作

---

## Prompt 输入来源

| Prompt | 输入 |
|--------|------|
| base.md | 静态文本 |
| architecture.md | 静态文本 |
| security.md | 静态文本 |
| performance.md | 静态文本 |

User Message 动态拼接：

```
请审查以下代码文件：{file_path}

```{lang}
{code_content}
```

[diff 模式] 重点关注以下行号附近的代码：{focus_lines}
```

## Prompt 输出格式

所有 prompt 约束输出为 JSON 数组：

```json
[
  {
    "file_path": "example.py",
    "line_number": 10,
    "category": "Security",
    "level": "Warning",
    "description": "...",
    "suggestion": "..."
  }
]
```

经 Pydantic `IssueModel` 验证后转为 `AgentIssue`。

## 关键 Prompt

**base.md** — 最关键，决定 LLM 输出是否能被正确解析。如果 LLM 不遵守格式约束，整个审查流程失败。

## 会影响 Agent 行为的 Prompt

所有 4 个 prompt 都影响 Agent 行为：
- `base.md` 影响输出格式可靠性
- 3 个 role prompt 影响审查维度和深度
