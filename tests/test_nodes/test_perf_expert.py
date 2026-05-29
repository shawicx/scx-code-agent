import json
from unittest.mock import MagicMock, patch

import pytest

from agent.nodes.perf_expert import _review_single_file, perf_expert_node


class TestPerfExpert:
    """测试性能专家节点"""

    @pytest.fixture
    def performance_issue_response(self):
        """性能问题响应"""
        return [
            {
                "file_path": "performance.py",
                "line_number": 4,
                "category": "Performance",
                "level": "Warning",
                "description": "Nested loop with unnecessary iterations causes O(n*m) complexity",
                "suggestion": "def optimized(items):\n    return [item * i for item in items for i in range(100)]",
            }
        ]

    @pytest.fixture
    def mock_llm_client(self, performance_issue_response):
        """模拟 LLM 客户端"""
        client = MagicMock()
        client.review_code.return_value = performance_issue_response
        return client

    @pytest.fixture
    def mock_prompts(self):
        """模拟 prompts 加载"""
        return {"performance.md": "You are a performance expert.", "base.md": "Base prompt for code review."}

    def test_perf_expert_finds_performance_issue(self, sample_state, mock_llm_client, mock_prompts):
        """测试发现性能问题"""
        sample_state["target_files"] = [
            {
                "path": "performance.py",
                "content": (
                    "def slow():\n"
                    "    result = []\n"
                    "    for i in range(10000):\n"
                    "        result.append(i)\n"
                    "    return result"
                ),
            }
        ]

        with (
            patch("agent.nodes.perf_expert.LLMClient", return_value=mock_llm_client),
            patch("agent.nodes.perf_expert.load_prompt", side_effect=lambda x: mock_prompts.get(x, "")),
        ):
            result = perf_expert_node(sample_state)

        comments = result["raw_comments"]
        assert len(comments) >= 1
        assert comments[0]["category"] == "Performance"
        assert comments[0]["level"] == "Warning"

    def test_perf_expert_no_issues(self, sample_state, mock_llm_client, mock_prompts):
        """测试无性能问题"""
        sample_state["target_files"] = [{"path": "fast.py", "content": "def fast(): return [x * 2 for x in range(10)]"}]

        mock_llm_client.review_code.return_value = []

        with (
            patch("agent.nodes.perf_expert.LLMClient", return_value=mock_llm_client),
            patch("agent.nodes.perf_expert.load_prompt", side_effect=lambda x: mock_prompts.get(x, "")),
        ):
            result = perf_expert_node(sample_state)

        assert len(result["raw_comments"]) == 0

    def test_perf_expert_multiple_files(self, sample_state, mock_llm_client, mock_prompts):
        """测试多文件并发处理"""
        sample_state["target_files"] = [
            {"path": "slow1.py", "content": "for i in range(10000): pass"},
            {"path": "slow2.py", "content": "result = []\nfor i in range(1000):\n    result.append(str(i))"},
            {"path": "fast.py", "content": "def fast(): return [x * 2 for x in range(10)]"},
        ]

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                return [
                    {
                        "file_path": f"slow{call_count[0]}.py",
                        "line_number": 1,
                        "category": "Performance",
                        "level": "Warning",
                        "description": "Inefficient loop",
                        "suggestion": "Use list comprehension",
                    }
                ]
            return []

        mock_llm_client.review_code.side_effect = side_effect

        with (
            patch("agent.nodes.perf_expert.LLMClient", return_value=mock_llm_client),
            patch("agent.nodes.perf_expert.load_prompt", side_effect=lambda x: mock_prompts.get(x, "")),
        ):
            result = perf_expert_node(sample_state)

        assert mock_llm_client.review_code.call_count == 3
        assert len(result["raw_comments"]) == 2

    def test_perf_expert_empty_target_files(self, sample_state, mock_llm_client, mock_prompts):
        """测试空文件列表"""
        sample_state["target_files"] = []

        with (
            patch("agent.nodes.perf_expert.LLMClient", return_value=mock_llm_client),
            patch("agent.nodes.perf_expert.load_prompt", side_effect=lambda x: mock_prompts.get(x, "")),
        ):
            result = perf_expert_node(sample_state)

        assert len(result["raw_comments"]) == 0
        mock_llm_client.review_code.assert_not_called()

    def test_perf_expert_skip_deleted_files(self, sample_state, mock_llm_client, mock_prompts):
        """测试跳过已删除文件（content 为 None）"""
        sample_state["target_files"] = [
            {"path": "deleted.py", "content": None},
            {"path": "normal.py", "content": "code here"},
        ]

        with (
            patch("agent.nodes.perf_expert.LLMClient", return_value=mock_llm_client),
            patch("agent.nodes.perf_expert.load_prompt", side_effect=lambda x: mock_prompts.get(x, "")),
        ):
            perf_expert_node(sample_state)

        assert mock_llm_client.review_code.call_count == 1

    def test_perf_expert_diff_mode(self, sample_state, mock_llm_client, mock_prompts):
        """测试 diff 模式"""
        sample_state["mode"] = "diff"
        sample_state["target_files"] = [{"path": "test.py", "content": "code", "diff_lines": [5, 10]}]

        with (
            patch("agent.nodes.perf_expert.LLMClient", return_value=mock_llm_client),
            patch("agent.nodes.perf_expert.load_prompt", side_effect=lambda x: mock_prompts.get(x, "")),
        ):
            perf_expert_node(sample_state)

        mock_llm_client.review_code.assert_called_once()
        call_args = mock_llm_client.review_code.call_args
        assert call_args.kwargs.get("diff_lines") == [5, 10]

    def test_review_single_file(self, mock_llm_client, mock_prompts):
        """测试单个文件审查辅助函数"""
        file_info = {"path": "test.py", "content": "def test(): pass"}

        _review_single_file(
            client=mock_llm_client,
            file_info=file_info,
            role_prompt=mock_prompts["performance.md"],
            base_prompt=mock_prompts["base.md"],
            mode="all",
        )

        mock_llm_client.review_code.assert_called_once_with(
            file_path="test.py",
            content="def test(): pass",
            role_prompt=mock_prompts["performance.md"],
            base_prompt=mock_prompts["base.md"],
            diff_lines=[],
        )

    def test_review_single_file_with_diff_lines(self, mock_llm_client, mock_prompts):
        """测试带 diff_lines 的单文件审查"""
        file_info = {"path": "test.py", "content": "code", "diff_lines": [5, 10, 15]}

        _review_single_file(
            client=mock_llm_client,
            file_info=file_info,
            role_prompt=mock_prompts["performance.md"],
            base_prompt=mock_prompts["base.md"],
            mode="diff",
        )

        call_args = mock_llm_client.review_code.call_args
        assert call_args.kwargs.get("diff_lines") == [5, 10, 15]

    def test_review_single_file_none_content(self, mock_llm_client, mock_prompts):
        """测试 content 为 None 时返回空列表"""
        file_info = {"path": "deleted.py", "content": None}

        result = _review_single_file(
            client=mock_llm_client,
            file_info=file_info,
            role_prompt=mock_prompts["performance.md"],
            base_prompt=mock_prompts["base.md"],
            mode="all",
        )

        assert result == []
        mock_llm_client.review_code.assert_not_called()

    def test_review_single_file_exception_handling(self, mock_llm_client, mock_prompts):
        """测试异常处理"""
        file_info = {"path": "test.py", "content": "code"}

        mock_llm_client.review_code.side_effect = Exception("API Error")

        result = _review_single_file(
            client=mock_llm_client,
            file_info=file_info,
            role_prompt=mock_prompts["performance.md"],
            base_prompt=mock_prompts["base.md"],
            mode="all",
        )

        assert result == []

    def test_perf_expert_malformed_response(self, sample_state, mock_llm_client, mock_prompts):
        """测试处理格式错误的 LLM 响应"""
        sample_state["target_files"] = [{"path": "test.py", "content": "code"}]

        mock_llm_client.review_code.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)

        with (
            patch("agent.nodes.perf_expert.LLMClient", return_value=mock_llm_client),
            patch("agent.nodes.perf_expert.load_prompt", side_effect=lambda x: mock_prompts.get(x, "")),
        ):
            result = perf_expert_node(sample_state)

        assert result["raw_comments"] == []
