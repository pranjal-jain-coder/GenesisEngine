# Godot 4 — Common GDScript Mistakes and Pitfalls

## Godot 4 vs Godot 3 breaking changes

### yield → await
```gdscript
# Godot 3 (WRONG in 4):
yield(get_tree().create_timer(1.0), "timeout")

# Godot 4 (CORRECT):
await get_tree().create_timer(1.0).timeout
```

### connect() signature changed
```gdscript
# Godot 3 (WRONG in 4):
$Button.connect("pressed", self, "_on_pressed")

# Godot 4 (CORRECT):
$Button.pressed.connect(_on_pressed)
```

### export keyword changed
```gdscript
# Godot 3 (WRONG in 4):
export var speed = 200

# Godot 4 (CORRECT):
@export var speed: float = 200.0
```

### onready keyword changed
```gdscript
# Godot 3 (WRONG in 4):
onready var sprite = $Sprite

# Godot 4 (CORRECT):
@onready var sprite: Sprite2D = $Sprite2D
```

### Sprite → Sprite2D
```gdscript
# Godot 3: Sprite
# Godot 4: Sprite2D  ← use this
```

### KinematicBody2D → CharacterBody2D
```gdscript
# Godot 3:
extends KinematicBody2D
move_and_slide(velocity, Vector2.UP)

# Godot 4:
extends CharacterBody2D
move_and_slide()  # velocity is now a property, no args needed
```

### RandomNumberGenerator
```gdscript
# Godot 4: use global functions directly:
var r = randi_range(0, 10)      # random int between 0 and 10
var f = randf_range(0.0, 1.0)   # random float
randomize()                      # seed RNG (usually not needed — auto-seeded)
```

## Type errors
```gdscript
# WRONG: can't multiply Vector2 * int
velocity = Vector2(1, 0) * 200   # ERROR: use float
velocity = Vector2(1, 0) * 200.0 # OK

# WRONG: comparing int to null
if health == null:  # use 'is' for null checks
if health == 0:     # correct numeric comparison
if node == null:    # OK for nodes
```

## Null reference errors
```gdscript
# Always check before using nodes that may not exist:
var player = get_tree().get_first_node_in_group("player")
if player == null:
    return

# Use get_node_or_null instead of $:
var node = get_node_or_null("OptionalChild")
if node:
    node.do_something()
```

## _ready() vs _init()
```gdscript
func _init():
    # DON'T access $Children here — they don't exist yet
    # DON'T call get_node() here

func _ready():
    # Safe to access $Children here
    $Sprite2D.texture = load("...")
```

## Scene not saving (common mistake)
After calling add_node / set_property / attach_script on the editor interface,
you MUST call save_scene() otherwise the .tscn file on disk is unchanged.

## Duplicate node names cause silent bugs
Always call node_exists() before add_node(). Adding a node with a duplicate name
causes Godot to silently rename it (e.g., "Player" → "Player2"), breaking any
$Player references in scripts.

## delta usage
```gdscript
# WRONG: velocity already incorporates delta in move_and_slide()
velocity = Vector2(SPEED, 0) * delta  # double-counting delta!

# CORRECT: set velocity as units per second; move_and_slide handles delta internally
velocity.x = SPEED
move_and_slide()

# For manual position movement (NOT using move_and_slide):
position += velocity * delta  # correct
```

## Area2D not detecting collisions
Common causes:
1. CollisionShape2D is disabled or has no shape assigned
2. collision_layer / collision_mask don't overlap between Area2D and the target body
3. Body is on a different layer than what Area2D monitors
4. monitoring = false on the Area2D

Fix:
```gdscript
$Area2D.monitoring = true
$Area2D.monitorable = true
$Area2D.collision_layer = 1
$Area2D.collision_mask = 1
```

## is_on_floor() always false
Causes:
1. Not calling move_and_slide() (required for floor detection)
2. Floor is not a StaticBody2D with CollisionShape2D
3. up_direction not set correctly (default Vector2.UP is fine for most platformers)
4. CollisionShape2D not overlapping with floor

## String concatenation with numbers
```gdscript
# WRONG in strict-typed context:
var s = "Score: " + score  # ERROR: can't concat String + int

# CORRECT:
var s = "Score: " + str(score)
var s = "Score: %d" % score
```

## Physics process vs process
- Use `_process(delta)` for: visuals, input response, UI updates, non-physics movement
- Use `_physics_process(delta)` for: CharacterBody2D movement, collision-dependent logic, forces

## call_deferred vs direct call
When modifying the scene tree inside a physics callback, use call_deferred:
```gdscript
# WRONG (may crash in physics tick):
queue_free()
add_child(new_node)

# CORRECT:
call_deferred("queue_free")
call_deferred("add_child", new_node)
```
