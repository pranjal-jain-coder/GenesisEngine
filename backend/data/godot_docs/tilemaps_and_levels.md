# Godot 4 — TileMaps and Level Design

## TileMap vs TileMapLayer (Godot 4.3+)
In Godot 4.3+, TileMap is deprecated. Use TileMapLayer instead.
TileMapLayer is a single-layer tilemap; use multiple TileMapLayer nodes for layers.

## Basic TileMapLayer usage
```gdscript
extends TileMapLayer

func _ready():
    # Set a cell (column x, row y) to tile from source_id at atlas_coords
    set_cell(Vector2i(0, 0), 0, Vector2i(0, 0))
    # Erase a cell:
    erase_cell(Vector2i(0, 0))
    # Get cell source id (-1 if empty):
    var src = get_cell_source_id(Vector2i(0, 0))
    # Convert world position to tile coords:
    var tile_pos = local_to_map(to_local(global_position))
    # Convert tile coords to world position:
    var world_pos = map_to_local(Vector2i(3, 5))
```

## TileMapLayer collision
TileMapLayer supports physics collisions through TileSet physics layers.
Physics collision is configured in the TileSet resource:
- Each tile can have one or more collision polygons
- The TileMapLayer uses these to generate static collision for the whole map

You do NOT need to add separate collision shapes — the TileSet handles it.

## Procedural level generation (simple)
```gdscript
extends TileMapLayer

func _ready():
    generate_level()

func generate_level():
    var width = 20
    var height = 10
    for x in range(width):
        for y in range(height):
            if y == height - 1:
                # Floor tile (source 0, atlas pos (0,0))
                set_cell(Vector2i(x, y), 0, Vector2i(0, 0))
            elif randf() < 0.1:
                # Random platform (source 0, atlas pos (1,0))
                set_cell(Vector2i(x, y), 0, Vector2i(1, 0))
```

## Using TileMap for collision detection
```gdscript
# Check if a tile exists at a world position:
var tile_pos = tile_map_layer.local_to_map(
    tile_map_layer.to_local(global_position)
)
var tile_id = tile_map_layer.get_cell_source_id(tile_pos)
if tile_id == -1:
    print("no tile here")
```

## Level scenes (recommended structure)
```
Level.tscn
├── TileMapLayer (ground/platforms)
├── TileMapLayer (decorations — no collision)
├── Node2D "Entities"
│   ├── Player (instanced from player.tscn)
│   ├── Enemy1
│   └── Enemy2
├── Node2D "Collectibles"
│   └── Coin1, Coin2, ...
└── CanvasLayer "HUD"
    └── Label (score), ProgressBar (health)
```

## Parallax background
```gdscript
# ParallaxBackground + ParallaxLayer:
# ParallaxLayer.motion_scale controls scroll speed relative to camera
# motion_scale = Vector2(0.5, 0.5) → scrolls at half camera speed (background)
# motion_scale = Vector2(0.2, 0.0) → slow horizontal scroll only (sky layer)
```

## TileMap pathfinding with AStarGrid2D
```gdscript
var astar = AStarGrid2D.new()
astar.region = Rect2i(0, 0, 20, 10)
astar.cell_size = Vector2(16, 16)
astar.update()

# Mark walls as solid:
for x in range(20):
    for y in range(10):
        if tile_map.get_cell_source_id(Vector2i(x, y)) != -1:
            astar.set_point_solid(Vector2i(x, y), true)

# Get path:
var path = astar.get_id_path(
    astar.local_to_map(start_pos),
    astar.local_to_map(end_pos)
)
```
