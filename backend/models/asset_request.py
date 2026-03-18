"""
Pydantic models for asset requests and responses.

These models define the specification format that agents use to request
sprites, sprite sheets, and audio assets from the AssetService.
"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from enum import Enum


class AssetType(str, Enum):
    """Types of assets that can be requested."""
    SPRITE = "sprite"
    SPRITESHEET = "spritesheet"
    TILESET = "tileset"
    BACKGROUND = "background"
    AUDIO_SFX = "audio_sfx"
    AUDIO_MUSIC = "audio_music"


class SpriteStyle(str, Enum):
    """Visual style for sprite generation."""
    PIXEL_ART = "pixel_art"
    FLAT = "flat"
    CARTOON = "cartoon"
    HAND_DRAWN = "hand_drawn"


class SpriteRequest(BaseModel):
    """Specification for requesting a single sprite or sprite sheet."""
    name: str = Field(description="Identifier for this asset (e.g., 'player', 'coin', 'enemy_slime')")
    description: str = Field(description="Visual description of the sprite (e.g., 'a small blue slime monster')")
    style: SpriteStyle = Field(default=SpriteStyle.PIXEL_ART, description="Visual style for the sprite")
    width: int = Field(default=512, description="Width of a single frame in pixels")
    height: int = Field(default=512, description="Height of a single frame in pixels")
    poses: List[str] = Field(
        default_factory=lambda: ["idle"],
        description="List of poses/frames to generate (e.g., ['idle', 'walk_1', 'walk_2', 'jump', 'attack'])"
    )
    transparent_background: bool = Field(default=True, description="Whether the background should be transparent")
    color_palette: Optional[List[str]] = Field(
        default=None,
        description="Optional list of hex colors to constrain the palette (e.g., ['#3a3a6e', '#6b8cff'])"
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Search tags for online lookup (e.g., ['character', 'platformer', 'fantasy'])"
    )


class TilesetRequest(BaseModel):
    """Specification for requesting a tileset (ground, walls, etc.)."""
    name: str = Field(description="Identifier for this tileset (e.g., 'grass_tileset', 'dungeon_walls')")
    description: str = Field(description="Visual description of the tileset")
    style: SpriteStyle = Field(default=SpriteStyle.PIXEL_ART)
    tile_size: int = Field(default=128, description="Size of each tile in pixels (square)")
    columns: int = Field(default=4, description="Number of tile columns in the sheet")
    rows: int = Field(default=4, description="Number of tile rows in the sheet")
    tile_types: List[str] = Field(
        default_factory=lambda: ["ground"],
        description="Types of tiles to include (e.g., ['ground', 'wall_top', 'wall_side', 'corner'])"
    )
    tags: List[str] = Field(default_factory=list)


class BackgroundRequest(BaseModel):
    """Specification for requesting a background image."""
    name: str = Field(description="Identifier for this background (e.g., 'forest_bg')")
    description: str = Field(description="Visual description of the background")
    style: SpriteStyle = Field(default=SpriteStyle.PIXEL_ART)
    width: int = Field(default=1920, description="Width of the background in pixels")
    height: int = Field(default=1080, description="Height of the background in pixels")
    tags: List[str] = Field(default_factory=list)


class AudioRequest(BaseModel):
    """Specification for requesting audio (SFX or music)."""
    name: str = Field(description="Identifier for this audio (e.g., 'jump_sfx', 'bg_music')")
    description: str = Field(description="Description of the sound (e.g., 'short 8-bit jump sound effect')")
    audio_type: Literal["sfx", "music"] = Field(default="sfx")
    duration_seconds: Optional[float] = Field(default=None, description="Target duration in seconds")
    tags: List[str] = Field(default_factory=list, description="Search tags for online lookup")


class AssetResult(BaseModel):
    """Result of an asset acquisition (search or generation)."""
    success: bool = Field(description="Whether the asset was successfully acquired")
    asset_path: Optional[str] = Field(default=None, description="Absolute path where the asset was saved")
    godot_path: Optional[str] = Field(default=None, description="Godot res:// path for the asset")
    source: Optional[str] = Field(default=None, description="Where the asset came from (e.g., 'opengameart', 'kenney', 'generated')")
    message: str = Field(default="", description="Human-readable status message")
    frame_count: int = Field(default=1, description="Number of frames (for sprite sheets)")
    frame_width: int = Field(default=0, description="Width of each frame in the sprite sheet")
    frame_height: int = Field(default=0, description="Height of each frame in the sprite sheet")
