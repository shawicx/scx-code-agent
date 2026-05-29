import os
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown

from agent.graph import create_review_graph
from agent.state import SharedReviewState
from config import load_config

console = Console()


@click.command()
@click.option("--all", is_flag=True, help="扫描当前目录全量代码")
@click.option("--diff", type=str, default=None, help="增量审查基准分支")
@click.option("--path", type=str, default=None, help="指定路径审查")
@click.option("--output", "-o", type=str, default=None, help="报告输出路径")
@click.option("--format", "-f", type=click.Choice(["markdown", "json"]), default="markdown", help="报告格式")
@click.option("--pr-comment", is_flag=True, help="发表 PR 评论")
def audit(all, diff, path, output, format, pr_comment):
    """多智能体代码审查系统"""
    # 验证参数互斥
    mode_count = sum([all, diff is not None, path is not None])
    if mode_count > 1:
        console.print("[red]--all、--diff、--path 不能同时使用[/red]")
        raise click.Abort()

    if mode_count == 0:
        console.print("[red]必须指定 --all、--diff 或 --path 之一[/red]")
        raise click.Abort()

    # 加载配置
    config = load_config()
    console.print(f"使用配置: {config.provider.name} / {config.provider.model}")

    # 确定模式
    if path:
        mode = "path"
    elif all:
        mode = "all"
    else:
        mode = "diff"

    if mode == "diff" and not diff:
        console.print("[red]--diff 需要指定基准分支[/red]")
        raise click.Abort()

    if mode == "path" and not path:
        console.print("[red]--path 需要指定路径[/red]")
        raise click.Abort()

    # 初始化状态
    initial_state: SharedReviewState = {
        "mode": mode,
        "target_files": [],
        "raw_comments": [],
        "final_report": "",
        "diff_branch": diff or "",
        "target_path": path or "",
        "output_format": format,
    }

    # 执行审查
    graph = create_review_graph()
    console.print("开始代码审查...\n")

    result = graph.invoke(initial_state)
    report = result.get("final_report", "# 无审查结果")

    # 输出报告
    if output:
        output_file = Path(output)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(report, encoding="utf-8")
        console.print(f"[green]报告已写入: {output}[/green]")
    else:
        if format == "json":
            console.print(report)
        else:
            console.print(Markdown(report))

    # PR 评论
    if pr_comment:
        try:
            from github_client import GitHubClient

            github_token = config.github.token
            if not github_token:
                console.print("[yellow]警告: GITHUB_TOKEN 未设置，跳过 PR 评论[/yellow]")
                return

            raw_comments = result.get("raw_comments", [])
            gh_client = GitHubClient(token=github_token)

            pr_number = gh_client.get_current_pr()
            if not pr_number:
                console.print("[yellow]未找到关联的 PR，跳过评论[/yellow]")
                return

            summary = GitHubClient.format_pr_summary(raw_comments)
            if gh_client.post_pr_comment(pr_number, summary):
                console.print(f"[green]✓ 评论已发表到 PR #{pr_number}[/green]")
            else:
                console.print("[red]评论发表失败[/red]")

        except ImportError:
            console.print("[yellow]PyGitHub 未安装，跳过 PR 评论[/yellow]")
        except Exception as e:
            console.print(f"[red]PR 评论出错: {e}[/red]")


if __name__ == "__main__":
    audit()
