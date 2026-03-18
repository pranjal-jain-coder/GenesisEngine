"""
Architect Agent — ReAct/Tool-Calling Design Partner.

The Architect converses naturally with the user about their game idea and uses
tools (update_gdd, get_gdd_status, get_current_gdd) to incrementally build the
Game Design Document as details are agreed upon.
"""
from enum import Enum
from typing import List, Optional, Dict, Any
import json
import logging
from pathlib import Path
from core.llm import LLMProvider
from core.log import console
from models.gdd import GameDesignDocument, GameMechanic, ArtStyle, SystemDetail
from pydantic import BaseModel
import google.generativeai as genai

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared models (Task, TaskList, etc.) — unchanged from original
# ---------------------------------------------------------------------------

class AgentState(Enum):
    IDLE = "IDLE"
    CHATTING = "CHATTING"       # Actively conversing (replaces DRAFTING/REFINING)

class TaskStatus(Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class Task(BaseModel):
    id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    feedback: Optional[str] = None

class TaskList(BaseModel):
    tasks: List[Task]


# ---------------------------------------------------------------------------
# Tool declarations for Gemini function-calling
# Uses genai.protos.Schema with proper Type enums (not raw JSON Schema dicts).
# ---------------------------------------------------------------------------

_T = genai.protos.Type  # shorthand

_TOOL_DECLARATIONS = [
    genai.protos.FunctionDeclaration(
        name="update_gdd",
        description=(
            "Update one or more sections of the Game Design Document. "
            "Call this whenever the user agrees on a detail or you want to record something. "
            "Pass a JSON string where keys are GDD field names and values are the new content. "
            "Valid keys: title, genre, target_audience, core_loop, story, theme, controls, "
            "progression, audio_style, art_style (object with visual_style, color_palette, perspective), "
            "mechanics (list of objects with name, description, complexity_score), "
            "levels (list of strings), enemies (list of strings), items (list of strings), "
            "detailed_systems (list of objects with name, description, components, implementation_guide). "
            "Example: {\"title\": \"Space Quest\", \"genre\": \"Adventure\"}"
        ),
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "updates_json": genai.protos.Schema(
                    type_=_T.STRING,
                    description=(
                        "A JSON string containing updates. Example: "
                        '{\"title\": \"My Game\", \"genre\": \"RPG\"}'
                    ),
                ),
            },
            required=["updates_json"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="get_gdd_status",
        description=(
            "Returns a summary of which GDD sections are filled and which are still empty. "
            "Use this to decide what to ask the user about next."
        ),
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={},
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="get_current_gdd",
        description=(
            "Returns the full current Game Design Document as JSON. "
            "Use this when you need to reference existing content."
        ),
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={},
        ),
    ),
]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are the **Architect** — a creative, collaborative game design partner inside the Genesis Engine.

Your job is to help the user flesh out their game idea into a detailed Game Design Document (GDD) through natural conversation.

## Rules
1. **Be conversational.** Ask focused questions (2–3 at a time), suggest interesting ideas, and validate with the user before committing.
2. **Never hallucinate major details.** If something is important (core mechanics, story, art style), always confirm with the user before writing it to the GDD.
3. **Use your tools** to record agreed-upon details. Call `update_gdd` whenever the user confirms a detail. Call `get_gdd_status` to see what sections still need filling.
4. **Be a smart assistant, not an author.** Propose options like: "For the art style, I'm thinking either pixel art or low-poly — which feels right for your vision?" rather than deciding unilaterally.
5. **Start light.** On the first message, focus on understanding the core concept: title, genre, and core gameplay loop. Don't try to fill everything at once.
6. **Keep responses concise.** 2–4 paragraphs max. Use markdown formatting for readability.
7. **Progressive disclosure.** After core details are set, suggest which section to tackle next: "We've got the basics down! Want to work on mechanics, story, or art style next?"
8. Minor details (folder structure, default items) you can fill in yourself without asking.
9. **Implementation Guide.** Once the core concept and systems are agreed upon, independently flesh out the `detailed_systems` section with step-by-step implementation guides and required components for the Coder agent to build.

