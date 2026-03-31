from typing import TypedDict, List, Dict, Annotated, Optional, Any
import operator
from langchain_core.messages import BaseMessage

class StudioState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    project_path: str
    gdd: Dict
    current_task: str
    file_context: Dict
    iterations: int
    errors: List[str]
    pending_review: Optional[Dict]
    user_feedback: Optional[str]
    approved_assets: Optional[Dict]  # Maps asset name -> godot_path for approved assets
    latest_screenshot: Optional[str]  # Base64 screenshot from test_game, passed to reviewer
    # Agentic loop resumption state
    tool_loop_history: Optional[List[Dict[str, Any]]]  # Gemini conversation history saved mid-loop
    pending_tool_call: Optional[Dict[str, Any]]  # {name, args} of the paused asset tool call
    completed_tasks_context: Optional[str]  # Descriptions of already-completed tasks for prior-work awareness
    # Legacy (kept for backward compat with any in-flight states)
    pending_actions: Optional[List[Dict]]
