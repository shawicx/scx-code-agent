from agent.nodes.base_expert import _run_expert
from agent.state import SharedReviewState


def perf_expert_node(state: SharedReviewState):
    """性能专家节点：审查代码性能问题"""
    return _run_expert(state, "performance.md", "⚡ Performance")
