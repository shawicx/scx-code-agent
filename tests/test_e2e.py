"""E2E integration tests for the full review pipeline."""

import json
from unittest.mock import MagicMock, patch

from agent.graph import create_review_graph
from agent.state import SharedReviewState


class TestE2EAllMode:
    """E2E tests for --all mode (full codebase scan)."""

    @patch("agent.nodes.base_expert.LLMClient")
    def test_all_mode_empty_directory(self, mock_llm, tmp_path):
        """--all 模式扫描空目录应返回无问题报告"""
        graph = create_review_graph()
        state: SharedReviewState = {
            "mode": "all",
            "target_files": [],
            "raw_comments": [],
            "final_report": "",
            "diff_branch": "",
            "target_path": str(tmp_path),
            "output_format": "markdown",
            "progress": None,
        }

        with patch("agent.nodes.coordinator._scan_directory", return_value=[]):
            result = graph.invoke(state)

        assert "final_report" in result
        assert result["final_report"]  # 非空报告

    @patch("agent.nodes.base_expert.LLMClient")
    @patch("agent.nodes.base_expert.LLMClient")
    @patch("agent.nodes.base_expert.LLMClient")
    def test_all_mode_with_code_files(self, mock_perf_llm, mock_arch_llm, mock_sec_llm, sample_py_project):
        """--all 模式完整流程：coordinator 收集文件 -> 专家审查 -> reporter 生成报告"""
        for mock_cls in [mock_sec_llm, mock_arch_llm, mock_perf_llm]:
            instance = MagicMock()
            instance.review_code.return_value = [
                {
                    "file_path": "main.py",
                    "line_number": 1,
                    "category": "Security",
                    "level": "Warning",
                    "description": "Test issue",
                    "suggestion": "Fix it",
                }
            ]
            mock_cls.return_value = instance

        graph = create_review_graph()
        state: SharedReviewState = {
            "mode": "all",
            "target_files": [],
            "raw_comments": [],
            "final_report": "",
            "diff_branch": "",
            "target_path": str(sample_py_project),
            "output_format": "markdown",
            "progress": None,
        }

        with patch("agent.nodes.coordinator._scan_directory") as mock_scan:
            mock_scan.return_value = [
                {"path": "main.py", "content": 'print("hello")'},
                {"path": "utils.py", "content": "def add(a, b): return a + b"},
            ]
            result = graph.invoke(state)

        report = result.get("final_report", "")
        assert report
        assert "Code Review Report" in report or "Total Issues" in report or "issue" in report.lower()

    @patch("agent.nodes.base_expert.LLMClient")
    @patch("agent.nodes.base_expert.LLMClient")
    @patch("agent.nodes.base_expert.LLMClient")
    def test_all_mode_no_issues_found(self, mock_perf_llm, mock_arch_llm, mock_sec_llm):
        """所有专家均未发现问题时应输出无问题报告"""
        for mock_cls in [mock_sec_llm, mock_arch_llm, mock_perf_llm]:
            instance = MagicMock()
            instance.review_code.return_value = []
            mock_cls.return_value = instance

        graph = create_review_graph()
        state: SharedReviewState = {
            "mode": "all",
            "target_files": [],
            "raw_comments": [],
            "final_report": "",
            "diff_branch": "",
            "target_path": ".",
            "output_format": "markdown",
            "progress": None,
        }

        with patch(
            "agent.nodes.coordinator._scan_directory",
            return_value=[
                {"path": "good.py", "content": "x = 1"},
            ],
        ):
            result = graph.invoke(state)

        report = result.get("final_report", "")
        assert report
        assert "No issues" in report or "0" in report


class TestE2EOutputFormats:
    """E2E tests for output format switching."""

    @patch("agent.nodes.base_expert.LLMClient")
    def test_json_output_format(self, mock_llm):
        """JSON 输出格式应返回有效 JSON"""
        graph = create_review_graph()
        state: SharedReviewState = {
            "mode": "all",
            "target_files": [],
            "raw_comments": [],
            "final_report": "",
            "diff_branch": "",
            "target_path": ".",
            "output_format": "json",
            "progress": None,
        }

        with patch("agent.nodes.coordinator._scan_directory", return_value=[]):
            result = graph.invoke(state)

        report = result.get("final_report", "")
        data = json.loads(report)
        assert "summary" in data
        assert "issues" in data

    @patch("agent.nodes.base_expert.LLMClient")
    def test_markdown_output_format(self, mock_llm):
        """Markdown 输出格式应包含标题"""
        graph = create_review_graph()
        state: SharedReviewState = {
            "mode": "all",
            "target_files": [],
            "raw_comments": [],
            "final_report": "",
            "diff_branch": "",
            "target_path": ".",
            "output_format": "markdown",
            "progress": None,
        }

        with patch("agent.nodes.coordinator._scan_directory", return_value=[]):
            result = graph.invoke(state)

        report = result.get("final_report", "")
        assert "# " in report


