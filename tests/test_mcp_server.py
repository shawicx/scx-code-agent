from unittest.mock import MagicMock, patch

from mcp_server import _do_review_all, _do_review_diff, _do_review_path, _make_state, _run_review, mcp


class TestToolRegistration:
    """测试 MCP tools 注册正确"""

    def test_server_has_three_tools(self):
        tool_names = list(mcp._tool_manager._tools.keys())
        assert "review_path" in tool_names
        assert "review_diff" in tool_names
        assert "review_all" in tool_names

    def test_review_path_tool_schema(self):
        tool = mcp._tool_manager._tools["review_path"]
        assert tool.parameters["required"] == ["path"]
        props = tool.parameters["properties"]
        assert "path" in props
        assert "format" in props

    def test_review_diff_tool_schema(self):
        tool = mcp._tool_manager._tools["review_diff"]
        assert tool.parameters["required"] == ["base_branch"]
        props = tool.parameters["properties"]
        assert "base_branch" in props
        assert "format" in props

    def test_review_all_tool_schema(self):
        tool = mcp._tool_manager._tools["review_all"]
        props = tool.parameters["properties"]
        assert "format" in props


class TestMakeState:
    """测试 _make_state 辅助函数"""

    def test_default_state(self):
        state = _make_state()
        assert state["mode"] == ""
        assert state["target_files"] == []
        assert state["raw_comments"] == []
        assert state["output_format"] == "markdown"

    def test_state_with_overrides(self):
        state = _make_state(mode="path", target_path="/src")
        assert state["mode"] == "path"
        assert state["target_path"] == "/src"
        assert state["output_format"] == "markdown"


class TestReviewPath:
    """测试 review_path 逻辑"""

    def test_invalid_format(self):
        result = _do_review_path(path=".", format="xml")
        assert "Error" in result
        assert "xml" in result

    def test_nonexistent_path(self):
        result = _do_review_path(path="/nonexistent/path")
        assert "Error" in result
        assert "does not exist" in result

    def test_review_path_success(self, tmp_path):
        (tmp_path / "test.py").write_text("def foo(): pass\n")

        mock_client = MagicMock()
        mock_client.review_code.return_value = []

        with (
            patch("agent.nodes.sec_expert.LLMClient", return_value=mock_client),
            patch("agent.nodes.arch_expert.LLMClient", return_value=mock_client),
            patch("agent.nodes.perf_expert.LLMClient", return_value=mock_client),
            patch("agent.nodes.sec_expert.load_prompt", return_value=""),
            patch("agent.nodes.arch_expert.load_prompt", return_value=""),
            patch("agent.nodes.perf_expert.load_prompt", return_value=""),
        ):
            result = _do_review_path(path=str(tmp_path))

        assert result
        assert "No issues found" in result or "Code Review" in result


class TestReviewDiff:
    """测试 review_diff 逻辑"""

    def test_invalid_format(self):
        result = _do_review_diff(base_branch="main", format="xml")
        assert "Error" in result

    def test_empty_branch(self):
        result = _do_review_diff(base_branch="")
        assert "Error" in result

    def test_dangerous_branch_name(self):
        result = _do_review_diff(base_branch="--inject")
        assert "Error" in result


class TestReviewAll:
    """测试 review_all 逻辑"""

    def test_invalid_format(self):
        result = _do_review_all(format="xml")
        assert "Error" in result

    def test_review_all_success(self, tmp_path, monkeypatch):
        (tmp_path / "test.py").write_text("def foo(): pass\n")
        monkeypatch.chdir(tmp_path)

        mock_client = MagicMock()
        mock_client.review_code.return_value = []

        with (
            patch("agent.nodes.sec_expert.LLMClient", return_value=mock_client),
            patch("agent.nodes.arch_expert.LLMClient", return_value=mock_client),
            patch("agent.nodes.perf_expert.LLMClient", return_value=mock_client),
            patch("agent.nodes.sec_expert.load_prompt", return_value=""),
            patch("agent.nodes.arch_expert.load_prompt", return_value=""),
            patch("agent.nodes.perf_expert.load_prompt", return_value=""),
        ):
            result = _do_review_all()

        assert result


class TestRunReview:
    """测试 _run_review 核心逻辑"""

    def test_returns_final_report(self, tmp_path):
        (tmp_path / "test.py").write_text("x = 1\n")

        state = _make_state(mode="path", target_path=str(tmp_path))

        mock_client = MagicMock()
        mock_client.review_code.return_value = []

        with (
            patch("agent.nodes.sec_expert.LLMClient", return_value=mock_client),
            patch("agent.nodes.arch_expert.LLMClient", return_value=mock_client),
            patch("agent.nodes.perf_expert.LLMClient", return_value=mock_client),
            patch("agent.nodes.sec_expert.load_prompt", return_value=""),
            patch("agent.nodes.arch_expert.load_prompt", return_value=""),
            patch("agent.nodes.perf_expert.load_prompt", return_value=""),
        ):
            result = _run_review(state)

        assert isinstance(result, str)
        assert len(result) > 0
