import asyncio
import logging
import json
from typing import Dict, List, Optional, Any
from langchain_core.messages import AIMessage
from agents.studio.state import StudioState
from agents.studio.tools import GodotInterface, AssetInterface
from core.llm import LLMFactory
from core.log import log_node_start, log_node_done, log_action_exec, log_asset_acquire
from services.project_scanner import ProjectScanner
from services.godot_rag import godot_rag
from services.project_rag import project_rag
import google.generativeai as genai

logger = logging.getLogger(__name__)

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
        description="List all .gd/.tscn/.tres files in the Godot project. ALWAYS call this first to see what already exists before creating anything.",
        parameters=genai.protos.Schema(type_=_T.OBJECT, properties={}),
    ),
    genai.protos.FunctionDeclaration(
        name="get_input_map",
        description="Read the project's InputMap (action names → key bindings). Call before writing player movement/input code.",
        parameters=genai.protos.Schema(type_=_T.OBJECT, properties={}),
    ),
    genai.protos.FunctionDeclaration(
        name="node_exists",
        description="Check if a node already exists in the currently open scene. Useful for verifying state, but NOT required before add_node/instance_scene as they handle duplicates safely.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={"node_path": _s(_T.STRING, "Path to check, e.g. 'Player' or 'UI/HUD'. Use '.' for root.")},
            required=["node_path"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="read_scene",
        description="Get the current scene tree from the Godot Editor. Use after opening a scene to see existing nodes.",
        parameters=genai.protos.Schema(type_=_T.OBJECT, properties={}),
    ),
    genai.protos.FunctionDeclaration(
        name="create_scene",
        description="Create a new .tscn scene file with the given root node type. Also opens it in the editor.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "scene_path": _s(_T.STRING, "res:// path to the new scene, e.g. 'res://scenes/player.tscn'"),
                "root_type": _s(_T.STRING, "Root node type, e.g. 'CharacterBody2D', 'Area2D', 'Node2D'"),
            },
            required=["scene_path", "root_type"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="open_scene",
        description="Open an existing .tscn scene in the editor for modification.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={"scene_path": _s(_T.STRING, "res:// path to the scene to open")},
            required=["scene_path"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="add_node",
        description="Add a node to the currently open scene. Just call it - duplicates will be skipped automatically.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "parent_path": _s(_T.STRING, "Parent node path. Use '.' for root."),
                "node_type": _s(_T.STRING, "Godot node type, e.g. 'Sprite2D', 'CollisionShape2D'"),
                "node_name": _s(_T.STRING, "SHORT semantic name, e.g. 'Sprite', 'Collision', 'Player'. NEVER use the type name as the node name."),
            },
            required=["parent_path", "node_type", "node_name"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="set_property",
        description="Set a property on a node. Use for shape resources (RectangleShape2D etc). NEVER use for textures — load textures in GDScript instead.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "node_path": _s(_T.STRING, "Node path in the scene, e.g. 'Collision'"),
                "property_name": _s(_T.STRING, "Property name, e.g. 'shape'"),
                "value": _s(_T.STRING, "Property value as a string or JSON-serialisable value"),
            },
            required=["node_path", "property_name", "value"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="create_script",
        description="Write a GDScript (.gd) file to disk. Always validate complex scripts first. Load textures inside _ready() using load(\"res://...\"), never via set_property.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "file_path": _s(_T.STRING, "res:// or absolute path to the script, e.g. 'res://scripts/enemy.gd'"),
                "content": _s(_T.STRING, "Full GDScript source code"),
            },
            required=["file_path", "content"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="validate_script",
        description="Validate GDScript syntax without writing to disk. Returns 'Script is valid' or an error. Call before create_script for complex scripts.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={"content": _s(_T.STRING, "GDScript source to validate")},
            required=["content"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="attach_script",
        description="Attach a script file to a node in the currently open scene.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "node_path": _s(_T.STRING, "Node path, e.g. '.' for root, or 'Sprite'"),
                "script_path": _s(_T.STRING, "res:// path to the .gd script"),
            },
            required=["node_path", "script_path"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="save_scene",
        description="Save the currently open scene to disk. CRITICAL — MUST be called after add_node/set_property/attach_script or changes are lost.",
        parameters=genai.protos.Schema(type_=_T.OBJECT, properties={}),
    ),
    genai.protos.FunctionDeclaration(
        name="instance_scene",
        description="Instance a .tscn sub-scene as a child of a node. Just call it - duplicates will be skipped automatically. Use to add player/enemy/UI into the main scene.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "scene_path": _s(_T.STRING, "res:// path to the .tscn to instance"),
                "parent_path": _s(_T.STRING, "Parent node path in the current scene"),
                "node_name": _s(_T.STRING, "Name for the instance node, e.g. 'Player'"),
            },
            required=["scene_path", "parent_path"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="set_main_scene",
        description="Set the main scene that Godot runs when pressing Play (F5). Must be called once.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={"scene_path": _s(_T.STRING, "res:// path to the main scene")},
            required=["scene_path"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="scan_filesystem",
        description="Tell Godot to re-scan files. Call after writing asset files and before using them.",
        parameters=genai.protos.Schema(type_=_T.OBJECT, properties={}),
    ),
    genai.protos.FunctionDeclaration(
        name="execute_godot_script",
        description="Execute arbitrary GDScript in the Godot Editor context. Use for complex automation, ProjectSettings changes, or operations not covered by other tools.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={"code": _s(_T.STRING, "GDScript code to execute (no 'func' or 'extends' — just the body)")},
            required=["code"],
        ),
    ),
    # ------------------------------------------------------------------
    # Asset acquisition tools — call BEFORE creating scenes/scripts
    # ------------------------------------------------------------------
    genai.protos.FunctionDeclaration(
        name="get_sprite",
        description=(
            "Acquire a single-frame 2D pixel art sprite. "
            "ALWAYS call this BEFORE create_scene or create_script when the task needs a character, enemy, pickup, or icon sprite. "
            "Returns the confirmed res:// path — use it directly in your GDScript load() call."
        ),
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "name": _s(_T.STRING, "Snake_case asset identifier, e.g. 'enemy_swarm_ship'"),
                "description": _s(_T.STRING, "Concise visual description, e.g. 'pixel art red enemy spaceship top-down view transparent background'"),
                "style": _s(_T.STRING, "Art style: pixel_art | flat | cartoon | hand_drawn (default: pixel_art)"),
                "width": _s(_T.INTEGER, "Width in pixels, e.g. 24"),
                "height": _s(_T.INTEGER, "Height in pixels, e.g. 24"),
                "tags": _s(_T.STRING, "Comma-separated search tags, e.g. 'enemy,spaceship,pixel_art'"),
            },
            required=["name", "description"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="get_spritesheet",
        description=(
            "Acquire a multi-frame sprite sheet (animation strip). "
            "Call BEFORE create_scene when the task needs an animated character. "
            "Returns the confirmed res:// path and frame metadata."
        ),
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "name": _s(_T.STRING, "Snake_case asset identifier, e.g. 'player_walk'"),
                "description": _s(_T.STRING, "Concise visual description"),
                "poses": _s(_T.STRING, "Comma-separated animation frames, e.g. 'idle,walk_1,walk_2,jump'"),
                "style": _s(_T.STRING, "Art style: pixel_art | flat | cartoon | hand_drawn"),
                "frame_width": _s(_T.INTEGER, "Width of each frame in pixels"),
                "frame_height": _s(_T.INTEGER, "Height of each frame in pixels"),
                "tags": _s(_T.STRING, "Comma-separated search tags"),
            },
            required=["name", "description"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="get_tileset",
        description="Acquire a tileset image for Godot TileMaps. Call before creating TileMap scenes.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "name": _s(_T.STRING, "Asset identifier, e.g. 'space_tileset'"),
                "description": _s(_T.STRING, "Concise visual description"),
                "style": _s(_T.STRING, "Art style"),
                "tile_size": _s(_T.INTEGER, "Pixels per tile (square)"),
                "columns": _s(_T.INTEGER, "Number of tile columns"),
                "rows": _s(_T.INTEGER, "Number of tile rows"),
                "tile_types": _s(_T.STRING, "Comma-separated tile type labels, e.g. 'ground,wall,platform'"),
                "tags": _s(_T.STRING, "Comma-separated search tags"),
            },
            required=["name", "description"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="get_background",
        description="Acquire a 2D background image. Call before creating scenes that need a background.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "name": _s(_T.STRING, "Asset identifier, e.g. 'space_bg'"),
                "description": _s(_T.STRING, "Concise visual description"),
                "style": _s(_T.STRING, "Art style"),
                "width": _s(_T.INTEGER, "Width in pixels (default 1280)"),
                "height": _s(_T.INTEGER, "Height in pixels (default 720)"),
                "tags": _s(_T.STRING, "Comma-separated search tags"),
            },
            required=["name", "description"],
        ),
    ),
    genai.protos.FunctionDeclaration(
        name="get_audio",
        description="Acquire an audio asset (SFX or music). Call before creating scenes that need sound.",
        parameters=genai.protos.Schema(
            type_=_T.OBJECT,
            properties={
                "name": _s(_T.STRING, "Asset identifier, e.g. 'shoot_sfx'"),
                "description": _s(_T.STRING, "Description of the sound"),
                "audio_type": _s(_T.STRING, "'sfx' or 'music'"),
                "duration_seconds": _s(_T.NUMBER, "Target duration in seconds"),
                "tags": _s(_T.STRING, "Comma-separated search tags"),
            },
            required=["name", "description"],
        ),
    ),
]

