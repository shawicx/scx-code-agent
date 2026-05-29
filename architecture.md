## 1. 项目目录结构 (Directory Tree)

请让 Claude Code 按照以下结构在本地初始化项目。该结构完全解耦了 **CLI 输入层**、**Git 数据层**和 **LangGraph 多智能体内核**。

Plaintext

```
scx-code-agent/                # 项目根目录
├── pyproject.toml              # 依赖管理 (Poetry / Pipenv)
├── README.md                   # 项目使用说明
├── __init__.py
├── cli.py                      # CLI 入口 (Typer 框架)
├── git_utils.py                # Git 差异与行号捞取逻辑 (GitPython)
├── config.py                   # 环境变量与 LLM 客户端配置
└── agent/
    ├── __init__.py
    ├── state.py                # LangGraph 全局状态定义 (TypedDict)
    ├── graph.py                # LangGraph 拓扑图编排
    └── nodes/
        ├── __init__.py
        ├── coordinator.py      # 协调者 Node (分发/输入剪裁)
        ├── sec_expert.py       # 安全专家 Node (LLM)
        ├── arch_expert.py      # 架构专家 Node (LLM)
        ├── perf_expert.py      # 性能专家 Node (LLM)
        └── reporter.py         # 报告官 Node (去重/分发输出)
```

## 2. LangGraph 多智能体拓扑状态图

本系统的多智能体协同采用 **并行专家组模式 (Parallel Workers Pattern)** 。由协调者切分代码后，三位专家并行审查，最后由报告官收敛。

```
[CLI / CI Trigger] 
       │
       ▼
┌──────────────┐
│ coordinator  │ (根据全量/增量参数，清洗代码并塞入 State)
└──────┬───────┘
       │
       ├───────────────────────────────┼───────────────────────────────┐
       ▼                               ▼                               ▼
┌──────────────┐                ┌──────────────┐                ┌──────────────┐
│  sec_expert  │                │ arch_expert  │                │ perf_expert  │
│ (安全审查专家)│                │ (架构复用专家)│                │ (性能安全专家)│
└──────┬───────┘                └──────┬───────┘                └──────┬───────┘
       │                               │                               │
       └───────────────────────────────┼───────────────────────────────┘
                                       ▼ (并行结束，状态自动 Merge)
                               ┌──────────────┐
                               │   reporter   │ (去重、定级、格式化输出)
                               └──────┬───────┘
                                       │
                                       ▼
                       [Terminal Rich / GitHub PR JSON]
```

## 3. 核心代码设计图纸 (Blueprint)

以下是系统最核心的三个代码模块定义。Claude Code 可以直接以此为骨架填充业务逻辑。

### A. 全局状态定义 (`agent/state.py`)

利用 Python 的 `TypedDict` 和 `Annotated` 实现状态的并行追加（Using `operator.add`）。

Python

```
from typing import List, TypedDict, Annotated
import operator

class AgentIssue(TypedDict):
    file_path: str
    line_number: int  # 若为全量则是绝对行号，若为 PR 则是 Diff 行号
    category: str     # "Security" | "Architecture" | "Performance"
    level: str        # "Blocker" | "Warning" | "Info"
    description: str  # 问题描述
    suggestion: str   # 修复建议与 Diff 代码段

class SharedReviewState(TypedDict):
    # 【输入数据】
    mode: str         # "all" (全量大检) 或 "diff" (PR 增量)
    target_files: List[dict]  # [{"path": "src/main.ts", "content": "...", "diff_lines": [...]}]
    
    # 【中间数据】使用 operator.add 让并行 Agent 的结果自动叠加
    raw_comments: Annotated[List[AgentIssue], operator.add]
    
    # 【最终输出】
    final_report: str # Markdown 格式的最终报告
```

### B. 拓扑图编排核心 (`agent/graph.py`)

使用原生 LangGraph 声明并行路由和无缝等待。

Python

```
from langgraph.graph import StateGraph, END
from agent.state import SharedReviewState
from agent.nodes.coordinator import coordinator_node
from .agent.nodes.sec_expert import sec_expert_node
from .agent.nodes.arch_expert import arch_expert_node
from .agent.nodes.perf_expert import perf_expert_node
from .agent.nodes.reporter import reporter_node

def create_review_graph():
    workflow = StateGraph(SharedReviewState)
    
    # 1. 注册所有节点
    workflow.add_node("coordinator", coordinator_node)
    workflow.add_node("sec_expert", sec_expert_node)
    workflow.add_node("arch_expert", arch_expert_node)
    workflow.add_node("perf_expert", perf_expert_node)
    workflow.add_node("reporter", reporter_node)
    
    # 2. 确立主线流程
    workflow.set_entry_point("coordinator")
    
    # 3. 编排 1 对多 并行分支 (Fan-out)
    workflow.add_edge("coordinator", "sec_expert")
    workflow.add_edge("coordinator", "arch_expert")
    workflow.add_edge("coordinator", "perf_expert")
    
    # 4. 汇聚到报告官 (Fan-in) -> LangGraph 会自动等待以上三个节点全部执行完毕
    workflow.add_edge("sec_expert", "reporter")
    workflow.add_edge("arch_expert", "reporter")
    workflow.add_edge("perf_expert", "reporter")
    
    workflow.add_edge("reporter", END)
    
    return workflow.compile()
```

### C. 专家节点 Prompt 隔离原则 (`agent/nodes/*`)

在让 Claude Code 编写具体的专家 Node 时，必须为其设定严苛的 **JSON 约束**，防止模型输出废话破坏 Python 数据解析：

Python

```
# 每个专家 Node 的 System Prompt 基调：
EXPERT_SYSTEM_PROMPT = """
你是一名专门负责【{role_name}】的代码审计专家。
请严格审视用户给出的代码片段，只指出属于你职责范围内的缺陷。

【强制输出格式】
你必须返回一个标准的 JSON 数组，严禁包含任何 Markdown 语法外壳（如 ```json）。格式如下：
[
  {{
    "file_path": "文件的相对路径",
    "line_number": 整数行号,
    "category": "{role_name}",
    "level": "Blocker 或 Warning 或 Info",
    "description": "缺陷原因",
    "suggestion": "重构后的改进代码段"
  }}
]
如果未发现任何相关缺陷，直接返回空数组 []。
"""
```

## 4. CLI 交互与环境隔离设计

### 命令设计

- **场景一（主动大检）：**  `code-cop audit --all`

  - 扫描项目全量代码，通过 `reporter` 节点输出到本地文件：`dist/audit_report.md`。
- **场景二（CI/CD PR审查）：**  `code-cop audit --diff origin/main`

  - 通过 `git_utils.py` 获取增量行号，通过 `reporter` 节点直接消费结构化 JSON，调用 GitHub Check API 贴回 PR 页面。

### 依赖配置项 (`pyproject.toml`)

让 Claude Code 优先锁定以下基础依赖包：

Ini, TOML

```
[tool.poetry.dependencies]
python = "^3.11"
langgraph = "^0.0.15"  # 核心图编排
langchain-core = "*"   # 提示词抽象
langchain-openai = "*" # 用于对接 OpenAI / DeepSeek 等 API
typer = {extras = ["rich"], version = "^0.12.0"} # 炫酷命令行
gitpython = "^3.1.43"  # 本地 Git 差异抓取
requests = "^2.31.0"   # GitHub API 交互
```
