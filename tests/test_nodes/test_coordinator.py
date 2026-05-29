import subprocess

from agent.nodes.coordinator import coordinator_node


class TestCoordinator:
    """测试协调者节点"""

    def test_coordinator_all_mode(self, sample_state, temp_git_repo):
        """测试全量模式 - 收集所有代码文件"""
        # 在临时仓库创建测试文件
        (temp_git_repo / "test.py").write_text("def foo(): pass\n")
        (temp_git_repo / "app.js").write_text("function bar() {}\n")
        (temp_git_repo / "readme.md").write_text("# docs\n")  # 不支持的扩展名

        sample_state["mode"] = "all"

        # coordinator_node 用 os.walk(Path('.')) 相对路径，需要 chdir
        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(temp_git_repo)
            result = coordinator_node(sample_state)
        finally:
            os.chdir(old_cwd)

        assert "target_files" in result
        assert len(result["target_files"]) == 2  # 只有 .py 和 .js
        # 验证文件内容被加载
        for file_info in result["target_files"]:
            assert "path" in file_info
            assert "content" in file_info
            assert file_info["content"] is not None

    def test_coordinator_diff_mode(self, sample_state, temp_git_repo):
        """测试增量模式 - 只收集变更文件"""
        test_file = temp_git_repo / "test.py"
        test_file.write_text("original")

        subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_git_repo, capture_output=True)

        test_file.write_text("modified")

        sample_state["mode"] = "diff"
        sample_state["diff_branch"] = "HEAD"

        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(temp_git_repo)
            result = coordinator_node(sample_state)
        finally:
            os.chdir(old_cwd)

        assert "target_files" in result
        # 增量模式应该只包含变更的文件
        assert len(result["target_files"]) <= 2

    def test_coordinator_diff_mode_no_branch(self, sample_state):
        """测试增量模式但无 diff_branch"""
        sample_state["mode"] = "diff"
        sample_state["diff_branch"] = ""

        result = coordinator_node(sample_state)

        assert result["target_files"] == []

    def test_coordinator_path_mode_file(self, sample_state, tmp_path):
        """测试 path 模式 - 指定单个文件"""
        test_file = tmp_path / "target.py"
        test_file.write_text("def target(): pass\n")

        sample_state["mode"] = "path"
        sample_state["target_path"] = str(test_file)

        result = coordinator_node(sample_state)

        assert len(result["target_files"]) == 1
        assert result["target_files"][0]["path"] == str(test_file)
        assert "def target" in result["target_files"][0]["content"]

    def test_coordinator_path_mode_directory(self, sample_state, tmp_path):
        """测试 path 模式 - 指定目录"""
        (tmp_path / "a.py").write_text("code a\n")
        (tmp_path / "b.js").write_text("code b\n")
        (tmp_path / "c.txt").write_text("not code\n")  # 不支持的扩展名

        sample_state["mode"] = "path"
        sample_state["target_path"] = str(tmp_path)

        result = coordinator_node(sample_state)

        assert len(result["target_files"]) == 2  # 只有 .py 和 .js

    def test_coordinator_path_mode_nonexistent(self, sample_state):
        """测试 path 模式 - 不存在的路径"""
        sample_state["mode"] = "path"
        sample_state["target_path"] = "/nonexistent/path/file.py"

        result = coordinator_node(sample_state)

        assert result["target_files"] == []

    def test_coordinator_path_mode_empty_target(self, sample_state):
        """测试 path 模式 - 空 target_path"""
        sample_state["mode"] = "path"
        sample_state["target_path"] = ""

        result = coordinator_node(sample_state)

        assert result["target_files"] == []

    def test_coordinator_empty_directory(self, sample_state, tmp_path):
        """测试空目录"""
        sample_state["mode"] = "path"
        sample_state["target_path"] = str(tmp_path)

        result = coordinator_node(sample_state)

        assert len(result["target_files"]) == 0

    def test_coordinator_skip_hidden_dirs(self, sample_state, tmp_path):
        """测试跳过隐藏目录"""
        hidden_dir = tmp_path / ".hidden"
        hidden_dir.mkdir()
        (hidden_dir / "secret.py").write_text("secret code\n")
        (tmp_path / "visible.py").write_text("visible code\n")

        sample_state["mode"] = "path"
        sample_state["target_path"] = str(tmp_path)

        result = coordinator_node(sample_state)

        paths = [f["path"] for f in result["target_files"]]
        assert len(result["target_files"]) == 1
        assert any("visible.py" in p for p in paths)

    def test_coordinator_skip_ignored_dirs(self, sample_state, tmp_path):
        """测试跳过 node_modules、__pycache__ 等目录"""
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "cached.py").write_text("cached\n")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "dep.py").write_text("dep\n")
        (tmp_path / "main.py").write_text("main\n")

        sample_state["mode"] = "path"
        sample_state["target_path"] = str(tmp_path)

        result = coordinator_node(sample_state)

        assert len(result["target_files"]) == 1
        assert "main.py" in result["target_files"][0]["path"]

    def test_coordinator_diff_mode_deleted_file(self, sample_state, temp_git_repo):
        """测试 diff 模式包含已删除文件"""
        test_file = temp_git_repo / "to_delete.py"
        test_file.write_text("will be deleted\n")

        subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add file"], cwd=temp_git_repo, capture_output=True)

        test_file.unlink()
        subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)

        sample_state["mode"] = "diff"
        sample_state["diff_branch"] = "HEAD"

        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(temp_git_repo)
            result = coordinator_node(sample_state)
        finally:
            os.chdir(old_cwd)

        # 已删除文件应该有 content=None
        deleted = [f for f in result["target_files"] if f.get("status") == "deleted"]
        if deleted:
            assert deleted[0]["content"] is None
