import json
import logging
import asyncio
import subprocess
from pathlib import Path
from typing import List, Any
from langchain_core.tools import tool, StructuredTool
from session import ConnectionManager
from services.asset_service import AssetService

logger = logging.getLogger(__name__)

@tool
def read_file(file_path: str) -> str:
    """Read the contents of a file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

@tool
def list_files(directory: str) -> str:
    """List all files in a directory."""
    try:
        p = Path(directory)
        if not p.exists():
            return f"Directory {directory} does not exist."
        files = [f.name for f in p.iterdir() if f.is_file()]
        return json.dumps(files)
    except Exception as e:
        return f"Error listing files: {str(e)}"

class GodotInterface:
    def __init__(self, manager: ConnectionManager):
        self.manager = manager

    async def apply_code(self, project_path: str, file_path: str, code: str) -> str:
        """
        Applies code changes to a specific file in the Godot project.
        It sends a 'write_script' command to the connected Godot Editor instance.
        """
        if file_path.endswith('.gd'):
            try:
                validation_result = await self.validate_script(project_path, code)
                if "valid" not in validation_result.lower():
                    return f"Failed syntax validation: {validation_result}"
            except Exception as e:
                logger.warning(f"Error validating script before apply: {e}")

        payload = {
            "method": "write_script",
            "params": {
                "path": file_path,
                "content": code
            }
        }
        
        try:
            result = await self.manager.send_command(project_path, payload)
            if result.get("success"):
                return result.get("message", f"Successfully sent code update for {file_path}")
            else:
                return f"Failed: {result.get('message', 'Unknown error')}"
        except Exception as e:
            return f"Error apply_code: {str(e)}"

    async def create_scene(self, project_path: str, scene_path: str, root_type: str) -> str:
        """
        Creates a new scene in the Godot project.
        """
        payload = {
            "method": "create_scene",
            "params": {
                "path": scene_path,
                "root_type": root_type
            }
        }

        try:
            result = await self.manager.send_command(project_path, payload)
            if result.get("success"):
                msg = result.get("message", f"Successfully created scene {scene_path}")
                scene_tree = result.get("scene_tree")
                if scene_tree:
                    return (
                        f"{msg}\n\n"
                        f"Scene contents (current state — do NOT recreate these nodes):\n"
                        f"{json.dumps(scene_tree)}"
                    )
                return msg
            else:
                return f"Failed: {result.get('message', 'Unknown error')}"
        except Exception as e:
            return f"Error create_scene: {str(e)}"

    async def delete_node(self, project_path: str, node_path: str) -> str:
        """
        Permanently removes a node and all its children from the currently open scene.
        """
        payload = {
            "method": "delete_node",
            "params": {"node_path": node_path}
        }
        try:
            result = await self.manager.send_command(project_path, payload)
            if result.get("success"):
                return result.get("message", f"Deleted node {node_path}")
            else:
                return f"Failed: {result.get('message', 'Unknown error')}"
        except Exception as e:
            return f"Error delete_node: {str(e)}"

    async def add_node(self, project_path: str, parent_path: str, node_type: str, node_name: str) -> str:
        """
        Adds a new node to the scene.
        """
        payload = {
            "method": "add_node",
            "params": {
                "parent_path": parent_path,
                "node_type": node_type,
                "node_name": node_name
            }
        }
        
        try:
            result = await self.manager.send_command(project_path, payload)
            if result.get("success"):
                return result.get("message", f"Successfully added node {node_name}")
            else:
                return f"Failed: {result.get('message', 'Unknown error')}"
        except Exception as e:
            return f"Error add_node: {str(e)}"

    async def set_property(self, project_path: str, node_path: str, property_name: str, value: Any) -> str:
        """
        Sets a property on a node.
        """
        payload = {
            "method": "set_property",
            "params": {
                "node_path": node_path,
                "property_name": property_name,
                "value": value
            }
        }
        
        try:
            result = await self.manager.send_command(project_path, payload)
            if result.get("success"):
                return result.get("message", f"Successfully set property {property_name}")
            else:
                return f"Failed: {result.get('message', 'Unknown error')}"
        except Exception as e:
            return f"Error set_property: {str(e)}"

    async def attach_script(self, project_path: str, node_path: str, script_path: str) -> str:
        """
        Attaches a script to a node.
        """
        payload = {
            "method": "attach_script",
            "params": {
                "node_path": node_path,
                "script_path": script_path
            }
        }
        
        try:
            result = await self.manager.send_command(project_path, payload)
            if result.get("success"):
                return result.get("message", f"Successfully attached script to {node_path}")
            else:
                return f"Failed: {result.get('message', 'Unknown error')}"
        except Exception as e:
            return f"Error attach_script: {str(e)}"
            
    async def read_scene(self, project_path: str) -> str:
        """
        Reads the currently open scene in the Godot Editor.
        Returns a JSON representation of the scene tree.
        """
        payload = {
            "method": "read_scene",
            "params": {}
        }

        try:
            result = await self.manager.send_command(project_path, payload)
            if result.get("success"):
                scene_tree = result.get("scene_tree", {})
                return json.dumps(scene_tree)
            else:
                return f"Failed: {result.get('message', 'Unknown error')}"
        except Exception as e:
            return f"Error read_scene: {str(e)}"

    async def save_scene(self, project_path: str) -> str:
        """
        Saves the currently open scene in the Godot Editor to disk.
        Must be called after add_node / set_property / attach_script
        so changes persist to the .tscn file.
        """
        payload = {"method": "save_scene", "params": {}}
        try:
            result = await self.manager.send_command(project_path, payload)
            if result.get("success"):
                return result.get("message", "Scene saved successfully")
            else:
                return f"Failed: {result.get('message', 'Unknown error')}"
        except Exception as e:
            return f"Error save_scene: {str(e)}"

    async def open_scene(self, project_path: str, scene_path: str) -> str:
        """
        Opens an existing scene in the Godot Editor so it becomes the
        edited scene for subsequent add_node / set_property commands.
        The response includes the scene tree serialized in the same Godot frame
        as the open call — no timing race, no stale data.
        """
        payload = {"method": "open_scene", "params": {"path": scene_path}}
        try:
            result = await self.manager.send_command(project_path, payload)
            if result.get("success"):
                open_msg = result.get("message", f"Opened scene {scene_path}")
                scene_tree = result.get("scene_tree")
                if scene_tree:
                    return (
                        f"{open_msg}\n\n"
                        f"Scene contents (nodes that ALREADY EXIST — do NOT add these again):\n"
                        f"{json.dumps(scene_tree)}"
                    )
                return open_msg
            else:
                return f"Failed: {result.get('message', 'Unknown error')}"
        except Exception as e:
            return f"Error open_scene: {str(e)}"

    async def instance_scene(self, project_path: str, scene_path: str, parent_path: str, node_name: str = "") -> str:
        """
        Instances a PackedScene (.tscn) as a child of the given parent node
        in the currently open scene. Use this to add sub-scenes like player,
        enemies, or UI into the main scene.
        """
        payload = {
            "method": "instance_scene",
            "params": {
                "scene_path": scene_path,
                "parent_path": parent_path,
                "node_name": node_name,
            }
        }
        try:
            result = await self.manager.send_command(project_path, payload)
            if result.get("success"):
                msg = result.get("message", f"Instanced {scene_path}")
                instance_tree = result.get("instance_tree")
                if instance_tree:
                    return (
                        f"{msg}\n\n"
                        f"Nodes inside this instance (from its source scene — do NOT add these to the current scene):\n"
                        f"{json.dumps(instance_tree)}"
                    )
                return msg
            else:
                return f"Failed: {result.get('message', 'Unknown error')}"
        except Exception as e:
            return f"Error instance_scene: {str(e)}"

    async def set_main_scene(self, project_path: str, scene_path: str) -> str:
        """
        Sets the main scene in Godot's project settings so the game
        runs this scene when pressing Play (F5).
        """
        payload = {"method": "set_main_scene", "params": {"path": scene_path}}
        try:
            result = await self.manager.send_command(project_path, payload)
            if result.get("success"):
                return result.get("message", f"Main scene set to {scene_path}")
            else:
                return f"Failed: {result.get('message', 'Unknown error')}"
        except Exception as e:
            return f"Error set_main_scene: {str(e)}"

    async def scan_filesystem(self, project_path: str) -> str:
        """
        Triggers a Godot Editor filesystem scan so newly written assets
        are indexed and available for load(). Call this after writing
        asset files before referencing them with set_property.
        """
        payload = {"method": "scan_filesystem", "params": {}}
        try:
            result = await self.manager.send_command(project_path, payload)
            if result.get("success"):
                return "Filesystem scan completed"
            else:
                return f"Failed: {result.get('message', 'Unknown error')}"
        except Exception as e:
            return f"Error scan_filesystem: {str(e)}"

    async def reimport_files(self, project_path: str, paths: str) -> str:
        """
        Forces Godot to reimport specific files by their res:// paths.
        More targeted than scan_filesystem. Use this immediately after
        asset files are written and before referencing them in set_property.
        paths: comma-separated res:// paths, e.g. 'res://assets/sprites/player.png'
        """
        path_list = [p.strip() for p in paths.split(",") if p.strip()]
        payload = {"method": "scan_filesystem", "params": {"paths": path_list}}
        try:
            result = await self.manager.send_command(project_path, payload)
            if result.get("success"):
                return f"Reimport triggered for: {', '.join(path_list)}"
            else:
                return f"Failed: {result.get('message', 'Unknown error')}"
        except Exception as e:
            return f"Error reimport_files: {str(e)}"

    async def node_exists(self, project_path: str, node_path: str) -> str:
        """
        Check whether a node at the given path already exists in the currently open scene.
        Returns JSON with 'exists' (bool) and if true, 'node' with its name/type/script/child_count.
        Use this before add_node to avoid creating duplicate nodes.
        node_path: '.' for root, or relative path like 'Player' or 'UI/HUD'.
        """
        payload = {"method": "node_exists", "params": {"node_path": node_path}}
        try:
            result = await self.manager.send_command(project_path, payload)
            return json.dumps(result)
        except Exception as e:
            return f"Error node_exists: {str(e)}"

    async def validate_script(self, project_path: str, code: str) -> str:
        """
        Validates GDScript code for syntax errors without writing it to disk.
        Returns 'Script is valid' or an error message with the error code.
        Use this before apply_godot_code to catch syntax errors early.
        """
        payload = {"method": "validate_script", "params": {"code": code}}
        try:
            result = await self.manager.send_command(project_path, payload)
            return result.get("message", "Unknown validation result")
        except Exception as e:
            return f"Error validate_script: {str(e)}"

    async def get_project_files(self, project_path: str, extensions: str = "gd,tscn,tres") -> str:
        """
        Returns a list of all project files matching the given extensions.
        extensions: comma-separated list (default: 'gd,tscn,tres').
        Use this to check which scenes and scripts already exist before creating new ones.
        """
        ext_list = [e.strip() for e in extensions.split(",") if e.strip()]
        payload = {"method": "get_project_files", "params": {"extensions": ext_list}}
        try:
            result = await self.manager.send_command(project_path, payload)
            if result.get("success"):
                files = result.get("files", [])
                return json.dumps(files)
            else:
                return f"Failed: {result.get('message', 'Unknown error')}"
        except Exception as e:
            return f"Error get_project_files: {str(e)}"

    async def get_input_map(self, project_path: str) -> str:
        """
        Returns the project's InputMap as JSON: action names → list of event descriptions.
        Use this to check which input actions are already defined before writing player movement code.
        """
        payload = {"method": "get_input_map", "params": {}}
        try:
            result = await self.manager.send_command(project_path, payload)
            if result.get("success"):
                return json.dumps(result.get("input_map", {}))
            else:
                return f"Failed: {result.get('message', 'Unknown error')}"
        except Exception as e:
            return f"Error get_input_map: {str(e)}"

    async def execute_godot_script(self, project_path: str, code: str) -> str:
        """
        Executes arbitrary GDScript code in the Godot Editor context.
        The code is wrapped in a function that has access to 'editor' (EditorInterface)
        and 'bridge' (the bridge client node).
        Use this for complex editor operations not covered by other tools.
        """
        payload = {
            "method": "execute_script",
            "params": {
                "code": code
            }
        }
        try:
            result = await self.manager.send_command(project_path, payload)
            if result.get("success"):
                return f"Script executed successfully. Result: {result.get('result', 'OK')}"
            else:
                return f"Failed: {result.get('message', 'Unknown error')}"
        except Exception as e:
            return f"Error execute_godot_script: {str(e)}"

    async def test_game(self, project_path: str, scene_path: str) -> str:
        """
        Runs the specified scene in the Godot Editor, waits briefly, takes a screenshot,
        and returns the Base64 PNG data of the screenshot.
        """
        payload = {
            "method": "test_game",
            "params": {
                "scene_path": scene_path
            }
        }
        try:
            result = await self.manager.send_command(project_path, payload)
            if result.get("success"):
                # Result contains 'image_data' which is base64 PNG
                return json.dumps({
                    "success": True, 
                    "message": "Screenshot captured successfully",
                    "image_data": result.get("image_data", "")
                })
            else:
                return f"Failed: {result.get('message', 'Unknown error')}"
        except Exception as e:
            return f"Error test_game: {str(e)}"

    async def test_scene(self, project_path: str, scene_path: str, duration: float = 3.0) -> str:
        """
        Runs the specified scene in HEADLESS mode for `duration` seconds to check for runtime errors/crashes.
        Returns SUCCESS if scene runs without crashing, or CRASH/ERROR log if it fails.
        Use this regularly to catch 'null instance' or 'node not found' errors.
        """
        # Convert res:// path to absolute path just to check existence
        abs_scene_path = scene_path.replace("res://", "")
        # Remove leading slash if present to join correctly
        if abs_scene_path.startswith("/"):
             abs_scene_path = abs_scene_path[1:]
             
        full_scene_path = Path(project_path) / abs_scene_path
        
        if not full_scene_path.exists():
             return f"Error: Scene file not found at {full_scene_path}"

        cmd = [
            "godot",
            "--headless",
            "--path", project_path,
            scene_path
        ]
        
        logger.info(f"Running test_scene: {' '.join(cmd)}")
        
        try:
            # multiple async calls to create_subprocess_exec might be fine
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                # Wait for the process to finish OR confirm it's still running after duration
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=duration)
            except asyncio.TimeoutError:
                # If we timed out, it means the scene ran for duration seconds! Success.
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait() # reap process
                return f"SUCCESS: Scene ran for {duration} seconds without crashing."
            
            # If we are here, process exited early!
            stderr_str = stderr.decode() if stderr else ""
            stdout_str = stdout.decode() if stdout else ""
            
            if process.returncode != 0:
                # Crash!
                # Extract relevant error part (usually last few lines of stderr)
                errors = "\n".join([line for line in stderr_str.splitlines() if "ERROR" in line or "SCRIPT ERROR" in line])
                if not errors:
                    errors = stderr_str[-500:] # fallback to last 500 chars if no explicit ERROR tag found
                    
                return f"CRASH: Process exited early with code {process.returncode}.\nErrors found:\n{errors}\nFull Output:\n{stdout_str}"
            
            # Exited early but cleanly (returncode 0). Did script call get_tree().quit()?
            return f"WARNING: Scene closed early (0 exit code). Check logic.\nOutput: {stdout_str}"
            
        except Exception as e:
            return f"System Error running test_scene: {e}"

# ---------------------------------------------------------------------------
# Asset Acquisition Interface
# ---------------------------------------------------------------------------

class AssetInterface:
    """
    Wraps the AssetService for use as LangChain tools in the Studio Agent.
    
    Each method corresponds to a tool the Coder node can call to acquire
    game assets (sprites, tilesets, audio) during task execution.
    """

    def __init__(self, manager):
        self.manager = manager
        self._services = {}  # Cache per-project AssetService instances

    def _get_service(self, project_path: str):
        """Get or create an AssetService for a project."""
        if project_path not in self._services:
            def log_callback(msg: str):
                payload = {"method": "log", "params": {"message": f"[Asset Pipeline] {msg}"}}
                # Fire and forget with exception bubbling safety
                task = asyncio.create_task(self.manager.send_command(project_path, payload))
                task.add_done_callback(lambda t: t.exception())
                
            self._services[project_path] = AssetService(project_path, log_callback=log_callback)
        return self._services[project_path]

    async def get_sprite(
        self,
        project_path: str,
        name: str,
        description: str,
        style: str = "pixel_art",
        width: int = 32,
        height: int = 32,
        tags: str = "",
    ) -> str:
        """
        Get a single-frame sprite for the game project.
        Searches online first, then generates via AI as fallback.
        
        Args:
            project_path: Path to the Godot project
            name: Asset identifier (e.g., 'player', 'coin', 'enemy_bat')
            description: Visual description (e.g., 'a small blue slime monster with big eyes')
            style: Art style — one of: pixel_art, flat, cartoon, hand_drawn
            width: Width in pixels (default 32)
            height: Height in pixels (default 32)
            tags: Comma-separated search tags (e.g., 'platformer,fantasy,character')
            
        Returns:
            JSON string with the result including the Godot res:// path
        """
        from models.asset_request import SpriteRequest, SpriteStyle
        try:
            style_enum = SpriteStyle(style)
        except ValueError:
            style_enum = SpriteStyle.PIXEL_ART

        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        request = SpriteRequest(
            name=name,
            description=description,
            style=style_enum,
            width=width,
            height=height,
            poses=["idle"],
            tags=tag_list,
        )
        service = self._get_service(project_path)
        result = await service.get_sprite(request)
        return result.model_dump_json()

    async def get_sprite_options(
        self,
        project_path: str,
        name: str,
        description: str,
        style: str = "pixel_art",
        width: int = 32,
        height: int = 32,
        tags: str = "",
        max_options: int = 3,
    ) -> list:
        """Collect up to max_options candidate sprites. Returns a list of AssetResult."""
        from models.asset_request import SpriteRequest, SpriteStyle
        try:
            style_enum = SpriteStyle(style)
        except ValueError:
            style_enum = SpriteStyle.PIXEL_ART

        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        request = SpriteRequest(
            name=name,
            description=description,
            style=style_enum,
            width=width,
            height=height,
            poses=["idle"],
            tags=tag_list,
        )
        service = self._get_service(project_path)
        return await service.get_sprite_options(request, max_options=max_options)

    async def get_spritesheet_options(
        self,
        project_path: str,
        name: str,
        description: str,
        poses: str = "idle",
        style: str = "pixel_art",
        frame_width: int = 32,
        frame_height: int = 32,
        tags: str = "",
        max_options: int = 3,
    ) -> list:
        """Collect up to max_options candidate spritesheets. Returns a list of AssetResult."""
        from models.asset_request import SpriteRequest, SpriteStyle
        try:
            style_enum = SpriteStyle(style)
        except ValueError:
            style_enum = SpriteStyle.PIXEL_ART

        pose_list = [p.strip() for p in poses.split(",") if p.strip()]
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        request = SpriteRequest(
            name=name,
            description=description,
            style=style_enum,
            width=frame_width,
            height=frame_height,
            poses=pose_list,
            tags=tag_list,
        )
        service = self._get_service(project_path)
        return await service.get_sprite_options(request, max_options=max_options)

    async def get_spritesheet(
        self,
        project_path: str,
        name: str,
        description: str,
        poses: str = "idle",
        style: str = "pixel_art",
        frame_width: int = 32,
        frame_height: int = 32,
        tags: str = "",
    ) -> str:
        """
        Get a multi-frame sprite sheet (animation frames) for the game project.
        Searches online first, then generates via AI as fallback.
        
        Args:
            project_path: Path to the Godot project
            name: Asset identifier (e.g., 'player_walk', 'enemy_attack')
            description: Visual description of the character/object
            poses: Comma-separated list of poses/frames (e.g., 'idle,walk_1,walk_2,jump')
            style: Art style — one of: pixel_art, flat, cartoon, hand_drawn
            frame_width: Width of each frame in pixels (default 32)
            frame_height: Height of each frame in pixels (default 32)
            tags: Comma-separated search tags
            
        Returns:
            JSON string with the result including the Godot res:// path and frame metadata
        """
        from models.asset_request import SpriteRequest, SpriteStyle
        try:
            style_enum = SpriteStyle(style)
        except ValueError:
            style_enum = SpriteStyle.PIXEL_ART

        pose_list = [p.strip() for p in poses.split(",") if p.strip()]
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        request = SpriteRequest(
            name=name,
            description=description,
            style=style_enum,
            width=frame_width,
            height=frame_height,
            poses=pose_list,
            tags=tag_list,
        )
        service = self._get_service(project_path)
        result = await service.get_sprite(request)
        return result.model_dump_json()

    async def get_tileset(
        self,
        project_path: str,
        name: str,
        description: str,
        style: str = "pixel_art",
        tile_size: int = 16,
        columns: int = 4,
        rows: int = 4,
        tile_types: str = "ground",
        tags: str = "",
    ) -> str:
        """
        Get a tileset image for use in Godot TileMaps.
        Searches online first, then generates as fallback.
        
        Args:
            project_path: Path to the Godot project
            name: Asset identifier (e.g., 'grass_tileset', 'dungeon_walls')
            description: Visual description of the tileset
            style: Art style — one of: pixel_art, flat, cartoon, hand_drawn
            tile_size: Size of each tile in pixels, square (default 16)
            columns: Number of tile columns in the sheet (default 4)
            rows: Number of tile rows in the sheet (default 4)
            tile_types: Comma-separated tile types (e.g., 'ground,wall_top,wall_side,corner')
            tags: Comma-separated search tags
            
        Returns:
            JSON string with the result including the Godot res:// path
        """
        from models.asset_request import TilesetRequest, SpriteStyle
        try:
            style_enum = SpriteStyle(style)
        except ValueError:
            style_enum = SpriteStyle.PIXEL_ART

        type_list = [t.strip() for t in tile_types.split(",") if t.strip()]
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        request = TilesetRequest(
            name=name,
            description=description,
            style=style_enum,
            tile_size=tile_size,
            columns=columns,
            rows=rows,
            tile_types=type_list,
            tags=tag_list,
        )
        service = self._get_service(project_path)
        result = await service.get_tileset(request)
        return result.model_dump_json()

    async def get_background(
        self,
        project_path: str,
        name: str,
        description: str,
        style: str = "pixel_art",
        width: int = 1280,
        height: int = 720,
        tags: str = "",
    ) -> str:
        """
        Get a 2D background image for the game project.
        Searches online first, then generates via AI as fallback.
        
        Args:
            project_path: Path to the Godot project
            name: Asset identifier (e.g., 'forest_bg', 'space_bg')
            description: Visual description (e.g., 'a dark creepy forest')
            style: Art style — one of: pixel_art, flat, cartoon, hand_drawn
            width: Width in pixels (default 1280)
            height: Height in pixels (default 720)
            tags: Comma-separated search tags (e.g., 'background,forest')
            
        Returns:
            JSON string with the result including the Godot res:// path
        """
        from models.asset_request import BackgroundRequest, SpriteStyle
        try:
            style_enum = SpriteStyle(style)
        except ValueError:
            style_enum = SpriteStyle.PIXEL_ART

        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        request = BackgroundRequest(
            name=name,
            description=description,
            style=style_enum,
            width=width,
            height=height,
            tags=tag_list,
        )
        service = self._get_service(project_path)
        result = await service.get_background(request)
        return result.model_dump_json()

    async def get_audio(
        self,
        project_path: str,
        name: str,
        description: str,
        audio_type: str = "sfx",
        duration_seconds: float = 0.5,
        tags: str = "",
    ) -> str:
        """
        Get an audio asset (sound effect or music) for the game project.
        Searches online first, then synthesizes as fallback (SFX only).
        
        Args:
            project_path: Path to the Godot project
            name: Asset identifier (e.g., 'jump_sfx', 'coin_pickup', 'bg_music')
            description: Description of the sound (e.g., 'short 8-bit jump sound effect')
            audio_type: Either 'sfx' or 'music' (default 'sfx')
            duration_seconds: Target duration in seconds (default 0.5, for SFX)
            tags: Comma-separated search tags
            
        Returns:
            JSON string with the result including the Godot res:// path
        """
        from models.asset_request import AudioRequest

        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        request = AudioRequest(
            name=name,
            description=description,
            audio_type=audio_type,
            duration_seconds=duration_seconds,
            tags=tag_list,
        )
        service = self._get_service(project_path)
        result = await service.get_audio(request)
        return result.model_dump_json()


def _sync_placeholder(*args, **kwargs):
    raise NotImplementedError("This tool is async only")


def get_godot_tools(interface: GodotInterface) -> List[StructuredTool]:
    """Wraps GodotInterface methods as LangChain tools."""
    return [
        StructuredTool.from_function(
            func=_sync_placeholder,
            coroutine=interface.apply_code,
            name="apply_godot_code",
            description="Write code to a script file in the Godot project. Requires project_path, file_path, and code."
        ),
        StructuredTool.from_function(
            func=_sync_placeholder,
            coroutine=interface.create_scene,
            name="create_godot_scene",
        ),
        StructuredTool.from_function(
            func=_sync_placeholder,
            coroutine=interface.add_node,
            name="godot_add_node",
            description="Add a node to the current scene. Requires project_path, parent_path (use '.' for root or absolute path), node_type, and node_name."
        ),
        StructuredTool.from_function(
            func=_sync_placeholder,
            coroutine=interface.set_property,
            name="godot_set_property",
            description="Set a property of a node. Requires project_path, node_path, property_name, and value."
        ),
        StructuredTool.from_function(
            func=_sync_placeholder,
            coroutine=interface.attach_script,
            name="godot_attach_script",
            description="Attach a script to a node. Requires project_path, node_path, and script_path."
        ),
        StructuredTool.from_function(
            func=_sync_placeholder,
            coroutine=interface.read_scene,
            name="godot_read_scene",
            description="Reads the current scene layout open in the editor. Requires project_path. Returns the scene tree as a JSON string."
        ),
        StructuredTool.from_function(
            func=_sync_placeholder,
            coroutine=interface.save_scene,
            name="godot_save_scene",
            description="Save the currently open scene to disk. MUST be called after add_node/set_property/attach_script to persist changes to the .tscn file. Requires project_path."
        ),
        StructuredTool.from_function(
            func=_sync_placeholder,
            coroutine=interface.open_scene,
            name="godot_open_scene",
            description="Open an existing scene in the editor for modification. Requires project_path and scene_path (res:// path)."
        ),
        StructuredTool.from_function(
            func=_sync_placeholder,
            coroutine=interface.instance_scene,
            name="godot_instance_scene",
            description="Instance a .tscn sub-scene as a child of a node in the current scene. Use this to add player/enemy/UI sub-scenes into the main scene. Requires project_path, scene_path, parent_path. Optional: node_name."
        ),
        StructuredTool.from_function(
            func=_sync_placeholder,
            coroutine=interface.set_main_scene,
            name="godot_set_main_scene",
            description="Set the main scene in Godot project settings so it runs on Play (F5). Requires project_path and scene_path."
        ),
        StructuredTool.from_function(
            func=_sync_placeholder,
            coroutine=interface.scan_filesystem,
            name="godot_scan_filesystem",
            description="Trigger a Godot filesystem scan so newly written files are indexed and loadable. Call after writing assets and before referencing them. Requires project_path."
        ),
        StructuredTool.from_function(
            func=_sync_placeholder,
            coroutine=interface.reimport_files,
            name="godot_reimport_files",
            description="Force Godot to reimport specific files by res:// path. More reliable than scan_filesystem for targeting newly written asset files. Requires project_path and paths (comma-separated res:// paths)."
        ),
        StructuredTool.from_function(
            func=_sync_placeholder,
            coroutine=interface.execute_godot_script,
            name="execute_godot_script",
            description="Execute arbitrary GDScript code in the Godot Editor. Use this for complex operations like 'editor.get_selection().clear()' or custom automation. The code should NOT include the 'func' or 'extends' lines; it will be wrapped in a function with 'editor' (EditorInterface) and 'bridge' (Node) arguments. Requires project_path and code."
        ),
        StructuredTool.from_function(
            func=_sync_placeholder,
            coroutine=interface.node_exists,
            name="godot_node_exists",
            description="Check if a node already exists in the currently open scene. Returns JSON with 'exists' bool and node details (type, script, child_count). Call this before add_node to avoid duplicates. Requires project_path and node_path ('.' for root, or 'Player', 'UI/HUD', etc)."
        ),
        StructuredTool.from_function(
            func=_sync_placeholder,
            coroutine=interface.validate_script,
            name="godot_validate_script",
            description="Validate GDScript code for syntax errors WITHOUT writing it to disk. Returns 'Script is valid' or an error message. Call this before apply_godot_code to catch errors early. Requires project_path and code."
        ),
        StructuredTool.from_function(
            func=_sync_placeholder,
            coroutine=interface.get_project_files,
            name="godot_get_project_files",
            description="List all files in the Godot project matching given extensions. Returns a JSON array of res:// paths. Use this to check which scenes and scripts already exist. Requires project_path. Optional: extensions (comma-separated, default 'gd,tscn,tres')."
        ),
        StructuredTool.from_function(
            func=_sync_placeholder,
            coroutine=interface.get_input_map,
            name="godot_get_input_map",
            description="Read the project's InputMap as JSON (action names → event descriptions). Use this before writing player input code to see what actions are already defined (e.g. ui_left, ui_right, ui_accept). Requires project_path."
        ),
        StructuredTool.from_function(
            func=_sync_placeholder,
            coroutine=interface.test_game,
            name="godot_test_game",
            description="Runs the specified scene in the Godot Editor, waits briefly, takes a screenshot, and returns the screenshot data as a Base64 string. Use this to visually verify the game layout. Requires project_path and scene_path (res:// path)."
        ),
        StructuredTool.from_function(
            func=_sync_placeholder,
            coroutine=interface.test_scene,
            name="godot_test_scene",
            description="Runs the specified scene in HEADLESS mode for `duration` seconds to check for runtime errors/crashes. Returns SUCCESS if scene runs without crashing, or CRASH/ERROR log if it fails. Use this regularly to catch 'null instance' or 'node not found' errors. Requires project_path and scene_path."
        ),
    ]

def get_asset_tools(asset_interface: AssetInterface) -> List[StructuredTool]:
    """Wraps AssetInterface methods as LangChain tools for asset acquisition."""
    return [
        StructuredTool.from_function(
            func=_sync_placeholder,
            coroutine=asset_interface.get_sprite,
            name="get_sprite",
            description=(
                "Get a single-frame 2D sprite for the game. Searches free online databases first, "
                "then generates via AI as fallback. Returns a JSON result with the Godot res:// path. "
                "Requires: project_path, name, description. Optional: style (pixel_art|flat|cartoon|hand_drawn), "
                "width, height, tags (comma-separated)."
            ),
        ),
        StructuredTool.from_function(
            func=_sync_placeholder,
            coroutine=asset_interface.get_spritesheet,
            name="get_spritesheet",
            description=(
                "Get a multi-frame sprite sheet (for animations) for the game. "
                "Generates or downloads a horizontal strip of animation frames. "
                "Returns JSON with the Godot res:// path and frame metadata. "
                "Requires: project_path, name, description, poses (comma-separated like 'idle,walk_1,walk_2,jump'). "
                "Optional: style, frame_width, frame_height, tags."
            ),
        ),
        StructuredTool.from_function(
            func=_sync_placeholder,
            coroutine=asset_interface.get_tileset,
            name="get_tileset",
            description=(
                "Get a tileset image for use in Godot TileMaps. "
                "Returns a grid of tiles suitable for TileSet resources. "
                "Requires: project_path, name, description. "
                "Optional: style, tile_size, columns, rows, tile_types (comma-separated), tags."
            ),
        ),
        StructuredTool.from_function(
            func=_sync_placeholder,
            coroutine=asset_interface.get_background,
            name="get_background",
            description=(
                "Get a 2D background image for the game. Searches free online databases first, "
                "then generates via AI as fallback. Returns a JSON result with the Godot res:// path. "
                "Requires: project_path, name, description. Optional: style, width, height, tags."
            ),
        ),
        StructuredTool.from_function(
            func=_sync_placeholder,
            coroutine=asset_interface.get_audio,
            name="get_audio",
            description=(
                "Get an audio asset (sound effect or music). Searches online first, "
                "then synthesizes SFX programmatically as fallback. "
                "Requires: project_path, name, description. "
                "Optional: audio_type ('sfx'|'music'), duration_seconds, tags."
            ),
        ),
    ]
