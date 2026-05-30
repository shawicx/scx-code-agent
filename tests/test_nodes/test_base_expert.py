from unittest.mock import MagicMock, patch

import pytest

from agent.nodes.base_expert import _review_single_file, _run_expert


class TestReviewSingleFile:
    """测试单个文件审查辅助函数"""

    @pytest.fixture
    def mock_client(self):
        return MagicMock()

    @pytest.fixture
    def mock_prompts(self):
        return {"role": "You are an expert.", "base": "Base prompt."}

    def test_basic_review(self, mock_client, mock_prompts):
        file_info = {"path": "test.py", "content": "def test(): pass"}

        _review_single_file(
            client=mock_client,
            file_info=file_info,
            role_prompt=mock_prompts["role"],
            base_prompt=mock_prompts["base"],
            mode="all",
        )

        mock_client.review_code.assert_called_once_with(
            file_path="test.py",
            content="def test(): pass",
            role_prompt=mock_prompts["role"],
            base_prompt=mock_prompts["base"],
            diff_lines=[],
        )

    def test_with_diff_lines(self, mock_client, mock_prompts):
        file_info = {"path": "test.py", "content": "code", "diff_lines": [5, 10, 15]}

        _review_single_file(
            client=mock_client,
            file_info=file_info,
            role_prompt=mock_prompts["role"],
            base_prompt=mock_prompts["base"],
            mode="diff",
        )

        call_args = mock_client.review_code.call_args
        assert call_args.kwargs.get("diff_lines") == [5, 10, 15]

    def test_none_content_returns_empty(self, mock_client, mock_prompts):
        file_info = {"path": "deleted.py", "content": None}

        result = _review_single_file(
            client=mock_client,
            file_info=file_info,
            role_prompt=mock_prompts["role"],
            base_prompt=mock_prompts["base"],
            mode="all",
        )

        assert result == []
        mock_client.review_code.assert_not_called()

    def test_exception_returns_empty(self, mock_client, mock_prompts):
        file_info = {"path": "test.py", "content": "code"}
        mock_client.review_code.side_effect = Exception("API Error")

        result = _review_single_file(
            client=mock_client,
            file_info=file_info,
            role_prompt=mock_prompts["role"],
            base_prompt=mock_prompts["base"],
            mode="all",
        )

        assert result == []


class TestRunExpert:
    """测试共享专家执行函数"""

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.review_code.return_value = [
            {
                "file_path": "test.py",
                "line_number": 1,
                "category": "Security",
                "level": "Blocker",
                "description": "SQL injection",
                "suggestion": "Fix it",
            }
        ]
        return client

    @pytest.fixture
    def mock_prompts(self):
        return {"security.md": "You are a security expert.", "base.md": "Base prompt."}

    def test_run_expert_without_progress(self, sample_state, mock_client, mock_prompts):
        """无 progress 时静默运行"""
        sample_state["target_files"] = [{"path": "test.py", "content": "code"}]
        sample_state["progress"] = None

        with (
            patch("agent.nodes.base_expert.LLMClient", return_value=mock_client),
            patch("agent.nodes.base_expert.load_prompt", side_effect=lambda x: mock_prompts.get(x, "")),
        ):
            result = _run_expert(sample_state, "security.md", "Security")

        assert len(result["raw_comments"]) == 1

    def test_run_expert_with_progress(self, sample_state, mock_client, mock_prompts):
        """有 progress 时调用 add_task 和 advance"""
        mock_progress = MagicMock()
        mock_progress.add_task.return_value = 0

        sample_state["target_files"] = [
            {"path": "a.py", "content": "code"},
            {"path": "b.py", "content": "code"},
        ]
        sample_state["progress"] = mock_progress

        with (
            patch("agent.nodes.base_expert.LLMClient", return_value=mock_client),
            patch("agent.nodes.base_expert.load_prompt", side_effect=lambda x: mock_prompts.get(x, "")),
        ):
            _run_expert(sample_state, "security.md", "Security")

        mock_progress.add_task.assert_called_once_with("Security", total=2)
        assert mock_progress.advance.call_count == 2
        mock_progress.update.assert_called_once()
        update_call = mock_progress.update.call_args
        assert "✓" in str(update_call)

    def test_run_expert_empty_files(self, sample_state, mock_client, mock_prompts):
        """空文件列表不创建进度条也不调用 LLM"""
        sample_state["target_files"] = []

        with (
            patch("agent.nodes.base_expert.LLMClient", return_value=mock_client),
            patch("agent.nodes.base_expert.load_prompt", side_effect=lambda x: mock_prompts.get(x, "")),
        ):
            result = _run_expert(sample_state, "security.md", "Security")

        assert result["raw_comments"] == []
        mock_client.review_code.assert_not_called()

    def test_run_expert_skips_deleted_files(self, sample_state, mock_client, mock_prompts):
        """跳过 content=None 的文件"""
        sample_state["target_files"] = [
            {"path": "deleted.py", "content": None},
            {"path": "normal.py", "content": "code"},
        ]

        with (
            patch("agent.nodes.base_expert.LLMClient", return_value=mock_client),
            patch("agent.nodes.base_expert.load_prompt", side_effect=lambda x: mock_prompts.get(x, "")),
        ):
            _run_expert(sample_state, "security.md", "Security")

        assert mock_client.review_code.call_count == 1
