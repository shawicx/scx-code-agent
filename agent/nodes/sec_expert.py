from agent.nodes.base_expert import _run_expert
from agent.state import SharedReviewState


def sec_expert_node(state: SharedReviewState):
    """安全专家节点：审查代码安全缺陷"""
    return _run_expert(state, "security.md", "Security")
