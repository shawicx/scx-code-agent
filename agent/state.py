import operator
from typing import Annotated, List, TypedDict


class AgentIssue(TypedDict):
    file_path: str
    line_number: int
    category: str
    level: str
    description: str
    suggestion: str


class SharedReviewState(TypedDict):
    mode: str
    target_files: List[dict]
    raw_comments: Annotated[List[AgentIssue], operator.add]
    final_report: str
    diff_branch: str
    target_path: str
    output_format: str
