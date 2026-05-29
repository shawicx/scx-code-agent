# Tools

本项目不使用 LangChain Tool、MCP、RAG、Browser 或 Code Executor。

所有"工具"是 Python 函数直接调用。

## LLMClient

| 属性 | 值 |
|------|-----|
| 文件 | `llm_client.py` |
| 用途 | 封装 LLM 调用，处理重试、JSON 解析、验证 |
| 调用来源 | 3 个 expert 节点 |
| 重试 | 3 次，指数退避（2s-10s），仅对网络/超时错误重试 |

### 核心方法

| 方法 | 用途 |
|------|------|
| `review_code()` | 审查单个文件，返回 `[AgentIssue]` |
| `_prepare_code_content()` | diff 模式下裁剪代码到变更行 ± context_lines |
| `_parse_response()` | JSON 提取 + 修复 + Pydantic 验证 |
| `_extract_json()` | 从 Markdown 代码块或混合文本中提取 JSON |
| `_repair_json()` | 修复未闭合字符串等常见 JSON 错误 |

### 成本

每次 `review_code()` 调用 = 1 次 LLM API 请求。

总请求数 = `target_files 数量` × `3（专家数）`

### 延迟

- 单次调用超时：60s（anthropic/openai）、120s（glm）
- 并发上限：15（3 专家 × 5 线程）
- 重试最大等待：2+4+8 = 14s

---

## Git Diff 解析

| 属性 | 值 |
|------|-----|
| 文件 | `git_utils.py` |
| 用途 | 解析 `git diff` 输出，提取变更文件和行号 |
| 调用来源 | `coordinator_node`（diff 模式） |
| 安全风险 | 低（分支名已校验不以 `-` 开头） |

### 函数

| 函数 | 用途 |
|------|------|
| `get_diff_files(branch)` | 执行 `git diff`，解析变更文件列表 |
| `filter_code_files(files)` | 按扩展名和目录过滤 |

---

## GitHub Client

| 属性 | 值 |
|------|-----|
| 文件 | `github_client.py` |
| 用途 | PR 评论发布 |
| 调用来源 | `cli.py`（`--pr-comment` 选项） |

### 函数

| 函数 | 用途 |
|------|------|
| `get_current_pr()` | 获取当前分支关联的 PR 编号 |
| `post_pr_comment()` | 在 PR 发表评论 |
| `format_pr_summary()` | 格式化问题为 PR 评论摘要 |
| `detect_repo_info()` | 自动检测仓库信息 |

### 权限风险

需要 `GITHUB_TOKEN` 有 repo 写权限。

---

## 报告格式化器

| 属性 | 值 |
|------|-----|
| 文件 | `formatter.py` |
| 用途 | 将 `AgentIssue` 列表格式化为 Markdown 或 JSON |

### 类

| 类 | 输出 |
|-----|------|
| `MarkdownFormatter` | Markdown 报告（按级别分组） |
| `JSONFormatter` | JSON 报告（含 summary 统计） |

---

## 高成本 Tool

| Tool | 成本原因 |
|------|----------|
| `LLMClient.review_code()` | 每文件 × 3 专家 = N × 3 次 API 调用 |

## 高延迟 Tool

| Tool | 延迟原因 |
|------|----------|
| `LLMClient.review_code()` | LLM 响应时间 + 重试 |

## 不稳定 Tool

| Tool | 不稳定原因 |
|------|-----------|
| `LLMClient._parse_response()` | 依赖 LLM 返回合法 JSON，需修复逻辑兜底 |
| `git_utils.get_diff_files()` | 依赖正则解析 git diff 输出格式 |
