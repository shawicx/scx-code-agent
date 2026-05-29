from pathlib import Path

from fastmcp import FastMCP

from agent.graph import create_review_graph
from agent.state import SharedReviewState

mcp = FastMCP(
    name="scx-code-agent",
    instructions="Code review agent powered by multi-expert LangGraph workflow. "
    "Use review_diff for incremental PR review, review_path for specific files/dirs, "
    "review_all for full project scan.",
)


def _run_review(state: SharedReviewState) -> str:
    graph = create_review_graph()
    result = graph.invoke(state)
    return result.get("final_report") or "No review results"


def _make_state(**overrides) -> SharedReviewState:
    base: SharedReviewState = {
        "mode": "",
        "target_files": [],
        "raw_comments": [],
        "final_report": "",
        "diff_branch": "",
        "target_path": "",
        "output_format": "markdown",
    }
    base.update(overrides)
    return base


def _do_review_path(path: str, format: str = "markdown") -> str:
    if format not in ("markdown", "json"):
        return f"Error: invalid format '{format}', must be 'markdown' or 'json'"

    target = Path(path)
    if not target.exists():
        return f"Error: path '{path}' does not exist"

    state = _make_state(mode="path", target_path=path, output_format=format)
    return _run_review(state)


def _do_review_diff(base_branch: str, format: str = "markdown") -> str:
    if format not in ("markdown", "json"):
        return f"Error: invalid format '{format}', must be 'markdown' or 'json'"

    if not base_branch or base_branch.startswith("-"):
        return f"Error: invalid branch name '{base_branch}'"

    state = _make_state(mode="diff", diff_branch=base_branch, output_format=format)
    return _run_review(state)


def _do_review_all(format: str = "markdown") -> str:
    if format not in ("markdown", "json"):
        return f"Error: invalid format '{format}', must be 'markdown' or 'json'"

    state = _make_state(mode="all", output_format=format)
    return _run_review(state)


@mcp.tool()
def review_path(path: str, format: str = "markdown") -> str:
    """Review code at a specific file or directory path.

    Scans the given path for code files and runs a multi-expert review
    (security, architecture, performance). Accepts a single file or directory.

    Args:
        path: Absolute or relative path to a file or directory to review.
        format: Output format — "markdown" or "json". Defaults to "markdown".
    """
    return _do_review_path(path, format)


@mcp.tool()
def review_diff(base_branch: str, format: str = "markdown") -> str:
    """Review code changes in the current branch against a base branch.

    Uses git diff to find changed files, then runs a multi-expert review
    focused on the diff lines. Best for PR / code-change reviews.

    Args:
        base_branch: Git base branch to diff against (e.g. "origin/main", "main").
        format: Output format — "markdown" or "json". Defaults to "markdown".
    """
    return _do_review_diff(base_branch, format)


@mcp.tool()
def review_all(format: str = "markdown") -> str:
    """Scan and review all code files in the current directory.

    Walks the current working directory, collects all supported code files,
    and runs a full multi-expert review. Can be slow for large projects.

    Args:
        format: Output format — "markdown" or "json". Defaults to "markdown".
    """
    return _do_review_all(format)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
