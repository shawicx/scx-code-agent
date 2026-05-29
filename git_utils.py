import logging
import re
import subprocess
from typing import Dict, List

logger = logging.getLogger(__name__)

# 代码文件扩展名
SUPPORTED_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".go",
    ".rs",
    ".cpp",
    ".c",
    ".h",
    ".cs",
    ".swift",
    ".kt",
    ".rb",
    ".php",
}

# 需要跳过的目录
SKIP_DIRS = {"docs", ".git", "venv", "__pycache__", "node_modules"}


def get_diff_files(base_branch: str) -> List[Dict]:
    """获取相对于基准分支的变更文件列表

    Args:
        base_branch: 基准分支名称，如 'origin/main'

    Returns:
        [
            {
                'path': 'src/main.py',
                'status': 'modified',  # 'added' | 'modified' | 'deleted'
                'diff_lines': [10, 11, 12, 25]  # 变更行号，deleted 为 []
            },
            ...
        ]
    """
    # 防止 Git 参数注入：验证分支名不以 '-' 开头
    if not base_branch or base_branch.startswith("-"):
        raise ValueError(f"Invalid branch name: {base_branch}")

    result = subprocess.run(["git", "diff", base_branch], capture_output=True, text=True)

    # 检查 git 命令执行结果
    if result.returncode != 0:
        logger.error(f"Git diff failed: {result.stderr}")
        raise RuntimeError(f"Failed to get git diff: {result.stderr}")

    diff_output = result.stdout
    files = []

    file_pattern = re.compile(r"^diff --git a/(.*?) b/(.*?)$", re.MULTILINE)
    hunk_pattern = re.compile(r"^@@ -\d+,?\d* \+(\d+),(\d+) @@", re.MULTILINE)

    current_file = None
    current_status = None
    diff_lines: list[int] = []
    current_line_in_hunk = None  # 当前 hunk 中的行号

    lines = diff_output.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        file_match = file_pattern.match(line)
        if file_match:
            if current_file:
                files.append({"path": current_file, "status": current_status, "diff_lines": diff_lines})

            current_file = file_match.group(2)
            diff_lines = []
            current_line_in_hunk = None

            if i + 1 < len(lines):
                next_line = lines[i + 1]
                if next_line.startswith("new file"):
                    current_status = "added"
                elif next_line.startswith("deleted"):
                    current_status = "deleted"
                else:
                    current_status = "modified"
            i += 1

        elif line.startswith("@@"):
            hunk_match = hunk_pattern.search(line)
            if hunk_match:
                # 记录新 hunk 的起始行号
                current_line_in_hunk = int(hunk_match.group(1))

        elif current_file and current_line_in_hunk is not None:
            # 在 hunk 内容中，只记录以 + 开头的行（新增行）
            if line.startswith("+") and not line.startswith("++"):
                diff_lines.append(current_line_in_hunk)
            # 无论是什么行，都递增行号（除了 +++ 文件名行）
            if not line.startswith("+++") and not line.startswith("---"):
                current_line_in_hunk += 1
            elif line.startswith("+++"):
                current_line_in_hunk += 1

        i += 1

    if current_file:
        files.append({"path": current_file, "status": current_status, "diff_lines": diff_lines})

    return files


def filter_code_files(files: List[Dict]) -> List[Dict]:
    """过滤代码文件并排除指定目录

    Args:
        files: get_diff_files 返回的文件列表

    Returns:
        过滤后的文件列表
    """
    filtered = []
    for file_info in files:
        path = file_info["path"]

        if any(part in SKIP_DIRS for part in path.split("/")):
            continue

        if file_info["status"] == "deleted":
            filtered.append(file_info)
            continue

        if any(path.endswith(ext) for ext in SUPPORTED_EXTENSIONS):
            filtered.append(file_info)

    return filtered
