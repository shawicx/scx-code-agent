import json
import os
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from cli import audit


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_config():
    """Mock config to avoid loading real config files or env."""
    mock_cfg = MagicMock()
    mock_cfg.provider.name = "openai"
    mock_cfg.provider.model = "gpt-4"
    return mock_cfg


@pytest.fixture
def mock_graph_result():
    return {
        "final_report": "# Review Report\n\nNo issues found.",
        "raw_comments": [],
    }


def _patch_graph(result):
    """Return a patch for create_review_graph that returns a mock graph."""
    mock_graph = MagicMock()
    mock_graph.invoke.return_value = result
    return patch("cli.create_review_graph", return_value=mock_graph)


class TestCLIModes:
    """Test CLI mode selection and validation."""

    def test_no_mode_specified_aborts(self, runner):
        """No mode flags should abort."""
        with patch("cli.load_config"):
            result = runner.invoke(audit, [])
        assert result.exit_code != 0
        assert "必须指定" in result.output or result.exit_code == 1

    def test_multiple_modes_aborts(self, runner):
        """Using more than one mode flag should abort."""
        with patch("cli.load_config"):
            result = runner.invoke(audit, ["--all", "--path", "src"])
        assert result.exit_code != 0
        assert "不能同时使用" in result.output or result.exit_code == 1

    def test_all_mode(self, runner, mock_config, mock_graph_result):
        """--all mode invokes graph and outputs report."""
        with (
            patch("cli.load_config", return_value=mock_config),
            _patch_graph(mock_graph_result),
        ):
            result = runner.invoke(audit, ["--all"])

        assert result.exit_code == 0
        assert any(keyword in result.output for keyword in ["审查", "Review", "Report", "无审查结果", "config"])

    def test_diff_mode(self, runner, mock_config, mock_graph_result):
        """--diff mode with a base branch invokes graph."""
        with (
            patch("cli.load_config", return_value=mock_config),
            _patch_graph(mock_graph_result),
        ):
            result = runner.invoke(audit, ["--diff", "main"])

        assert result.exit_code == 0

    def test_path_mode(self, runner, mock_config, mock_graph_result):
        """--path mode with a directory invokes graph."""
        with (
            patch("cli.load_config", return_value=mock_config),
            _patch_graph(mock_graph_result),
        ):
            result = runner.invoke(audit, ["--path", "src"])

        assert result.exit_code == 0

    def test_all_mode_uses_progress(self, runner, mock_config, mock_graph_result):
        """--all mode creates a Progress context and passes it to graph."""
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = mock_graph_result

        with (
            patch("cli.load_config", return_value=mock_config),
            patch("cli.create_review_graph", return_value=mock_graph),
        ):
            result = runner.invoke(audit, ["--all"])

        assert result.exit_code == 0
        # Verify progress was passed in the state
        invoke_args = mock_graph.invoke.call_args[0][0]
        assert invoke_args.get("progress") is not None

    def test_path_mode_empty_path_aborts(self, runner, mock_config):
        """--path without a value should abort (click enforces type=str, default=None)."""
        # Click's type=str with default=None means empty string isn't naturally produced.
        # Simulate by invoking with --path "" explicitly.
        with patch("cli.load_config", return_value=mock_config):
            result = runner.invoke(audit, ["--path", ""])

        # The CLI checks `if mode == "path" and not path`
        assert result.exit_code != 0


class TestCLIFormatOutput:
    """Test format and output options."""

    def test_json_format(self, runner, mock_config):
        """--format json outputs the report as raw text."""
        graph_result = {
            "final_report": json.dumps({"summary": {"total_issues": 0}}),
            "raw_comments": [],
        }
        with (
            patch("cli.load_config", return_value=mock_config),
            _patch_graph(graph_result),
        ):
            result = runner.invoke(audit, ["--all", "--format", "json"])

        assert result.exit_code == 0

    def test_markdown_format(self, runner, mock_config, mock_graph_result):
        """--format markdown (default) outputs Markdown-rendered report."""
        with (
            patch("cli.load_config", return_value=mock_config),
            _patch_graph(mock_graph_result),
        ):
            result = runner.invoke(audit, ["--all", "--format", "markdown"])

        assert result.exit_code == 0

    def test_output_writes_to_file(self, runner, mock_config, mock_graph_result, tmp_path):
        """--output writes report to the specified file."""
        output_file = tmp_path / "report.md"
        with (
            patch("cli.load_config", return_value=mock_config),
            _patch_graph(mock_graph_result),
        ):
            result = runner.invoke(audit, ["--all", "--output", str(output_file)])

        assert result.exit_code == 0
        assert output_file.exists()
        assert "No issues found" in output_file.read_text(encoding="utf-8")

    def test_output_creates_parent_dirs(self, runner, mock_config, mock_graph_result, tmp_path):
        """--output creates parent directories if they don't exist."""
        output_file = tmp_path / "subdir" / "nested" / "report.md"
        with (
            patch("cli.load_config", return_value=mock_config),
            _patch_graph(mock_graph_result),
        ):
            result = runner.invoke(audit, ["--all", "--output", str(output_file)])

        assert result.exit_code == 0
        assert output_file.exists()


