"""
Review Agent — Handles ad-hoc user feedback and formulates fix tasks.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List, Dict, Any, Optional
import os
import json
import logging
import asyncio
from core.llm import LLMProvider
from core.log import console
import google.generativeai as genai

if TYPE_CHECKING:
    from agents.architect import ArchitectAgent
    from session import ConnectionManager

logger = logging.getLogger(__name__)

_T = genai.protos.Type

_TOOL_DECLARATIONS = [
    genai.protos.FunctionDeclaration(
        name="finalize_review",
        description=(
            "Call this tool when you have enough information to write a clear, actionable task "
            "for the Coder agent. The task description must be completely self-contained: it should "
            "describe the expected behavior, which nodes/scripts are involved, and exactly what fix "
            "to apply. When in doubt, finalize with what you know — do not keep reading files."
        ),
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "task_description": genai.protos.Schema(
                    type_=_T.STRING,
                    description="The detailed, actionable task description for the Coder.",
                ),
            },
            required=["task_description"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="get_completed_tasks",
        description="Retrieve the list of tasks already completed or in-progress in this project.",
        parameters=genai.protos.Schema(type_=_T.OBJECT),
    ),
    genai.protos.FunctionDeclaration(
        name="read_scene",
        description="Read the node tree of the Godot scene currently open in the editor.",
        parameters=genai.protos.Schema(type_=_T.OBJECT),
    ),
    genai.protos.FunctionDeclaration(
        name="read_file",
        description=(
            "Read the contents of a script or resource file. "
            "Provide the path relative to res://, e.g. 'scripts/player.gd'."
        ),
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "file_path": genai.protos.Schema(
                    type_=_T.STRING,
                    description="Path relative to res://, e.g. scripts/player.gd",
                )
            },
            required=["file_path"],
        ),
    ),
]

# Maximum tool-call iterations before we force the model to finalize.
_MAX_ITERATIONS = 14
# On this iteration (0-indexed), inject a hard stop telling the model to finalize now.
_FORCE_FINALIZE_AT = _MAX_ITERATIONS - 2

_SYSTEM_PROMPT = """\
You are a **Senior Developer** responding to live playtest feedback for a Godot game project.
The user has switched to the 'Review' tab to report a bug, request a tweak, or describe unexpected behaviour they noticed while playing.

## PRIMARY DIRECTIVE
Your only goal is to call `finalize_review` with a precise, actionable task description as quickly as possible.

### When to finalize immediately (WITHOUT reading files first)
- The user describes a clear gameplay change: "make the player jump higher", "enemies should spawn faster"
- The bug is self-evident from the description: "the player falls through the floor when touching a wall"

### When to read files first
- You need an exact line number or variable name to write a precise fix
- The bug is ambiguous and you need to trace control flow across scripts
- Limit yourself to **at most 3–4 file reads** before finalizing

