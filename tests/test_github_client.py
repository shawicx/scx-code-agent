import os
from unittest.mock import MagicMock, patch

import pytest

from agent.state import AgentIssue
from github_client import GitHubClient, detect_repo_info


class TestDetectRepoInfo:
    """Test detect_repo_info function."""

    def setup_method(self):
        """Clear the cache before each test."""
        import github_client

        github_client._repo_info_cache.clear()

    def test_from_github_actions_env(self):
        """Detects repo info from GitHub Actions environment variables."""
        import github_client

        github_client._repo_info_cache.clear()

        env = {
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_REF_NAME": "feature-branch",
            "GITHUB_SHA": "abc123",
            "GITHUB_EVENT_PATH": "",
        }
        with patch.dict(os.environ, env, clear=False):
            result = detect_repo_info()

        assert result["repo"] == "owner/repo"
        assert result["ref"] == "feature-branch"
        assert result["sha"] == "abc123"

        # Cleanup cache
        github_client._repo_info_cache.clear()

    def test_from_github_actions_pr_event(self, tmp_path):
        """Detects source branch and PR number from pull_request event payload."""
        import github_client

        github_client._repo_info_cache.clear()

        event_file = tmp_path / "event.json"
        event_file.write_text('{"pull_request": {"number": 42, "head": {"ref": "feature-x"}}}')

        env = {
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_REF_NAME": "42/merge",
            "GITHUB_SHA": "abc123",
            "GITHUB_EVENT_PATH": str(event_file),
        }
        with patch.dict(os.environ, env, clear=False):
            result = detect_repo_info()

        assert result["repo"] == "owner/repo"
        assert result["ref"] == "feature-x"
        assert result["pr_number"] == "42"
        assert result["sha"] == "abc123"

        github_client._repo_info_cache.clear()

    def test_from_git_remote_ssh(self):
        """Detects repo info from git remote (SSH URL)."""
        import github_client

        github_client._repo_info_cache.clear()

        mock_repo = MagicMock()
        mock_repo.remotes.origin.url = "git@github.com:owner/my-repo.git"
        mock_repo.head.commit.hexsha = "deadbeef"
        mock_repo.active_branch.name = "main"

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("github_client._HAS_GITPYTHON", True),
            patch("github_client.gitpython.Repo", return_value=mock_repo),
        ):
            result = detect_repo_info()

        assert result["repo"] == "owner/my-repo"
        assert result["sha"] == "deadbeef"
        assert result["ref"] == "main"

        github_client._repo_info_cache.clear()

    def test_from_git_remote_https(self):
        """Detects repo info from git remote (HTTPS URL)."""
        import github_client

        github_client._repo_info_cache.clear()

        mock_repo = MagicMock()
        mock_repo.remotes.origin.url = "https://github.com/owner/my-repo.git"
        mock_repo.head.commit.hexsha = "cafe1234"
        mock_repo.active_branch.name = "develop"

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("github_client._HAS_GITPYTHON", True),
            patch("github_client.gitpython.Repo", return_value=mock_repo),
        ):
            result = detect_repo_info()

        assert result["repo"] == "owner/my-repo"
        assert result["sha"] == "cafe1234"

        github_client._repo_info_cache.clear()

    def test_from_git_remote_non_github(self):
        """Non-GitHub remote URL returns empty info."""
        import github_client

        github_client._repo_info_cache.clear()

        mock_repo = MagicMock()
        mock_repo.remotes.origin.url = "https://gitlab.com/owner/repo.git"

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("github_client._HAS_GITPYTHON", True),
            patch("github_client.gitpython.Repo", return_value=mock_repo),
        ):
            result = detect_repo_info()

        assert "repo" not in result or result.get("repo") is None

        github_client._repo_info_cache.clear()

    def test_no_gitpython(self):
        """When gitpython is not available and no env vars, returns empty dict."""
        import github_client

        github_client._repo_info_cache.clear()

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("github_client._HAS_GITPYTHON", False),
        ):
            result = detect_repo_info()

        assert result == {}

        github_client._repo_info_cache.clear()

    def test_git_exception_returns_empty(self):
        """Git exceptions are caught and return empty info."""
        import github_client

        github_client._repo_info_cache.clear()

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("github_client._HAS_GITPYTHON", True),
            patch("github_client.gitpython.Repo", side_effect=Exception("no repo")),
        ):
            result = detect_repo_info()

        assert result == {}

        github_client._repo_info_cache.clear()

    def test_caches_result(self):
        """Second call returns cached result."""
        import github_client

        github_client._repo_info_cache.clear()

        env = {"GITHUB_REPOSITORY": "owner/cached"}
        with patch.dict(os.environ, env, clear=False):
            detect_repo_info()

        # Even without env vars, should return cached
        with patch.dict(os.environ, {}, clear=True):
            result2 = detect_repo_info()

        assert result2["repo"] == "owner/cached"

        github_client._repo_info_cache.clear()


