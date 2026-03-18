import logging
from typing import Dict, Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from agents.studio.state import StudioState
from agents.studio.nodes import supervisor_node, coder_node, reviewer_node, human_review_node
from agents.studio.tools import GodotInterface, AssetInterface
from session import ConnectionManager

logger = logging.getLogger(__name__)

def should_continue(state: StudioState) -> Literal["coder", "end"]:
    """
    Determines whether to continue the loop or end the workflow.
    
    Returns:
        - "coder" if the reviewer found issues and iterations < 6
        - "end" if approved or max iterations reached
    """
    messages = state.get("messages", [])
    iterations = state.get("iterations", 0)

    # Check if we've exceeded max iterations
    if iterations > 5:
        logger.warning("Max iterations (6) reached. Ending workflow.")
        return "end"
    
    # Check the last message from the reviewer
    for msg in reversed(messages):
        if hasattr(msg, 'content') and "[Reviewer]" in msg.content:
            if "APPROVED" in msg.content:
                logger.info("Code approved by reviewer.")
                return "end"
            else:
                logger.info("Reviewer found issues. Sending back to coder.")
                return "coder"
    
    # Default to end if no reviewer message found
    return "end"

def after_coder(state: StudioState) -> Literal["human_review", "reviewer"]:
    """Only route through human_review (and its interrupt) when there's an asset to review."""
    if state.get("pending_review"):
        return "human_review"
    return "reviewer"

def should_review_continue(state: StudioState) -> Literal["coder", "reviewer", "wait"]:
    """
    Determines the next node after human_review.

    After APPROVED the coder broke out of its action loop early (stopped at the
    asset acquisition step). The remaining actions (create scene, write script,
    etc.) were never executed. We must route back to the coder so it can finish
    them — NOT to the reviewer, which would flag the work as incomplete and
    start another coder pass that re-acquires the already-approved asset.
    """
    pending = state.get("pending_review")
    feedback = state.get("user_feedback")

    if not pending:
        # Asset was just approved: coder needs to finish remaining task actions.
        if feedback == "APPROVED":
            return "coder"
        return "reviewer"

    # Pending review still set (shouldn't happen after human_review_node runs,
    # but handle defensively).
    if feedback == "APPROVED":
        return "reviewer"

    if feedback:
        # User provided regeneration feedback → redo asset acquisition.
        return "coder"

    return "wait"

def create_coder_wrapper(godot_interface: GodotInterface, asset_interface: AssetInterface):
    """Creates a wrapper for the coder node that includes the GodotInterface and AssetInterface."""
    async def coder_wrapper(state: StudioState) -> Dict:
        # Increment iterations
        new_iterations = state.get("iterations", 0) + 1
        result = await coder_node(state, godot_interface, asset_interface)
        result["iterations"] = new_iterations
        return result
    return coder_wrapper

def compile_graph(connection_manager: ConnectionManager):
    """
    Compiles and returns the Studio Agent workflow graph.
    
    Args:
        connection_manager: The ConnectionManager instance for Godot communication
        
    Returns:
        A compiled LangGraph runnable
    """
    # Create GodotInterface
    godot_interface = GodotInterface(connection_manager)
    
    # Create AssetInterface for asset acquisition tools
    asset_interface = AssetInterface(connection_manager)
    
    # Initialize the StateGraph
    workflow = StateGraph(StudioState)
    
    # Add nodes
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("coder", create_coder_wrapper(godot_interface, asset_interface))
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("human_review", human_review_node)
    
    # Add edges
    # Start -> Supervisor
    workflow.set_entry_point("supervisor")
    
    # Supervisor -> Coder
    workflow.add_edge("supervisor", "coder")
    
    # Coder -> Human Review (only when pending_review is set) or directly to Reviewer
    workflow.add_conditional_edges(
        "coder",
        after_coder,
        {"human_review": "human_review", "reviewer": "reviewer"}
    )
    
    # Conditional edge from Human Review
    workflow.add_conditional_edges(
        "human_review",
        should_review_continue,
        {
            "coder": "coder",
            "reviewer": "reviewer",
            "wait": END
        }
    )
    
    # Reviewer -> Coder or END
    workflow.add_conditional_edges(
        "reviewer",
        should_continue,
        {
            "coder": "coder",
            "end": END
        }
    )
    
    # Compile the graph with a checkpointer and interrupt
    memory = MemorySaver()
    app = workflow.compile(checkpointer=memory, interrupt_before=["human_review"])
    
    logger.info("Studio Agent graph compiled successfully with HITL support.")
    return app