## Rules
- Do NOT write GDScript code in your text reply — put all implementation detail in `finalize_review`
- Do NOT keep reading files in circles — prefer finalizing with reasonable assumptions over exhausting your tool budget
- The task description passed to `finalize_review` must be self-contained: describe expected vs. actual behaviour, identify involved nodes/scripts, and state the exact fix
"""


class ReviewAgent:
    def __init__(self, llm: LLMProvider):
        self.llm = llm
        self.history: List[Dict[str, Any]] = []
        # Cached within a session so we don't round-trip to Godot on every message.
        self._files_cache: Optional[str] = None

    async def chat(
        self,
        user_input: str,
        project_path: str,
        architect: "ArchitectAgent",
        manager: "ConnectionManager",
    ) -> Dict[str, Any]:
        """Process a user message in the review tab.

        Returns:
            {"response": str, "task_description": str | None}
        """
        preview = (user_input[:70] + "…") if len(user_input) > 70 else user_input
        console.print(f"\n  [bold cyan]💬 Review chat:[/bold cyan]  [dim]{preview}[/dim]")

        self.history.append({"role": "user", "parts": [user_input]})

        from agents.studio.tools import GodotInterface

        godot = GodotInterface(manager)

        # Fetch project file list once per session to avoid repeated Godot round-trips.
        if self._files_cache is None:
            try:
                files_str = await godot.get_project_files(project_path)
                files_list = json.loads(files_str)
                self._files_cache = "\n".join(f"- {f}" for f in files_list)
            except Exception as e:
                logger.warning(f"[ReviewAgent] Could not fetch project files: {e}")
                self._files_cache = "(Project file list unavailable)"

        gdd_obj = architect.get_current_gdd()
        gdd_context = gdd_obj.to_json() if gdd_obj else "No GDD found."

        dynamic_system_prompt = (
            f"{_SYSTEM_PROMPT}\n\n"
            f"## Project Files\n{self._files_cache}\n\n"
            f"## Game Design Document\n{gdd_context}"
        )

        task_description: Optional[str] = None
        final_text = ""

        for iteration in range(_MAX_ITERATIONS):
            # On the penultimate iteration, force the model to stop reading and finalize.
            if iteration == _FORCE_FINALIZE_AT and task_description is None:
                logger.info(
                    f"[ReviewAgent] Forcing finalization at iteration {iteration}"
                )
                self.history.append(
                    {
                        "role": "user",
                        "parts": [
                            "You have used most of your tool budget. "
                            "You MUST call `finalize_review` RIGHT NOW with everything you have gathered. "
                            "Do not read any more files."
                        ],
                    }
                )

            # Run the synchronous LLM call off the event loop to avoid blocking
            # WebSocket handling and other async tasks during the 2-12s API call.
            result = await asyncio.to_thread(
                self.llm.generate_with_tools,
                system_instruction=dynamic_system_prompt,
                history=self.history,
                tool_declarations=_TOOL_DECLARATIONS,
                caller="ReviewAgent",
            )

            text: str = result.get("text") or ""
            tool_calls = result.get("tool_calls")
            raw_parts = result.get("raw_parts", [])

            self.history.append(
                {
                    "role": "model",
                    "parts": raw_parts if raw_parts else ([text] if text else [""]),
                }
            )

            # No tool calls → the model gave a plain text reply; we're done.
            if not tool_calls:
                final_text = text
                break

            function_responses: List[Dict] = []
            should_finalize = False

            for tc in tool_calls:
                name = tc["name"]
                args = tc.get("args", {})
                tool_id = tc.get("id", "")

                logger.debug(f"[ReviewAgent] Tool call: {name} (iter {iteration})")

                if name == "finalize_review":
                    desc = args.get("task_description", "").strip()
                    if not desc:
                        func_res = {
                            "error": "task_description was empty — please provide a non-empty description."
                        }
                    else:
                        task_description = desc
                        logger.info(
                            f"[ReviewAgent] Finalized: {task_description[:100]}…"
                        )
                        func_res = {
                            "result": "Task recorded. Awaiting user to click Execute Fix."
                        }
                        should_finalize = True
                        if not final_text:
                            final_text = text or "I've formulated the fix. Click **Execute Fix** when you're ready!"

                elif name == "get_completed_tasks":
                    func_res = {
                        "tasks": [t.model_dump(mode="json") for t in architect.tasks]
                    }

                elif name == "read_scene":
                    try:
                        scene_json = await godot.read_scene(project_path)
                        func_res = {"scene_tree": scene_json}
                    except Exception as e:
                        func_res = {"error": f"Could not read scene: {e}"}

                elif name == "read_file":
                    raw_path = args.get("file_path", "")
                    # Use removeprefix so we strip the literal "res://" string,
                    # not individual characters (lstrip would mangle the filename).
                    rel = raw_path.removeprefix("res://").lstrip("/")
                    full_path = os.path.join(project_path, rel)
                    try:
                        with open(full_path, "r", encoding="utf-8") as f:
                            content = f.read()
                        func_res = {"content": content}
                    except FileNotFoundError:
                        func_res = {"error": f"File not found: {raw_path}"}
                    except Exception as e:
                        func_res = {"error": str(e)}

                else:
                    logger.warning(f"[ReviewAgent] Unknown tool called: {name!r}")
                    func_res = {"error": f"Unknown tool: {name}"}

                fr: Dict[str, Any] = {
                    "function_response": {"name": name, "response": func_res}
                }
                if tool_id:
                    fr["function_response"]["id"] = tool_id
                function_responses.append(fr)

            if function_responses:
                self.history.append(
                    {"role": "user", "parts": function_responses}
                )

            if should_finalize:
                break

        # Loop exhausted without finalization — give the user actionable feedback.
        if not final_text and task_description is None:
            logger.warning("[ReviewAgent] Loop exhausted without finalization.")
            final_text = (
                "I wasn't able to gather enough information to formulate a complete fix. "
                "Could you describe the issue in more detail? For example, which script or node "
                "is involved, and what exact behaviour you're seeing versus what you expect."
            )

        return {"response": final_text, "task_description": task_description}

    def reset(self) -> None:
        self.history = []
        self._files_cache = None  # Clear so next session gets a fresh file list.
