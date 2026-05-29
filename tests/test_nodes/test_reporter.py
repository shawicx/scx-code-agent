import json

from agent.nodes.reporter import deduplicate_issues, reporter_node


class TestReporter:
    """测试报告官节点"""

    def test_reporter_markdown_output(self, sample_state):
        """测试 Markdown 格式输出"""
        sample_state["raw_comments"] = [
            {
                "file_path": "test.py",
                "line_number": 10,
                "category": "Security",
                "level": "Blocker",
                "description": "SQL injection",
                "suggestion": "Use parameterized queries",
            }
        ]
        sample_state["output_format"] = "markdown"

        result = reporter_node(sample_state)

        assert "final_report" in result
        assert "#" in result["final_report"]
        assert "Security" in result["final_report"]
        assert "test.py" in result["final_report"]
        assert "Blocker" in result["final_report"]

    def test_reporter_json_output(self, sample_state):
        """测试 JSON 格式输出"""
        sample_state["raw_comments"] = [
            {
                "file_path": "test.py",
                "line_number": 10,
                "category": "Security",
                "level": "Blocker",
                "description": "SQL injection",
                "suggestion": "Use parameterized queries",
            }
        ]
        sample_state["output_format"] = "json"

        result = reporter_node(sample_state)

        report_data = json.loads(result["final_report"])
        assert isinstance(report_data, dict)
        assert "summary" in report_data
        assert "issues" in report_data
        assert report_data["summary"]["total_issues"] == 1

    def test_reporter_empty_comments(self, sample_state):
        """测试无评论时的报告"""
        sample_state["raw_comments"] = []
        sample_state["output_format"] = "markdown"

        result = reporter_node(sample_state)

        assert "final_report" in result
        assert "No issues found" in result["final_report"]

    def test_reporter_empty_comments_json(self, sample_state):
        """测试无评论时的 JSON 报告"""
        sample_state["raw_comments"] = []
        sample_state["output_format"] = "json"

        result = reporter_node(sample_state)

        report_data = json.loads(result["final_report"])
        assert report_data["summary"]["total_issues"] == 0
        assert report_data["issues"] == []

    def test_reporter_deduplication(self, sample_state):
        """测试去重功能 - 同一位置相同问题只保留一个"""
        duplicate_comment = {
            "file_path": "test.py",
            "line_number": 10,
            "category": "Security",
            "level": "Blocker",
            "description": "Same issue",
            "suggestion": "Same fix",
        }
        sample_state["raw_comments"] = [duplicate_comment, duplicate_comment.copy()]
        sample_state["output_format"] = "json"

        result = reporter_node(sample_state)

        report_data = json.loads(result["final_report"])
        assert report_data["summary"]["total_issues"] == 1

    def test_reporter_dedup_keeps_more_severe(self, sample_state):
        """测试去重保留更严重的问题"""
        sample_state["raw_comments"] = [
            {
                "file_path": "test.py",
                "line_number": 10,
                "category": "Security",
                "level": "Warning",
                "description": "Minor issue",
                "suggestion": "Fix",
            },
            {
                "file_path": "test.py",
                "line_number": 10,
                "category": "Security",
                "level": "Blocker",
                "description": "Critical issue",
                "suggestion": "Fix ASAP",
            },
        ]
        sample_state["output_format"] = "json"

        result = reporter_node(sample_state)

        report_data = json.loads(result["final_report"])
        assert report_data["summary"]["total_issues"] == 1
        assert report_data["issues"][0]["level"] == "Blocker"

    def test_reporter_different_positions_not_deduped(self, sample_state):
        """测试不同位置的问题不被去重"""
        sample_state["raw_comments"] = [
            {
                "file_path": "test.py",
                "line_number": 10,
                "category": "Security",
                "level": "Blocker",
                "description": "Issue at line 10",
                "suggestion": "Fix",
            },
            {
                "file_path": "test.py",
                "line_number": 20,
                "category": "Security",
                "level": "Blocker",
                "description": "Issue at line 20",
                "suggestion": "Fix",
            },
        ]
        sample_state["output_format"] = "json"

        result = reporter_node(sample_state)

        report_data = json.loads(result["final_report"])
        assert report_data["summary"]["total_issues"] == 2

    def test_reporter_default_markdown(self, sample_state):
        """测试默认格式为 markdown"""
        sample_state["raw_comments"] = [
            {
                "file_path": "test.py",
                "line_number": 1,
                "category": "Performance",
                "level": "Warning",
                "description": "Slow code",
                "suggestion": "Optimize",
            }
        ]
        sample_state["output_format"] = "markdown"

        result = reporter_node(sample_state)

        assert "#" in result["final_report"]

    def test_reporter_multiple_categories(self, sample_state):
        """测试多类别问题输出"""
        sample_state["raw_comments"] = [
            {
                "file_path": "a.py",
                "line_number": 1,
                "category": "Security",
                "level": "Blocker",
                "description": "SQL injection",
                "suggestion": "Parameterize",
            },
            {
                "file_path": "b.py",
                "line_number": 5,
                "category": "Performance",
                "level": "Warning",
                "description": "N+1 query",
                "suggestion": "Batch queries",
            },
            {
                "file_path": "c.py",
                "line_number": 10,
                "category": "Architecture",
                "level": "Info",
                "description": "Missing type hints",
                "suggestion": "Add type hints",
            },
        ]
        sample_state["output_format"] = "markdown"

        result = reporter_node(sample_state)

        assert "Blocker" in result["final_report"]
        assert "Warning" in result["final_report"]
        assert "Info" in result["final_report"]


class TestDeduplicateIssues:
    """测试去重辅助函数"""

    def test_empty_list(self):
        """测试空列表"""
        assert deduplicate_issues([]) == []

    def test_no_duplicates(self):
        """测试无重复"""
        issues = [
            {
                "file_path": "a.py",
                "line_number": 1,
                "category": "Security",
                "level": "Blocker",
                "description": "A",
                "suggestion": "",
            },
            {
                "file_path": "b.py",
                "line_number": 2,
                "category": "Performance",
                "level": "Warning",
                "description": "B",
                "suggestion": "",
            },
        ]
        result = deduplicate_issues(issues)
        assert len(result) == 2

    def test_same_position_keeps_severe(self):
        """测试同一位置保留更严重的问题"""
        issues = [
            {
                "file_path": "a.py",
                "line_number": 1,
                "category": "Security",
                "level": "Warning",
                "description": "Low",
                "suggestion": "",
            },
            {
                "file_path": "a.py",
                "line_number": 1,
                "category": "Security",
                "level": "Blocker",
                "description": "High",
                "suggestion": "",
            },
        ]
        result = deduplicate_issues(issues)
        assert len(result) == 1
        assert result[0]["level"] == "Blocker"

    def test_same_level_merges_description(self):
        """测试同级别合并描述"""
        issues = [
            {
                "file_path": "a.py",
                "line_number": 1,
                "category": "Security",
                "level": "Warning",
                "description": "Issue A",
                "suggestion": "Fix A",
            },
            {
                "file_path": "a.py",
                "line_number": 1,
                "category": "Security",
                "level": "Warning",
                "description": "Issue B",
                "suggestion": "Fix B",
            },
        ]
        result = deduplicate_issues(issues)
        assert len(result) == 1
        assert "Issue A" in result[0]["description"]
        assert "Issue B" in result[0]["description"]
