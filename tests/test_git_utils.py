import os
import subprocess

import pytest

from git_utils import SUPPORTED_EXTENSIONS, filter_code_files, get_diff_files


class TestGetDiffFiles:
    def test_get_diff_files_real_repo(self, temp_git_repo):
        """真实仓库测试 diff 文件获取"""
        # 创建测试文件并提交
        test_file = temp_git_repo / "test.py"
        test_file.write_text("def foo(): pass")

        subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_git_repo, capture_output=True, check=True)

        # 创建测试分支
        subprocess.run(["git", "checkout", "-b", "test-branch"], cwd=temp_git_repo, capture_output=True, check=True)

        # 修改文件
        test_file.write_text("def foo():\n    return 1")

        # 获取 diff - 需要在临时仓库目录中运行
        original_cwd = os.getcwd()
        os.chdir(temp_git_repo)
        try:
            diff_files = get_diff_files("main")

            assert len(diff_files) > 0
            # 检查文件路径
            paths = [f["path"] for f in diff_files]
            assert "test.py" in paths

            # 验证返回结构
            file_info = diff_files[0]
            assert "path" in file_info
            assert "status" in file_info
            assert "diff_lines" in file_info
            assert file_info["status"] == "modified"
            assert isinstance(file_info["diff_lines"], list)
        finally:
            os.chdir(original_cwd)

    def test_get_diff_files_new_file(self, temp_git_repo):
        """测试新增文件的 diff"""
        # 创建初始提交
        (temp_git_repo / "initial.txt").write_text("content")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_git_repo, capture_output=True, check=True)

        # 创建分支并添加新文件
        subprocess.run(["git", "checkout", "-b", "new-file-branch"], cwd=temp_git_repo, capture_output=True, check=True)

        new_file = temp_git_repo / "new.py"
        new_file.write_text("def new_func(): pass")
        # 需要添加到 git 才能检测到变更
        subprocess.run(["git", "add", "new.py"], cwd=temp_git_repo, capture_output=True, check=True)

        original_cwd = os.getcwd()
        os.chdir(temp_git_repo)
        try:
            diff_files = get_diff_files("main")

            assert len(diff_files) > 0
            new_file_info = next((f for f in diff_files if f["path"] == "new.py"), None)
            assert new_file_info is not None
            assert new_file_info["status"] == "added"
        finally:
            os.chdir(original_cwd)

    def test_get_diff_files_deleted_file(self, temp_git_repo):
        """测试删除文件的 diff"""
        # 创建并提交文件
        test_file = temp_git_repo / "to_delete.py"
        test_file.write_text("def will_be_deleted(): pass")

        subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "add file"], cwd=temp_git_repo, capture_output=True, check=True)

        # 创建分支并删除文件
        subprocess.run(["git", "checkout", "-b", "delete-branch"], cwd=temp_git_repo, capture_output=True, check=True)

        test_file.unlink()

        original_cwd = os.getcwd()
        os.chdir(temp_git_repo)
        try:
            diff_files = get_diff_files("main")

            deleted_info = next((f for f in diff_files if f["path"] == "to_delete.py"), None)
            assert deleted_info is not None
            assert deleted_info["status"] == "deleted"
            # 删除的文件 diff_lines 应该是空列表
            assert deleted_info["diff_lines"] == []
        finally:
            os.chdir(original_cwd)

    def test_get_diff_files_line_numbers(self, temp_git_repo):
        """测试 diff 行号解析"""
        test_file = temp_git_repo / "example.py"
        test_file.write_text("line1\n" "line2\n" "line3\n" "line4\n" "line5\n")

        subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_git_repo, capture_output=True, check=True)

        # 创建分支并修改第 3-4 行
        subprocess.run(["git", "checkout", "-b", "modify-branch"], cwd=temp_git_repo, capture_output=True, check=True)

        test_file.write_text("line1\n" "line2\n" "modified line3\n" "modified line4\n" "line5\n")

        original_cwd = os.getcwd()
        os.chdir(temp_git_repo)
        try:
            diff_files = get_diff_files("main")

            example_info = next((f for f in diff_files if f["path"] == "example.py"), None)
            assert example_info is not None
            # 验证变更行号包含修改的行
            # diff_lines 记录的是新增行 (+ 开头) 的行号
            # 对于修改的行，新行号应该被记录
            assert len(example_info["diff_lines"]) >= 2
        finally:
            os.chdir(original_cwd)

    def test_get_diff_files_invalid_branch(self):
        """测试无效分支名"""
        # 测试以 - 开头的无效分支名
        with pytest.raises(ValueError, match="Invalid branch name"):
            get_diff_files("-evil-branch")

    def test_empty_diff(self, temp_git_repo):
        """测试无变更时的 diff"""
        # 创建初始提交
        (temp_git_repo / "test.txt").write_text("content")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_git_repo, capture_output=True, check=True)

        # 创建空提交后的状态
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "empty"], cwd=temp_git_repo, capture_output=True, check=True
        )

        # 获取 diff - 应该返回空列表（没有变更）
        original_cwd = os.getcwd()
        os.chdir(temp_git_repo)
        try:
            result = get_diff_files("HEAD~1")
            assert result == []
        finally:
            os.chdir(original_cwd)