## Current GDD Status
{gdd_status}
"""


# ---------------------------------------------------------------------------
# ArchitectAgent
# ---------------------------------------------------------------------------

class ArchitectAgent:
    """
    The Architect Agent uses ReAct-style tool-calling to conversationally
    build a Game Design Document. It chats naturally and calls tools to
    incrementally update the GDD as details are agreed upon.
    """

    # Maximum number of LLM re-invocations per single user message
    # (to handle consecutive tool calls without infinite loops)
    MAX_TOOL_DEPTH = 3

    def __init__(self, llm_provider: LLMProvider):
        self.llm = llm_provider
        self.state = AgentState.IDLE
        self.history: List[Dict[str, Any]] = []   # Gemini-format history
        self.current_gdd: Optional[GameDesignDocument] = None
        self.tasks: List[Task] = []
        self.current_task_index: int = 0

    # -------------------------------------------------------------------
    # Public chat entry point
    # -------------------------------------------------------------------

    def chat(self, user_input: str, project_path: str) -> Dict[str, Any]:
        """Process a user message and return a response + optional GDD update.
        
        Args:
            user_input: The message from the user.
            project_path: The path to the game project.
        
        Returns:
            {"response": str, "gdd": dict | None}
            - response: The agent's conversational reply.
            - gdd: The updated GDD dict if it was modified, else None.
        """
        # Ensure we have a GDD object to work with
        if self.current_gdd is None:
            self.current_gdd = GameDesignDocument()

        self.state = AgentState.CHATTING
        preview = (user_input[:70] + "…") if len(user_input) > 70 else user_input
        console.print(f"\n  [bold cyan]💬 Architect chat:[/bold cyan]  [dim]{preview}[/dim]")

        # Append user message to history
        self.history.append({
            "role": "user",
            "parts": [user_input],
        })

        # Build the system prompt with current GDD status
        system_prompt = _SYSTEM_PROMPT.format(
            gdd_status=self.current_gdd.completion_summary()
        )

        # Track whether the GDD was modified during this turn
        gdd_modified = False

        # ReAct loop: call LLM, handle tool calls, repeat if needed
        for depth in range(self.MAX_TOOL_DEPTH):
            result = self.llm.generate_with_tools(
                system_instruction=system_prompt,
                history=self.history,
                tool_declarations=_TOOL_DECLARATIONS,
            )

            text = result.get("text")
            tool_calls = result.get("tool_calls")
            raw_parts = result.get("raw_parts", [])

            # --- Case 1: Pure text response, no tools ---
            if not tool_calls:
                response_text = text or "I'm here to help design your game! What's your idea?"
                self.history.append({
                    "role": "model",
                    "parts": raw_parts if raw_parts else [response_text],
                })
                return self._build_response(response_text, gdd_modified, project_path)

            # --- Case 2: Tool calls (possibly with text) ---
            # Record the model's exact response in history (including function_call and thought parts)
            self.history.append({"role": "model", "parts": raw_parts})

            # Execute each tool call and collect results
            function_response_parts = []
            for tc in tool_calls:
                logger.info("Architect tool call: %s", tc["name"])
                tool_result = self._execute_tool(tc["name"], tc["args"], project_path)
                if tc["name"] == "update_gdd":
                    gdd_modified = True
                    console.print("  [dim]📝 GDD updated[/dim]")
                function_response_parts.append({
                    "function_response": {
                        "name": tc["name"],
                        "response": {"result": tool_result},
                    }
                })

            # Append tool results back into history so the LLM can formulate a response
            self.history.append({
                "role": "user",
                "parts": function_response_parts,
            })

            # Continue the loop — the LLM will now see the tool results and
            # either respond with text or make more tool calls

        # If we exhausted the depth limit, return whatever text we have
        fallback = text or "I've updated the design document. What would you like to work on next?"
        self.history.append({"role": "model", "parts": [fallback]})
        return self._build_response(fallback, gdd_modified, project_path)

    # -------------------------------------------------------------------
    # Tool execution
    # -------------------------------------------------------------------

    def _execute_tool(self, tool_name: str, args: dict, project_path: str) -> str:
        """Execute a tool call and return a string result.
        
        All tool calls are wrapped in try/except so a bad LLM output
        never crashes the server.
        """
        try:
            if tool_name == "update_gdd":
                return self._tool_update_gdd(args, project_path)
            elif tool_name == "get_gdd_status":
                return self._tool_get_gdd_status()
            elif tool_name == "get_current_gdd":
                return self._tool_get_current_gdd()
            else:
                return f"Unknown tool: {tool_name}"
        except Exception as e:
            logger.error(f"Tool execution error ({tool_name}): {e}", exc_info=True)
            return f"Error executing {tool_name}: {str(e)}"

    def _tool_update_gdd(self, args: dict, project_path: str) -> str:
        """Apply partial updates to the GDD.
        
        The LLM passes updates_json as a JSON string (or sometimes a raw dict).
        We parse it robustly to handle model unpredictability.
        """
        # The tool schema asks for updates_json (string), but handle both formats
        raw = args.get("updates_json") or args.get("updates", {})
        
        if isinstance(raw, str):
            try:
                updates = json.loads(raw)
            except json.JSONDecodeError as e:
                return f"Invalid JSON in updates_json: {e}"
        elif isinstance(raw, dict):
            updates = raw
        else:
            return f"Expected updates_json to be a JSON string or dict, got {type(raw).__name__}."
        
        if not updates or not isinstance(updates, dict):
            return "No valid updates provided."

        applied = []
        skipped = []

        for key, value in updates.items():
            if not hasattr(self.current_gdd, key):
                skipped.append(f"{key} (unknown field)")
                continue

            try:
                # Handle nested model fields
                if key == "art_style" and isinstance(value, dict):
                    if self.current_gdd.art_style is None:
                        self.current_gdd.art_style = ArtStyle(**value)
                    else:
                        # Merge with existing
                        existing = self.current_gdd.art_style.model_dump()
                        existing.update(value)
                        self.current_gdd.art_style = ArtStyle(**existing)
                    applied.append(key)

                elif key == "mechanics" and isinstance(value, list):
                    new_mechanics = []
                    for m in value:
                        if isinstance(m, dict):
                            # Provide defaults for missing required fields
                            m.setdefault("complexity_score", 5)
                            m.setdefault("description", "")
                            m.setdefault("name", "Unnamed Mechanic")
                            new_mechanics.append(GameMechanic(**m))
                        elif isinstance(m, GameMechanic):
                            new_mechanics.append(m)
                    # Append to existing rather than replacing
                    existing_names = {em.name for em in (self.current_gdd.mechanics or [])}
                    for nm in new_mechanics:
                        if nm.name not in existing_names:
                            self.current_gdd.mechanics.append(nm)
                            existing_names.add(nm.name)
                        else:
                            # Update existing mechanic
                            for i, em in enumerate(self.current_gdd.mechanics):
                                if em.name == nm.name:
                                    self.current_gdd.mechanics[i] = nm
                                    break
                    applied.append(key)

                elif key == "detailed_systems" and isinstance(value, list):
                    new_systems = []
                    for s in value:
                        if isinstance(s, dict):
                            s.setdefault("description", "")
                            s.setdefault("name", "Unnamed System")
                            s.setdefault("components", [])
                            s.setdefault("implementation_guide", "")
                            new_systems.append(SystemDetail(**s))
                        elif isinstance(s, SystemDetail):
                            new_systems.append(s)
                    # Append or update existing systems by name
                    existing_names = {es.name for es in (self.current_gdd.detailed_systems or [])}
                    for ns in new_systems:
                        if ns.name not in existing_names:
                            self.current_gdd.detailed_systems.append(ns)
                            existing_names.add(ns.name)
                        else:
                            # Update existing system
                            for i, es in enumerate(self.current_gdd.detailed_systems):
                                if es.name == ns.name:
                                    self.current_gdd.detailed_systems[i] = ns
                                    break
                    applied.append(key)

                elif key in ("levels", "enemies", "items") and isinstance(value, list):
                    # Append new unique entries
                    existing = set(getattr(self.current_gdd, key) or [])
                    for item in value:
                        if isinstance(item, str) and item not in existing:
                            getattr(self.current_gdd, key).append(item)
                            existing.add(item)
                    applied.append(key)

                else:
                    # Simple scalar field
                    setattr(self.current_gdd, key, value)
                    applied.append(key)

            except Exception as e:
                skipped.append(f"{key} (error: {str(e)})")

        # Persist to disk
        self._save_gdd(project_path)

        result_parts = []
        if applied:
            result_parts.append(f"Updated: {', '.join(applied)}")
        if skipped:
            result_parts.append(f"Skipped: {', '.join(skipped)}")
        return ". ".join(result_parts) if result_parts else "No changes applied."

    def _tool_get_gdd_status(self) -> str:
        """Return the GDD completion summary."""
        if self.current_gdd is None:
            return "No GDD exists yet."
        return self.current_gdd.completion_summary()

    def _tool_get_current_gdd(self) -> str:
        """Return the full GDD as JSON."""
        if self.current_gdd is None:
            return "{}"
        return self.current_gdd.to_json()

    # -------------------------------------------------------------------
    # Response building
    # -------------------------------------------------------------------

    def _build_response(
        self, text: str, gdd_modified: bool, project_path: str
    ) -> Dict[str, Any]:
        """Build the return dict for the chat endpoint."""
        result = {"response": text, "gdd": None}
        if gdd_modified and self.current_gdd is not None:
            result["gdd"] = self.current_gdd.to_dict()
        return result

    # -------------------------------------------------------------------
    # GDD persistence
    # -------------------------------------------------------------------

    def _save_gdd(self, project_path: str) -> None:
        """Save the current GDD to disk."""
        if not project_path or self.current_gdd is None:
            return
        try:
            gdd_path = Path(project_path) / "gdd.json"
            self.current_gdd.save_to_file(str(gdd_path))
            logger.info(f"GDD saved to {gdd_path}")
        except Exception as e:
            logger.error(f"Failed to save GDD: {e}")

    # -------------------------------------------------------------------
    # Public accessors (unchanged interface for main.py / studio agent)
    # -------------------------------------------------------------------

    def get_current_gdd(self) -> Optional[GameDesignDocument]:
        """Return the current GDD being worked on."""
        return self.current_gdd

    def reset(self):
        """Reset the agent to start a new project."""
        self.state = AgentState.IDLE
        self.history = []
        self.current_gdd = None
        self.tasks = []
        self.current_task_index = 0

    def load_project(self, project_path: str) -> bool:
        """Load an existing project GDD and tasks if they exist."""
        self.reset()
        gdd_path = Path(project_path) / "gdd.json"
        
        loaded_gdd = False
        if gdd_path.exists():
            try:
                self.current_gdd = GameDesignDocument.load_from_file(str(gdd_path))
                self.state = AgentState.CHATTING
                logger.info(f"Loaded existing GDD from {gdd_path}")
                loaded_gdd = True
            except Exception as e:
                logger.error(f"Failed to load GDD from {gdd_path}: {e}")
                self.current_gdd = GameDesignDocument() # Ensure an empty GDD object exists for later chat
        else:
             self.current_gdd = GameDesignDocument()

        # Always try to load tasks, even if GDD failed or doesn't exist
        self.load_tasks(project_path)
        
        # Return True if either GDD or tasks were successfully loaded
        return loaded_gdd or len(self.tasks) > 0

    # -------------------------------------------------------------------
    # Task management (unchanged from original)
    # -------------------------------------------------------------------

    def save_tasks(self, project_path: str):
        """Save current tasks to tasks.json."""
        if not project_path:
            return

        tasks_path = Path(project_path) / "tasks.json"
        try:
            task_list = TaskList(tasks=self.tasks)
            with open(tasks_path, 'w') as f:
                f.write(task_list.model_dump_json(indent=2))
            logger.info(f"Saved {len(self.tasks)} tasks to {tasks_path}")
        except Exception as e:
            logger.error(f"Failed to save tasks: {e}")

    def load_tasks(self, project_path: str):
        """Load tasks from tasks.json if exists."""
        tasks_path = Path(project_path) / "tasks.json"
        if tasks_path.exists():
            try:
                with open(tasks_path, 'r') as f:
                    data = json.load(f)
                    task_list = TaskList.model_validate(data)
                    self.tasks = task_list.tasks

                    # Find first non-completed task
                    for i, task in enumerate(self.tasks):
                        if task.status != TaskStatus.COMPLETED:
                            self.current_task_index = i
                            break
                    else:
                        self.current_task_index = len(self.tasks)

                logger.info(f"Loaded {len(self.tasks)} tasks from {tasks_path}")
            except Exception as e:
                logger.error(f"Failed to load tasks: {e}")

    async def generate_tasks(self, gdd: GameDesignDocument, project_path: str = None) -> List[Task]:
        """Generate a list of actionable tasks from the GDD."""
        logger.info("Generating task list from GDD...")

        prompt = f"""You are a Technical Lead for a Godot 4 game development project.

