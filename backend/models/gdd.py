from typing import List, Optional
from pydantic import BaseModel, Field

class GameMechanic(BaseModel):
    """Represents a specific game mechanic."""
    name: str = Field(description="Name of the mechanic")
    description: str = Field(description="Detailed description of how the mechanic works")
    complexity_score: int = Field(description="Complexity score from 1 to 10")

class ArtStyle(BaseModel):
    """Represents the visual and artistic style of the game."""
    visual_style: str = Field(default="", description="Describe the visual style of the game (e.g., Pixel Art, Low Poly, Realistic)")
    color_palette: List[str] = Field(default_factory=list, description="List of primary and secondary colors in hex format")
    perspective: str = Field(default="", description="Camera perspective (e.g., Top-down, First Person, Isometric)")

class SystemDetail(BaseModel):
    """Represents a detailed explanation and guide for a specific aspect of the game."""
    name: str = Field(description="Name of the system or aspect (e.g., 'Player Movement', 'Inventory System')")
    description: str = Field(description="High-level description of the system")
    components: List[str] = Field(default_factory=list, description="List of core components needed (e.g., specific scripts, nodes, scenes)")
    implementation_guide: str = Field(description="Step-by-step or detailed guide on how to implement this system in Godot")

class GameDesignDocument(BaseModel):
    """The main Game Design Document (GDD) model.
    
    All fields are Optional so the GDD can be incrementally populated
    through conversation, rather than requiring everything upfront.
    """
    title: Optional[str] = Field(default=None, description="Title of the game")
    genre: Optional[str] = Field(default=None, description="Primary genre of the game")
    target_audience: Optional[str] = Field(default=None, description="Target audience demographic")
    core_loop: Optional[str] = Field(default=None, description="Description of the core gameplay loop")
    
    # Story and Theme
    story: Optional[str] = Field(default=None, description="Game story or narrative premise")
    theme: Optional[str] = Field(default=None, description="Overall theme or mood")
    
    # Gameplay
    mechanics: List[GameMechanic] = Field(default_factory=list, description="List of key game mechanics")
    controls: Optional[str] = Field(default=None, description="Control scheme description")
    progression: Optional[str] = Field(default=None, description="How the player progresses through the game")
    
    # Visuals and Audio
    art_style: Optional[ArtStyle] = Field(default=None, description="Visual style configuration")
    audio_style: Optional[str] = Field(default=None, description="Music and sound design direction")
    
    # Content
    levels: List[str] = Field(default_factory=list, description="List of level/area descriptions")
    enemies: List[str] = Field(default_factory=list, description="Enemy types")
    items: List[str] = Field(default_factory=list, description="Collectibles and items")
    
    # Technical
    folder_structure: List[str] = Field(
        default_factory=lambda: [
            "scenes/", "scripts/", "assets/sprites/", "assets/audio/", "assets/fonts/"
        ],
        description="Suggested project folder structure"
    )
    world_constants: Optional[str] = Field(default=None, description="Important world rules and constants (e.g., '1 unit = 1 pixel', 'Gravity = 980'). This contextualizes scale for the AI.")

    # Detailed Implementation Guide
    detailed_systems: List[SystemDetail] = Field(default_factory=list, description="Detailed explanation and implementation guide on every single aspect of the game")

    # --- Introspection Helpers ---

    # Fields that use list defaults and shouldn't count as "empty" just 
    # because they're an empty list — only string/object fields matter.
    _STRING_FIELDS = [
        "title", "genre", "target_audience", "core_loop",
        "story", "theme", "controls", "progression", "audio_style",
    ]
    _OBJECT_FIELDS = ["art_style"]
    _LIST_FIELDS = ["mechanics", "levels", "enemies", "items", "detailed_systems"]

    def filled_sections(self) -> List[str]:
        """Return names of sections that have been populated."""
        filled = []
        for f in self._STRING_FIELDS:
            if getattr(self, f, None):
                filled.append(f)
        for f in self._OBJECT_FIELDS:
            val = getattr(self, f, None)
            if val is not None:
                filled.append(f)
        for f in self._LIST_FIELDS:
            val = getattr(self, f, None)
            if val:  # non-empty list
                filled.append(f)
        return filled

    def empty_sections(self) -> List[str]:
        """Return names of sections that are still empty/None."""
        filled = set(self.filled_sections())
        all_sections = self._STRING_FIELDS + self._OBJECT_FIELDS + self._LIST_FIELDS
        return [s for s in all_sections if s not in filled]

    def completion_summary(self) -> str:
        """Human-readable summary of GDD completion status."""
        filled = self.filled_sections()
        empty = self.empty_sections()
        total = len(filled) + len(empty)
        lines = [f"GDD Progress: {len(filled)}/{total} sections filled."]
        if filled:
            lines.append(f"  ✅ Filled: {', '.join(filled)}")
        if empty:
            lines.append(f"  ⬜ Empty: {', '.join(empty)}")
        return "\n".join(lines)

    def to_json(self) -> str:
        """Serializes the GDD to a JSON string, excluding None fields."""
        return self.model_dump_json(indent=4, exclude_none=True)
    
    def to_dict(self) -> dict:
        """Serializes the GDD to a dict, excluding None fields."""
        return self.model_dump(exclude_none=True)
        
    @classmethod
    def from_json(cls, json_str: str) -> 'GameDesignDocument':
        """Deserializes a JSON string to a GDD object."""
        return cls.model_validate_json(json_str)

    def save_to_file(self, filepath: str):
        """Saves the GDD to a JSON file."""
        with open(filepath, 'w') as f:
            f.write(self.to_json())

    @classmethod
    def load_from_file(cls, filepath: str) -> 'GameDesignDocument':
        """Loads a GDD from a JSON file."""
        with open(filepath, 'r') as f:
            content = f.read()
        return cls.from_json(content)
    
    def update_from_partial(self, partial_data: dict) -> None:
        """Update GDD fields from partial dictionary data."""
        for key, value in partial_data.items():
            if hasattr(self, key) and value is not None:
                setattr(self, key, value)