class TestFilterCodeFiles:
    def test_filter_code_files(self):
        """测试代码文件过滤"""
        files = [
            {"path": "src/main.py", "status": "modified", "diff_lines": [1, 2, 3]},
            {"path": "docs/guide.md", "status": "modified", "diff_lines": [1]},
            {"path": "test.js", "status": "added", "diff_lines": [5]},
            {"path": "README.md", "status": "modified", "diff_lines": [1]},
            {"path": "deleted.py", "status": "deleted", "diff_lines": []},
            {"path": ".git/config", "status": "modified", "diff_lines": [1]},
        ]

        filtered = filter_code_files(files)

        # 应该保留 Python 和 JS 文件，以及已删除的文件
        paths = [f["path"] for f in filtered]
        assert "src/main.py" in paths
        assert "test.js" in paths
        assert "deleted.py" in paths  # 删除的文件应该保留

        # 应该过滤掉 markdown 文件
        assert "docs/guide.md" not in paths
        assert "README.md" not in paths

        # 应该过滤掉 .git 目录中的文件
        assert ".git/config" not in paths

    def test_filter_skip_dirs(self):
        """测试跳过指定目录"""
        files = [
            {"path": "src/main.py", "status": "modified", "diff_lines": [1]},
            {"path": "docs/api.py", "status": "modified", "diff_lines": [1]},
            {"path": ".git/util.py", "status": "modified", "diff_lines": [1]},
            {"path": "venv/lib/module.py", "status": "modified", "diff_lines": [1]},
            {"path": "node_modules/pkg/index.js", "status": "modified", "diff_lines": [1]},
            {"path": "__pycache__/compiled.py", "status": "modified", "diff_lines": [1]},
        ]

        filtered = filter_code_files(files)

        paths = [f["path"] for f in filtered]
        assert "src/main.py" in paths
        assert "docs/api.py" not in paths
        assert ".git/util.py" not in paths
        assert "venv/lib/module.py" not in paths
        assert "node_modules/pkg/index.js" not in paths
        assert "__pycache__/compiled.py" not in paths

    def test_filter_all_supported_extensions(self):
        """测试所有支持的扩展名"""
        # 创建各种代码类型文件
        files = [{"path": f"file{ext}", "status": "modified", "diff_lines": [1]} for ext in SUPPORTED_EXTENSIONS]

        filtered = filter_code_files(files)

        # 所有支持的扩展名都应该保留
        assert len(filtered) == len(SUPPORTED_EXTENSIONS)

    def test_filter_deleted_files_preserved(self):
        """测试删除的文件即使不是代码文件也被保留"""
        files = [
            {"path": "deleted.txt", "status": "deleted", "diff_lines": []},
            {"path": "deleted.md", "status": "deleted", "diff_lines": []},
            {"path": "normal.txt", "status": "modified", "diff_lines": [1]},
        ]

        filtered = filter_code_files(files)

        # 删除的文件应该被保留
        assert len(filtered) == 2
        paths = [f["path"] for f in filtered]
        assert "deleted.txt" in paths
        assert "deleted.md" in paths
        assert "normal.txt" not in paths
