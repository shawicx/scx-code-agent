import logging
import os
from typing import Dict, List, Optional

from github import Github, GithubException

from agent.state import AgentIssue

try:
    import git as gitpython

    _HAS_GITPYTHON = True
except ImportError:
    _HAS_GITPYTHON = False

logger = logging.getLogger(__name__)

_repo_info_cache: Dict[str, str | None] = {}


def detect_repo_info() -> Dict[str, str | None]:
    """从环境变量或 git remote 检测仓库信息

    Returns:
        包含 repo, sha, ref 等信息的字典
    """
    if _repo_info_cache:
        return _repo_info_cache

    info = {}

    # GitHub Actions 环境变量
    if os.getenv("GITHUB_REPOSITORY"):
        info["repo"] = os.getenv("GITHUB_REPOSITORY")
        info["ref"] = os.getenv("GITHUB_REF_NAME") or None
        info["sha"] = os.getenv("GITHUB_SHA") or None
        info["event_path"] = os.getenv("GITHUB_EVENT_PATH") or None
        _repo_info_cache.update(info)
        return info

    # 尝试从 git remote 获取
    if _HAS_GITPYTHON:
        try:
            repo = gitpython.Repo(search_parent_directories=True)
            remote_url = repo.remotes.origin.url

            # 解析 remote_url
            # git@github.com:owner/repo.git -> owner/repo
            # https://github.com/owner/repo.git -> owner/repo
            if remote_url.startswith("git@"):
                repo_path = remote_url.split(":")[1].replace(".git", "")
            elif "github.com" in remote_url:
                repo_path = remote_url.split("github.com/")[-1].replace(".git", "")
            else:
                _repo_info_cache.update(info)
                return info

            info["repo"] = repo_path
            info["sha"] = repo.head.commit.hexsha
            info["ref"] = repo.active_branch.name
        except Exception as e:
            logger.warning(f"Failed to detect repo info: {e}")

    _repo_info_cache.update(info)
    return info


class GitHubClient:
    """GitHub API 客户端"""

    def __init__(self, token: str, repo: str | None = None):
        """初始化 GitHub 客户端

        Args:
            token: GitHub Personal Access Token
            repo: 仓库格式 (owner/repo)，如果为空则自动检测
        """
        self.github = Github(token)
        self._token = token

        # 自动检测 repo
        if not repo:
            detected = detect_repo_info()
            repo = detected.get("repo", "")

        if not repo:
            raise ValueError("无法检测仓库信息，请手动提供或设置 GITHUB_REPOSITORY 环境变量")

        self.repo_name = repo
        self.repo = self.github.get_repo(repo)

    def get_current_pr(self, branch: str | None = None) -> Optional[int]:
        """获取当前分支关联的 PR 编号

        Args:
            branch: 分支名，如果为空则从缓存的环境变量或 git 获取

        Returns:
            PR 编号，如果没有找到则返回 None
        """
        if not branch:
            detected = detect_repo_info()
            branch = detected.get("ref", "")

        if not branch:
            return None

        try:
            pulls = self.repo.get_pulls(state="open", head=branch)
            for pr in pulls:
                if pr.head.ref == branch:
                    return pr.number
        except GithubException as e:
            logger.error(f"Failed to get PR: {e}")

        return None

    def post_pr_comment(self, pr_number: int, report: str) -> bool:
        """在 PR 发表评论

        Args:
            pr_number: PR 编号
            report: Markdown 格式的报告

        Returns:
            是否成功
        """
        try:
            pr = self.repo.get_pull(pr_number)
            pr.create_issue_comment(report)
            logger.info(f"Successfully posted comment to PR #{pr_number}")
            return True
        except GithubException as e:
            logger.error(f"Failed to post PR comment: {e}")
            return False

    @staticmethod
    def format_pr_summary(issues: List[AgentIssue]) -> str:
        """格式化问题为 PR 评论摘要

        Args:
            issues: 问题列表

        Returns:
            Markdown 格式的摘要
        """
        if not issues:
            return "## ✅ Code Review Report\n\nNo issues found!"

        files_affected = len(set(issue.get("file_path", "") for issue in issues))

        lines = ["## 🔍 Code Review Report\n\n", f"**Found {len(issues)} issues** across {files_affected} file(s)\n\n"]

        # 按级别分组
        by_level: dict[str, list[AgentIssue]] = {"Blocker": [], "Warning": [], "Info": []}
        for issue in issues:
            level = issue.get("level", "Info")
            by_level[level].append(issue)

        level_emoji = {"Blocker": "🚫", "Warning": "⚠️", "Info": "ℹ️"}

        for level in ["Blocker", "Warning", "Info"]:
            level_issues = by_level[level]
            if not level_issues:
                continue

            lines.append(f"### {level_emoji[level]} {level} ({len(level_issues)})\n\n")

            for issue in level_issues[:10]:
                file_path = issue.get("file_path", "unknown")
                line = issue.get("line_number", 0)
                description = issue.get("description", "")
                lines.append(f"- `{file_path}:{line}` - {description}\n")

            if len(level_issues) > 10:
                lines.append(f"\n*... and {len(level_issues) - 10} more*\n")

            lines.append("\n")

        lines.append("\n---\n\n*Generated by SCX Code Agent*")

        return "".join(lines)
