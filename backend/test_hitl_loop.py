import asyncio
import json
import os
import sys
from unittest.mock import MagicMock

# Add current directory (backend) to sys.path
sys.path.append(os.getcwd())

# Mock and inject modules BEFORE other imports
mock_git = MagicMock()
sys.modules['services.git_manager'] = mock_git

# Correct imports
from agents.architect import Task  # noqa: E402
# Removed incorrect import

# Mock WebSocket
class MockWebSocket:
    def __init__(self):
        self.sent_messages = []
        self._receive_queue = asyncio.Queue()

    async def send_text(self, message):
        msg_obj = json.loads(message)
        print(f"[MockWS] Sent: {msg_obj.get('type')}")
        self.sent_messages.append(msg_obj)

    async def receive_text(self):
        return await self._receive_queue.get()

    def mock_receive(self, data):
        self._receive_queue.put_nowait(json.dumps(data))

async def test_hitl_loop():
    print("--- Testing HITL Asset Review Loop ---")
    
    project_path = "/tmp/genesis_hitl_test"
    os.makedirs(project_path, exist_ok=True)
    
    next_task = Task(id="task_1", name="Create Sword", description="Create a 32x32 pixel art magical sword sprite", type="asset")
    
    # Mock WebSocket
    websocket = MockWebSocket()
    
    # Initial state
    initial_state = {
        "messages": [],
        "project_path": project_path,
        "gdd": {},
        "current_task": next_task.description,
        "file_context": {},
        "iterations": 0,
        "errors": [],
        "pending_review": None,
        "user_feedback": None
    }
    
    from main import run_studio_agent_step, studio_agent
    
    config = {"configurable": {"thread_id": project_path}}
    
    print("\nPhase 1: Starting agent task...")
    finished = await run_studio_agent_step(project_path, next_task, websocket, initial_state)
    
    # Loop until finished (simulating main.py loop)
    # We'll use a timeout for the whole test to prevent infinite hangs
    try:
        while not finished:
            # Check if we have an asset review request
            review_msg = next((m for m in reversed(websocket.sent_messages) if m.get("type") == "asset_review_request"), None)
            
            if review_msg:
                # Correctly pull asset_path from the 'asset' object
                asset_info = review_msg.get('asset', {})
                print(f"DEBUG: Captured Asset Review Request for: {asset_info.get('name')}")
                print(f"DEBUG: Asset Path: {asset_info.get('asset_path')}")
                
                # If we haven't provided our 1st feedback yet
                if not any("[User Feedback]" in str(m.content) for m in (await studio_agent.aget_state(config)).values.get("messages", [])):
                    print("\nPhase 2: Sending user feedback 'Make the flames blue instead'...")
                    user_feedback = "The sword looks great, but make the flames blue instead of red."
                    await studio_agent.aupdate_state(config, {"user_feedback": user_feedback})
                    finished = await run_studio_agent_step(project_path, next_task, websocket)
                    continue
                else:
                    # We've already provided feedback, now approve
                    print("\nPhase 3: Approving the asset...")
                    await studio_agent.aupdate_state(config, {"user_feedback": "APPROVED"})
                    finished = await run_studio_agent_step(project_path, next_task, websocket)
                    continue
            else:
                print("No review request found yet. Waiting...")
                await asyncio.sleep(2)
                # This part is a bit tricky because run_studio_agent_step is sync-ish in terms of waiting for the interrupt.
                # If it didn't finish and didn't send a review request, something is wrong.
                break

        if any(m.get("type") == "task_completed" for m in websocket.sent_messages):
            print("\nTask Completed Successfully!")
            print("Test Finished Successfully!")
    except Exception as e:
        print(f"Test failed with error: {e}")

if __name__ == "__main__":
    asyncio.run(test_hitl_loop())
