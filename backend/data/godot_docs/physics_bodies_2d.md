# Godot 4 Physics Bodies 2D Reference

## CharacterBody2D (Player & Enemies)
Used for characters that need custom movement logic (platformers, top-down RPGs).
Replaces Godot 3 `KinematicBody2D`.

**Key Properties:**
- `velocity`: Vector2 (pixels/sec). Modify this, then call `move_and_slide()`.
- `up_direction`: Vector2 (default UP). Used for `is_on_floor()`.
- `wall_min_slide_angle`: Radians.

**Movement Code Pattern (Platformer):**
```gdscript
extends CharacterBody2D

const SPEED = 300.0
const JUMP_VELOCITY = -400.0
var gravity = ProjectSettings.get_setting("physics/2d/default_gravity")

func _physics_process(delta):
    # Add gravity
    if not is_on_floor():
        velocity.y += gravity * delta

    # Handle Jump
    if Input.is_action_just_pressed("ui_accept") and is_on_floor():
        velocity.y = JUMP_VELOCITY

    # Get input direction (-1, 0, 1)
    var direction = Input.get_axis("ui_left", "ui_right")
    if direction:
        velocity.x = direction * SPEED
    else:
        velocity.x = move_toward(velocity.x, 0, SPEED)

    move_and_slide()
```

**Movement Code Pattern (Top-Down):**
```gdscript
extends CharacterBody2D

const SPEED = 200.0

func _physics_process(delta):
    var direction = Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")
    velocity = direction * SPEED
    move_and_slide()
```

**Collision Layers:**
- `collision_layer`: What I am.
- `collision_mask`: What I hit.
- Use `set_collision_layer_value(1, true)` to set layer 1 via code.

## Area2D (Triggers & Hitboxes)
Used for detection, bullets, coins, and damage zones. Does NOT block movement.

**Key Signals:**
- `body_entered(body: Node2D)`: Fired when a physics body enters.
- `area_entered(area: Area2D)`: Fired when another Area2D enters.

**Setup in Editor:**
1. Add node `Area2D`.
2. Add child `CollisionShape2D`.
3. Assign shape (RectangleShape2D, CircleShape2D).

**Bullet Pattern:**
```gdscript
extends Area2D

var speed = 400
var direction = Vector2.RIGHT

func _process(delta):
    position += direction * speed * delta

func _on_body_entered(body):
    if body.has_method("take_damage"):
        body.take_damage(10)
    queue_free() # Destroy bullet
```

**Coin Pickup Pattern:**
```gdscript
extends Area2D

func _on_body_entered(body):
    if body.name == "Player":
        GameManager.add_score(1)
        queue_free()
```

## RigidBody2D (Physics Objects)
Controlled by physics engine (bouncing balls, falling crates).
Do **NOT** set `position` or `velocity` directly every frame. Use `apply_impulse` or `apply_force`.

**Key Methods:**
- `apply_impulse(vector)`: Instant kick.
- `apply_central_impulse(vector)`: Kick at center (no rotation).

**Example:**
```gdscript
func kick():
    apply_central_impulse(Vector2.UP * 500)
```