class TestGitHubClientInit:
    """Test GitHubClient initialization."""

    def test_init_with_repo(self):
        """Init with explicit repo name."""
        with patch("github_client.Github") as mock_github_cls:
            mock_github_cls.return_value.get_repo.return_value = MagicMock()
            client = GitHubClient(token="fake-token", repo="owner/repo")

        assert client.repo_name == "owner/repo"
        mock_github_cls.assert_called_once_with("fake-token")

    def test_init_detects_repo(self):
        """Init without repo detects from environment."""
        with (
            patch("github_client.Github") as mock_github_cls,
            patch("github_client.detect_repo_info", return_value={"repo": "auto/repo"}),
        ):
            mock_github_cls.return_value.get_repo.return_value = MagicMock()
            client = GitHubClient(token="fake-token")

        assert client.repo_name == "auto/repo"

    def test_init_no_repo_raises(self):
        """Init fails when no repo can be detected."""
        with (
            patch("github_client.Github"),
            patch("github_client.detect_repo_info", return_value={}),
        ):
            with pytest.raises(ValueError, match="无法检测仓库信息"):
                GitHubClient(token="fake-token")


class TestGetCurrentPR:
    """Test get_current_pr method."""

    def _make_client(self):
        """Create a client with mocked GitHub."""
        with patch("github_client.Github") as mock_github_cls:
            mock_repo = MagicMock()
            mock_github_cls.return_value.get_repo.return_value = mock_repo
            client = GitHubClient(token="fake-token", repo="owner/repo")
        return client

    def test_finds_pr_by_branch(self):
        """Finds open PR matching the branch."""
        client = self._make_client()

        mock_pr = MagicMock()
        mock_pr.head.ref = "feature-branch"
        mock_pr.number = 42
        client.repo.get_pulls.return_value = [mock_pr]

        with patch("github_client.detect_repo_info", return_value={"ref": "feature-branch"}):
            result = client.get_current_pr()

        assert result == 42

    def test_no_branch_returns_none(self):
        """Returns None when no branch is detected."""
        client = self._make_client()

        with patch("github_client.detect_repo_info", return_value={"ref": ""}):
            result = client.get_current_pr()

        assert result is None

    def test_explicit_branch(self):
        """Uses explicit branch parameter."""
        client = self._make_client()

        mock_pr = MagicMock()
        mock_pr.head.ref = "my-branch"
        mock_pr.number = 7
        client.repo.get_pulls.return_value = [mock_pr]

        result = client.get_current_pr(branch="my-branch")
        assert result == 7

    def test_no_matching_pr_returns_none(self):
        """Returns None when no PR matches the branch."""
        client = self._make_client()

        client.repo.get_pulls.return_value = []

        result = client.get_current_pr(branch="nonexistent")
        assert result is None

    def test_github_exception_returns_none(self):
        """Returns None when GitHub API raises an exception."""
        from github import GithubException

        client = self._make_client()
        client.repo.get_pulls.side_effect = GithubException(404, "Not Found", {})

        result = client.get_current_pr(branch="any-branch")
        assert result is None

    def test_uses_cached_pr_number(self):
        """Returns PR number from cached event payload without API call."""
        client = self._make_client()

        with patch("github_client.detect_repo_info", return_value={"pr_number": "42", "ref": "feature-x"}):
            result = client.get_current_pr()

        assert result == 42
        client.repo.get_pulls.assert_not_called()