Based on the following Game Design Document:
{gdd.to_json()}

Pay special attention to `detailed_systems` and `mechanics` — use their `implementation_guide` and `description` fields to make task descriptions technically specific.

Create an implementation plan of 5-12 tasks (use fewer tasks for simpler games, more for complex ones). Follow these STRICT rules:
## RULE 1: Task Ordering
- The FIRST task must ALWAYS be project setup: configure window size (1280×720), pixel art renderer (Nearest filter), create main scene, set Camera2D zoom.
- Build incrementally — each block of 1-3 tasks adds one meaningful layer (movement, enemies, UI, etc.).
- Core systems come before polish. Assets (sprites) come before the scenes that use them.

## RULE 2: Task Descriptions and Asset Handling
- Each task should represent roughly 1 focused feature or scene. Combine trivial steps into a single task so unnecessary tasks are not created. Be conservative but meaningful with task generation.
- EVERY task MUST produce a testable result. At the end of EVERY task description, describe exactly what the developer can see, do, or test in Godot to validate the state at the end of that task.
- Task descriptions should read like actual natural language tasks or objectives, NOT as dense code snippets or raw pseudocode.
- Provide clear guidance on what the AI needs to build, mentioning key technical details (like file paths or root node types) naturally.
- **Specific Emphasis on Asset Handling**: Whenever visuals or sounds are needed, clearly instruct the AI to acquire the assets first (e.g., "Use the asset tools to generate a player sprite"). Then, explicitly instruct the AI to ensure the acquired assets are properly attached to their respective nodes (like Sprite2D) via code. For example: "Retrieve a pixel-art enemy sprite, then build the enemy scene, making sure to load and assign the new texture to the enemy's Sprite2D node."

