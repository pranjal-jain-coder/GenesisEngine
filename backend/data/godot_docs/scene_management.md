# Godot 4 — Scene Management

## Instancing a scene at runtime
```gdscript
# preload (at parse time, for frequently used scenes):
const BulletScene = preload("res://scenes/bullet.tscn")

# load (at runtime):
var EnemyScene = load("res://scenes/enemy.tscn")

# Instantiate and add to tree:
var bullet = BulletScene.instantiate()
bullet.position = global_position
get_parent().add_child(bullet)   # or: get_tree().current_scene.add_child(bullet)
add_child(bullet)                # add as child of THIS node
```

## Changing scenes
```gdscript
# Replace the current scene (deferred, safe):
get_tree().change_scene_to_file("res://scenes/game_over.tscn")
get_tree().change_scene_to_packed(preload("res://scenes/menu.tscn"))

# Reload current scene:
get_tree().reload_current_scene()
```

## Removing nodes
```gdscript
queue_free()          # remove this node (deferred, safe)
node.queue_free()     # remove another node
# NEVER use free() directly — use queue_free() instead
```

## Finding nodes
```gdscript
$ChildName                     # direct child by name
$"Path/To/Child"               # nested path
get_node("ChildName")          # same as $
get_node_or_null("MaybeChild") # returns null if not found
find_child("*Player*")         # wildcard search among all descendants
get_parent()                   # parent node
get_tree().get_root()          # scene root
get_tree().current_scene       # current scene root node
```

## @onready for node references
```gdscript
# BAD: node may not exist yet in _init()
var sprite = $Sprite2D  # ERROR if called before _ready

# GOOD: @onready assigns after the node enters the scene tree
@onready var sprite: Sprite2D = $Sprite2D
@onready var timer: Timer = $Timer
@onready var anim: AnimationPlayer = $AnimationPlayer
```

## Pausing and unpausing
```gdscript
get_tree().paused = true   # pause all nodes (unless process_mode overrides)
get_tree().paused = false  # resume

# Node.process_mode determines behavior when paused:
# PROCESS_MODE_PAUSABLE (default): paused when tree is paused
# PROCESS_MODE_WHEN_PAUSED: only runs when paused (for pause menus)
# PROCESS_MODE_ALWAYS: always runs regardless
$PauseMenu.process_mode = Node.PROCESS_MODE_WHEN_PAUSED
```

## Node lifecycle order
1. `_init()` — constructor (before entering tree)
2. `_enter_tree()` — node just added to scene tree
3. `_ready()` — node and all children are ready
4. `_process(delta)` — every frame
5. `_physics_process(delta)` — every physics tick
6. `_exit_tree()` — node being removed from tree

## Deferred calls (safe cross-frame operations)
```gdscript
# Avoid modifying the scene tree mid-physics tick:
call_deferred("add_child", new_node)
call_deferred("queue_free")
set_deferred("position", Vector2(0, 0))
```

## Scene tree groups for game management
```gdscript
# Pause all enemies:
get_tree().call_group("enemies", "set_process", false)

# Find the player:
var players = get_tree().get_nodes_in_group("player")
if players.size() > 0:
    var player = players[0]
```

## Spawning enemies / bullets (common pattern)
```gdscript
# In a level manager script:
const EnemyScene = preload("res://scenes/enemy.tscn")

func spawn_enemy(pos: Vector2):
    var enemy = EnemyScene.instantiate()
    enemy.position = pos
    add_child(enemy)
    enemy.add_to_group("enemies")
    enemy.died.connect(_on_enemy_died)
```

## ResourceLoader (async loading for large scenes)
```gdscript
ResourceLoader.load_threaded_request("res://scenes/big_level.tscn")
# Later:
var scene = ResourceLoader.load_threaded_get("res://scenes/big_level.tscn")
```
