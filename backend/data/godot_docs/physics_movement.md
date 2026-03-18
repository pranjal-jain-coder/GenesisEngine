# Godot 4 — Physics & Movement

## CharacterBody2D movement (platformer)
```gdscript
extends CharacterBody2D

const SPEED := 200.0
const JUMP_VELOCITY := -400.0

func _physics_process(delta: float) -> void:
    # Gravity
    if not is_on_floor():
        velocity += get_gravity() * delta  # uses Project Settings gravity

    # Jump
    if Input.is_action_just_pressed("jump") and is_on_floor():
        velocity.y = JUMP_VELOCITY

    # Horizontal input
    var dir := Input.get_axis("move_left", "move_right")
    velocity.x = dir * SPEED if dir else move_toward(velocity.x, 0, SPEED)

    move_and_slide()  # must be called every frame
```

## CharacterBody2D movement (top-down)
```gdscript
extends CharacterBody2D
const SPEED := 150.0

func _physics_process(delta: float) -> void:
    var input := Vector2(
        Input.get_axis("move_left", "move_right"),
        Input.get_axis("move_up", "move_down")
    ).normalized()
    velocity = input * SPEED
    move_and_slide()
```

## Checking floor / walls / ceiling
```gdscript
is_on_floor()    # true if standing on floor
is_on_ceiling()  # true if hitting ceiling
is_on_wall()     # true if touching a wall
get_floor_normal()  # Vector2 of the floor surface
```

## move_and_slide details
- Automatically applies `velocity` * delta internally — do NOT multiply velocity by delta yourself.
- Handles collision sliding along surfaces.
- Returns a boolean (was there a collision this frame?).

## Custom gravity
```gdscript
const GRAVITY := 980.0
func _physics_process(delta):
    if not is_on_floor():
        velocity.y += GRAVITY * delta
    move_and_slide()
```

## RigidBody2D forces
```gdscript
# One-time impulse (e.g., explosion knockback)
apply_impulse(Vector2(0, -500))

# Continuous force (e.g., rocket thrust)
apply_force(Vector2(0, -100))

# Central impulse (at center of mass)
apply_central_impulse(Vector2(100, 0))

# Freeze physics temporarily
freeze = true
```

## Collision Layers and Masks
- **collision_layer**: what layer this body occupies
- **collision_mask**: what layers this body detects
```gdscript
# Set via script:
collision_layer = 1   # bit 1
collision_mask = 2    # detect layer 2
# Set multiple layers: collision_layer = 1 | 4 | 8
```

## KinematicCollision2D (manual collision info)
```gdscript
var collision = move_and_collide(velocity * delta)
if collision:
    var normal = collision.get_normal()
    velocity = velocity.bounce(normal)
```

## move_toward (smooth deceleration)
```gdscript
# Smoothly reduce velocity.x to 0 at rate SPEED per second
velocity.x = move_toward(velocity.x, 0, SPEED)
# General form: move_toward(from, to, delta)
```

## lerp (smooth interpolation)
```gdscript
position = lerp(position, target_position, 0.1)  # 10% per frame (frame-rate dependent)
position = position.lerp(target_position, delta * 5.0)  # frame-rate independent
```

## Vector2 utilities
```gdscript
Vector2.ZERO       # (0, 0)
Vector2.UP         # (0, -1)
Vector2.DOWN       # (0, 1)
Vector2.LEFT       # (-1, 0)
Vector2.RIGHT      # (1, 0)
v.normalized()     # unit vector (length 1)
v.length()         # magnitude
v.distance_to(other)
v.dot(other)       # dot product
v.rotated(angle)   # rotate by radians
```

## Detecting collision with groups
```gdscript
func _on_body_entered(body):
    if body.is_in_group("enemy"):
        take_damage(10)
```