class TestPostPRComment:
    """Test post_pr_comment method."""

    def _make_client(self):
        with patch("github_client.Github") as mock_github_cls:
            mock_repo = MagicMock()
            mock_github_cls.return_value.get_repo.return_value = mock_repo
            client = GitHubClient(token="fake-token", repo="owner/repo")
        return client

    def test_post_success(self):
        """Successfully posts a PR comment."""
        client = self._make_client()

        mock_pr = MagicMock()
        client.repo.get_pull.return_value = mock_pr

        result = client.post_pr_comment(42, "## Report")
        assert result is True
        mock_pr.create_issue_comment.assert_called_once_with("## Report")

    def test_post_failure_returns_false(self):
        """Returns False when API call fails."""
        from github import GithubException

        client = self._make_client()
        client.repo.get_pull.side_effect = GithubException(500, "Server Error", {})

        result = client.post_pr_comment(42, "## Report")
        assert result is False


class TestFormatPRSummary:
    """Test format_pr_summary static method."""

    def test_no_issues(self):
        """Returns success message when no issues."""
        result = GitHubClient.format_pr_summary([])
        assert "No issues found" in result

    def test_single_issue(self):
        """Formats a single issue correctly."""
        issues: list[AgentIssue] = [
            {
                "file_path": "src/main.py",
                "line_number": 10,
                "category": "Security",
                "level": "Blocker",
                "description": "SQL injection vulnerability",
                "suggestion": "Use parameterized queries",
            }
        ]
        result = GitHubClient.format_pr_summary(issues)
        assert "1 issues" in result
        assert "Blocker" in result
        assert "src/main.py:10" in result
        assert "SQL injection vulnerability" in result

    def test_multiple_levels(self):
        """Groups issues by level."""
        issues: list[AgentIssue] = [
            {
                "file_path": "a.py",
                "line_number": 1,
                "category": "Security",
                "level": "Blocker",
                "description": "Issue 1",
                "suggestion": "Fix 1",
            },
            {
                "file_path": "b.py",
                "line_number": 2,
                "category": "Style",
                "level": "Warning",
                "description": "Issue 2",
                "suggestion": "Fix 2",
            },
            {
                "file_path": "c.py",
                "line_number": 3,
                "category": "Info",
                "level": "Info",
                "description": "Issue 3",
                "suggestion": "Fix 3",
            },
        ]
        result = GitHubClient.format_pr_summary(issues)
        assert "Blocker" in result
        assert "Warning" in result
        assert "Info" in result
        assert "3 issues" in result
        assert "3 file(s)" in result

    def test_many_issues_truncates(self):
        """Truncates when more than 10 issues in a level."""
        issues: list[AgentIssue] = [
            {
                "file_path": f"file_{i}.py",
                "line_number": i,
                "category": "Security",
                "level": "Blocker",
                "description": f"Issue {i}",
                "suggestion": "Fix",
            }
            for i in range(15)
        ]
        result = GitHubClient.format_pr_summary(issues)
        assert "and 5 more" in result

    def test_generates_markdown(self):
        """Output contains Markdown formatting."""
        issues: list[AgentIssue] = [
            {
                "file_path": "x.py",
                "line_number": 1,
                "category": "Bug",
                "level": "Warning",
                "description": "test issue",
                "suggestion": "fix it",
            }
        ]
        result = GitHubClient.format_pr_summary(issues)
        assert "##" in result
        assert "Generated by SCX Code Agent" in result