class TestCLIPRComment:
    """Test --pr-comment flag behavior."""

    def test_pr_comment_no_token(self, runner, mock_config, mock_graph_result):
        """--pr-comment without GITHUB_TOKEN prints warning."""
        with (
            patch("cli.load_config", return_value=mock_config),
            _patch_graph(mock_graph_result),
            patch.dict(os.environ, {}, clear=True),
        ):
            result = runner.invoke(audit, ["--all", "--pr-comment"])

        assert result.exit_code == 0
        assert "GITHUB_TOKEN" in result.output or "未设置" in result.output

    def test_pr_comment_with_token(self, runner, mock_config, mock_graph_result):
        """--pr-comment with token posts comment via GitHubClient."""
        mock_gh = MagicMock()
        mock_gh.get_current_pr.return_value = 42
        mock_gh.post_pr_comment.return_value = True

        with (
            patch("cli.load_config", return_value=mock_config),
            _patch_graph(mock_graph_result),
            patch.dict(os.environ, {"GITHUB_TOKEN": "fake-token"}),
            patch("github_client.GitHubClient", return_value=mock_gh),
            patch("github_client.GitHubClient.format_pr_summary", return_value="summary"),
        ):
            result = runner.invoke(audit, ["--all", "--pr-comment"])

        assert result.exit_code == 0

    def test_pr_comment_no_pr_found(self, runner, mock_config, mock_graph_result):
        """--pr-comment when no PR is found shows warning."""
        mock_gh = MagicMock()
        mock_gh.get_current_pr.return_value = None

        with (
            patch("cli.load_config", return_value=mock_config),
            _patch_graph(mock_graph_result),
            patch.dict(os.environ, {"GITHUB_TOKEN": "fake-token"}),
            patch("github_client.GitHubClient", return_value=mock_gh),
        ):
            result = runner.invoke(audit, ["--all", "--pr-comment"])

        assert result.exit_code == 0
        assert "未找到" in result.output or "PR" in result.output

    def test_pr_comment_post_failure(self, runner, mock_config, mock_graph_result):
        """--pr-comment when post fails shows error."""
        mock_gh = MagicMock()
        mock_gh.get_current_pr.return_value = 42
        mock_gh.post_pr_comment.return_value = False

        with (
            patch("cli.load_config", return_value=mock_config),
            _patch_graph(mock_graph_result),
            patch.dict(os.environ, {"GITHUB_TOKEN": "fake-token"}),
            patch("github_client.GitHubClient", return_value=mock_gh),
            patch("github_client.GitHubClient.format_pr_summary", return_value="summary"),
        ):
            result = runner.invoke(audit, ["--all", "--pr-comment"])

        assert result.exit_code == 0
        assert "失败" in result.output or "error" in result.output.lower() or "失败" in result.output

    def test_pr_comment_import_error(self, runner, mock_config, mock_graph_result):
        """--pr-comment when PyGitHub not installed shows warning."""
        with (
            patch("cli.load_config", return_value=mock_config),
            _patch_graph(mock_graph_result),
            patch.dict(os.environ, {"GITHUB_TOKEN": "fake-token"}),
            patch("github_client.GitHubClient", side_effect=ImportError("No module named 'github'")),
        ):
            result = runner.invoke(audit, ["--all", "--pr-comment"])

        assert result.exit_code == 0
        assert "PyGitHub" in result.output or "未安装" in result.output

    def test_pr_comment_generic_exception(self, runner, mock_config, mock_graph_result):
        """--pr-comment when a generic exception occurs shows error."""
        with (
            patch("cli.load_config", return_value=mock_config),
            _patch_graph(mock_graph_result),
            patch.dict(os.environ, {"GITHUB_TOKEN": "fake-token"}),
            patch("github_client.GitHubClient", side_effect=Exception("API error")),
        ):
            result = runner.invoke(audit, ["--all", "--pr-comment"])

        assert result.exit_code == 0
        assert "出错" in result.output or "error" in result.output.lower()


class TestCLIConfig:
    """Test config loading output."""

    def test_config_info_printed(self, runner, mock_config, mock_graph_result):
        """Config provider info is printed on startup."""
        with (
            patch("cli.load_config", return_value=mock_config),
            _patch_graph(mock_graph_result),
        ):
            result = runner.invoke(audit, ["--all"])

        assert result.exit_code == 0
        assert "openai" in result.output
        assert "gpt-4" in result.output
