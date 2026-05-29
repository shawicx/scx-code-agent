import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List

from agent.state import AgentIssue, SharedReviewState
from llm_client import LLMClient, load_prompt

logger = logging.getLogger(__name__)


def _review_single_file(
    client: LLMClient, file_info: Dict, role_prompt: str, base_prompt: str, mode: str
) -> List[AgentIssue]:
    """审查单个文件的辅助函数（用于并发处理）"""
    path = file_info.get("path", "")
    content = file_info.get("content")

    if content is None:
        return []

    diff_lines = file_info.get("diff_lines", []) if mode == "diff" else []

    try:
        issues = client.review_code(
            file_path=path, content=content, role_prompt=role_prompt, base_prompt=base_prompt, diff_lines=diff_lines
        )
        return issues
    except Exception as e:
        logger.error(f"Error reviewing {path}: {e}")
        return []


def arch_expert_node(state: SharedReviewState) -> Dict[str, List[AgentIssue]]:
    """架构专家节点：审查代码架构与复用性（并发处理）"""
    client = LLMClient()

    role_prompt = load_prompt("architecture.md")
    base_prompt = load_prompt("base.md")

    target_files = state.get("target_files", [])
    mode = state.get("mode", "all")

    all_issues = []
    max_workers = 5

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_review_single_file, client, file_info, role_prompt, base_prompt, mode): file_info
            for file_info in target_files
            if file_info.get("content") is not None
        }

        for future in as_completed(futures):
            try:
                issues = future.result()
                all_issues.extend(issues)
            except Exception as e:
                logger.error(f"Error in concurrent processing: {e}")

    return {"raw_comments": all_issues}