class TestE2EDeduplication:
    """E2E tests for issue deduplication across experts."""

    @patch("agent.nodes.base_expert.LLMClient")
    @patch("agent.nodes.base_expert.LLMClient")
    @patch("agent.nodes.base_expert.LLMClient")
    def test_cross_expert_deduplication(self, mock_perf_llm, mock_arch_llm, mock_sec_llm):
        """不同专家发现同一位置的同一问题时应去重"""
        duplicate_issue = {
            "file_path": "main.py",
            "line_number": 5,
            "category": "Security",
            "level": "Warning",
            "description": "Duplicate issue from expert A",
            "suggestion": "Fix A",
        }
        duplicate_issue_b = {
            "file_path": "main.py",
            "line_number": 5,
            "category": "Architecture",
            "level": "Warning",
            "description": "Duplicate issue from expert B",
            "suggestion": "Fix B",
        }

        mock_sec = MagicMock()
        mock_sec.review_code.return_value = [duplicate_issue]
        mock_sec_llm.return_value = mock_sec

        mock_arch = MagicMock()
        mock_arch.review_code.return_value = [duplicate_issue_b]
        mock_arch_llm.return_value = mock_arch

        mock_perf = MagicMock()
        mock_perf.review_code.return_value = []
        mock_perf_llm.return_value = mock_perf

        graph = create_review_graph()
        state: SharedReviewState = {
            "mode": "all",
            "target_files": [],
            "raw_comments": [],
            "final_report": "",
            "diff_branch": "",
            "target_path": ".",
            "output_format": "markdown",
            "progress": None,
        }

        with patch(
            "agent.nodes.coordinator._scan_directory",
            return_value=[
                {"path": "main.py", "content": "x = 1"},
            ],
        ):
            result = graph.invoke(state)

        # raw_comments should contain issues from both experts (dedup happens in reporter)
        raw_comments = result.get("raw_comments", [])
        assert len(raw_comments) >= 2

        report = result.get("final_report", "")
        assert report
        # After reporter deduplication, same file+line issues are merged
        # The report should contain evidence of the deduplication
        assert "main.py" in report


class TestE2EErrorRecovery:
    """E2E tests for error recovery."""

    @patch("agent.nodes.base_expert.LLMClient")
    @patch("agent.nodes.base_expert.LLMClient")
    @patch("agent.nodes.base_expert.LLMClient")
    def test_llm_returns_empty_result(self, mock_perf_llm, mock_arch_llm, mock_sec_llm):
        """LLM 返回空结果时流程应正常完成"""
        for mock_cls in [mock_sec_llm, mock_arch_llm, mock_perf_llm]:
            instance = MagicMock()
            instance.review_code.return_value = []
            mock_cls.return_value = instance

        graph = create_review_graph()
        state: SharedReviewState = {
            "mode": "all",
            "target_files": [],
            "raw_comments": [],
            "final_report": "",
            "diff_branch": "",
            "target_path": ".",
            "output_format": "markdown",
            "progress": None,
        }

        with patch(
            "agent.nodes.coordinator._scan_directory",
            return_value=[
                {"path": "file.py", "content": "x = 1"},
            ],
        ):
            result = graph.invoke(state)

        assert result.get("final_report")

    @patch("agent.nodes.base_expert.LLMClient")
    @patch("agent.nodes.base_expert.LLMClient")
    @patch("agent.nodes.base_expert.LLMClient")
    def test_llm_raises_exception(self, mock_perf_llm, mock_arch_llm, mock_sec_llm):
        """某个 LLM 调用抛异常时，其余专家应继续工作"""
        mock_sec = MagicMock()
        mock_sec.review_code.side_effect = Exception("API error")
        mock_sec_llm.return_value = mock_sec

        mock_arch = MagicMock()
        mock_arch.review_code.return_value = [
            {
                "file_path": "file.py",
                "line_number": 1,
                "category": "Architecture",
                "level": "Info",
                "description": "Test",
                "suggestion": "Test",
            }
        ]
        mock_arch_llm.return_value = mock_arch

        mock_perf = MagicMock()
        mock_perf.review_code.return_value = []
        mock_perf_llm.return_value = mock_perf

        graph = create_review_graph()
        state: SharedReviewState = {
            "mode": "all",
            "target_files": [],
            "raw_comments": [],
            "final_report": "",
            "diff_branch": "",
            "target_path": ".",
            "output_format": "markdown",
            "progress": None,
        }

        with patch(
            "agent.nodes.coordinator._scan_directory",
            return_value=[
                {"path": "file.py", "content": "x = 1"},
            ],
        ):
            result = graph.invoke(state)

        assert result.get("final_report")
