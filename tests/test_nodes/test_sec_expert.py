import json
from unittest.mock import MagicMock, patch

import pytest

from agent.nodes.sec_expert import _review_single_file, sec_expert_node


class TestSecExpert:
    """测试安全专家节点"""

    @pytest.fixture
    def security_issue_response(self):
        """安全漏洞问题响应"""
        return [
            {
                "file_path": "security.py",
                "line_number": 2,
                "category": "Security",
                "level": "Blocker",
                "description": "SQL injection vulnerability: user input directly interpolated into SQL query",
                "suggestion": "Use parameterized queries instead",
            }
        ]

    @pytest.fixture
    def mock_llm_client(self, security_issue_response):
        """模拟 LLM 客户端"""
        client = MagicMock()
        client.review_code.return_value = security_issue_response
        return client

    @pytest.fixture
    def mock_prompts(self):
        """模拟 prompts 加载"""
        return {"security.md": "You are a security expert.", "base.md": "Base prompt for code review."}

    def test_sec_expert_finds_vulnerability(self, sample_state, mock_llm_client, mock_prompts):
        """测试发现安全漏洞"""
        # 准备状态
        sample_state["target_files"] = [
            {
                "path": "security.py",
                "content": "def query(user_input): return f'SELECT * FROM users WHERE id={user_input}'",
            }
        ]

        # Mock LLMClient 和 load_prompt
        with (
            patch("agent.nodes.sec_expert.LLMClient", return_value=mock_llm_client),
            patch("agent.nodes.sec_expert.load_prompt", side_effect=lambda x: mock_prompts.get(x, "")),
        ):
            # 执行
            result = sec_expert_node(sample_state)

            # 验证
            assert "raw_comments" in result
            comments = result["raw_comments"]
            assert len(comments) >= 1
            assert comments[0]["category"] == "Security"
            assert comments[0]["level"] == "Blocker"

    def test_sec_expert_no_vulnerabilities(self, sample_state, mock_llm_client, mock_prompts):
        """测试无漏洞情况"""
        sample_state["target_files"] = [
            {
                "path": "good_code.py",
                "content": "def safe_query(user_id): return query_db('SELECT * FROM users WHERE id=%s', (user_id,))",
            }
        ]

        # Mock 返回空列表
        mock_llm_client.review_code.return_value = []

        with (
            patch("agent.nodes.sec_expert.LLMClient", return_value=mock_llm_client),
            patch("agent.nodes.sec_expert.load_prompt", side_effect=lambda x: mock_prompts.get(x, "")),
        ):
            result = sec_expert_node(sample_state)

            assert len(result["raw_comments"]) == 0

    def test_sec_expert_multiple_files(self, sample_state, mock_llm_client, mock_prompts):
        """测试多文件处理"""
        sample_state["target_files"] = [
            {"path": "security.py", "content": "vulnerable code"},
            {"path": "another.py", "content": "more code"},
            {"path": "safe.py", "content": "safe code"},
        ]

        # 每次调用返回不同结果
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:  # 第一次调用返回问题
                return [
                    {
                        "file_path": "security.py",
                        "line_number": 1,
                        "category": "Security",
                        "level": "Blocker",
                        "description": "SQL injection",
                        "suggestion": "Fix it",
                    }
                ]
            return []  # 其他文件返回空

        mock_llm_client.review_code.side_effect = side_effect

        with (
            patch("agent.nodes.sec_expert.LLMClient", return_value=mock_llm_client),
            patch("agent.nodes.sec_expert.load_prompt", side_effect=lambda x: mock_prompts.get(x, "")),
        ):
            result = sec_expert_node(sample_state)

            # 应该被调用3次（3个文件）
            assert mock_llm_client.review_code.call_count == 3
            assert len(result["raw_comments"]) == 1

    def test_sec_expert_empty_target_files(self, sample_state, mock_llm_client, mock_prompts):
        """测试空文件列表"""
        sample_state["target_files"] = []

        with (
            patch("agent.nodes.sec_expert.LLMClient", return_value=mock_llm_client),
            patch("agent.nodes.sec_expert.load_prompt", side_effect=lambda x: mock_prompts.get(x, "")),
        ):
            result = sec_expert_node(sample_state)

            assert len(result["raw_comments"]) == 0
            # 不应该调用 review_code
            mock_llm_client.review_code.assert_not_called()

    def test_sec_expert_skip_deleted_files(self, sample_state, mock_llm_client, mock_prompts):
        """测试跳过已删除文件（content 为 None）"""
        sample_state["target_files"] = [
            {"path": "deleted.py", "content": None},  # 已删除文件
            {"path": "normal.py", "content": "code here"},
        ]

        with (
            patch("agent.nodes.sec_expert.LLMClient", return_value=mock_llm_client),
            patch("agent.nodes.sec_expert.load_prompt", side_effect=lambda x: mock_prompts.get(x, "")),
        ):
            sec_expert_node(sample_state)

            # 应该只调用一次（跳过 content=None 的文件）
            assert mock_llm_client.review_code.call_count == 1

    def test_sec_expert_diff_mode(self, sample_state, mock_llm_client, mock_prompts):
        """测试 diff 模式"""
        sample_state["mode"] = "diff"
        sample_state["target_files"] = [{"path": "test.py", "content": "code", "diff_lines": [5, 10]}]

        with (
            patch("agent.nodes.sec_expert.LLMClient", return_value=mock_llm_client),
            patch("agent.nodes.sec_expert.load_prompt", side_effect=lambda x: mock_prompts.get(x, "")),
        ):
            sec_expert_node(sample_state)

            # 验证 diff_lines 被传递
            mock_llm_client.review_code.assert_called_once()
            call_args = mock_llm_client.review_code.call_args
            assert call_args.kwargs.get("diff_lines") == [5, 10]

    def test_review_single_file(self, mock_llm_client, mock_prompts):
        """测试单个文件审查辅助函数"""
        file_info = {"path": "test.py", "content": "def test(): pass"}

        _review_single_file(
            client=mock_llm_client,
            file_info=file_info,
            role_prompt=mock_prompts["security.md"],
            base_prompt=mock_prompts["base.md"],
            mode="all",
        )

        mock_llm_client.review_code.assert_called_once_with(
            file_path="test.py",
            content="def test(): pass",
            role_prompt=mock_prompts["security.md"],
            base_prompt=mock_prompts["base.md"],
            diff_lines=[],
        )

    def test_review_single_file_with_diff_lines(self, mock_llm_client, mock_prompts):
        """测试带 diff_lines 的单文件审查"""
        file_info = {"path": "test.py", "content": "code", "diff_lines": [5, 10, 15]}

        _review_single_file(
            client=mock_llm_client,
            file_info=file_info,
            role_prompt=mock_prompts["security.md"],
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
            role_prompt=mock_prompts["security.md"],
            base_prompt=mock_prompts["base.md"],
            mode="all",
        )

        assert result == []
        mock_llm_client.review_code.assert_not_called()

    def test_review_single_file_exception_handling(self, mock_llm_client, mock_prompts):
        """测试异常处理"""
        file_info = {"path": "test.py", "content": "code"}

        # 模拟异常
        mock_llm_client.review_code.side_effect = Exception("API Error")

        result = _review_single_file(
            client=mock_llm_client,
            file_info=file_info,
            role_prompt=mock_prompts["security.md"],
            base_prompt=mock_prompts["base.md"],
            mode="all",
        )

        # 异常应该被捕获，返回空列表
        assert result == []

    def test_sec_expert_malformed_response(self, sample_state, mock_llm_client, mock_prompts):
        """测试处理格式错误的 LLM 响应"""
        sample_state["target_files"] = [{"path": "test.py", "content": "code"}]

        # 模拟 LLM 返回无效格式（引发解析异常）
        mock_llm_client.review_code.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)

        with (
            patch("agent.nodes.sec_expert.LLMClient", return_value=mock_llm_client),
            patch("agent.nodes.sec_expert.load_prompt", side_effect=lambda x: mock_prompts.get(x, "")),
        ):
            result = sec_expert_node(sample_state)

            # JSON 解析错误应该被捕获，返回空列表
            assert result["raw_comments"] == []