## RULE 3: First Task is Always Project Setup
The first task description must instruct the AI to configure the project settings optimally for 2D. It should mention setting the viewport to 1280×720, the texture filter to Nearest, and the renderer to gl_compatibility, followed by creating the main scene with a Camera2D and setting it as the main run scene.

## EXAMPLE STRUCTURE (for a pixel art platformer):
1. TASK-01: Configure the core project settings for a pixel art game. Use a Godot script to set the viewport to 1280x720, enable the Nearest texture filter, and set the renderer to gl_compatibility. Create 'res://scenes/main.tscn' (Node2D root) with a Camera2D zoomed to (2,2), and set it as the main scene. 🎮 End State: A blank main scene opens correctly when the game is played.
2. TASK-02: Implement the basic Player character. First, use the appropriate tool to acquire a 32x64 pixel art hero sprite. Create a new 'res://scenes/player.tscn' scene using CharacterBody2D, adding a Sprite2D and a Capsule CollisionShape2D. Write a player script to handle left/right movement and jumping. Crucially, ensure the script loads the acquired sprite texture and assigns it to the Sprite2D node. Attach the script and save the scene. Instance the player into the main scene. 🎮 End State: The player character is visible in the main scene, the imported sprite is fully visible and correctly attached, and falls downwards smoothly.
3. TASK-03: Create a static platform block. Acquire a 32x32 stone block sprite. Create 'res://scenes/platform.tscn' (StaticBody2D). Add Sprite2D and CollisionShape2D (RectangleShape2D). Load the block logic. Instance a floor out of these blocks in the main scene. 🎮 End State: The player spawns, falls, and successfully lands and stops on the platforms. Can move left/right and jump over them.
... and so on.

