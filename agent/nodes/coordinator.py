import os
from pathlib import Path

from agent.state import SharedReviewState
from git_utils import filter_code_files, get_diff_files

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

SKIP_DIRS = {"venv", "__pycache__", "node_modules", ".git", ".vscode", ".idea", "dist", "build", "target", "bin", "obj"}


def _scan_directory(base_path: Path) -> list:
    """遍历目录收集代码文件"""
    target_files = []
    for dirpath, dirnames, filenames in os.walk(base_path):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]

        for filename in filenames:
            file_path = Path(dirpath) / filename
            if file_path.suffix in SUPPORTED_EXTENSIONS:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    target_files.append({"path": str(file_path), "content": content})
                except (UnicodeDecodeError, IOError):
                    continue
    return target_files


def coordinator_node(state: SharedReviewState) -> SharedReviewState:
    """协调者节点：扫描目录收集代码文件"""
    result: SharedReviewState = {**state}
    mode = state.get("mode", "all")
    result["mode"] = mode
    result["final_report"] = ""

    if mode == "all":
        target_files = _scan_directory(Path("."))

    elif mode == "diff":
        diff_branch = state.get("diff_branch", "")
        if not diff_branch:
            result["target_files"] = []
            result["diff_branch"] = ""
            return result

        changed_files = get_diff_files(diff_branch)
        changed_files = filter_code_files(changed_files)

        target_files = []
        for file_info in changed_files:
            path = file_info["path"]
            status = file_info["status"]
            diff_lines = file_info.get("diff_lines", [])

            if status == "deleted":
                target_files.append({"path": path, "status": status, "content": None, "diff_lines": []})
            else:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                    target_files.append({"path": path, "status": status, "content": content, "diff_lines": diff_lines})
                except (UnicodeDecodeError, IOError, FileNotFoundError):
                    continue

    elif mode == "path":
        target_path_str = state.get("target_path", "")
        if not target_path_str:
            result["target_files"] = []
            result["target_path"] = ""
            return result

        base_path = Path(target_path_str)
        if not base_path.exists():
            result["target_files"] = []
            return result

        if base_path.is_file() and base_path.suffix in SUPPORTED_EXTENSIONS:
            try:
                with open(base_path, "r", encoding="utf-8") as f:
                    content = f.read()
                target_files = [{"path": str(base_path), "content": content}]
            except (UnicodeDecodeError, IOError):
                target_files = []
        elif base_path.is_dir():
            target_files = _scan_directory(base_path)
        else:
            target_files = []

    else:
        target_files = []

    result["target_files"] = target_files
    return result
