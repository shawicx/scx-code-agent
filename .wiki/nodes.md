# Nodes

## coordinator

| 属性 | 值 |
|------|-----|
| 文件 | `agent/nodes/coordinator.py` |
| 函数 | `coordinator_node(state)` |
| 角色 | 文件收集器 |
| 核心程度 | **最高** — 所有节点的输入来源 |

**输入 State**: `mode`, `diff_branch`, `target_path`

**输出 State**: `target_files`, 透传其他字段

**逻辑**:
- `mode=all`: 遍历当前目录，收集所有 `SUPPORTED_EXTENSIONS` 文件
- `mode=diff`: 调用 `get_diff_files(branch)` + `filter_code_files`，解析 git diff
- `mode=path`: 单文件或目录扫描

**副作用**: 文件系统读取（`os.walk`, `open`）

**复杂度**: diff 模式下涉及 git diff 解析，逻辑较复杂

**风险**: 无输入校验时 `mode` 异常值导致空列表

---

## sec_expert

| 属性 | 值 |
|------|-----|
| 文件 | `agent/nodes/sec_expert.py` |
| 函数 | `sec_expert_node(state)` |
| 角色 | 安全审查专家 |
| Prompt | `security.md` + `base.md` + custom_rules(security) |

**输入 State**: `target_files`, `mode`

**输出 State**: `{"raw_comments": [AgentIssue]}`（累加）

**调用 Tool**: `LLMClient.review_code()` — 每文件一次 LLM 调用

**并发**: `ThreadPoolExecutor(max_workers=5)`

**category 输出**: `"Security"`

**风险**: 高成本（每个文件一次 LLM 调用）

---

## arch_expert

| 属性 | 值 |
|------|-----|
| 文件 | `agent/nodes/arch_expert.py` |
| 函数 | `arch_expert_node(state)` |
| 角色 | 架构审查专家 |
| Prompt | `architecture.md` + `base.md` + custom_rules(architecture) |

**输入 State**: `target_files`, `mode`

**输出 State**: `{"raw_comments": [AgentIssue]}`（累加）

**调用 Tool**: `LLMClient.review_code()` — 每文件一次 LLM 调用

**并发**: `ThreadPoolExecutor(max_workers=5)`

**category 输出**: `"Architecture"`

**风险**: 高成本（每个文件一次 LLM 调用）

---

## perf_expert

| 属性 | 值 |
|------|-----|
| 文件 | `agent/nodes/perf_expert.py` |
| 函数 | `perf_expert_node(state)` |
| 角色 | 性能审查专家 |
| Prompt | `performance.md` + `base.md` + custom_rules(performance) |

**输入 State**: `target_files`, `mode`

**输出 State**: `{"raw_comments": [AgentIssue]}`（累加）

**调用 Tool**: `LLMClient.review_code()` — 每文件一次 LLM 调用

**并发**: `ThreadPoolExecutor(max_workers=5)`

**category 输出**: `"Performance"`

**风险**: 高成本（每个文件一次 LLM 调用）

---

## reporter

| 属性 | 值 |
|------|-----|
| 文件 | `agent/nodes/reporter.py` |
| 函数 | `reporter_node(state)` |
| 角色 | 报告生成器 |
| 核心程度 | **高** — 最终输出 |

**输入 State**: `raw_comments`, `output_format`

**输出 State**: `final_report`, 透传其他字段

**逻辑**:
1. `deduplicate_issues()` — 同一位置只保留最严重级别，相同级别合并描述
2. 选择格式化器（Markdown / JSON）
3. 格式化输出

**调用 Tool**: `MarkdownFormatter.format()` 或 `JSONFormatter.format()`

**无 LLM 调用**

**Memory**: 无

**风险**: 去重逻辑合并同位置描述可能丢失信息

---

## 核心性排序

1. **coordinator** — 输入源头，所有节点依赖
2. **reporter** — 输出终端，决定报告质量
3. **3 个 expert** — 并行等同，可独立移除/添加

## 复杂度排序

1. **coordinator** — 三种模式分支，diff 解析
2. **reporter** — 去重逻辑
3. **3 个 expert** — 结构相同，逻辑简单

## 容易失控排序

1. **3 个 expert** — LLM 调用数量 = 文件数 × 3，成本不可控
2. **coordinator** — diff 解析依赖正则，边界情况多
3. **reporter** — 去重合并可能改变问题语义
