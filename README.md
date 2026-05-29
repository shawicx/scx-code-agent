# SCX Code Agent

多智能体代码审查系统，基于 LangGraph 构建。

## 安装

```bash
poetry install
```

## 配置

### 方式一：配置文件（推荐）

在项目根目录创建 `.scx-code-agent.yaml`：

```yaml
provider:
  name: deepseek
  model: deepseek-v4-flash
  api_key: ${LLM_API_KEY}
  base_url: https://api.deepseek.com

review:
  max_workers: 5
  skip_dirs:
    - node_modules
    - .venv
```

示例配置文件：
```bash
cp .scx-code-agent.yaml.example .scx-code-agent.yaml
```

### 方式二：环境变量

复制 `.env.example` 为 `.env` 并配置：

```bash
cp .env.example .env
```

### 配置优先级

命令行参数 > 配置文件 > 环境变量 > 默认值

## 使用

### 全量审查

```bash
# 扫描当前目录
poetry run scx-code-agent --all

# 扫描指定路径
poetry run scx-code-agent --path src/
```

### 增量审查（PR）

```bash
poetry run scx-code-agent --diff origin/main
```

### 输出选项

```bash
# 输出到文件
poetry run scx-code-agent --path src/ --output dist/report.md

# JSON 格式输出
poetry run scx-code-agent --path src/ --format json --output dist/report.json
```

### PR 评论（CI/CD）

在 GitHub Actions 等环境中，可将审查结果发表为 PR 评论：

```bash
# 设置 GitHub Token
export GITHUB_TOKEN=ghp_xxx

# 发表 PR 评论
poetry run scx-code-agent --diff origin/main --pr-comment
```

环境变量：
- `GITHUB_TOKEN`: GitHub Personal Access Token（需要 `repo:status` 权限）
- `GITHUB_REPOSITORY`: 仓库路径（可选，通常自动检测）

## 架构

- **Coordinator**: 文件收集与分发
- **Security Expert**: 安全审查
- **Architecture Expert**: 架构审查
- **Performance Expert**: 性能审查
- **Reporter**: 报告生成与格式化
