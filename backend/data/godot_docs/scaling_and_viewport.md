# Godot 4 — Scale, Viewport, and Window Size

## Godot 4 unit system
In Godot 4, 1 world unit = 1 pixel at the default Camera2D zoom.
A Sprite2D showing a 32×32 texture occupies a 32×32 pixel area on screen at scale (1,1) and zoom (1,1).
In a 1280×720 window a 32px character is tiny (~4% of screen height) — essentially invisible without zoom.

## MANDATORY project settings (call in execute_godot_script in the FIRST task)
```gdscript
ProjectSettings.set_setting("display/window/size/viewport_width", 1280)
ProjectSettings.set_setting("display/window/size/viewport_height", 720)
ProjectSettings.set_setting("display/window/size/resizable", false)
ProjectSettings.set_setting("rendering/renderer/rendering_method", "gl_compatibility")
ProjectSettings.set_setting("rendering/textures/canvas_textures/default_texture_filter", 0)
ProjectSettings.save()
```
Value 0 for default_texture_filter = Nearest neighbour (sharp pixel art). Value 1 = Linear (blurry). Always use 0.

## Recommended sprite sizes by game type
| Game type        | Sprite size  | Camera zoom    | Effective viewport |
|-----------------|-------------|----------------|-------------------|
| Pixel platformer | 32×64 px    | Vector2(2, 2)  | 640×360 units     |
| Top-down RPG     | 48×48 px    | Vector2(2, 2)  | 640×360 units     |
| Arcade shooter   | 64×64 px    | Vector2(1, 1)  | 1280×720 units    |
| Puzzle / card    | 64×64 px    | Vector2(1, 1)  | 1280×720 units    |
| Tiny 16px art    | 16×16 px    | Vector2(4, 4)  | 320×180 units     |

## Camera2D zoom
```gdscript
# Place Camera2D as a child of Player, then in player.gd _ready():
$Camera2D.zoom = Vector2(2.0, 2.0)   # For 32px sprites
$Camera2D.position_smoothing_enabled = true
$Camera2D.position_smoothing_speed = 5.0

# Or set via set_property in the action list:
# set_property("Player/Camera2D", "zoom", Vector2(2, 2))
```
zoom > 1 = zoomed IN (world appears larger). zoom < 1 = zoomed out.

## Effective viewport size at Camera2D zoom
At zoom Vector2(2, 2) with a 1280×720 window:
- Visible world width  = 1280 / 2 = 640 units
- Visible world height =  720 / 2 = 360 units

Position objects within these bounds:
```gdscript
# Platformer layout example (zoom 2× → 640×360 effective viewport)
# Ground (StaticBody2D):  position = Vector2(320, 330), scale covers full width
# Player start:           position = Vector2(100, 270)
# Platform 1:             position = Vector2(200, 200)
# Platform 2:             position = Vector2(400, 150)
# Enemy patrol range:     x from 150 to 450
```

## Node scale vs texture size
Use `scale` on the root node to enlarge sprites without regenerating textures:
```gdscript
# In CharacterBody2D _ready() — doubles visual and collision size:
scale = Vector2(2.0, 2.0)

# For just the Sprite2D visual (does NOT scale collision):
$Sprite2D.scale = Vector2(2.0, 2.0)
```
Scaling a CharacterBody2D also scales its CollisionShape2D, which is usually correct for gameplay.

## TileMap tile size
```gdscript
# Set tile size to match sprites:
# 32px sprites → 32×32 tiles
# In GDScript after creating TileSet:
$TileMap.tile_set.tile_size = Vector2i(32, 32)
```

## Setting position and size via set_property
```gdscript
# These are valid set_property calls for positioning:
set_property("Player", "position", Vector2(100, 270))
set_property("Ground", "position", Vector2(320, 330))
set_property("Camera2D", "zoom", Vector2(2, 2))

# DO NOT use set_property for textures — use load() in GDScript instead.
```

## Complete project setup script (execute_godot_script)
```gdscript
# Run this in the first task:
ProjectSettings.set_setting("display/window/size/viewport_width", 1280)
ProjectSettings.set_setting("display/window/size/viewport_height", 720)
ProjectSettings.set_setting("display/window/size/resizable", false)
ProjectSettings.set_setting("rendering/renderer/rendering_method", "gl_compatibility")
ProjectSettings.set_setting("rendering/textures/canvas_textures/default_texture_filter", 0)
ProjectSettings.save()
```
