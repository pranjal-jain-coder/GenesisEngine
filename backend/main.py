"""
Genesis Engine Orchestrator - Main FastAPI Application.
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
import asyncio
import logging
import json
from pathlib import Path
from typing import Dict, Any
from session import ConnectionManager
from core.llm import LLMFactory
from core.log import setup_logging, console, log_task_start, log_task_done
from agents.architect import ArchitectAgent, TaskStatus
from agents.studio.graph import compile_graph
from services.git_manager import GitManager
from services.godot_rag import godot_rag

setup_logging()
logger = logging.getLogger("Orchestrator")

app = FastAPI(title="Genesis Engine Orchestrator")
manager = ConnectionManager()
project_tasks = {} # Store tasks for each project

# Initialize Agents
architect = None
studio_agent = None

console.rule("[bold cyan]Genesis Engine[/bold cyan]", style="cyan")
console.print("  [cyan]Orchestrator starting up…[/cyan]\n")

try:
    llm_provider = LLMFactory.get_provider()
    architect = ArchitectAgent(llm_provider)
    studio_agent = compile_graph(manager)
    logger.info("Agents initialized.")
except Exception as e:
    logger.error(f"Failed to initialize Agents: {e}")

# Pre-build Godot RAG index at startup (non-fatal if it fails)
try:
    godot_rag.build_index()
    logger.info("Godot RAG index ready.")
except Exception as e:
    logger.warning(f"Godot RAG index build failed (coder will run without it): {e}")

console.print("  [bold cyan]Ready.[/bold cyan]  Listening on [cyan]ws://0.0.0.0:8000/ws[/cyan]\n")

class Command(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Dict[str, Any] = {}
    id: int | str | None = None

class ChatRequest(BaseModel):
    message: str

@app.get("/status")
async def get_status():
    return {
        "projects": manager.get_connected_projects(),
        "count": len(manager.get_connected_projects())
    }

@app.post("/command")
async def send_command(project_path: str, command: Command):
    """Entry point for Agents to control Godot."""
    if not manager.is_connected(project_path):
        raise HTTPException(status_code=404, detail="Project not connected")
    
    success = await manager.send_command(project_path, command.dict())
    return {"status": "sent" if success else "failed", "project": project_path}

@app.post("/chat/{project_path:path}")
async def chat_with_architect(project_path: str, request: ChatRequest):
    """
    Chat with the Architect Agent.
    """
    try:
        result = architect.chat(request.message, project_path)
        return {
            "response": result.get("response", ""),
            "gdd": result.get("gdd"),
            "state": architect.state.value,
        }
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def run_studio_agent_step(project_path: str, next_task: Any, websocket: WebSocket, initial_state: Dict = None):
    """
    Runs or resumes the Studio Agent for a specific project and task.
    Handles LangGraph interrupts for human-in-the-loop steps.
    """
    config = {"configurable": {"thread_id": project_path}}
    try:
        if initial_state:
            logger.info(f"[StudioAgent] Initial invoke for task: {next_task.description}")
            log_task_start(next_task.description)
            await websocket.send_text(json.dumps({
                "type": "status",
                "content": f"Studio Agent starting task: {next_task.description}"
            }))
            await studio_agent.ainvoke(initial_state, config=config)
        else:
            logger.info(f"[StudioAgent] Resuming task: {next_task.description}")
            console.print(f"  [green]↩  Resuming[/green]  [dim]{next_task.description}[/dim]")
            await websocket.send_text(json.dumps({
                "type": "status",
                "content": f"Studio Agent resuming task: {next_task.description}"
            }))
            await studio_agent.ainvoke(None, config=config)
            
        # Inspect state after run
        state_full = await studio_agent.aget_state(config)
        
        if state_full.next:
            # We hit an interrupt (likely human_review)
            logger.info(f"[StudioAgent] Interrupted at node: {state_full.next}")
            pending = state_full.values.get("pending_review")
            if pending:
                logger.info(f"[StudioAgent] Pending asset review detected for: {pending.get('name')}")
                if not manager.is_connected(project_path):
                    logger.warning("[StudioAgent] Client disconnected before asset review could be sent")
                    return True  # Treat as finished — can't continue without client
                await websocket.send_text(json.dumps({
                    "type": "asset_review_request",
                    "asset": pending,
                    "task_id": next_task.id,
                    "content": f"Please review the acquired asset: {pending.get('name')}"
                }))
                return False # Not finished; waiting for human review
            else:
                # Interrupt fired but no pending review — auto-resume so graph can continue
                logger.warning("[StudioAgent] Interrupt at human_review with no pending review — auto-resuming")
                await studio_agent.ainvoke(None, config=config)
                state_full = await studio_agent.aget_state(config)
                # BUG 5: If still stuck after auto-resume, bail out rather than
                # falsely marking the task complete.
                if state_full.next:
                    logger.error("[StudioAgent] Still stuck at interrupt after auto-resume — bailing")
                    return True

        logger.info(f"[StudioAgent] Execution finished for task: {next_task.description}. Requesting verification.")
        
        # Do NOT complete the task yet. Ask for user verification.
        if manager.is_connected(project_path):
            try:
                await websocket.send_text(json.dumps({
                    "type": "task_verification_request",
                    "task_id": next_task.id,
                    "content": f"Task '{next_task.description}' finished. Please verify the result in Godot."
                }))
            except Exception:
                logger.warning("[StudioAgent] Client disconnected before verification request could be sent")
        
        return True # Execution step finished (interaction pending)

    except Exception as e:
        logger.error(f"[StudioAgent] Execution failed: {e}", exc_info=True)

        # Check if the client is still connected before trying to send anything.
        client_connected = manager.is_connected(project_path)

        if client_connected:
            try:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "content": f"Task execution failed: {str(e)}"
                }))
            except Exception:
                client_connected = False

        # On failure, revert the entire project to the state after the
        # previously completed task.
        logger.info("[StudioAgent] Attempting project revert to last successful task snapshot.")
        commits = GitManager.get_commits(project_path)
        target_commit = None
        for commit in commits:
            message = commit.get("message", "")
            if message.startswith("Completed Task:"):
                target_commit = commit["hash"]
                break

        if not target_commit and commits:
            target_commit = commits[-1]["hash"]

        if target_commit:
            revert_success = GitManager.revert_to_commit(project_path, target_commit)
            if revert_success:
                logger.info(f"[StudioAgent] Reverted project to commit {target_commit[:7]}")
                if architect:
                    architect.load_project(project_path)

                    if client_connected:
                        try:
                            current_gdd = architect.get_current_gdd()
                            await websocket.send_text(json.dumps({
                                "type": "project_reverted",
                                "content": "Project reverted to the last successful task snapshot due to a generation failure.",
                                "tasks": [t.model_dump(mode='json') for t in architect.tasks],
                                "gdd": json.loads(current_gdd.to_json()) if current_gdd else {}
                            }))
                        except Exception:
                            pass
        return True

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    project_path = None
    
    try:
        # 1. Handshake Phase: Wait for registration
        data = await websocket.receive_text()
        msg = json.loads(data)
        
        if msg.get("type") != "register" or not msg.get("project_path"):
            await websocket.close(code=1008)
            return

        project_path = msg["project_path"]
        await manager.register(project_path, websocket)
        console.print(f"\n  [bold cyan]⚡ Project connected:[/bold cyan]  [dim]{project_path}[/dim]")
        
        # Confirm registration
        await websocket.send_text(json.dumps({
            "jsonrpc": "2.0",
            "result": {"status": "connected", "path": project_path}
        }))

        # Ensure Git repository exists for version control
        GitManager.init_repo(project_path)

        if architect is None:
             await websocket.send_text(json.dumps({
                "type": "error",
                "content": "Server Error: Agents not initialized (LLM Provider failed). Check server logs."
            }))
             # Allow connection but maybe limit functionality? Or just return? 
             # For now, let's proceed but subsequent calls might fail. 
             # Actually, better to check before usage.

        # Project state is loaded on-demand when the client sends get_project_state

        # 2. Loop Phase: Background receive task + message queue.
        # The receive_loop runs as an independent asyncio Task so that
        # JSON-RPC responses from the Godot plugin are routed to
        # incoming_response() immediately — even while run_studio_agent_step
        # is executing.  Without this, the response futures created by
        # send_command() would never be resolved (receive_text() was never
        # called while the agent was running), causing every Godot command
        # to time out after 30 s.
        message_queue: asyncio.Queue = asyncio.Queue()

        async def receive_loop():
            try:
                while True:
                    data = await websocket.receive_text()
                    msg = json.loads(data)
                    if msg.get("id") and ("result" in msg or "error" in msg):
                        # JSON-RPC response — resolve the pending future now.
                        await manager.incoming_response(msg)
                    else:
                        # UI command / chat message — hand off to main loop.
                        await message_queue.put(msg)
            except Exception:
                # WebSocketDisconnect or any other error: signal shutdown.
                await message_queue.put(None)

        receive_task = asyncio.create_task(receive_loop())
        try:
            while True:
                msg = await message_queue.get()
                if msg is None:
                    break  # receive_loop ended (client disconnected)

                if architect is None:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "content": "Agents not initialized. Check server configuration."
                    }))
                    continue

                # Handle chat messages
                if msg.get("type") == "chat":
                    mode = msg.get("mode", "planning")
                    user_message = msg.get("message", "")

                    logger.info(f"[WebSocket] Incoming chat message mode={mode}, action={msg.get('action')}, project={project_path}")

                    try:
                        if mode == "planning":
                            # Use Architect agent (returns dict with response + optional gdd)
                            result = architect.chat(user_message, project_path)

                            # Build the response message
                            response_msg = {
                                "type": "chat_response",
                                "content": result.get("response", ""),
                            }

                            # Include GDD in the same message if it was updated
                            gdd_data = result.get("gdd")
                            if gdd_data:
                                response_msg["gdd"] = gdd_data

                            await websocket.send_text(json.dumps(response_msg))

                        elif mode == "execution":
                            action = msg.get("action")
                            logger.info(f"[Execution] Received execution action='{action}' for project={project_path}")

                            # 0. Get Project State (GDD + tasks) — called automatically on connect
                            if action == "get_project_state":
                                architect.load_project(project_path)
                                current_gdd = architect.get_current_gdd()
                                
                                # Send GDD state (or empty state if not found)
                                if current_gdd and current_gdd.filled_sections():
                                    await websocket.send_text(json.dumps({
                                        "type": "chat_response",
                                        "content": f"✅ Loaded existing project: **{current_gdd.title or 'Untitled'}**",
                                        "gdd": json.loads(current_gdd.to_json())
                                    }))
                                else:
                                    await websocket.send_text(json.dumps({
                                        "type": "chat_response",
                                        "content": "No existing Game Design Document found. Let's create one!",
                                        "gdd": {}
                                    }))
                                
                                # Always send tasks, even if empty, to refresh UI state
                                await websocket.send_text(json.dumps({
                                    "type": "task_list",
                                    "tasks": [t.model_dump(mode='json') for t in architect.tasks]
                                }))

                            # 1. Generate Tasks
                            elif action == "generate_tasks":
                                current_gdd = architect.get_current_gdd()
                                if not current_gdd:
                                    await websocket.send_text(json.dumps({
                                        "type": "error",
                                        "content": "No Game Design Document found. Please switch to Planning mode first."
                                    }))
                                else:
                                    await websocket.send_text(json.dumps({
                                        "type": "status",
                                        "content": "Generating tasks..."
                                    }))

                                    tasks = await architect.generate_tasks(current_gdd, project_path)
                                    # Send structured task list
                                    await websocket.send_text(json.dumps({
                                        "type": "task_list",
                                        "tasks": [t.model_dump(mode='json') for t in tasks]
                                    }))

                            # 2. Execute Next Task
                            elif action == "execute_next_task":
                                next_task = architect.get_next_task()
                                if not next_task:
                                    await websocket.send_text(json.dumps({
                                        "type": "error",
                                        "content": "No pending tasks found."
                                    }))
                                else:
                                    # Notify start
                                    next_task.status = TaskStatus.IN_PROGRESS
                                    architect.save_tasks(project_path) # Save in-progress state

                                    logger.info(f"[Execution] Starting next task: {next_task.id} - {next_task.description}")

                                    # Auto-commit before task execution
                                    GitManager.commit_state(project_path, f"State before Task: {next_task.description}")

                                    await websocket.send_text(json.dumps({
                                        "type": "task_started",
                                        "task_id": next_task.id,
                                        "content": f"Executing: {next_task.description}"
                                    }))

                                    ### STUDIO AGENT EXECUTION ###
                                    current_gdd = architect.get_current_gdd()

                                    # Build prior-work context from completed tasks
                                    completed_tasks = [t for t in architect.tasks if t.status == TaskStatus.COMPLETED]
                                    if completed_tasks:
                                        completed_lines = "\n".join(
                                            f"{i+1}. {t.description}"
                                            for i, t in enumerate(completed_tasks)
                                        )
                                        completed_tasks_ctx = f"Previously completed tasks:\n{completed_lines}"
                                    else:
                                        completed_tasks_ctx = ""

                                    initial_state = {
                                        "messages": [],
                                        "project_path": project_path,
                                        "gdd": current_gdd.model_dump() if current_gdd else {},
                                        "current_task": next_task.description,
                                        "file_context": {},
                                        "iterations": 0,
                                        "errors": [],
                                        "pending_review": None,
                                        "user_feedback": None,
                                        "approved_assets": {},
                                        "pending_actions": None,
                                        # New agentic loop state keys — must be initialised
                                        # explicitly so LangGraph doesn't carry stale values
                                        # from a previous thread checkpoint.
                                        "tool_loop_history": None,
                                        "pending_tool_call": None,
                                        "latest_screenshot": None,
                                        "completed_tasks_context": completed_tasks_ctx,
                                    }

                                    await run_studio_agent_step(project_path, next_task, websocket, initial_state)

                            # 3. Asset Feedback
                            elif action == "asset_feedback":
                                feedback = msg.get("feedback")
                                task_id = msg.get("task_id")
                                selected_index = msg.get("selected_index", 0)

                                next_task = architect.get_next_task() # Should be the in-progress one
                                if not next_task or next_task.id != task_id:
                                    # Try to find by ID if not next
                                    next_task = next((t for t in architect.tasks if t.id == task_id), None)

                                if not next_task:
                                    await websocket.send_text(json.dumps({
                                        "type": "error",
                                        "content": f"Task {task_id} not found."
                                    }))
                                else:
                                    logger.info(f"Received feedback for task {task_id}: {feedback} (selected_index={selected_index})")
                                    thread_config = {"configurable": {"thread_id": project_path}}

                                    # Fetch current state to ensure valid pending review (prevent double-submit)
                                    state_snap = await studio_agent.aget_state(thread_config)
                                    pending = state_snap.values.get("pending_review")

                                    if not pending:
                                        logger.warning(f"Ignoring duplicate/stale feedback for task {task_id} - no pending review found.")
                                        await websocket.send_text(json.dumps({
                                            "type": "error",
                                            "content": "No asset review pending. This may proceed from a duplicate click."
                                        }))
                                        continue

                                    # If user approved and there are multiple options, rename the
                                    # selected one to the canonical filename and delete the others.
                                    if feedback == "APPROVED":
                                        options = pending.get("options", [])
                                        canonical_name = pending.get("canonical_name", pending.get("name", ""))

                                        if options and canonical_name:
                                            sel = options[selected_index] if selected_index < len(options) else options[0]
                                            sel_path = Path(sel["asset_path"])
                                            canonical_path = sel_path.parent / (canonical_name + sel_path.suffix)

                                            # Rename selected option to canonical name
                                            if sel_path.exists() and sel_path != canonical_path:
                                                if canonical_path.exists():
                                                    canonical_path.unlink()
                                                sel_path.rename(canonical_path)
                                                logger.info(f"Renamed {sel_path.name} → {canonical_path.name}")

                                            # Remove rejected options
                                            for i, opt in enumerate(options):
                                                if i != selected_index:
                                                    p = Path(opt["asset_path"])
                                                    if p.exists():
                                                        p.unlink()
                                                        logger.info(f"Deleted rejected option: {p.name}")

                                        # Trigger filesystem scan so Godot sees the renamed file immediately
                                        try:
                                            await manager.send_command(project_path, {"method": "scan_filesystem", "params": {}})
                                        except Exception as scan_err:
                                            logger.warning(f"Failed to trigger scan after approval: {scan_err}")

                                    # Build state update with feedback and approved asset path
                                    state_update = {"user_feedback": feedback}

                                    if feedback == "APPROVED":
                                        # Propagate the approved asset's godot_path so the coder
                                        # knows the exact res:// path when setting node properties.
                                        existing_approved = state_snap.values.get("approved_assets") or {}

                                        if options and canonical_name:
                                            sel = options[selected_index] if selected_index < len(options) else options[0]

                                            # Derive the correct godot_path after the rename.
                                            # sel["godot_path"] points to the pre-rename filename;
                                            # rebuild it using the canonical name + same directory.
                                            original_godot = sel.get("godot_path", "")
                                            if original_godot:
                                                godot_dir = original_godot.rsplit("/", 1)[0]  # e.g. res://assets/sprites
                                                godot_ext = Path(sel["asset_path"]).suffix
                                                approved_godot_path = f"{godot_dir}/{canonical_name}{godot_ext}"
                                            else:
                                                # Fallback: infer from asset_path relative to project
                                                abs_sel = Path(sel["asset_path"])
                                                try:
                                                    rel = abs_sel.parent.relative_to(project_path)
                                                    approved_godot_path = f"res://{rel.as_posix()}/{canonical_name}{abs_sel.suffix}"
                                                except ValueError:
                                                    approved_godot_path = f"res://assets/sprites/{canonical_name}{abs_sel.suffix}"

                                            existing_approved[canonical_name] = approved_godot_path
                                            logger.info(f"Approved asset '{canonical_name}' → {approved_godot_path}")

                                        elif pending.get("godot_path"):
                                            asset_name = pending.get("name", "asset")
                                            existing_approved[asset_name] = pending["godot_path"]

                                        state_update["approved_assets"] = existing_approved

                                    await studio_agent.aupdate_state(thread_config, state_update)
                                    await run_studio_agent_step(project_path, next_task, websocket)

                            # 4. Regenerate Tasks
                            elif action == "regenerate_tasks":
                                feedback = msg.get("feedback", "")
                                if not feedback:
                                    await websocket.send_text(json.dumps({
                                        "type": "error",
                                        "content": "Feedback is required for regeneration."
                                    }))
                                else:
                                    await websocket.send_text(json.dumps({
                                        "type": "status",
                                        "content": "Regenerating tasks..."
                                    }))
                                    new_tasks = await architect.regenerate_tasks_from_feedback(feedback, project_path)
                                    await websocket.send_text(json.dumps({
                                        "type": "task_list",
                                        "tasks": [t.model_dump(mode='json') for t in new_tasks]
                                    }))

                            # 5. Update Task (Manual)
                            elif action == "update_task":
                                task_id = msg.get("task_id")
                                description = msg.get("description")
                                status = msg.get("status")
                                if architect.update_task(task_id, description, status, project_path):
                                    await websocket.send_text(json.dumps({
                                        "type": "task_list",
                                        "tasks": [t.model_dump(mode='json') for t in architect.tasks]
                                    }))
                                else:
                                    await websocket.send_text(json.dumps({
                                        "type": "error",
                                        "content": "Failed to update task."
                                    }))

                            # 6. Update GDD (Manual)
                            elif action == "update_gdd":
                                gdd_data = msg.get("gdd")
                                if gdd_data and architect.update_gdd_manual(gdd_data, project_path):
                                    await websocket.send_text(json.dumps({
                                        "type": "gdd_update",
                                        "gdd": json.loads(architect.current_gdd.to_json())
                                    }))
                                else:
                                    await websocket.send_text(json.dumps({
                                        "type": "error",
                                        "content": "Failed to update GDD."
                                    }))

                            # 7. Add Task (Manual)
                            elif action == "add_task":
                                description = msg.get("description", "New Task")
                                if architect.add_task(description, project_path):
                                    await websocket.send_text(json.dumps({
                                        "type": "task_list",
                                        "tasks": [t.model_dump(mode='json') for t in architect.tasks]
                                    }))
                                else:
                                    await websocket.send_text(json.dumps({
                                        "type": "error",
                                        "content": "Failed to add task."
                                    }))

                            # 8. Reorder Tasks
                            elif action == "reorder_tasks":
                                task_ids = msg.get("task_ids", [])
                                if architect.reorder_tasks(task_ids, project_path):
                                    await websocket.send_text(json.dumps({
                                        "type": "task_list",
                                        "tasks": [t.model_dump(mode='json') for t in architect.tasks]
                                    }))

                            # 9. Insert Task
                            elif action == "insert_task":
                                description = msg.get("description")
                                index = msg.get("index", 0)
                                if description and architect.insert_task(description, project_path, index):
                                    await websocket.send_text(json.dumps({
                                        "type": "task_list",
                                        "tasks": [t.model_dump(mode='json') for t in architect.tasks]
                                    }))

                            # 10. Task Verification
                            elif action == "task_verification_feedback":
                                feedback = msg.get("feedback")
                                task_id = msg.get("task_id")
                                
                                task = next((t for t in architect.tasks if t.id == task_id), None)
                                
                                if task:
                                    if feedback == "APPROVED":
                                        logger.info(f"Task {task_id} verified.")
                                        if task.status != TaskStatus.COMPLETED:
                                            architect.complete_current_task(project_path)
                                            GitManager.commit_state(project_path, f"Completed Task: {task.description}")

                                        await websocket.send_text(json.dumps({
                                            "type": "task_completed",
                                            "task_id": task.id,
                                            "tasks": [t.model_dump(mode='json') for t in architect.tasks]
                                        }))
                                        
                                    else:
                                        logger.info(f"Task {task_id} rejected: {feedback}")
                                        # Mark attempted as done
                                        if task.status != TaskStatus.COMPLETED:
                                            architect.complete_current_task(project_path)
                                            GitManager.commit_state(project_path, f"Attempted Task: {task.description}")

                                        # Create fix task
                                        fix_desc = f"Fix: {feedback} (from task '{task.description}')"
                                        architect.insert_task(fix_desc, project_path, index=0)

                                        await websocket.send_text(json.dumps({
                                            "type": "task_completed",
                                            "task_id": task.id,
                                            "tasks": [t.model_dump(mode='json') for t in architect.tasks]
                                        }))
                                        await websocket.send_text(json.dumps({
                                            "type": "status",
                                            "content": f"Issue logged. Added fix task: {fix_desc}"
                                        }))

                            # 11. Get Task/Commit History
                            elif action == "get_task_history":
                                commits = GitManager.get_commits(project_path)
                                await websocket.send_text(json.dumps({
                                    "type": "task_history",
                                    "commits": commits
                                }))

                            # 9. Revert Project
                            elif action == "revert_project":
                                commit_hash = msg.get("commit_hash")
                                if not commit_hash:
                                    await websocket.send_text(json.dumps({
                                        "type": "error",
                                        "content": "commit_hash is required to revert project."
                                    }))
                                    continue

                                revert_success = GitManager.revert_to_commit(project_path, commit_hash)
                                if revert_success:
                                    # Reload AI state (Tasks, GDD) from the reverted files
                                    architect.load_project(project_path)
                                    current_gdd = architect.get_current_gdd()

                                    await websocket.send_text(json.dumps({
                                        "type": "project_reverted",
                                        "content": f"Successfully reverted to task snapshot {commit_hash[:7]}.",
                                        "tasks": [t.model_dump(mode='json') for t in architect.tasks],
                                        "gdd": json.loads(current_gdd.to_json()) if current_gdd else {}
                                    }))
                                else:
                                    await websocket.send_text(json.dumps({
                                        "type": "error",
                                        "content": f"Failed to revert project to commit {commit_hash}."
                                    }))

                            else:
                                await websocket.send_text(json.dumps({
                                    "type": "error",
                                    "content": f"Unknown execution action: {action}"
                                }))

                    except WebSocketDisconnect:
                        raise
                    except RuntimeError as e:
                        if 'Cannot call "send"' in str(e):
                            raise
                        logger.error(f"Error processing chat message: {e}", exc_info=True)
                        try:
                            await websocket.send_text(json.dumps({
                                "type": "chat_response",
                                "error": str(e)
                            }))
                        except Exception:
                            pass
                    except Exception as e:
                        logger.error(f"Error processing chat message: {e}", exc_info=True)
                        try:
                            await websocket.send_text(json.dumps({
                                "type": "chat_response",
                                "error": str(e)
                            }))
                        except Exception:
                            pass

                # Handle other event types
                elif msg.get("type") == "event":
                    logger.info(f"Event from {project_path}: {msg}")
                else:
                    logger.info(f"Unknown message from {project_path}: {msg}")
        finally:
            receive_task.cancel()
            # Ensure the project is deregistered whether we exit via break or exception.
            if project_path:
                console.print(f"\n  [dim]🔌 Project disconnected: {project_path}[/dim]")
                await manager.disconnect(project_path)

    except WebSocketDisconnect:
        # Normal close — the inner finally block already called manager.disconnect.
        # Do NOT call it again here or it logs a spurious KeyError.
        console.print(f"\n  [dim]🔌 Project disconnected: {project_path}[/dim]")
        logger.info(f"WebSocket disconnected normally: {project_path}")
    except RuntimeError as e:
        if 'Cannot call "send"' in str(e):
            logger.info(f"WebSocket disconnected normally (send after close): {project_path}")
            if project_path:
                await manager.disconnect(project_path)
        else:
            logger.error(f"Connection error: {e}")
            if project_path:
                await manager.disconnect(project_path)
    except Exception as e:
        logger.error(f"Connection error: {e}")
        if project_path:
            await manager.disconnect(project_path)

if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting Genesis Engine Orchestrator...")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
        ws_ping_interval=None,
        ws_ping_timeout=None
    )
