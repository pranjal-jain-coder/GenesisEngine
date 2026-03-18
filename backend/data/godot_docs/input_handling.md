# Godot 4 — Input Handling

## Input Actions (InputMap)
Define actions in Project Settings → Input Map, then use:
```gdscript
Input.is_action_pressed("move_left")       # held down
Input.is_action_just_pressed("jump")       # pressed this frame only
Input.is_action_just_released("shoot")     # released this frame
Input.get_axis("move_left", "move_right")  # -1.0 to 1.0 (analog or keyboard)
Input.get_vector("move_left", "move_right", "move_up", "move_down")  # Vector2
```

## Default built-in actions
```
ui_left, ui_right, ui_up, ui_down  — arrow keys / D-pad
ui_accept  — Enter / Space
ui_cancel  — Escape
ui_select  — Space
```

## Keyboard input (raw keys)
```gdscript
if Input.is_key_pressed(KEY_SPACE):
    jump()
if Input.is_key_pressed(KEY_A):
    move_left()
# Key constants: KEY_W, KEY_A, KEY_S, KEY_D, KEY_SPACE, KEY_SHIFT, KEY_CTRL, KEY_ESCAPE
```

## Mouse input
```gdscript
# In _input(event) or _unhandled_input(event):
func _input(event: InputEvent):
    if event is InputEventMouseButton:
        if event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
            shoot()
    if event is InputEventMouseMotion:
        look_at(get_global_mouse_position())

# Get mouse position:
var mouse_pos = get_global_mouse_position()   # world space
var local_mouse = get_local_mouse_position()  # local to this node
```

## _input vs _unhandled_input
- `_input(event)`: receives ALL input events (including those consumed by UI)
- `_unhandled_input(event)`: only gets events NOT consumed by UI controls
- For gameplay input, prefer `_unhandled_input` to avoid conflicts with menus

## Gamepad input
```gdscript
Input.is_joy_button_pressed(0, JOY_BUTTON_A)  # gamepad 0, A button
Input.get_joy_axis(0, JOY_AXIS_LEFT_X)        # left stick X axis
```

## Checking input in _physics_process (recommended for movement)
```gdscript
func _physics_process(delta):
    var dir = Input.get_axis("move_left", "move_right")
    velocity.x = dir * SPEED
    move_and_slide()
```

## Input.get_axis explained
Returns a float from -1.0 to 1.0:
- -1.0 when only "negative" action (e.g., move_left) is pressed
- +1.0 when only "positive" action (e.g., move_right) is pressed
- 0.0 when neither or both are pressed

## Reading the InputMap at runtime
```gdscript
# List all defined actions:
InputMap.get_actions()
# Check if action exists:
InputMap.has_action("jump")
```

## Common player input pattern (platformer)
```gdscript
extends CharacterBody2D
const SPEED = 200.0
const JUMP_VELOCITY = -400.0

func _physics_process(delta: float) -> void:
    if not is_on_floor():
        velocity += get_gravity() * delta
    if Input.is_action_just_pressed("ui_accept") and is_on_floor():
        velocity.y = JUMP_VELOCITY
    var direction = Input.get_axis("ui_left", "ui_right")
    velocity.x = direction * SPEED if direction else move_toward(velocity.x, 0, SPEED)
    move_and_slide()
```

## Common player input pattern (top-down shooter)
```gdscript
extends CharacterBody2D
const SPEED = 150.0

func _physics_process(delta: float) -> void:
    var input = Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")
    velocity = input * SPEED
    move_and_slide()

func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
        shoot()

func shoot():
    # Instance a bullet scene
    var bullet = preload("res://scenes/bullet.tscn").instantiate()
    bullet.position = global_position
    bullet.rotation = (get_global_mouse_position() - global_position).angle()
    get_parent().add_child(bullet)
```
