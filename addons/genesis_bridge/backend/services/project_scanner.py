import logging
import re
from pathlib import Path
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class ProjectScanner:
    """
    Scans a Godot project directory to build context for the AI agents.
    Provides file trees and parses project.godot for ground-truth settings
    like InputMap actions, AutoLoads, and Collision Layers.
    """

    @staticmethod
    def scan_directory(project_path: str) -> Dict[str, Any]:
        """Scans directory and returns a JSON-serializable tree of relevant files."""
        root_path = Path(project_path)
        if not root_path.exists():
            return {"error": "Project path does not exist"}

        ignored_dirs = {'.git', '.godot', 'venv', 'node_modules', 'backend', '.claude'}
        tree = {}

        def _scan(current_path: Path, current_dict: dict):
            try:
                for item in sorted(current_path.iterdir()):
                    if item.is_dir():
                        if item.name not in ignored_dirs and not item.name.startswith('.'):
                            current_dict[item.name] = {}
                            _scan(item, current_dict[item.name])
                    elif item.suffix in {'.gd', '.tscn', '.tres', '.png', '.jpg', '.ogg', '.wav'}:
                        current_dict[item.name] = "file"
            except PermissionError:
                pass

        _scan(root_path, tree)
        return tree

    @staticmethod
    def get_project_context(project_path: str) -> str:
        """
        Parses project.godot directly to extract ground-truth context
        for prompt injection, preventing LLM hallucinations.
        Extracts:
        1. [input] actions
        2. [autoload] singletons
        3. [layer_names] (physics layers)
        """
        godot_file = Path(project_path) / "project.godot"
        if not godot_file.exists():
            return "No project.godot found."

        try:
            content = godot_file.read_text(encoding="utf-8")
            
            inputs = []
            autoloads = []
            layers = []
            
            current_section = None
            
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith(";"):
                    continue
                    
                # Match section headers like [input] or [autoload]
                section_match = re.match(r'^\[(.*?)\]$', line)
                if section_match:
                    # e.g., "input" from "[input]" or "layer_names" from "[layer_names]"
                    current_section = section_match.group(1).split(".")[0]
                    continue
                    
                # Parse based on current section
                if current_section == "input":
                    # Input map entries look like: ui_accept={...}
                    key_match = re.match(r'^([A-Za-z0-9_]+)=', line)
                    if key_match:
                        inputs.append(key_match.group(1))
                        
                elif current_section == "autoload":
                    # Autoload entries look like: GameManager="*res://scripts/game_manager.gd"
                    key_match = re.match(r'^([A-Za-z0-9_]+)="?\*?(.*?)"?$', line)
                    if key_match:
                        name, path = key_match.groups()
                        autoloads.append(f"{name} ({path})")
                        
                elif current_section == "layer_names":
                    # Layers look like: 2d_physics/layer_1="Player"
                    key_match = re.match(r'^([A-Za-z0-9_]+)/layer_(\d+)="(.*?)"$', line)
                    if key_match:
                        type_name, layer_num, name = key_match.groups()
                        layers.append(f"Layer {layer_num}: '{name}' ({type_name})")

            # Format the output context
            context_blocks = ["=== PROJECT GROUND TRUTH CONTEXT ==="]
            
            if inputs:
                context_blocks.append("REGISTERED INPUT ACTIONS (Do NOT invent others):")
                context_blocks.append(", ".join(set(inputs)))
            else:
                context_blocks.append("REGISTERED INPUT ACTIONS: Only default Godot UI actions exist (ui_accept, ui_cancel, ui_left, ui_right, ui_up, ui_down).")
                
            if autoloads:
                context_blocks.append("\nREGISTERED AUTOLOADS (Globally accessible Singletons):")
                context_blocks.extend([f"- {a}" for a in autoloads])
                
            if layers:
                context_blocks.append("\nDEFINED COLLISION LAYERS:")
                context_blocks.extend([f"- {l}" for l in layers])
                
            return "\n".join(context_blocks)
            
        except Exception as e:
            logger.error(f"Failed to parse project.godot context: {e}")
            return f"Failed to read project context: {e}"
