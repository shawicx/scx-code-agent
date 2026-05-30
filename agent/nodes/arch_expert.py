from agent.nodes.base_expert import _run_expert
from agent.state import SharedReviewState


def arch_expert_node(state: SharedReviewState):
    """架构专家节点：审查代码架构与复用性"""
    return _run_expert(state, "architecture.md", "🏗 Architecture")
