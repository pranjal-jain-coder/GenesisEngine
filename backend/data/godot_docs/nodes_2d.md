# Godot 4 — Common 2D Node Types

## Node2D (base for all 2D nodes)
```gdscript
extends Node2D
# Properties: position, rotation, scale, z_index
position = Vector2(100, 200)
rotation = deg_to_rad(45.0)
scale = Vector2(2.0, 2.0)
z_index = 1  # draw order (higher = on top)
```

## Sprite2D
Used to display a 2D texture/image on screen.
```gdscript
extends Sprite2D
# Key properties: texture, frame, hframes, vframes, offset, centered, flip_h, flip_v
@onready var sprite: Sprite2D = $Sprite2D
func _ready():
    sprite.texture = load("res://assets/player.png")
    sprite.hframes = 4   # columns in spritesheet
    sprite.vframes = 2   # rows in spritesheet
    sprite.frame = 0     # current frame index
    sprite.flip_h = false
```

## CharacterBody2D
The primary node for player/enemy characters with physics movement.
```gdscript
extends CharacterBody2D
const SPEED = 200.0
const JUMP_VELOCITY = -400.0

func _physics_process(delta: float) -> void:
    # Apply gravity
    if not is_on_floor():
        velocity += get_gravity() * delta

    # Jump
    if Input.is_action_just_pressed("ui_accept") and is_on_floor():
        velocity.y = JUMP_VELOCITY

    # Horizontal movement
    var direction := Input.get_axis("ui_left", "ui_right")
    if direction:
        velocity.x = direction * SPEED
    else:
        velocity.x = move_toward(velocity.x, 0, SPEED)

    move_and_slide()  # moves and handles collisions automatically
```

## RigidBody2D
Physics-simulated body (falls, bounces). Don't manually set position.
```gdscript
extends RigidBody2D
# Properties: mass, gravity_scale, linear_velocity, angular_velocity
# Apply forces:
func _ready():
    apply_impulse(Vector2(100, -200))
    apply_force(Vector2(0, 50))
```

## StaticBody2D
Immovable collision body (platforms, walls, ground).
```gdscript
extends StaticBody2D
# No movement API — just position it in the scene
# Requires a CollisionShape2D child
```

## Area2D
Detects overlapping bodies/areas. Used for pickups, triggers, hitboxes.
```gdscript
extends Area2D
func _ready():
    body_entered.connect(_on_body_entered)
    area_entered.connect(_on_area_entered)

func _on_body_entered(body: Node2D):
    if body.is_in_group("player"):
        queue_free()  # remove self (e.g., coin collected)

func _on_area_entered(area: Area2D):
    print("area overlap: ", area.name)
```

## CollisionShape2D
Must be a child of any physics body or Area2D.
```gdscript
# Common shapes (set via script or Inspector):
var shape = RectangleShape2D.new()
shape.size = Vector2(32, 64)
$CollisionShape2D.shape = shape

# Or via set_property in ActionList:
# set_property("CollisionShape2D", "shape", "RectangleShape2D")
# set_property("CollisionShape2D", "shape", "CapsuleShape2D")
# set_property("CollisionShape2D", "shape", "CircleShape2D")
```

## Camera2D
Follows the player or any node.
```gdscript
extends Camera2D
# Make it follow a target in _process:
@export var target: Node2D
func _process(delta):
    if target:
        position = target.position
# Or: make Camera2D a child of the player node — it follows automatically.
# Properties: zoom, limit_left, limit_right, limit_top, limit_bottom
zoom = Vector2(2.0, 2.0)  # zoom in (bigger = closer)
```

## AnimatedSprite2D
Plays frame-based animations using a SpriteFrames resource.
```gdscript
extends AnimatedSprite2D
func _ready():
    play("idle")

func _physics_process(delta):
    if velocity.x != 0:
        play("run")
    else:
        play("idle")
    flip_h = velocity.x < 0  # face left
```

## TileMapLayer (Godot 4.3+) / TileMap
Used for tile-based worlds. In Godot 4.3+ TileMap is deprecated, use TileMapLayer.
```gdscript
extends TileMapLayer
# Set tiles via:
set_cell(Vector2i(x, y), source_id, atlas_coords)
# Erase:
erase_cell(Vector2i(x, y))
```

## Label
Displays text in 2D space.
```gdscript
extends Label
func _ready():
    text = "Score: 0"
    add_theme_font_size_override("font_size", 24)
```

## CanvasLayer
Renders UI/HUD on top of everything, unaffected by camera.
```gdscript
extends CanvasLayer
# layer property: lower = behind, higher = in front
layer = 1
# Children (Label, Button, etc.) are drawn over the game world
```
