# SCX Code Agent Wiki

## 项目作用

多智能体代码审查系统。通过 LangGraph 构建 3 个专家 Agent 并发审查代码，生成结构化审查报告。

## 技术栈

| 组件 | 技术 |
|------|------|
| Agent 框架 | LangGraph 0.2+ |
| LLM 抽象 | LangChain Core 0.3+ |
| 模型提供商 | Anthropic (Claude), OpenAI, DeepSeek, GLM |
| 数据验证 | Pydantic 2.0+ |
| CLI | Click |
| 配置 | YAML + dotenv |
| Git 集成 | GitPython |
| GitHub | PyGithub |
| 重试 | Tenacity |

## LangGraph 架构

StateGraph 单层并行模式：
- coordinator 收集文件
- 3 个专家节点（sec/arch/perf）并发执行
- reporter 汇总去重输出

## 启动方式

```bash
# 安装
poetry install

# 全量审查
code-agent --all

# 增量审查（对比分支）
code-agent --diff origin/main

# 指定路径
code-agent --path src/

# 输出到文件
code-agent --all -o report.md

# JSON 格式
code-agent --all -f json

# 发表 PR 评论
code-agent --diff origin/main --pr-comment
```

## 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `LLM_PROVIDER` | 是 | anthropic / openai / deepseek / glm |
| `LLM_MODEL` | 是 | 模型名称 |
| `LLM_API_KEY` | 是 | API Key |
| `LLM_BASE_URL` | 否 | 自定义 API 端点 |
| `GITHUB_TOKEN` | 否 | PR 评论功能需要 |
| `GITHUB_REPOSITORY` | 否 | owner/repo，默认自动检测 |

## 核心目录

```
.
├── agent/             # Agent 核心
│   ├── graph.py       # StateGraph 定义
│   ├── state.py       # State 类型定义
│   └── nodes/         # 各专家节点
│       ├── coordinator.py
│       ├── sec_expert.py
│       ├── arch_expert.py
│       ├── perf_expert.py
│       └── reporter.py
├── prompts/           # Prompt 模板
│   ├── base.md
│   ├── architecture.md
│   ├── security.md
│   └── performance.md
├── cli.py             # CLI 入口
├── config.py          # 配置加载
├── llm_client.py      # LLM 客户端封装
├── formatter.py       # 报告格式化器
├── git_utils.py       # Git diff 解析
├── github_client.py   # GitHub API 客户端
└── tests/             # 测试
```

## 模型提供商

| Provider | 基类 | 默认 Base URL |
|----------|------|---------------|
| anthropic | ChatAnthropic | - |
| openai | ChatOpenAI | - |
| deepseek | ChatOpenAI | https://api.deepseek.com |
| glm | ChatOpenAI | https://open.bigmodel.cn/api/paas/v4/ |

## Tool 类型

无外部 Tool 调用。Agent 通过 LLM 直接分析代码文本，不使用 function calling、MCP、RAG、Browser 或 Code Executor。