## OUTPUT FORMAT
Return a JSON object with a "tasks" key containing the list of Task objects.
Each Task must have:
- 'id': unique string ("TASK-XX")
- 'description': string — MUST read as a natural language objective with explicit asset attachment instructions, necessary technical details, and end state test validation.
- 'status': "PENDING"
"""
        console.print("\n  [bold green]📋 Generating task list from GDD…[/bold green]")
        try:
            task_list_obj = self.llm.generate_structured(prompt, TaskList)
            self.tasks = task_list_obj.tasks
            self.current_task_index = 0

            if project_path:
                self.save_tasks(project_path)

            console.print(f"  [green]✓ Generated {len(self.tasks)} task(s)[/green]\n")
            return self.tasks

        except Exception as e:
            logger.error(f"Failed to generate tasks: {e}")
            return []

    async def regenerate_tasks_from_feedback(self, feedback: str, project_path: str = None) -> List[Task]:
        """Regenerate remaining tasks based on user feedback."""
        if not self.tasks:
            return []

        completed_tasks = self.tasks[:self.current_task_index]
        remaining_tasks = self.tasks[self.current_task_index:]

        logger.info(f"Regenerating tasks with feedback: {feedback}")

        prompt = f"""You are a Technical Lead adapting a Godot 4 game implementation plan based on user feedback.

