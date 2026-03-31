import asyncio
import logging
import json
import re
import time
from typing import Dict, List, Optional, Any, Set
from langchain_core.messages import AIMessage
from agents.studio.state import StudioState
from agents.studio.tools import GodotInterface, AssetInterface
from core.llm import LLMFactory
from core.config import config
from core.log import log_node_start, log_node_done, log_action_exec, log_asset_acquire
from services.project_scanner import ProjectScanner
import google.generativeai as genai


# ---------------------------------------------------------------------------
# .tscn file parser — extracts instanced scenes without Godot bridge calls
# ---------------------------------------------------------------------------

def _parse_tscn_instances(content: str) -> List[str]:
    """Return list of res:// scene paths that are instanced inside this .tscn."""
    # Build id → path map for PackedScene external resources
    ext_resources: Dict[str, str] = {}
    for m in re.finditer(r'\[ext_resource[^\]]*\]', content):
        attrs = m.group(0)
        id_m = re.search(r'\bid="([^"]+)"', attrs)
        path_m = re.search(r'\bpath="([^"]+)"', attrs)
        type_m = re.search(r'\btype="([^"]+)"', attrs)
        if id_m and path_m and type_m and type_m.group(1) == "PackedScene":
            ext_resources[id_m.group(1)] = path_m.group(1)
    # Find all instance= references
    instances = []
    for m in re.finditer(r'instance=ExtResource\("([^"]+)"\)', content):
        res_id = m.group(1)
        if res_id in ext_resources:
            instances.append(ext_resources[res_id])
    return instances


def _parse_tscn_nodes(content: str) -> List[str]:
    """Return list of 'NodeName (NodeType)' for every owned node in this .tscn."""
    nodes = []
    for m in re.finditer(r'\[node name="([^"]+)" type="([^"]+)"', content):
        nodes.append(f"{m.group(1)} ({m.group(2)})")
    return nodes


def _build_tscn_summary(tscn_files: Dict[str, str]) -> str:
    """
    Parse all .tscn files and return a human-readable summary listing:
      - Each scene's own nodes (so the AI knows what already exists before opening it)
      - Any sub-scenes instanced inside it
    """
    lines = []

    for tscn_path, content in tscn_files.items():
        own_nodes = _parse_tscn_nodes(content)
        instanced = _parse_tscn_instances(content)
        parts = []
        if own_nodes:
            parts.append(f"nodes: {', '.join(own_nodes)}")
        if instanced:
            parts.append(f"instances: {', '.join(instanced)}  ← do NOT instance these again")
        if parts:
            lines.append(f"  {tscn_path}  —  {' | '.join(parts)}")
        else:
            lines.append(f"  {tscn_path}: (empty)")

    return "\n".join(lines) if lines else "  (no .tscn files found)"

logger = logging.getLogger(__name__)


_LLM_STEP_MAX_RETRIES = 4
_RETRYABLE_HTTP_STATUS = {500, 502, 503, 504}


def _extract_http_status(err: Exception) -> Optional[int]:
    """Best-effort HTTP status extraction from provider exceptions."""
    msg = str(err)
    m = re.search(r"\b([45]\d{2})\b", msg)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def _is_retryable_llm_error(err: Exception) -> bool:
    status = _extract_http_status(err)
    if status in _RETRYABLE_HTTP_STATUS:
        return True
    msg = str(err).lower()
    return any(token in msg for token in (
        "timeout",
        "timed out",
        "deadline exceeded",
        "internal server error",
        "service unavailable",
        "bad gateway",
        "gateway timeout",
        "temporarily unavailable",
        "connection reset",
    ))


async def _run_llm_step_with_retries(step_name: str, llm_call, **kwargs):
    """
    Retry transient LLM/API failures for a single node step.
    This keeps the workflow on the same failed step instead of advancing blindly.
    """
    for attempt in range(1, _LLM_STEP_MAX_RETRIES + 1):
        try:
            return await asyncio.to_thread(llm_call, **kwargs)
        except Exception as err:
            if _is_retryable_llm_error(err) and attempt < _LLM_STEP_MAX_RETRIES:
                delay_s = 1.5 * attempt
                logger.warning(
                    "%s LLM call failed with transient error (%s). Retry %d/%d in %.1fs.",
                    step_name,
                    err,
                    attempt,
                    _LLM_STEP_MAX_RETRIES,
                    delay_s,
                )
                await asyncio.sleep(delay_s)
                continue
            raise


# ---------------------------------------------------------------------------
# Tool declarations for the Coder's agentic loop (Gemini function-calling)
# ---------------------------------------------------------------------------

_T = genai.protos.Type  # shorthand


def _s(type_: Any, description: str, **kwargs) -> genai.protos.Schema:
    """Helper to build a Schema with less boilerplate."""
    return genai.protos.Schema(type_=type_, description=description, **kwargs)


