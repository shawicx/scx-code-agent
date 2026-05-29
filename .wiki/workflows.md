# Workflows

## 核心工作流：Fan-out / Fan-in

唯一工作流。无 planner-executor、multi-agent 协作、reflection、self-correction 等。

```mermaid
graph TD
    Start[用户触发审查] --> Mode{mode?}
    Mode -->|all| ScanAll[扫描当前目录]
    Mode -->|diff| ScanDiff[解析 git diff]
    Mode -->|path| ScanPath[扫描指定路径]
    ScanAll --> FanOut
    ScanDiff --> FanOut
    ScanPath --> FanOut

    FanOut[并发启动 3 个专家] --> Sec
    FanOut --> Arch
    FanOut --> Perf

    subgraph 并发审查
        Sec[安全专家] -->|ThreadPool| SecLLM[LLM × N files]
        Arch[架构专家] -->|ThreadPool| ArchLLM[LLM × N files]
        Perf[性能专家] -->|ThreadPool| PerfLLM[LLM × N files]
    end

    SecLLM --> FanIn[汇总 raw_comments]
    ArchLLM --> FanIn
    PerfLLM --> FanIn

    FanIn --> Dedup[去重]
    Dedup --> Format[格式化]
    Format --> Output[输出报告]
    Output --> PRComment{--pr-comment?}
    PRComment -->|是| PostPR[发表 PR 评论]
    PRComment -->|否| End([结束])
    PostPR --> End
```

## 模式分支

### all 模式

1. `os.walk(".")` 遍历当前目录
2. 按 `SUPPORTED_EXTENSIONS` 过滤
3. 跳过 `SKIP_DIRS`
4. 读取每个文件内容

### diff 模式

1. 执行 `git diff {branch}` 获取 diff 输出
2. 正则解析变更文件、状态（added/modified/deleted）、变更行号
3. 按 `SUPPORTED_EXTENSIONS` 过滤
4. 读取非 deleted 文件内容
5. 保留 `diff_lines` 用于 LLM 聚焦

### path 模式

1. 判断路径是文件还是目录
2. 文件：直接读取（需扩展名匹配）
3. 目录：遍历扫描（同 all 模式）

## Workflow 切换条件

无动态切换。模式在 CLI 入口确定，整个 Graph 执行期间不变。

## Fallback

**无**。任何节点异常直接导致结果不完整：
- coordinator 异常 → `target_files` 为空 → 专家无文件可审
- 专家异常 → `raw_comments` 缺少该专家的问题
- reporter 异常 → 无报告输出

## Retry

仅 LLM 调用层有重试（`tenacity`），Graph 层无重试。

```
LLM 调用重试策略：
- 最大重试次数：3
- 退避策略：指数退避（2s, 4s, 8s, max 10s）
- 仅对网络/超时错误重试
- ValidationError 不重试（说明 LLM 输出格式错误）
```

## Human Approval

**无**。全自动化，无人工审批节点。