Completed Tasks (do NOT change these):
{[t.description for t in completed_tasks]}

Remaining Tasks (to be revised based on feedback):
{[t.description for t in remaining_tasks]}

User Feedback: "{feedback}"

Generate a NEW list of remaining tasks that incorporates the feedback. Target a total plan size of 5-12 tasks; with {len(completed_tasks)} already completed, aim for roughly {max(1, 5 - len(completed_tasks))}-{max(1, 12 - len(completed_tasks))} more tasks. Combine trivial steps into single tasks where necessary.

## STRICT RULES (same as original plan):
1. Keep tasks granular but ensure unnecessary tasks are not created. Tasks must read as natural language objectives, not raw code. ALWAYS emphasize generating assets first and properly attaching them to sprites.
2. EVERY task MUST produce a testable result. At the end of EVERY task description, describe exactly what the developer can see, do, or test in Godot to validate the state at the end of that task.

Return a JSON object with a "tasks" key containing the list of Task objects.
Each Task must have: 'id' (string "TASK-XX"), 'description' (string), 'status' ("PENDING").
"""
        try:
            new_task_list_obj = self.llm.generate_structured(prompt, TaskList)
            self.tasks = completed_tasks + new_task_list_obj.tasks

            if project_path:
                self.save_tasks(project_path)

            return self.tasks
        except Exception as e:
            logger.error(f"Failed to regenerate tasks: {e}")
            return self.tasks

    def add_task(self, description: str, project_path: str = None) -> bool:
        """Add a new task manually.
        
        Args:
            description: Human-readable task description.
        """
        import uuid
        prefix = "TASK-"
        new_task = Task(
            id=f"{prefix}{uuid.uuid4().hex[:8].upper()}",
            description=description,
        )
        self.tasks.append(new_task)
        if project_path:
            self.save_tasks(project_path)
        return True

    def get_next_task(self) -> Optional[Task]:
        """Get the next pending task."""
        if 0 <= self.current_task_index < len(self.tasks):
            return self.tasks[self.current_task_index]
        return None

    def complete_current_task(self, project_path: str = None):
        """Mark the current task as completed and advance."""
        if 0 <= self.current_task_index < len(self.tasks):
            self.tasks[self.current_task_index].status = TaskStatus.COMPLETED
            self.current_task_index += 1
            if project_path:
                self.save_tasks(project_path)

    def update_task(
        self,
        task_id: str,
        description: str = None,
        status: str = None,
        project_path: str = None,
    ) -> bool:
        """Manually update a task."""
        for task in self.tasks:
            if task.id == task_id:
                if description is not None:
                    task.description = description
                if status is not None:
                    try:
                        task.status = TaskStatus(status)
                    except ValueError:
                        logger.error(f"Invalid status: {status}")
                        return False

                if project_path:
                    self.save_tasks(project_path)
                return True
        return False

    def update_gdd_manual(self, gdd_data: dict, project_path: str = None) -> bool:
        """Manually update GDD content."""
        try:
            new_gdd = GameDesignDocument(**gdd_data)
            self.current_gdd = new_gdd

            if project_path:
                gdd_path = Path(project_path) / "gdd.json"
                new_gdd.save_to_file(str(gdd_path))

            return True
        except Exception as e:
            logger.error(f"Failed to manually update GDD: {e}")
            return False

    def insert_task(self, description: str, project_path: str = None, index: int = 0) -> bool:
        """Insert a new task at a specific index (relative to pending tasks).
        
        If index is 0, it becomes the NEXT task to execute.
        """
        import uuid
        prefix = "TASK-"
        new_task = Task(
            id=f"{prefix}{uuid.uuid4().hex[:8].upper()}",
            description=description,
            status=TaskStatus.PENDING
        )
        
        # Calculate actual insertion index.
        # self.current_task_index points to the first PENDING task.
        # So index=0 means insert at current_task_index.
        insert_pos = self.current_task_index + index
        
        if insert_pos < 0: insert_pos = 0
        if insert_pos > len(self.tasks): insert_pos = len(self.tasks)
        
        self.tasks.insert(insert_pos, new_task)
        
        if project_path:
            self.save_tasks(project_path)
            
        return True

    def reorder_tasks(self, task_ids: List[str], project_path: str = None) -> bool:
        """Reorder pending tasks based on a list of IDs.
        
        Only affects PENDING tasks. Completed tasks remain fixed at the start.
        """
        # Separate completed tasks
        completed = [t for t in self.tasks if t.status == TaskStatus.COMPLETED]
        pending = [t for t in self.tasks if t.status != TaskStatus.COMPLETED]
        
        # Map pending tasks by ID for easy lookup
        pending_map = {t.id: t for t in pending}
        
        new_pending = []
        for tid in task_ids:
            if tid in pending_map:
                new_pending.append(pending_map[tid])
                del pending_map[tid]
                
        # Add any remaining tasks (those not in new order list) to the end
        # to ensure no tasks are lost
        remaining = [t for t in pending if t.id in pending_map]
        new_pending.extend(remaining)
        
        self.tasks = completed + new_pending
        # Ensure current_task_index is correct
        self.current_task_index = len(completed)
        
        if project_path:
            self.save_tasks(project_path)
            
        return True