_CODER_TOOL_DECLARATIONS = [
    # ------------------------------------------------------------------
    # Godot scene / script tools
    # ------------------------------------------------------------------
    genai.protos.FunctionDeclaration(
        name="get_project_files",
        description="List all .gd/.tscn/.tres files. Call first.",
        parameters=genai.protos.Schema(type_=_T.OBJECT, properties={}),
    ),
    genai.protos.FunctionDeclaration(
        name="get_input_map",
        description="Read InputMap (action names).",
        parameters=genai.protos.Schema(type_=_T.OBJECT, properties={}),
    ),
    genai.protos.FunctionDeclaration(
        name="node_exists",
        description="Check if node exists in open scene.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={"node_path": _s(_T.STRING, "Path to check.")},
            required=["node_path"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="read_scene",
        description="Get current scene tree.",
        parameters=genai.protos.Schema(type_=_T.OBJECT, properties={}),
    ),
    genai.protos.FunctionDeclaration(
        name="create_scene",
        description="Create .tscn scene logic.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "scene_path": _s(_T.STRING, "res:// path"),
                "root_type": _s(_T.STRING, "Root type (CharacterBody2D, etc)"),
            },
            required=["scene_path", "root_type"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="open_scene",
        description="Open .tscn in editor.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={"scene_path": _s(_T.STRING, "res:// path")},
            required=["scene_path"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="delete_node",
        description=(
            "⚠️ DESTRUCTIVE — permanently removes a node AND ALL ITS CHILDREN from the currently open scene. "
            "Cannot be undone. Only use this as a corrective measure when a node was added by mistake "
            "(e.g. a duplicate node that should not exist, or a misplaced node that needs to be "
            "re-added in the correct scene). "
            "DO NOT delete nodes that are part of the intended design. "
            "DO NOT delete scene instance roots (use instance_scene instead). "
            "Always call read_scene first to confirm the exact node_path before deleting. "
            "After deleting, call save_scene to persist the change."
        ),
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "node_path": _s(_T.STRING, "Path of the node to delete (e.g. 'Sprite2D' or 'Player/Sprite2D')"),
            },
            required=["node_path"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="add_node",
        description="Add node to open scene.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "parent_path": _s(_T.STRING, "Parent path ('.' for root)"),
                "node_type": _s(_T.STRING, "Type (Sprite2D)"),
                "node_name": _s(_T.STRING, "Name (Sprite)"),
            },
            required=["parent_path", "node_type", "node_name"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="set_property",
        description="Set node property. For textures, use 'res://...' path. To create a new Godot Resource (like a shape), use its class name directly (e.g., 'RectangleShape2D').",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "node_path": _s(_T.STRING, "Node path"),
                "property_name": _s(_T.STRING, "Property"),
                "value": _s(_T.STRING, "Value (string/path/class name)"),
            },
            required=["node_path", "property_name", "value"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="read_file",
        description="Read the contents of a specific file (e.g. res://player.gd).",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={"file_path": _s(_T.STRING, "res:// path")},
            required=["file_path"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="create_script",
        description="Write .gd file. Use set_property for static textures.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "file_path": _s(_T.STRING, "res:// path"),
                "content": _s(_T.STRING, "GDScript code"),
            },
            required=["file_path", "content"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="edit_script",
        description=(
            "Make a targeted edit to an existing .gd file. "
            "old_str MUST be a small, focused snippet — the fewest lines that uniquely identify the location (e.g. the function signature + 1-2 surrounding lines). "
            "NEVER put the entire file content in old_str or new_str — that defeats the purpose and wastes tokens. "
            "Always call read_file first to get the exact text. "
            "Use this instead of create_script whenever the file already exists."
        ),
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "file_path": _s(_T.STRING, "res:// path to the .gd file"),
                "old_str": _s(_T.STRING, "Small verbatim snippet to find — must be unique in the file, NOT the whole file"),
                "new_str": _s(_T.STRING, "Replacement for old_str only"),
            },
            required=["file_path", "old_str", "new_str"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="validate_script",
        description="Validate GDScript syntax.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={"content": _s(_T.STRING, "Code")},
            required=["content"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="attach_script",
        description="Attach script to node.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "node_path": _s(_T.STRING, "Node path"),
                "script_path": _s(_T.STRING, "res:// path"),
            },
            required=["node_path", "script_path"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="save_scene",
        description="Save open scene.",
        parameters=genai.protos.Schema(type_=_T.OBJECT, properties={}),
    ),
    genai.protos.FunctionDeclaration(
        name="instance_scene",
        description=(
            "Instance a .tscn as a child of parent_path. "
            "By default rejects a second instance of the same scene under the same parent — "
            "pass allow_multiple:true ONLY when multiple instances are intentional (e.g. enemies, coins, projectiles). "
            "Never use node_name to work around a duplicate rejection."
        ),
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "scene_path": _s(_T.STRING, "res:// path"),
                "parent_path": _s(_T.STRING, "Parent path"),
                "node_name": _s(_T.STRING, "Optional override name for the instance root"),
                "allow_multiple": _s(_T.BOOLEAN, "Set true only when multiple instances of the same scene are intentional (enemies, coins, etc.)"),
            },
            required=["scene_path", "parent_path"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="set_main_scene",
        description="Set project main scene.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={"scene_path": _s(_T.STRING, "res:// path")},
            required=["scene_path"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="scan_filesystem",
        description="Rescan files.",
        parameters=genai.protos.Schema(type_=_T.OBJECT, properties={}),
    ),
    genai.protos.FunctionDeclaration(
        name="execute_godot_script",
        description=(
            "Run arbitrary GDScript in the editor as a last resort ONLY. "
            "NEVER use this to add nodes, instance scenes, set properties, or attach scripts — "
            "use the dedicated tools (add_node, instance_scene, set_property, attach_script) instead. "
            "Those tools have duplicate-prevention guards; this one does not. "
            "Valid uses: reading editor state, triggering editor actions not covered by other tools."
        ),
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={"code": _s(_T.STRING, "Code")},
            required=["code"],
        ),
    ),
    # ------------------------------------------------------------------
    # Asset acquisition tools — call BEFORE creating scenes/scripts
    # ------------------------------------------------------------------
    genai.protos.FunctionDeclaration(
        name="get_sprite",
        description="Acquire 2D sprite. Returns res:// path.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "name": _s(_T.STRING, "Asset name"),
                "description": _s(_T.STRING, "Visual description"),
                "style": _s(_T.STRING, "Style"),
                "width": _s(_T.INTEGER, "Width"),
                "height": _s(_T.INTEGER, "Height"),
                "tags": _s(_T.STRING, "Tags"),
            },
            required=["name", "description"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="get_spritesheet",
        description="Acquire sprite sheet. Returns res:// path.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "name": _s(_T.STRING, "Asset name"),
                "description": _s(_T.STRING, "Description"),
                "poses": _s(_T.STRING, "Poses"),
                "style": _s(_T.STRING, "Style"),
                "frame_width": _s(_T.INTEGER, "Frame Width"),
                "frame_height": _s(_T.INTEGER, "Frame Height"),
                "tags": _s(_T.STRING, "Tags"),
            },
            required=["name", "description"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="get_tileset",
        description="Acquire tileset.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "name": _s(_T.STRING, "Name"),
                "description": _s(_T.STRING, "Description"),
                "style": _s(_T.STRING, "Style"),
                "tile_size": _s(_T.INTEGER, "Tile Size"),
                "columns": _s(_T.INTEGER, "Cols"),
                "rows": _s(_T.INTEGER, "Rows"),
                "tile_types": _s(_T.STRING, "Types"),
                "tags": _s(_T.STRING, "Tags"),
            },
            required=["name", "description"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="get_background",
        description="Acquire background.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "name": _s(_T.STRING, "Name"),
                "description": _s(_T.STRING, "Description"),
                "style": _s(_T.STRING, "Style"),
                "width": _s(_T.INTEGER, "W"),
                "height": _s(_T.INTEGER, "H"),
                "tags": _s(_T.STRING, "Tags"),
            },
            required=["name", "description"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="get_audio",
        description="Acquire audio.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "name": _s(_T.STRING, "Name"),
                "description": _s(_T.STRING, "Description"),
                "audio_type": _s(_T.STRING, "sfx/music"),
                "duration_seconds": _s(_T.NUMBER, "Seconds"),
                "tags": _s(_T.STRING, "Tags"),
            },
            required=["name", "description"],
        ),
    ),
]

# Orchestration model: supervisor, reviewer (gemini-3-flash-preview)
llm_provider = LLMFactory.get_provider(config.GEMINI_MODEL_FLASH)
# Execution model: coder (gemini-3.1-flash-lite-preview)
llm_provider_lite = LLMFactory.get_provider(config.GEMINI_MODEL_LITE)

async def supervisor_node(state: StudioState, godot_interface: GodotInterface = None) -> Dict:
    """
    The Supervisor reads the current_task and gdd, then decides what actions to take.
    It updates the messages with instructions for the Coder.
    """
    current_task = state.get("current_task", "")
    gdd = state.get("gdd", {})
    project_path = state.get("project_path", "")
    
    completed_tasks_context = state.get("completed_tasks_context", "")
    logger.info(f"Supervisor processing task: {current_task}")
    log_node_start("Supervisor", current_task)

    # Read the live editor state so the Supervisor knows which scene is currently
    # open — this prevents it from planning work that assumes a different open scene.
    current_scene_info = ""
    if godot_interface and godot_interface.manager.is_connected(project_path):
        try:
            current_scene_info = await godot_interface.read_scene(project_path)
        except Exception:
            pass

    # Pre-load file structure context (run in thread — synchronous file I/O)
    file_tree = await asyncio.to_thread(ProjectScanner.scan_directory, project_path)
    file_tree_str = json.dumps(file_tree, indent=2)

    # Pre-load project settings (InputMap, Autoloads, Layers) context
    project_context = await asyncio.to_thread(ProjectScanner.get_project_context, project_path)

    prompt = f"""You are the Supervisor for a Godot 4.x project.

GDD:
{gdd}

Task:
{current_task}

Completed:
{completed_tasks_context or "None"}

Files:
{file_tree_str}

{project_context}

Currently Open Scene in Editor:
{current_scene_info}

## INSTRUCTIONS
1. **Scene Structure**: Maintain proper, discrete scene architecture.
   - Create separate `.tscn` files for entities (Player, Enemy, UI components).
   - Use `instance_scene` to place these entities into the Main scene or Level scenes.
   - NEVER instruct the Coder to use `add_node` for any entity node (CharacterBody2D, RigidBody2D, Area2D, etc.) OR any component node (Sprite2D, CollisionShape2D, AudioStreamPlayer, etc.) directly in the Main or Level scene. All such nodes belong inside their entity's own .tscn.
   - Correct entity workflow: `create_scene(entity.tscn)` → `add_node` children inside that scene → `save_scene` → `open_scene(main.tscn)` → `instance_scene(entity.tscn)` → `save_scene`. No deviations.
2. **Architecture Guard**: The engine will BLOCK attempts to add nodes directly to instances (e.g. adding a Sprite to a Player instance in Main).
   - If you need to add a node to an entity, use `open_scene` to edit the entity's source file (e.g. `player.tscn`) directly.
   - Do NOT try to bypass this. It prevents scene corruption and "Load Errors".
3. **Asset Timing**: Acquire assets (sprites, audio) *only if this specific task uses them immediately*. Do not pre-optimize by fetching assets for future tasks.
4. **Simplicity**: Keep the steps lightweight but precise. Do not add bloat or useless constraints.
5. **Instancing**: Ensure scenes are correctly instanced and parented.

Translate this goal into specific, sequential Godot implementation steps for the Coder.
Use `create_scene` -> `add_node` -> `set_property` -> `save_scene`.

## STRICT RULES
1. **Scope**: Keep to the Task.
2. **Tools**:
   - `get_project_files()`: CALL FIRST to see existing files.
   - `set_property(node, "texture", "res://...")`: ALWAYS use this to assign textures.
   - `create_scene`: Use meaningful root types (CharacterBody2D).
   - `add_node`: Use short, semantic names ("Sprite" not "Sprite2D", "Collision" not "CollisionShape2D"). Only instruct `add_node` within an entity's own .tscn, never in main.tscn or a level scene.
3. **Assets**:
   - IF the task needs visual/audio, STEP 1 is: "Call `get_sprite`/`get_audio`...".
   - Do NOT reference assets that don't exist.
4. **Naming**:
   - Scene nodes must match script references (e.g. `$Sprite` node requires `$Sprite` in code).

Output a clear, numbered plan.
"""
    
    try:
        response = await _run_llm_step_with_retries(
            "Supervisor",
            llm_provider.generate,
            prompt=prompt,
            system_instruction="You are a game development project supervisor. You break down tasks into clear, actionable steps for a specific Godot 4.x environment.",
        )
        
        # Log the Supervisor's output to the terminal
        print(f"\n\033[94m[Supervisor Plan for Task '{current_task}']:\033[0m\n{response}\n")
        logger.info(f"Supervisor Plan for Task '{current_task}':\n{response}")

        # Add supervisor's instructions to messages
        new_message = AIMessage(content=f"[Supervisor]: {response}")
        log_node_done("Supervisor")
        return {
            "messages": [new_message]
        }
    except Exception as e:
        logger.error(f"Supervisor node error: {e}")
        error_message = AIMessage(content=f"[Supervisor Error]: {str(e)}")
        return {
            "messages": [error_message]
        }


async def _dispatch_tool(
    tool_name: str,
    tool_args: dict,
    project_path: str,
    godot_interface: GodotInterface,
    asset_interface,
    approved_assets: dict = None,
):
    """
    Execute a single tool call from the coder's agentic loop.

    Returns:
        (result_str, pending_review_dict)
        - result_str: string to feed back into the LLM as the function response
        - pending_review_dict: non-None only for asset tools that need human review
    """
    pending_review = None
    approved_assets = approved_assets or {}
    logger.info("Executing tool: %s with args: %s", tool_name, tool_args)
    start = time.monotonic()
    final_status = "completed"

    def _finish(res_value: Any, pending: Optional[Dict[str, Any]] = None, status: str = "completed"):
        elapsed = time.monotonic() - start
        if status == "completed":
            logger.info("Tool %s completed in %.2fs. Args: %s", tool_name, elapsed, tool_args)
        else:
            logger.info("Tool %s %s in %.2fs. Args: %s", tool_name, status, elapsed, tool_args)
        return str(res_value), pending

    try:
        if tool_name == "get_project_files":
            extensions = tool_args.get("extensions", "gd,tscn,tres")
            result = await godot_interface.get_project_files(project_path, extensions)

        elif tool_name == "get_input_map":
            result = await godot_interface.get_input_map(project_path)

        elif tool_name == "node_exists":
            result = await godot_interface.node_exists(project_path, tool_args.get("node_path", "."))

        elif tool_name == "read_scene":
            result = await godot_interface.read_scene(project_path)

        elif tool_name == "create_scene":
            result = await godot_interface.create_scene(
                project_path, tool_args["scene_path"], tool_args["root_type"]
            )

        elif tool_name == "open_scene":
            result = await godot_interface.open_scene(project_path, tool_args["scene_path"])

        elif tool_name == "delete_node":
            result = await godot_interface.delete_node(
                project_path, tool_args["node_path"]
            )

        elif tool_name == "add_node":
            result = await godot_interface.add_node(
                project_path,
                tool_args["parent_path"],
                tool_args["node_type"],
                tool_args["node_name"],
            )

        elif tool_name == "set_property":
            result = await godot_interface.set_property(
                project_path,
                tool_args["node_path"],
                tool_args["property_name"],
                tool_args["value"],
            )

        elif tool_name == "read_file":
            try:
                import os
                fp = tool_args.get("file_path", "")
                if fp.startswith("res://"): fp = fp[6:]
                elif fp.startswith("/"): fp = fp[1:]
                full_path = os.path.join(project_path, fp)
                with open(full_path, "r", encoding="utf-8") as f:
                    result = f.read()
            except Exception as e:
                result = f"Error reading file: {str(e)}"

        elif tool_name == "create_script":
            result = await godot_interface.apply_code(
                project_path, tool_args["file_path"], tool_args["content"]
            )

        elif tool_name == "edit_script":
            try:
                import os
                fp = tool_args.get("file_path", "")
                if fp.startswith("res://"): fp = fp[6:]
                elif fp.startswith("/"): fp = fp[1:]
                full_path = os.path.join(project_path, fp)
                with open(full_path, "r", encoding="utf-8") as f:
                    current = f.read()
                old_str = tool_args.get("old_str", "")
                new_str = tool_args.get("new_str", "")
                if old_str not in current:
                    result = f"edit_script failed: old_str not found verbatim in {tool_args.get('file_path')}. Use read_file to verify the exact text."
                else:
                    count = current.count(old_str)
                    if count > 1:
                        result = f"edit_script failed: old_str matches {count} locations — make it more specific."
                    else:
                        updated = current.replace(old_str, new_str, 1)
                        result = await godot_interface.apply_code(
                            project_path, tool_args["file_path"], updated
                        )
            except Exception as e:
                result = f"edit_script error: {str(e)}"

        elif tool_name == "validate_script":
            result = await godot_interface.validate_script(project_path, tool_args["content"])

        elif tool_name == "attach_script":
            result = await godot_interface.attach_script(
                project_path, tool_args["node_path"], tool_args["script_path"]
            )

        elif tool_name == "save_scene":
            result = await godot_interface.save_scene(project_path)

        elif tool_name == "instance_scene":
            result = await godot_interface.instance_scene(
                project_path,
                tool_args["scene_path"],
                tool_args.get("parent_path", "."),
                tool_args.get("node_name", ""),
            )

        elif tool_name == "set_main_scene":
            result = await godot_interface.set_main_scene(project_path, tool_args["scene_path"])

        elif tool_name == "scan_filesystem":
            result = await godot_interface.scan_filesystem(project_path)

        elif tool_name == "execute_godot_script":
            result = await godot_interface.execute_godot_script(project_path, tool_args["code"])

        elif tool_name == "test_game":
            result = await godot_interface.test_game(project_path, tool_args.get("scene_path", ""))

        elif tool_name == "test_scene":
            result = await godot_interface.test_scene(
                project_path, 
                tool_args.get("scene_path", ""), 
                duration=tool_args.get("duration", 3.0)
            )

        # ---------------------------------------------------------------
        # Asset acquisition tools — these pause for human review
        # ---------------------------------------------------------------
        elif tool_name == "get_sprite" and asset_interface:
            asset_name = tool_args.get("name", "sprite")
            
            # Idempotency check: if already approved, reuse without calling pipeline
            if asset_name in approved_assets:
                path = approved_assets[asset_name]
                return _finish(f"Asset '{asset_name}' is already approved at {path}. Use this path in your code.", None)

            log_asset_acquire("sprite", asset_name, tool_args.get("description", ""))
            options = await asset_interface.get_sprite_options(
                project_path=project_path,
                name=asset_name,
                description=tool_args.get("description", "game sprite"),
                style=tool_args.get("style", "pixel_art"),
                width=tool_args.get("width", 32),
                height=tool_args.get("height", 32),
                tags=tool_args.get("tags", ""),
            )
            result = f"Collected {len(options)} sprite option(s) for '{asset_name}'. Awaiting human selection."
            if options:
                pending_review = {
                    "type": "sprite",
                    "options": [
                        {"index": i, "asset_path": o.asset_path, "godot_path": o.godot_path, "source": o.source}
                        for i, o in enumerate(options)
                    ],
                    "name": asset_name,
                    "description": tool_args.get("description", ""),
                    "canonical_name": asset_name,
                    "_tool_name": tool_name,
                }

        elif tool_name == "get_spritesheet" and asset_interface:
            asset_name = tool_args.get("name", "spritesheet")
            
            if asset_name in approved_assets:
                path = approved_assets[asset_name]
                return _finish(f"Asset '{asset_name}' is already approved at {path}. Use this path in your code.", None)

            options = await asset_interface.get_spritesheet_options(
                project_path=project_path,
                name=asset_name,
                description=tool_args.get("description", "character sprite sheet"),
                poses=tool_args.get("poses", "idle"),
                style=tool_args.get("style", "pixel_art"),
                frame_width=tool_args.get("frame_width", 32),
                frame_height=tool_args.get("frame_height", 32),
                tags=tool_args.get("tags", ""),
            )
            result = f"Collected {len(options)} spritesheet option(s) for '{asset_name}'. Awaiting human selection."
            if options:
                pending_review = {
                    "type": "spritesheet",
                    "options": [
                        {
                            "index": i,
                            "asset_path": o.asset_path,
                            "godot_path": o.godot_path,
                            "source": o.source,
                            "frame_count": o.frame_count,
                            "frame_width": o.frame_width,
                            "frame_height": o.frame_height,
                        }
                        for i, o in enumerate(options)
                    ],
                    "name": asset_name,
                    "description": tool_args.get("description", ""),
                    "canonical_name": asset_name,
                    "_tool_name": tool_name,
                }

        elif tool_name == "get_tileset" and asset_interface:
            asset_name = tool_args.get("name", "tileset")

            if asset_name in approved_assets:
                path = approved_assets[asset_name]
                return _finish(f"Asset '{asset_name}' is already approved at {path}. Use this path in your code.", None)

            result_json = await asset_interface.get_tileset(
                project_path=project_path,
                name=asset_name,
                description=tool_args.get("description", "game tileset"),
                style=tool_args.get("style", "pixel_art"),
                tile_size=tool_args.get("tile_size", 16),
                columns=tool_args.get("columns", 4),
                rows=tool_args.get("rows", 4),
                tile_types=tool_args.get("tile_types", "ground"),
                tags=tool_args.get("tags", ""),
            )
            result = result_json
            try:
                res_data = json.loads(result_json)
                if res_data.get("success"):
                    pending_review = {
                        "type": "tileset",
                        "asset_path": res_data.get("asset_path"),
                        "godot_path": res_data.get("godot_path"),
                        "name": asset_name,
                        "description": tool_args.get("description", ""),
                        "_tool_name": tool_name,
                    }
            except Exception:
                pass

        elif tool_name == "get_background" and asset_interface:
            asset_name = tool_args.get("name", "background")

            if asset_name in approved_assets:
                path = approved_assets[asset_name]
                return _finish(f"Asset '{asset_name}' is already approved at {path}. Use this path in your code.", None)

            result_json = await asset_interface.get_background(
                project_path=project_path,
                name=asset_name,
                description=tool_args.get("description", "game background"),
                style=tool_args.get("style", "pixel_art"),
                width=tool_args.get("width", 1280),
                height=tool_args.get("height", 720),
                tags=tool_args.get("tags", ""),
            )
            result = result_json
            try:
                res_data = json.loads(result_json)
                if res_data.get("success"):
                    pending_review = {
                        "type": "background",
                        "asset_path": res_data.get("asset_path"),
                        "godot_path": res_data.get("godot_path"),
                        "name": asset_name,
                        "description": tool_args.get("description", ""),
                        "_tool_name": tool_name,
                    }
            except Exception:
                pass

        elif tool_name == "get_audio" and asset_interface:
            asset_name = tool_args.get("name", "audio")

            if asset_name in approved_assets:
                path = approved_assets[asset_name]
                return _finish(f"Asset '{asset_name}' is already approved at {path}. Use this path in your code.", None)

            result_json = await asset_interface.get_audio(
                project_path=project_path,
                name=asset_name,
                description=tool_args.get("description", "game sound"),
                audio_type=tool_args.get("audio_type", "sfx"),
                duration_seconds=tool_args.get("duration_seconds", 0.5),
                tags=tool_args.get("tags", ""),
            )
            result = result_json
            try:
                res_data = json.loads(result_json)
                if res_data.get("success"):
                    pending_review = {
                        "type": "audio",
                        "asset_path": res_data.get("asset_path"),
                        "godot_path": res_data.get("godot_path"),
                        "name": asset_name,
                        "description": tool_args.get("description", ""),
                        "_tool_name": tool_name,
                    }
            except Exception:
                pass

        else:
            result = f"Unknown tool: {tool_name}"

    except Exception as e:
        result = f"Tool {tool_name} FAILED: {str(e)}"
        logger.error("Tool %s raised: %s", tool_name, e, exc_info=True)
        final_status = "failed"

    return _finish(result, pending_review, status=final_status)


async def coder_node(state: StudioState, godot_interface: GodotInterface, asset_interface: AssetInterface = None) -> Dict:
    """
    The Coder uses a ReAct-style agentic tool-calling loop (generate_with_tools)
    to implement the task step by step.

    When an asset tool (get_sprite etc.) is called, the loop pauses for human review.
    On approval, human_review_node injects the approved path as a function response
    and this node resumes the loop from the saved history.
    """
    messages = state.get("messages", [])
    project_path = state.get("project_path", "")
    current_task = state.get("current_task", "")
    user_feedback = state.get("user_feedback")
    approved_assets = state.get("approved_assets") or {}

    logger.info("Coder node starting — task: %s", current_task)
    log_node_start("Coder", current_task)

    if not godot_interface.manager.is_connected(project_path):
        msg = AIMessage(content="[Coder Error]: Godot client is not connected.")
        log_node_done("Coder", "disconnected")
        return {"messages": [msg]}

    # -----------------------------------------------------------------------
    completed_tasks_context = state.get("completed_tasks_context", "")

    # RESUME PATH: loop was paused for an asset review; history is saved
    # -----------------------------------------------------------------------
    saved_history = state.get("tool_loop_history")
    pending_tool_call = state.get("pending_tool_call")
    
    # Detect reviewer-fix mode early so it can influence persistent instructions.
    latest_reviewer_feedback = ""
    for msg in messages:
        if isinstance(msg, AIMessage) and "[Reviewer]" in msg.content:
            latest_reviewer_feedback = msg.content
    reviewer_fix_mode = bool(
        latest_reviewer_feedback and "APPROVED" not in latest_reviewer_feedback.upper()
    )

    # Construct persistent system instruction (rules + checked assets)
    approved_assets_str = ""
    if approved_assets:
        approved_assets_str = (
            "\n\nAlready-approved asset paths (use these in GDScript load() calls):\n"
            + "\n".join(f"  - {n}: {p}" for n, p in approved_assets.items())
        )

    reviewer_fix_system_rules = ""
    if reviewer_fix_mode:
        reviewer_fix_system_rules = """
10. **Reviewer-fix mode**: This pass is for targeted corrections only. Do NOT restart implementation.
11. **No unnecessary reacquisition**: Do NOT call asset tools unless the reviewer explicitly requests a new/different asset.
12. **Minimal edits**: Use `edit_script` with a small targeted snippet — NEVER `create_script` on an existing file, and NEVER pass the full file content as old_str/new_str.
"""

    system_instruction = f"""You are a Godot 4.x Expert. Implement the task using the provided tools. Issue write operations ONE at a time.

## RULES
1. **No duplicates**: The context shows existing scene contents. Before adding a node or instancing a scene, check whether it is already there. Do not add it again. When a scene is instanced, its nodes become available in the parent scene — do not add them again. If you need to modify an instanced node, open the source scene and edit it there.
2. **Assets**: Check 'Approved Assets' first. If an asset is missing, call the asset tool and WAIT for approval before proceeding.
3. **Textures**: ALWAYS assign textures via `set_property(node, "texture", "res://...")`. This is VERY IMPORTANT
4. **Names**: Use short semantic names — "Sprite" not "Sprite2D", "Collision" not "CollisionShape2D".
5. **Scene structure**: Entity components (Sprite2D, CollisionShape2D, etc.) live inside entity .tscn files. Main/level scenes only use `instance_scene` to place entities — never `add_node` for entity-type nodes directly into main. Never use add node on an instance (e.g. adding a Sprite to a Player instance in Main) — open the source scene to edit instead.
6. **Godot 4**: `move_and_slide()` no args. Signals: `signal.connect(Callable)`. Use `validate_script` if unsure of syntax.
7. **execute_godot_script**: NEVER use this to add/remove nodes, instance scenes, or set properties. Use the dedicated tools — they have duplicate guards this one does not.
8. **Instance nodes (is_instance: true)**: When `read_scene` shows a node with `"is_instance": true` and a `"scene_file_path"`, that node is a PackedScene instance. You MUST NOT call `add_node` or `set_property` targeting that node or ANY of its descendants while the parent scene is open. Doing so creates local overrides that cause Godot "Load Error: name clashes" on every project reload. The ONLY correct action is: call `open_scene(scene_file_path)` → make changes there → `save_scene` → `open_scene(original_scene)`.
9. **ARCHITECTURAL VIOLATION response**: If `add_node` returns "ARCHITECTURAL VIOLATION", it means you tried to modify a scene instance or one of its children. STOP immediately. Do NOT retry `add_node` with the same or a different name. REQUIRED: call `open_scene` with the `scene_file_path` shown in the error message, then add the node there.
10. **Information Gathering**: Use get_project_files() to see existing files. Use read_file() to inspect code before modifying it. Do not guess contents.
11. **Script edits**: When a script already exists, ALWAYS use `edit_script` instead of `create_script`. In `edit_script`, `old_str` must be a small targeted snippet (a function signature, a few lines) — NEVER the whole file. `new_str` replaces only that snippet. Using the entire file as old_str/new_str is forbidden.
{reviewer_fix_system_rules}
{approved_assets_str}
"""

    if saved_history and pending_tool_call and user_feedback == "APPROVED":
        # The human picked an asset. Inject the approved godot_path as the
        # function response so the LLM knows where the asset lives.
        approved_tool_name = pending_tool_call.get("name", "get_sprite")
        approved_asset_name = pending_tool_call.get("asset_name", "")
        approved_path = approved_assets.get(approved_asset_name, "")

        if approved_path:
            function_response_result = (
                f"Asset '{approved_asset_name}' acquired and saved at {approved_path}. "
                f"Use this exact path in your GDScript: load(\"{approved_path}\")"
            )
        else:
            function_response_result = (
                f"Asset acquisition approved. Check res://assets/ for the file. "
                "Use set_property(node, 'texture', 'path') to assign it."
            )

        # FIX: Instead of popping the entire user turn, we find the placeholder
        # function_response inside the last turn and update its result.
        # This preserves responses for other tools (e.g. read-only tools) that
        # were parallelised in the same LLM turn.
        if saved_history and saved_history[-1].get("role") == "user":
            for part in saved_history[-1].get("parts", []):
                fr = part.get("function_response")
                if fr and fr.get("name") == approved_tool_name:
                    fr["response"]["result"] = function_response_result
                    break
        else:
            # Fallback if somehow there was no user turn
            saved_history.append({
                "role": "user",
                "parts": [{
                    "function_response": {
                        "name": approved_tool_name,
                        "response": {"result": function_response_result},
                    }
                }],
            })
            
        history = saved_history
        logger.info("Coder resuming loop after asset approval for '%s': %s", approved_asset_name, approved_path)

    # -----------------------------------------------------------------------
    # FRESH START: build initial history from supervisor instruction + context
    # -----------------------------------------------------------------------
    else:
        # Extract supervisor instructions from message history
        supervisor_instruction = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and "[Supervisor]" in msg.content:
                supervisor_instruction = msg.content
                break

        # Incorporate reviewer feedback if present
        reviewer_feedback = latest_reviewer_feedback
        if reviewer_feedback:
            logger.warning(f"[Coder] Acting on reviewer feedback:\n{reviewer_feedback[:600]}")

        # In reviewer-fix mode, prevent full task restarts and unnecessary asset reacquisition.
        reviewer_fix_rules = ""
        if reviewer_fix_mode:
            reviewer_fix_rules = """
## REVIEWER FIX MODE (highest priority for this pass)
- This is a correction pass, NOT a fresh implementation pass.
- Apply the minimal set of edits needed to resolve reviewer issues.
- Do NOT reacquire assets or recreate scenes/scripts that already exist unless the reviewer explicitly asks for a different/new asset.
- If reviewer feedback flags path/API/property mistakes, patch those directly in existing files/nodes.
- If supervisor instructions conflict with reviewer fixes, prioritize reviewer fixes for this pass.
"""

        # We no longer auto-populate all .gd scripts. The Coder must use `read_file`.
        file_context_str = "File contents intentionally omitted to save context length. Use the `read_file` tool to inspect existing scripts when needed."

        # Read existing .tscn scene files and parse them into a structured summary
        # instead of dumping raw .tscn text. Raw .tscn (e.g. instance=ExtResource("1_abc"))
        # is hard for LLMs to parse; the structured summary makes it unambiguous.
        tscn_files_raw: Dict[str, str] = {}
        scene_context_str = ""
        try:
            import os
            from pathlib import Path as _SPath
            for root, dirs, files in os.walk(_SPath(project_path)):
                if any(ign in _SPath(root).parts for ign in ['.git', '.godot', 'venv', 'node_modules', 'backend', '.claude']):
                    continue
                for file in files:
                    if file.endswith('.tscn'):
                        fp = _SPath(root) / file
                        try:
                            content = fp.read_text(encoding='utf-8')
                            if len(content) < 10000:
                                rel = f"res://{fp.relative_to(_SPath(project_path))}"
                                tscn_files_raw[rel] = content
                        except Exception:
                            pass
            scene_context_str = _build_tscn_summary(tscn_files_raw)
        except Exception as e:
            logger.warning("Could not load scene context: %s", e)

        # --- Pre-fetch all read-only context concurrently to save LLM iterations ---
        # Run filesystem scan, project settings, Godot bridge queries in parallel.
        
        (
            file_tree,
            project_context,
            godot_project_files,
            godot_input_map,
            current_scene_live,
        ) = await asyncio.gather(
            asyncio.to_thread(ProjectScanner.scan_directory, project_path),
            asyncio.to_thread(ProjectScanner.get_project_context, project_path),
            godot_interface.get_project_files(project_path),
            godot_interface.get_input_map(project_path),
            godot_interface.read_scene(project_path),
        )
        
        file_tree_str = json.dumps(file_tree, indent=2)

        # When re-running after Reviewer feedback, extract what the previous Coder
        # run already did so the Coder knows exactly which nodes/scenes exist and
        # doesn't blindly re-add them.
        prev_attempt_ctx = ""
        if reviewer_feedback:
            messages = state.get("messages", [])
            for msg in reversed(messages):
                if isinstance(msg, AIMessage) and "[Coder]" in msg.content:
                    # Filter the execution log to remove massive success payloads.
                    filtered_lines = []
                    for line in msg.content.split("\n"):
                        # Keep failures completely
                        if "FAILED" in line or "Failed" in line:
                            filtered_lines.append(line)
                        # Keep read operations directly
                        elif any(op in line for op in ["[read_scene]", "[get_project_files]", "[read_file]", "[node_exists]", "[validate_script]", "[SCENE SNAPSHOT"]):
                            filtered_lines.append(line)
                        # Shrink successful writes to just "Success" + context if available
                        elif line.startswith("["):
                            prefix = line.split("]:", 1)[0]
                            # Try to preserve scene context if we attached it previously e.g. "(scene: res://...)"
                            scene_ctx = ""
                            if "(scene:" in line:
                                scene_ctx = " " + line[line.find("(scene:"):]
                            filtered_lines.append(f"{prefix}]: Success{scene_ctx}")
                        else:
                            # Keep non-tool lines
                            filtered_lines.append(line)
                    
                    filtered_content = "\n".join(filtered_lines)

                    prev_attempt_ctx = (
                        f"\n\n## PREVIOUS ATTEMPT — ALREADY COMPLETED (do NOT redo these)\n"
                        f"{filtered_content}\n"
                        f"Fix ONLY what the Reviewer flagged below. Everything else is done."
                    )
                    break

        reviewer_ctx = (
            f"\n\n## REVIEWER FEEDBACK (must be fixed in this pass):\n{reviewer_feedback}"
            f"{prev_attempt_ctx}"
            if reviewer_feedback else ""
        )

        # Build context message (moved from system_instruction to history so it persists)
        context_msg = f"""## PRE-FETCHED PROJECT DATA (already current — do NOT call get_project_files or get_input_map again)
### Godot Project Files:
{godot_project_files}

### Input Map (only use these action names in Input.is_action_*):
{godot_input_map}

## PREVIOUSLY COMPLETED TASKS
{completed_tasks_context or "None — this is the first task."}
These tasks are already done. Open and extend existing scenes/scripts rather than recreating them.

## PROJECT CONTEXT
Project Path: {project_path}
File Tree:
{file_tree_str}

{project_context}

Existing Scripts:
{file_context_str}

## CURRENTLY OPEN SCENE IN EDITOR (live in-memory state — authoritative over disk)
{current_scene_live}
This is what the editor has open RIGHT NOW. Use this to know which scene is active before issuing any open_scene, add_node, or instance_scene calls.

## ALREADY-INSTANCED SUB-SCENES (parsed from disk — do NOT instance these again in the listed parent)
{scene_context_str or "No .tscn files found."}

## IMPORTANT: Any scene listed above as already instanced in a parent scene MUST NOT be instanced again.
## To modify the internals of an instanced scene, use open_scene(scene_path) — never add nodes to the instance directly.

{reviewer_ctx}
{reviewer_fix_rules}

Current Task: {current_task}

Supervisor Instructions:
{supervisor_instruction}
"""

        if reviewer_fix_mode:
            initial_user_message = (
                f"{context_msg}\n\n"
                f"Please perform a targeted fix pass for this task in Godot 4: {current_task}\n\n"
                "Do not restart the task. Fix only the reviewer-reported issues."
            )
        else:
            initial_user_message = (
                f"{context_msg}\n\n"
                f"Please implement the following task in Godot 4: {current_task}\n\n"
                "Acquire any needed assets BEFORE creating scenes or scripts."
            )

        history = [{"role": "user", "parts": [initial_user_message]}]

    # -----------------------------------------------------------------------
    # AGENTIC TOOL LOOP
    # -----------------------------------------------------------------------
    MAX_ITERATIONS = 40  # safety cap
    execution_log: List[str] = []
    pending_review = None
    screenshot_data = None
    hit_max_iterations = False  # BUG 7: track whether we exited via the safety cap

    # Python-level dedup: track scenes instanced in this Coder run to catch
    # duplicate instance_scene calls within the same loop.
    _instanced_this_run: Set[str] = set()
    # Track which scene is currently open so add_node log lines include scene context.
    _current_open_scene: str = ""

    for iteration in range(MAX_ITERATIONS):
        if not godot_interface.manager.is_connected(project_path):
            execution_log.append("ABORTED: Godot client disconnected")
            logger.warning("Coder aborting loop — client disconnected at iteration %d", iteration)
            break

        # Call the LLM with current history
        try:
            result = await _run_llm_step_with_retries(
                f"Coder iteration {iteration}",
                llm_provider_lite.generate_with_tools,
                system_instruction=system_instruction,
                history=history,
                tool_declarations=_CODER_TOOL_DECLARATIONS,
            )
        except Exception as llm_err:
            execution_log.append(f"[LLM ERROR at iter {iteration}]: {llm_err}")
            logger.error("Coder LLM call failed at iteration %d: %s", iteration, llm_err, exc_info=True)
            break

        # Keep system_instruction (rules + order) active for all iterations.
        # Previously we set it to None, but that caused the agent to lose context
        # about mandatory workflow rules and reused assets on subsequent turns.
        # system_instruction = None 

        text = result.get("text")
        tool_calls = result.get("tool_calls")
        raw_parts = result.get("raw_parts", [])

        # Record the model's turn in history
        history.append({"role": "model", "parts": raw_parts if raw_parts else []})

        if not tool_calls:
            # LLM is done — no more tool calls, just a text summary
            if text:
                execution_log.append(f"[Coder done]: {text}")
            logger.info("Coder agentic loop finished after %d iteration(s)", iteration + 1)
            break


        # Split tool calls into read-only (safe to parallelise) and write/asset (must be sequential)
        _READ_ONLY = {"get_project_files", "get_input_map", "node_exists", "read_scene", "validate_script", "read_file"}
        read_only_tcs = [tc for tc in tool_calls if tc["name"] in _READ_ONLY]
        write_tcs     = [tc for tc in tool_calls if tc["name"] not in _READ_ONLY]

        function_response_parts = []
        hit_asset_review = False

        # ---- Concurrent dispatch for read-only tools ----
        if read_only_tcs:
            names = [tc["name"] for tc in read_only_tcs]
            logger.info("Coder parallel read-only tools [iter %d]: %s", iteration, names)
            results = await asyncio.gather(*[
                _dispatch_tool(tc["name"], tc.get("args", {}), project_path, godot_interface, asset_interface, approved_assets)
                for tc in read_only_tcs
            ])
            for tc, (tool_result, _) in zip(read_only_tcs, results):
                execution_log.append(f"[{tc['name']}]: {tool_result[:400]}")
                fr = {
                    "name": tc["name"],
                    "response": {"result": tool_result},
                }
                if "id" in tc:
                    fr["id"] = tc["id"]
                function_response_parts.append({"function_response": fr})

        # ---- Sequential dispatch for write / asset tools ----
        for tc in write_tcs:
            tc_name = tc["name"]
            
            # If a previous asset tool triggered a review, we MUST NOT process this tool,
            # but we MUST supply a placeholder response so Gemini's function call validation doesn't fail.
            if hit_asset_review:
                fr = {
                    "name": tc_name,
                    "response": {"result": "Skipped because a previous tool is waiting for human approval. Please call this tool again in the next turn."},
                }
                if "id" in tc:
                    fr["id"] = tc["id"]
                function_response_parts.append({"function_response": fr})
                continue
                
            tc_args = tc.get("args", {})

            # Python-level dedup for instance_scene: catch duplicates regardless of
            # node_name or whether the Godot scene was reloaded since last open_scene.
            if tc_name == "instance_scene" and not tc_args.get("allow_multiple", False):
                raw_path = tc_args.get("scene_path", "")
                canon = raw_path if raw_path.startswith("res://") else f"res://{raw_path}"
                if canon in _instanced_this_run:
                    skip_msg = f"[instance_scene SKIPPED — duplicate]: '{canon}' was already instanced in this run."
                    execution_log.append(skip_msg)
                    logger.info(skip_msg)
                    fr = {
                        "name": tc_name,
                        "response": {"result": skip_msg},
                    }
                    if "id" in tc:
                        fr["id"] = tc["id"]
                    function_response_parts.append({"function_response": fr})
                    continue
                _instanced_this_run.add(canon)

            detail = tc_args.get("name") or tc_args.get("scene_path") or tc_args.get("file_path") or ""
            logger.info("Coder tool call [iter %d]: %s(%s)", iteration, tc_name, list(tc_args.keys()))
            log_action_exec(iteration + 1, MAX_ITERATIONS, tc_name, detail)

            tool_result, tool_pending_review = await _dispatch_tool(
                tc_name, tc_args, project_path, godot_interface, asset_interface, approved_assets
            )

            # Track which scene is open so add_node log lines carry scene context
            if tc_name in ("open_scene", "create_scene") and "Failed" not in tool_result[:6]:
                sp = tc_args.get("scene_path") or tc_args.get("path", "")
                if sp:
                    _current_open_scene = sp if sp.startswith("res://") else f"res://{sp}"

            if tc_name == "add_node" and _current_open_scene:
                execution_log.append(f"[add_node]: {tool_result[:380]} (scene: {_current_open_scene})")
            else:
                execution_log.append(f"[{tc_name}]: {tool_result[:400]}")

            # Handle test_game screenshot
            if tc_name == "test_game":
                try:
                    res_data = json.loads(tool_result)
                    if res_data.get("success") and res_data.get("image_data"):
                        screenshot_data = res_data["image_data"]
                        if not pending_review:
                            pending_review = {"type": "screenshot", "image_data": screenshot_data, "name": "Game Screenshot"}
                except Exception:
                    pass

            # If an asset tool triggered human review, pause the loop
            if tool_pending_review:
                pending_review = tool_pending_review
                hit_asset_review = True
                placeholder = f"Asset acquisition initiated for '{tc_args.get('name', 'asset')}'. Awaiting human approval."
                fr = {
                    "name": tc_name,
                    "response": {"result": placeholder},
                }
                if "id" in tc:
                    fr["id"] = tc["id"]
                function_response_parts.append({"function_response": fr})
                continue

            fr = {
                "name": tc_name,
                "response": {"result": tool_result},
            }
            if "id" in tc:
                fr["id"] = tc["id"]
            function_response_parts.append({"function_response": fr})

        # Feed tool results back into history
        history.append({"role": "user", "parts": function_response_parts})

        # Pause the loop if a real asset review (not screenshot) is pending
        if hit_asset_review:
            logger.info("Coder pausing loop for human review of '%s'", pending_review.get("name"))
            break

    else:
        execution_log.append(f"WARNING: Reached maximum tool iterations ({MAX_ITERATIONS}). Task may be incomplete.")
        hit_max_iterations = True

    # -----------------------------------------------------------------------
    # Auto-save safety net (if coder modified a scene but forgot save_scene)
    # Skip if max iterations hit — we don't know if the scene is in a good state.
    # -----------------------------------------------------------------------
    modified_tools = {"add_node", "set_property", "attach_script", "instance_scene", "delete_node"}
    executed_tool_names = {
        line.split("]")[0].lstrip("[") for line in execution_log if line.startswith("[")
    }
    if (not hit_max_iterations
            and (executed_tool_names & modified_tools)
            and "save_scene" not in executed_tool_names
            and not pending_review):
        try:
            save_result = await godot_interface.save_scene(project_path)
            execution_log.append(f"[save_scene (auto)]: {save_result}")
        except Exception as e:
            execution_log.append(f"[save_scene (auto) FAILED]: {str(e)}")

    # -----------------------------------------------------------------------
    # Scene snapshot for the Reviewer
    # -----------------------------------------------------------------------
    if not pending_review:
        try:
            scene_snapshot = await godot_interface.read_scene(project_path)
            execution_log.append(f"\n[SCENE SNAPSHOT]:\n{scene_snapshot}")
        except Exception as e:
            execution_log.append(f"[SCENE SNAPSHOT FAILED]: {str(e)}")

    log_str = "\n".join(execution_log)
    coder_message = AIMessage(content=f"[Coder]: Executed actions:\n{log_str}")

    result_label = "awaiting review" if pending_review else "done"
    log_node_done("Coder", result_label)

    new_state: Dict[str, Any] = {
        "messages": [coder_message],
        "pending_review": pending_review,
        "user_feedback": None,
        "latest_screenshot": screenshot_data,
        "tool_loop_history": None,
        "pending_tool_call": None,
        "pending_actions": None,
    }

    if pending_review and pending_review.get("type") != "screenshot":
        # Save history for resumption after human approval.
        # The history currently ends with the placeholder function response for
        # the asset tool. human_review_node will replace the last user turn with
        # a real function response containing the approved path.
        new_state["tool_loop_history"] = history
        new_state["pending_tool_call"] = {
            "name": pending_review.get("_tool_name", "get_sprite"),
            "asset_name": pending_review.get("canonical_name") or pending_review.get("name", ""),
        }

    return new_state


async def reviewer_node(state: StudioState) -> Dict:
    """
    The Reviewer checks the Coder's work.
    If errors exist, it sends the workflow back to the Coder.
    If the code looks good, it returns "APPROVED".
    """
    messages = state.get("messages", [])
    errors = state.get("errors", [])
    
    logger.info("Reviewer node checking code...")
    log_node_start("Reviewer")

    # Extract the latest coder message
    coder_code = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and "[Coder]" in msg.content:
            coder_code = msg.content
            break
            
    # Auto-fetch relevant files mentioned by the Coder
    project_path = state.get("project_path", "")
    import re
    import os
    
    mentioned_paths = set(re.findall(r'res://[^\s\'"<>`*]+?(?:\.gd|\.tscn)', coder_code))
    file_contents = []
    
    for res_path in mentioned_paths:
        relative_path = res_path.replace("res://", "")
        # Remove any trailing punctuation that might have been caught
        relative_path = relative_path.rstrip(".,;:\"\'")
        res_path_clean = f"res://{relative_path}"
        
        full_path = os.path.join(project_path, relative_path)
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            file_contents.append(f"--- {res_path_clean} ---\n{content}")
        except Exception as e:
            file_contents.append(f"--- {res_path_clean} ---\n(Could not read file: {e})")
            
    files_context = ""
    if file_contents:
        files_context = "\n\n### Auto-fetched File Context ###\n" + "\n\n".join(file_contents)
    
    # If there are existing errors in state, handle them
    if errors:
        error_summary = "\n".join(errors)
        review_message = AIMessage(
            content=f"[Reviewer]: Found errors in the code:\n{error_summary}\nPlease fix these issues."
        )
        return {
            "messages": [review_message],
            "errors": []  # Clear errors after reporting
        }
    
    # Check if a screenshot is available
    screenshot_data = state.get("latest_screenshot")
    
    # Use LLM to review the code
    prompt = f"""Review the following execution log and code changes for Godot 4.x:

{coder_code}
{files_context}

Check for:
1. GDScript syntax errors (Godot 4.x syntax: @onready, @export, signal.connect(callable), CharacterBody2D not KinematicBody2D).
2. Godot 4.x API correctness: move_and_slide() takes no arguments, velocity is a CharacterBody2D property (not linear_velocity), Sprite2D not Sprite.
3. Did all actions succeed per the execution log? CRITICAL: If ANY action has "FAILED" or "Failed syntax validation" in the log, you MUST NOT approve.
4. Game completeness (only if this is a full game task): Was set_main_scene() called? Is there a CanvasLayer for HUD? Is a GameManager or game state autoload present? Is there game-over/restart logic?
5. Collision shapes: was a shape resource (RectangleShape2D, CapsuleShape2D, etc.) set on each CollisionShape2D — not just the node added?
6. Node naming: Were any nodes added with generic type-based names (e.g. 'Sprite2D', 'CollisionShape2D', 'CharacterBody2D', 'Node2D' as a node name)? These cause name clashes with sub-scene instances. Flag this and recommend short semantic names like 'Sprite', 'Collision'.
7. Duplicate actions: Are there repeated add_node or instance_scene calls targeting the same node path? Each node should only be added once. If a 'Skipped: Node ... already exists' message appeared, verify the coder did not try to add it again.
8. Scene architecture violations: Did the Coder call `add_node` to place an entity-type node (CharacterBody2D, RigidBody2D, Area2D, or similar) directly in the main or level scene instead of using `instance_scene`? This is a critical error — flag it.
9. Component node placement: Did the Coder call `add_node` to place any component node (Sprite2D, CollisionShape2D, AudioStreamPlayer, AnimationPlayer, Camera2D, etc.) directly in the main or level scene? These belong only inside their entity's own .tscn. Adding them directly to main.tscn causes Godot "name clashes" load errors when the entity is instanced. Flag any such calls.
10. Root-type duplication: If `create_scene` was called with a root type (e.g. CharacterBody2D), was `add_node` then called with the same type under parent `"."`? That creates a duplicate root-type child — flag it.

If everything is correct and complete, respond with ONLY the word "APPROVED".
If there are issues, list them with specific fix instructions."""
    
    # Send text and image (if available) to the LLM
    if screenshot_data:
        prompt_content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": screenshot_data}}
        ]
        system_msg = "You are a code reviewer specializing in Godot 4.x. You evaluate code changes and visually inspect game screenshots to ensure assets are properly placed, scaled, and visible."
    else:
        prompt_content = prompt
        system_msg = "You are a code reviewer specializing in Godot 4.x GDScript. You are thorough but fair."

    try:
        review = await _run_llm_step_with_retries(
            "Reviewer",
            llm_provider.generate,
            prompt=prompt_content,
            system_instruction=system_msg,
        )
        
        # BUG 6: Use exact word match, not substring. The LLM is instructed to
        # return ONLY the word "APPROVED" when everything is fine. Substring
        # matching causes false positives (e.g. "The texture was APPROVED by...").
        cleaned = review.strip().upper()
        if cleaned == "APPROVED" or cleaned == "APPROVED." or cleaned == "APPROVED!":
            approval_message = AIMessage(content="[Reviewer]: APPROVED")
            log_node_done("Reviewer", "APPROVED")
            return {
                "messages": [approval_message]
            }
        else:
            logger.warning(f"[Reviewer] Sending feedback to Coder:\n{review}")
            feedback_message = AIMessage(content=f"[Reviewer]: Issues found:\n{review}")
            log_node_done("Reviewer", "issues found — looping back to Coder")
            return {
                "messages": [feedback_message]
            }
    except Exception as e:
        logger.error(f"Reviewer node error: {e}")
        error_message = AIMessage(content=f"[Reviewer Error]: {str(e)}")
        return {
            "messages": [error_message]
        }


def human_review_node(state: StudioState) -> Dict:
    """
    Checks if there's a pending asset or screenshot review.
    On approval, moves approved asset path into approved_assets so coder_node
    can inject it as the function response when resuming the tool loop.
    """
    pending = state.get("pending_review")
    feedback = state.get("user_feedback")

    if not pending:
        return {}

    logger.info("Human review node: pending=%s, feedback=%s", pending.get("type"), feedback)

    if feedback == "APPROVED":
        asset_name = pending.get("canonical_name") or pending.get("name", "")

        # BUG 4: main.py already handled file renaming and built the correct
        # approved_assets map (respecting the user's selected_index).
        # Trust that first; only fall back to option[0] path derivation if
        # main.py didn't populate approved_assets (e.g. non-sprite asset types).
        existing_approved = state.get("approved_assets") or {}
        approved_path = existing_approved.get(asset_name)  # set by main.py on approval

        if not approved_path:
            # Fallback: derive path from options (single-option or non-sprite types)
            if "options" in pending and pending["options"]:
                approved_path = pending["options"][0].get("godot_path")
                try:
                    import re as _re
                    import shutil as _shutil
                    from pathlib import Path as _Path
                    src = _Path(pending["options"][0].get("asset_path", ""))
                    if src.exists() and "_opt0" in src.name:
                        canonical_name = _re.sub(r"_opt\d+", "", src.stem)
                        dest = src.parent / f"{canonical_name}{src.suffix}"
                        if not dest.exists():
                            _shutil.copy2(str(src), str(dest))
                        approved_path = f"res://assets/sprites/{dest.name}"
                except Exception as e:
                    logger.warning("Could not rename opt file: %s", e)
            elif pending.get("godot_path"):
                approved_path = pending["godot_path"]

        if asset_name and approved_path:
            existing_approved[asset_name] = approved_path

        approval_msg = AIMessage(content=f"[User]: APPROVED asset '{asset_name}'")
        return {
            "messages": [approval_msg],
            "pending_review": None,
            "approved_assets": existing_approved,
            # Keep user_feedback = "APPROVED" so the router sends us back to coder
        }

    if feedback:
        # Non-approval feedback — route back to coder for a redo
        feedback_msg = AIMessage(content=f"[User Feedback]: {feedback}")
        return {
            "messages": [feedback_msg],
            # Clear pending_review so the dialog doesn't persist
            "pending_review": None,
            # Clear saved history so coder starts fresh with the feedback
            "tool_loop_history": None,
            "pending_tool_call": None,
        }

    # No feedback yet — waiting for user input (handled by Orchestrator interrupt)
    return {}
