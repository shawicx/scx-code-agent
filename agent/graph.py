from langgraph.graph import END, StateGraph

from agent.nodes.arch_expert import arch_expert_node
from agent.nodes.coordinator import coordinator_node
from agent.nodes.perf_expert import perf_expert_node
from agent.nodes.reporter import reporter_node
from agent.nodes.sec_expert import sec_expert_node
from agent.state import SharedReviewState


def create_review_graph():
    workflow = StateGraph(SharedReviewState)

    workflow.add_node("coordinator", coordinator_node)
    workflow.add_node("sec_expert", sec_expert_node)
    workflow.add_node("arch_expert", arch_expert_node)
    workflow.add_node("perf_expert", perf_expert_node)
    workflow.add_node("reporter", reporter_node)

    workflow.set_entry_point("coordinator")

    workflow.add_edge("coordinator", "sec_expert")
    workflow.add_edge("coordinator", "arch_expert")
    workflow.add_edge("coordinator", "perf_expert")

    workflow.add_edge("sec_expert", "reporter")
    workflow.add_edge("arch_expert", "reporter")
    workflow.add_edge("perf_expert", "reporter")

    workflow.add_edge("reporter", END)

    return workflow.compile()
