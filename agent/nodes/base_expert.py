import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from agent.state import AgentIssue, SharedReviewState
from config import load_config
from llm_client import LLMClient, load_prompt

logger = logging.getLogger(__name__)


_EXPERT_KEY_MAP = {
    "security.md": "security",
    "architecture.md": "architecture",
    "performance.md": "performance",
}


def _build_custom_rules_section(role_prompt_file: str) -> str:
    """根据配置构建追加到专家 prompt 的自定义规则段落。"""
    config = load_config()
    rules = config.review.custom_rules

    applicable = list(rules.general)
    expert_key = _EXPERT_KEY_MAP.get(role_prompt_file)
    if expert_key:
        applicable.extend(getattr(rules, expert_key, []))

    if not applicable:
        return ""

    lines = ["\n\n## 项目自定义审查规则\n\n", "你必须严格遵守以下项目特定的审查规则：\n\n"]
    for i, rule in enumerate(applicable, 1):
        lines.append(f"{i}. {rule}\n")
    return "".join(lines)


def _review_single_file(
    client: LLMClient, file_info: dict, role_prompt: str, base_prompt: str, mode: str
) -> List[AgentIssue]:
    """审查单个文件"""
    path = file_info.get("path", "")
    content = file_info.get("content")

    if content is None:
        return []

    diff_lines = file_info.get("diff_lines", []) if mode == "diff" else []

    try:
        return client.review_code(
            file_path=path, content=content, role_prompt=role_prompt, base_prompt=base_prompt, diff_lines=diff_lines
        )
    except Exception as e:
        logger.error(f"Error reviewing {path}: {e}")
        return []


def _run_expert(
    state: SharedReviewState,
    role_prompt_file: str,
    expert_name: str,
) -> Dict[str, List[AgentIssue]]:
    """共享专家节点逻辑：并发审查 + 进度展示"""
    client = LLMClient()
    role_prompt = load_prompt(role_prompt_file)
    base_prompt = load_prompt("base.md")

    custom_rules_section = _build_custom_rules_section(role_prompt_file)
    if custom_rules_section:
        role_prompt = role_prompt + custom_rules_section

    target_files = state.get("target_files", [])
    mode = state.get("mode", "all")
    progress: Optional[Any] = state.get("progress")

    reviewable = [f for f in target_files if f.get("content") is not None]
    total = len(reviewable)

    task_id = None
    if progress and total > 0:
        task_id = progress.add_task(expert_name, total=total)

    all_issues: List[AgentIssue] = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(_review_single_file, client, f, role_prompt, base_prompt, mode): f for f in reviewable
        }

        for future in as_completed(futures):
            try:
                issues = future.result()
                all_issues.extend(issues)
            except Exception as e:
                logger.error(f"Error in concurrent processing: {e}")

            if task_id is not None:
                progress.advance(task_id)  # type: ignore[union-attr]

    if task_id is not None:
        progress.update(task_id, description=f"{expert_name} ✓")  # type: ignore[union-attr]

    return {"raw_comments": all_issues}
