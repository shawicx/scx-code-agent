from abc import ABC, abstractmethod
from collections import Counter
from typing import Dict, List

from agent.state import AgentIssue


class ReportFormatter(ABC):
    """报告格式化器基类"""

    @abstractmethod
    def format(self, issues: List[AgentIssue]) -> str:
        """格式化问题列表为报告字符串"""
        pass


class MarkdownFormatter(ReportFormatter):
    """Markdown 格式化器"""

    LEVEL_ORDER = {"Blocker": 0, "Warning": 1, "Info": 2}
    LEVELS = list(LEVEL_ORDER.keys())
    LEVEL_EMOJI = {"Blocker": "🚫", "Warning": "⚠️", "Info": "ℹ️"}

    def format(self, issues: List[AgentIssue]) -> str:
        lines = ["# Code Review Report\n"]

        if not issues:
            lines.append("✅ No issues found!\n")
            return "".join(lines)

        # Summary 部分
        lines.extend(self._format_summary(issues))

        # 按级别分组
        by_level = self._group_by_level(issues)

        # 按级别顺序输出
        for level in self.LEVELS:
            if level not in by_level:
                continue
            lines.extend(self._format_level_section(level, by_level[level]))

        return "".join(lines)

    def _format_summary(self, issues: List[AgentIssue]) -> List[str]:
        """格式化摘要部分"""
        lines = ["## Summary\n\n"]

        level_counts = Counter(issue.get("level", "Info") for issue in issues)
        category_counts = Counter(issue.get("category", "Unknown") for issue in issues)
        files_affected = len(set(issue.get("file_path", "") for issue in issues))

        lines.append(f"- **Total Issues**: {len(issues)}\n")
        lines.append("- **By Level**: ")
        level_parts = []
        for level in self.LEVELS:
            count = level_counts.get(level, 0)
            if count:
                level_parts.append(f"{self.LEVEL_EMOJI[level]} {level}: {count}")
        lines.append(" | ".join(level_parts) + "\n")

        lines.append("- **By Category**: ")
        category_parts = [f"{cat}: {count}" for cat, count in category_counts.most_common()]
        lines.append(" | ".join(category_parts) + "\n")

        lines.append(f"- **Files Affected**: {files_affected}\n")
        lines.append("\n---\n\n")

        return lines

    def _group_by_level(self, issues: List[AgentIssue]) -> Dict[str, List[AgentIssue]]:
        """按级别分组"""
        by_level: Dict[str, List[AgentIssue]] = {"Blocker": [], "Warning": [], "Info": []}
        for issue in issues:
            level = issue.get("level", "Info")
            by_level[level].append(issue)
        return by_level

    def _format_level_section(self, level: str, issues: List[AgentIssue]) -> List[str]:
        """格式化单个级别部分"""
        lines = [f"## {self.LEVEL_EMOJI[level]} {level} ({len(issues)})\n\n"]

        for issue in issues:
            lines.extend(self._format_issue(issue))

        return lines

    def _format_issue(self, issue: AgentIssue) -> List[str]:
        """格式化单个问题"""
        file_path = issue.get("file_path", "unknown")
        line = issue.get("line_number", 0)
        category = issue.get("category", "Unknown")
        description = issue.get("description", "")
        suggestion = issue.get("suggestion", "")

        lines = [f"### {category}: {description}\n", f"**File**: `{file_path}:{line}`\n\n"]

        if suggestion:
            lines.append("**Suggestion**:\n")
            lines.append(f"```\n{suggestion}\n```\n")

        lines.append("\n---\n\n")

        return lines


class JSONFormatter(ReportFormatter):
    """JSON 格式化器"""

    def format(self, issues: List[AgentIssue]) -> str:
        import json
        from collections import Counter

        if not issues:
            return json.dumps({"summary": {"total_issues": 0}, "issues": []}, indent=2)

        level_counts = Counter(issue.get("level", "Info") for issue in issues)
        category_counts = Counter(issue.get("category", "Unknown") for issue in issues)
        files_affected = len(set(issue.get("file_path", "") for issue in issues))

        report = {
            "summary": {
                "total_issues": len(issues),
                "by_level": dict(level_counts),
                "by_category": dict(category_counts),
                "files_affected": files_affected,
            },
            "issues": issues,
        }

        return json.dumps(report, indent=2, ensure_ascii=False)
