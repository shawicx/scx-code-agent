from typing import Dict, List, Tuple

from agent.state import AgentIssue, SharedReviewState
from formatter import JSONFormatter, MarkdownFormatter

LEVEL_ORDER = {"Blocker": 0, "Warning": 1, "Info": 2}


def deduplicate_issues(issues: List[AgentIssue]) -> List[AgentIssue]:
    """去重问题列表，同一位置只保留最严重的问题

    Args:
        issues: 原始问题列表

    Returns:
        去重后的问题列表
    """
    position_map: Dict[Tuple[str, int], AgentIssue] = {}

    for issue in issues:
        key = (issue["file_path"], issue["line_number"])
        existing = position_map.get(key)

        if not existing:
            position_map[key] = issue  # 复制，避免修改原始对象
        else:
            current_level = LEVEL_ORDER.get(issue["level"], 99)
            existing_level = LEVEL_ORDER.get(existing["level"], 99)

            if current_level < existing_level:
                position_map[key] = issue
            elif current_level == existing_level and issue["level"] == existing["level"]:
                merged: AgentIssue = existing.copy() if isinstance(existing, dict) else {}
                merged["description"] = str(merged.get("description", "")) + f"; {issue['description']}"
                if issue.get("suggestion"):
                    existing_suggestion = str(merged.get("suggestion", "") if isinstance(merged, dict) else "")
                    merged["suggestion"] = (
                        f"{existing_suggestion}\n{str(issue['suggestion'])}"
                        if existing_suggestion
                        else str(issue["suggestion"])
                    )
                position_map[key] = merged

    return list(position_map.values())


def reporter_node(state: SharedReviewState) -> SharedReviewState:
    """报告官节点：去重、定级、格式化输出"""
    raw_comments = state.get("raw_comments", [])
    output_format = state.get("output_format", "markdown")

    # 1. 去重
    deduplicated = deduplicate_issues(raw_comments)

    # 2. 根据格式选择格式化器
    formatter: JSONFormatter | MarkdownFormatter
    if output_format == "json":
        formatter = JSONFormatter()
    else:
        formatter = MarkdownFormatter()

    report = formatter.format(deduplicated)

    return {
        "final_report": report,
        "raw_comments": raw_comments,
        "mode": state.get("mode", ""),
        "target_files": state.get("target_files", []),
        "diff_branch": state.get("diff_branch", ""),
        "target_path": state.get("target_path", ""),
        "output_format": state.get("output_format", ""),
    }