# Initialize LLM provider
llm_provider = LLMFactory.get_provider()

async def supervisor_node(state: StudioState) -> Dict:
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

    # Pre-load file structure context (run in thread — synchronous file I/O)
    file_tree = await asyncio.to_thread(ProjectScanner.scan_directory, project_path)
    file_tree_str = json.dumps(file_tree, indent=2)

    # Pre-load project settings (InputMap, Autoloads, Layers) context
    project_context = await asyncio.to_thread(ProjectScanner.get_project_context, project_path)

    # Build a prompt for the supervisor
    
    # RAG: Index current project code to help Supervisor understand existing naming conventions
    await asyncio.to_thread(project_rag.index_project, project_path)
    
    # Query for project structure and relevant docs
    rag_query = f"{current_task} common pitfalls"
    godot_docs_list, project_rag_list = await asyncio.gather(
        asyncio.to_thread(godot_rag.query, rag_query, 3),
        asyncio.to_thread(project_rag.query, current_task, 5),
    )
    rag_context = "\n\n".join(godot_docs_list + project_rag_list)

    prompt = f"""You are the Supervisor for a game development AI system that controls Godot 4.x.

Game Design Document:
{gdd}

Current Task:
{current_task}

Previously Completed Tasks (these are DONE — do NOT redo them; build on top of their results):
{completed_tasks_context or "None yet — this is the first task."}

Project Path: {project_path}

Project File Tree:
{file_tree_str}

{project_context}

## REFERENCE DOCS & EXISTING CODE:
{rag_context}

Your job is to analyze this task and decompose it into a specific list of step-by-step instructions for the Coder.
Encourage the Coder to batch operations where possible (e.g. "Create scene AND add nodes X, Y, Z").

**CRITICAL RULE - STRICT TASK SCOPE**: You MUST stick absolutely to the scope of the task defined above. Do NOT invent completely new features, add extra nodes, or modify unconnected systems outside the current task's objective.
**CRITICAL RULE - REALITY GROUNDING**: Never invent string identifiers for input actions, autoloads, or collision layers. You MUST only use the items listed in the "PROJECT GROUND TRUTH CONTEXT" above. If you need a basic input, strictly rely on default UI actions like `ui_up`, `ui_down`, etc., instead of inventing actions like `move_up`.

AVAILABLE TOOLS the Coder has:
- create_scene(path, root_type): Create a new .tscn scene (also opens it in editor)
- add_node(parent_path, node_type, node_name): Add nodes to the open scene
- set_property(node_path, property_name, value): Set node properties (textures, shapes, etc.)
- attach_script(node_path, script_path): Attach a GDScript to a node
- create_script(path, content): Write a .gd script file
- save_scene(): SAVE the open scene to disk — MUST be called after modifying a scene
- open_scene(path): Open an existing scene for editing
- instance_scene(scene_path, parent_path, node_name): Instance a sub-scene (.tscn) as a child
- scan_filesystem(): Refresh Godot's file index after writing new files
- execute_godot_script(code): Execute arbitrary GDScript in the editor context. Use this for ANY complex operation not covered by other tools (e.g. changing editor settings, multi-step automation, or using internal Godot APIs).
- get_sprite, get_spritesheet, get_tileset, get_background, get_audio: Acquire game assets
- validate_script(content): Validate GDScript syntax before writing to disk — call before create_script when scripts are complex
- get_project_files(): List all .gd/.tscn/.tres files in the project — call first to check what already exists
- get_input_map(): Read defined input actions (e.g. ui_left, jump) — call before writing player input code
- node_exists(node_path): Check if a specific node already exists in the open scene before adding it

CRITICAL INSTRUCTIONS FOR YOUR PLAN:
1. **ALWAYS START with get_project_files** to see what scenes and scripts already exist. If a .tscn file already exists for this task, instruct the Coder to open it and read the scene tree first — do NOT recreate it.
2. **DO NOT CHECK FOR NODE EXISTENCE manually**. The `add_node` and `instance_scene` tools handle duplicate checks safely. Skip `node_exists` or `read_scene` calls unless you really need to inspect properties.
3. **USE DESCRIPTIVE NODE NAMES**: Never use generic names like "Sprite2D", "CollisionShape2D", or "Node". Use short, meaningful names like "Sprite", "Collision", "Player", "HUD". This prevents name collisions between siblings and sub-scenes.
   **CRITICAL CONSISTENCY CHECK**: If you name a node "Sprite" in the scene, your script MUST refence it as `$Sprite`, not `$Sprite2D`. Mismatches cause "null instance" crashes.
4. Always include "save_scene" step after adding nodes/properties to a scene.
5. Always include "set_main_scene" for the first task that creates the main/root scene.
6. When composing scenes, instruct the Coder to use "instance_scene" to add sub-scenes (player, enemies) into the main scene rather than recreating all nodes.
7. ASSET ACQUISITION — MANDATORY FIRST STEP for any scene with visual/audio elements:
   Whenever the task creates a character, enemy, pickup, background, or tileset that needs a
   visual, your plan MUST include an explicit asset acquisition step BEFORE scene/script steps.
   Use this exact format when giving the Coder instructions:
     - Characters/enemies/sprites: "Call get_sprite('<name>', '<description>', 'pixel_art', <w>, <h>)"
       e.g. "Call get_sprite('player', 'pixel art platformer hero facing right', 'pixel_art', 32, 64)"
       e.g. "Call get_sprite('enemy_slime', 'green pixel art slime enemy', 'pixel_art', 32, 32)"
     - Animated characters: "Call get_spritesheet('<name>', '<desc>', 'idle,walk,jump', 'pixel_art', <fw>, <fh>)"
     - Tile levels: "Call get_tileset('tileset', '<desc>', 'pixel_art', 16, 8, 4, 'ground,wall,platform')"
     - Backgrounds: "Call get_background('background', '<desc>', 'pixel_art', 1280, 720)"
     - Sounds/music: "Call get_audio('<name>', '<desc>', 'sfx', 1)"
   Do NOT skip this step — the Coder cannot load a texture that doesn't exist on disk.
   Only skip asset acquisition if the asset file already appears in the Project File Tree above.
7. TEXTURE ASSIGNMENT:
   - Textures and sprites MUST be loaded inside GDScript (_ready) using load("res://..."), NEVER via set_property.
   - **SAFETY PATTERN**: To avoid "null instance" errors, prefer attaching the script DIRECTLY to the Sprite node if possible.
     - If script is on Sprite: USE `texture = load(...)`
     - If script is on Parent: USE `$Sprite.texture = load(...)` (Ensure $Sprite name matches `add_node` name exactly!)
8. SCALE AND VIEWPORT — MANDATORY: The FIRST action of any game must call execute_godot_script to configure:
   - Window: 1280×720 (viewport_width=1280, viewport_height=720)
   - Pixel art rendering: rendering/textures/canvas_textures/default_texture_filter = 0 (Nearest)
   - Renderer: rendering/renderer/rendering_method = "gl_compatibility"
   Then call ProjectSettings.save().
   Camera2D zoom: for 32px sprites use Vector2(2,2); for 64px use Vector2(1,1). ALWAYS set zoom explicitly.
   Effective viewport at zoom 2×: 640×360 world units. Position ground at y=300, player at y=250, platforms at y=100-200.
   NEVER rely on default camera/window settings — they will make sprites microscopic.
9. COMPLETE GAME CHECKLIST: If the task is to create a complete or playable game, your plan MUST cover ALL of the following:
   - Player scene: CharacterBody2D + Sprite2D + CollisionShape2D + player.gd (movement, health, input via get_axis/is_action_just_pressed)
   - Enemy/obstacle scene with simple AI or patrol behavior script
   - Main scene (Node2D): instances player + enemies via instance_scene, has Camera2D with zoom set
   - HUD scene (CanvasLayer): score Label, health ProgressBar or Label, connected to GameManager signals
   - GameManager autoload script (res://scripts/game_manager.gd): score, lives, game_over(), restart() — registered via execute_godot_script
   - set_main_scene() called on the main scene
   - Collision layers: player on layer 1, enemies on layer 2, collectibles on layer 4, environment on layer 8
   - Game-over logic: get_tree().paused = true, show game-over screen, restart button connected to GameManager.restart()

Break the task into smaller, logical chunks. Provide clear, actionable instructions.
"""
    
    try:
        response = await asyncio.to_thread(
            llm_provider.generate,
            prompt=prompt,
            system_instruction="You are a game development project supervisor. You break down tasks into clear, actionable steps.",
        )
        
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

        elif tool_name == "create_script":
            result = await godot_interface.apply_code(
                project_path, tool_args["file_path"], tool_args["content"]
            )

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
                return f"Asset '{asset_name}' is already approved at {path}. Use this path in your code.", None

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
                return f"Asset '{asset_name}' is already approved at {path}. Use this path in your code.", None

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
                return f"Asset '{asset_name}' is already approved at {path}. Use this path in your code.", None

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
                return f"Asset '{asset_name}' is already approved at {path}. Use this path in your code.", None

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
                return f"Asset '{asset_name}' is already approved at {path}. Use this path in your code.", None

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

    return str(result), pending_review


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
    
    # Construct persistent system instruction (rules + checked assets)
    approved_assets_str = ""
    if approved_assets:
        approved_assets_str = (
            "\n\nAlready-approved asset paths (use these in GDScript load() calls):\n"
            + "\n".join(f"  - {n}: {p}" for n, p in approved_assets.items())
        )

    system_instruction = f"""You are a Godot 4.x Expert and Automation Engineer implementing a game development task.
You have a set of tools to interact with the Godot Editor and acquire game assets.
Work efficiently: BATCH your tool calls. You can (and should) call multiple tools in a single turn.
For example: Create a scene, add 5 nodes, set their properties, and save the scene — all in ONE response.

## MANDATORY WORKFLOW ORDER
1. If the task needs a SPRITE, BACKGROUND, TILESET, or AUDIO — check "Already-approved asset paths" first.
   - If present, reuse the existing res:// path and do NOT call the asset tool again.
   - If not present, call the appropriate asset tool (get_sprite / get_spritesheet / ...).
   You will receive the confirmed res:// path in the tool result — use that exact path in your GDScript load() call.
2. Create scenes and scripts AFTER you have the asset paths confirmed.
3. DO NOT manually check if nodes exist using node_exists(). The add_node() and instance_scene() tools already handle duplicate checks safely.
4. ALWAYS call save_scene() after modifying a scene.
5. OPTIMIZE CONFIGURATION: When setting multiple project settings (window size, renderer, physics layers), write a SINGLE `execute_godot_script` block that sets them all at once.

## GODOT 4 CRITICAL FACTS
- CharacterBody2D (NOT KinematicBody2D). move_and_slide() takes NO arguments.
- Sprite2D (NOT Sprite). AnimatedSprite2D for animations.
- SCALE & VISIBILITY: When instancing nodes via script, ALWAYS setting `position`, `scale`, and `owner` is mandatory.
  - Pixel art scale: If using low-res assets (e.g., 32x32), use a zoomed Camera2D (Zoom 2.0 or 4.0) rather than scaling sprites up, unless specific effect is desired.
  - Visibility: Ensure nodes are added to the tree (`add_child`) and are not hitting `modulate.a = 0`.
- NODE COMPATIBILITY: Do NOT add `Control` nodes (UI) as children of `Node2D` without a `CanvasLayer` or proper anchoring. UI should usually be in a separate `CanvasLayer`.
- INSTANCE SAFETY: Just call `instance_scene`. The tool handles parent/name checks for you.
- Textures MUST be loaded in _ready() via load("res://...") — NEVER via set_property.
- Use @onready var node: Type = $NodeName for child references.
- Signals: signal_name.connect(callable) (NOT old connect("signal_name", ...)).
- CollisionShape2D needs a shape resource set via set_property.
- HUD elements must be children of CanvasLayer.
- Name nodes with short semantic names (Sprite, Collision) NOT type names (Sprite2D).
- REALITY GROUNDING: only use input actions listed in get_input_map() results or
  the default ui_* actions. Never invent action names like 'move_up'.
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
                "Use load() in _ready() to assign it to the Sprite2D texture."
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
        reviewer_feedback = ""
        for msg in messages:
            if isinstance(msg, AIMessage) and "[Reviewer]" in msg.content:
                reviewer_feedback = msg.content

        # Auto-populate file context with all .gd scripts
        import os
        file_context = state.get("file_context", {})
        if not file_context:
            try:
                from pathlib import Path as _Path
                p_root = _Path(project_path)
                for root, dirs, files in os.walk(p_root):
                    if any(ign in _Path(root).parts for ign in ['.git', '.godot', 'venv', 'node_modules', 'backend', '.claude']):
                        continue
                    for file in files:
                        if file.endswith('.gd'):
                            fp = _Path(root) / file
                            try:
                                rel = f"res://{fp.relative_to(p_root)}"
                                content = fp.read_text(encoding='utf-8')
                                if len(content) < 15000:
                                    file_context[str(rel)] = content
                            except Exception:
                                pass
            except Exception as e:
                logger.warning("Could not load script context: %s", e)

        file_context_str = "\n".join(
            f"File: {path}\n{content}\n" for path, content in file_context.items()
        )

        # --- Pre-fetch all read-only context concurrently to save LLM iterations ---
        # Run filesystem scan, project settings, Godot bridge queries, and RAG in parallel.
        
        # 0. Index current project code for RAG
        await asyncio.to_thread(project_rag.index_project, project_path)
        
        rag_query = f"{current_task} {supervisor_instruction}"
        (
            file_tree,
            project_context,
            godot_docs_list,
            project_rag_list,
            godot_project_files,
            godot_input_map,
        ) = await asyncio.gather(
            asyncio.to_thread(ProjectScanner.scan_directory, project_path),
            asyncio.to_thread(ProjectScanner.get_project_context, project_path),
            asyncio.to_thread(godot_rag.query, rag_query, 5),
            asyncio.to_thread(project_rag.query, rag_query, 3),
            godot_interface.get_project_files(project_path),
            godot_interface.get_input_map(project_path),
        )
        
        godot_docs_context = "\n\n".join(godot_docs_list + project_rag_list)
        
        file_tree_str = json.dumps(file_tree, indent=2)

        reviewer_ctx = (
            f"\n\nREVIEWER FEEDBACK (must be fixed in this pass):\n{reviewer_feedback}"
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

{godot_docs_context}{reviewer_ctx}

Current Task: {current_task}

Supervisor Instructions:
{supervisor_instruction}
"""

        initial_user_message = (
            f"{context_msg}\n\n"
            f"Please implement the following task in Godot 4: {current_task}\n\n"
            "Remember: start with get_project_files(), then acquire any needed assets "
            "BEFORE creating scenes or scripts."
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

    for iteration in range(MAX_ITERATIONS):
        if not godot_interface.manager.is_connected(project_path):
            execution_log.append("ABORTED: Godot client disconnected")
            logger.warning("Coder aborting loop — client disconnected at iteration %d", iteration)
            break

        # Call the LLM with current history
        try:
            result = await asyncio.to_thread(
                llm_provider.generate_with_tools,
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
        _READ_ONLY = {"get_project_files", "get_input_map", "node_exists", "read_scene", "validate_script"}
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
                function_response_parts.append({
                    "function_response": {
                        "name": tc["name"],
                        "response": {"result": tool_result},
                    }
                })

        # ---- Sequential dispatch for write / asset tools ----
        for tc in write_tcs:
            tc_name = tc["name"]
            
            # If a previous asset tool triggered a review, we MUST NOT process this tool,
            # but we MUST supply a placeholder response so Gemini's function call validation doesn't fail.
            if hit_asset_review:
                function_response_parts.append({
                    "function_response": {
                        "name": tc_name,
                        "response": {"result": "Skipped because a previous tool is waiting for human approval. Please call this tool again in the next turn."},
                    }
                })
                continue
                
            tc_args = tc.get("args", {})

            detail = tc_args.get("name") or tc_args.get("scene_path") or tc_args.get("file_path") or ""
            logger.info("Coder tool call [iter %d]: %s(%s)", iteration, tc_name, list(tc_args.keys()))
            log_action_exec(iteration + 1, MAX_ITERATIONS, tc_name, detail)

            tool_result, tool_pending_review = await _dispatch_tool(
                tc_name, tc_args, project_path, godot_interface, asset_interface, approved_assets
            )

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
                function_response_parts.append({
                    "function_response": {
                        "name": tc_name,
                        "response": {"result": placeholder},
                    }
                })
                continue

            function_response_parts.append({
                "function_response": {
                    "name": tc_name,
                    "response": {"result": tool_result},
                }
            })

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
    modified_tools = {"add_node", "set_property", "attach_script", "instance_scene"}
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

Check for:
1. GDScript syntax errors (Godot 4.x syntax: @onready, @export, signal.connect(callable), CharacterBody2D not KinematicBody2D).
2. Godot 4.x API correctness: move_and_slide() takes no arguments, velocity is a CharacterBody2D property (not linear_velocity), Sprite2D not Sprite.
3. Did all actions succeed per the execution log? CRITICAL: If ANY action has "FAILED" or "Failed syntax validation" in the log, you MUST NOT approve.
4. Game completeness (only if this is a full game task): Was set_main_scene() called? Is there a CanvasLayer for HUD? Is a GameManager or game state autoload present? Is there game-over/restart logic?
5. Collision shapes: was a shape resource (RectangleShape2D, CapsuleShape2D, etc.) set on each CollisionShape2D — not just the node added?
6. Node naming: Were any nodes added with generic type-based names (e.g. 'Sprite2D', 'CollisionShape2D', 'CharacterBody2D', 'Node2D' as a node name)? These cause name clashes with sub-scene instances. Flag this and recommend short semantic names like 'Sprite', 'Collision'.
7. Duplicate actions: Are there repeated add_node or instance_scene calls targeting the same node path? Each node should only be added once. If a 'Skipped: Node ... already exists' message appeared, verify the coder did not try to add it again.

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
        review = await asyncio.to_thread(
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


