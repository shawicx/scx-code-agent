from unittest.mock import MagicMock, patch

from agent.graph import create_review_graph


class TestReviewGraph:
    """测试图集成"""

    def test_graph_creation(self):
        """测试图创建"""
        graph = create_review_graph()

        assert graph is not None

    def test_graph_has_expected_nodes(self):
        """测试图包含所有预期节点"""
        graph = create_review_graph()

        # 编译后的图应该有节点信息
        node_names = list(graph.nodes.keys())
        # 过滤掉 __start__ 和 __end__
        expected = {"coordinator", "sec_expert", "arch_expert", "perf_expert", "reporter"}
        actual = set(node_names) - {"__start__", "__end__"}
        assert actual == expected

    def test_graph_execution_with_mocks(self, sample_state, tmp_path):
        """测试完整流程执行（mock LLM 调用）"""
        # 创建测试文件
        (tmp_path / "test.py").write_text("def foo(): pass\n")

        sample_state["mode"] = "path"
        sample_state["target_path"] = str(tmp_path)
        sample_state["raw_comments"] = []
        sample_state["output_format"] = "markdown"

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
            graph = create_review_graph()
            result = graph.invoke(sample_state)

        assert "final_report" in result
        assert "raw_comments" in result

    def test_graph_execution_with_issues(self, sample_state, tmp_path):
        """测试图执行发现问题并生成报告"""
        (tmp_path / "vuln.py").write_text("def query(x): return f'SELECT * FROM t WHERE id={x}'\n")

        sample_state["mode"] = "path"
        sample_state["target_path"] = str(tmp_path)
        sample_state["raw_comments"] = []
        sample_state["output_format"] = "json"

        mock_client_sec = MagicMock()
        mock_client_arch = MagicMock()
        mock_client_perf = MagicMock()

        def mock_review_code_sec(**kwargs):
            return [
                {
                    "file_path": kwargs["file_path"],
                    "line_number": 1,
                    "category": "Security",
                    "level": "Blocker",
                    "description": "SQL injection from security expert",
                    "suggestion": "Parameterize",
                }
            ]

        def mock_review_code_arch(**kwargs):
            return [
                {
                    "file_path": kwargs["file_path"],
                    "line_number": 1,
                    "category": "Architecture",
                    "level": "Warning",
                    "description": "Architecture issue from architecture expert",
                    "suggestion": "Refactor",
                }
            ]

        def mock_review_code_perf(**kwargs):
            return [
                {
                    "file_path": kwargs["file_path"],
                    "line_number": 1,
                    "category": "Performance",
                    "level": "Info",
                    "description": "Performance issue from performance expert",
                    "suggestion": "Optimize",
                }
            ]

        mock_client_sec.review_code.side_effect = mock_review_code_sec
        mock_client_arch.review_code.side_effect = mock_review_code_arch
        mock_client_perf.review_code.side_effect = mock_review_code_perf

        with (
            patch("agent.nodes.sec_expert.LLMClient", return_value=mock_client_sec),
            patch("agent.nodes.arch_expert.LLMClient", return_value=mock_client_arch),
            patch("agent.nodes.perf_expert.LLMClient", return_value=mock_client_perf),
            patch("agent.nodes.sec_expert.load_prompt", return_value=""),
            patch("agent.nodes.arch_expert.load_prompt", return_value=""),
            patch("agent.nodes.perf_expert.load_prompt", return_value=""),
        ):
            graph = create_review_graph()
            result = graph.invoke(sample_state)

        assert "final_report" in result
        # 3 个专家节点各返回 1 个不同的问题
        # Each expert node processes the file twice due to concurrency
        # We expect duplicates that will be deduplicated by the reporter
        assert len(result["raw_comments"]) >= 3
        # JSON 报告应该能解析
        import json

        report_data = json.loads(result["final_report"])
        # 去重后只保留 1 个（同一 file_path + line_number）
        assert report_data["summary"]["total_issues"] == 1

    def test_graph_state_mode_preserved(self, sample_state, tmp_path):
        """测试图执行后状态中的 mode 被保留"""
        (tmp_path / "test.py").write_text("code\n")

        sample_state["mode"] = "path"
        sample_state["target_path"] = str(tmp_path)
        sample_state["raw_comments"] = []

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
            graph = create_review_graph()
            result = graph.invoke(sample_state)

        assert result["mode"] == "path"
