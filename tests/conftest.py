import shutil
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def temp_git_repo(tmp_path):
    """创建临时 git 仓库用于测试"""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # 初始化 git 仓库
    subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    yield repo_path

    # 清理
    shutil.rmtree(repo_path, ignore_errors=True)


@pytest.fixture
def sample_code_files():
    """示例代码文件内容"""
    return {
        "test.py": "def foo():\n    pass\n",
        "security.py": (
            "def query(user_input):\n" "    sql = f'SELECT * FROM users WHERE id={user_input}'\n" "    return sql\n"
        ),
        "performance.py": (
            "def slow_function(items):\n"
            "    result = []\n"
            "    for item in items:\n"
            "        for i in range(10000):\n"
            "            result.append(item * i)\n"
            "    return result\n"
        ),
        "good_code.py": "def efficient(items):\n    return [item * 2 for item in items]\n",
    }


@pytest.fixture
def mock_llm_client():
    """模拟 LLM 客户端"""
    client = Mock()
    yield client


@pytest.fixture
def sample_state():
    """示例 LangGraph 状态"""
    return {
        "mode": "all",
        "target_files": [],
        "raw_comments": [],
        "final_report": "",
        "diff_branch": "",
        "target_path": ".",
        "output_format": "markdown",
        "progress": None,
    }


@pytest.fixture
def load_llm_response():
    """加载 LLM 响应 fixture 的辅助函数"""

    def _load(fixture_name: str) -> str:
        fixture_path = Path(__file__).parent / "fixtures" / "llm_responses" / fixture_name
        if not fixture_path.exists():
            raise FileNotFoundError(f"Fixture not found: {fixture_path}")
        return fixture_path.read_text(encoding="utf-8")

    return _load


@pytest.fixture
def sample_py_project(tmp_path):
    """创建包含多个 Python 文件的临时项目目录"""
    files = {}
    files["main.py"] = (
        "import os\n"
        "\n"
        "def hello():\n"
        "    name = os.environ.get('USER', 'world')\n"
        "    print(f'Hello, {name}!')\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    hello()\n"
    )
    files["utils.py"] = (
        "def add(a, b):\n"
        "    return a + b\n"
        "\n"
        "def multiply(a, b):\n"
        "    result = 0\n"
        "    for i in range(b):\n"
        "        result = add(result, a)\n"
        "    return result\n"
    )
    files["db.py"] = (
        "import sqlite3\n"
        "\n"
        "def query(user_input):\n"
        "    conn = sqlite3.connect('test.db')\n"
        "    cursor = conn.cursor()\n"
        "    cursor.execute(\n"
        "        f\"SELECT * FROM users WHERE name='{user_input}'\"\n"
        "    )\n"
        "    return cursor.fetchall()\n"
    )
    files["config.py"] = (
        "API_KEY = 'sk-1234567890abcdef'\n" "DATABASE_URL = 'postgresql://admin:password@localhost/db'\n"
    )

    for filename, content in files.items():
        (tmp_path / filename).write_text(content, encoding="utf-8")

    return tmp_path


@pytest.fixture
def mock_llm_response_factory():
    """创建 mock LLM 响应的工厂函数"""

    def _create_response(issues=None):
        if issues is None:
            return "[]"

        import json

        return json.dumps(issues)

    return _create_response
