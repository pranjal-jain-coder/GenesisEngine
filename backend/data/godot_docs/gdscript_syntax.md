# GDScript 4.x Syntax Reference

## Variables and Types
```gdscript
var x: int = 0              # typed variable
var name: String = "hero"
var speed: float = 200.0
const MAX_HEALTH: int = 100 # constant
@export var jump_force: float = 400.0  # exported to Inspector
@onready var sprite: Sprite2D = $Sprite2D  # assigned after _ready() is called
```

## Functions
```gdscript
func _ready() -> void:
    pass  # called once when node enters scene tree

func _process(delta: float) -> void:
    pass  # called every frame

func _physics_process(delta: float) -> void:
    pass  # called every physics frame (fixed rate)

func my_func(arg: int) -> String:
    return str(arg)
```

## Conditionals and Loops
```gdscript
if health <= 0:
    die()
elif health < 30:
    play_hurt_animation()
else:
    pass

for i in range(10):
    print(i)

while alive:
    update()

match state:
    "idle":
        play("idle")
    "run":
        play("run")
    _:
        pass  # default
```

## Arrays and Dictionaries
```gdscript
var arr: Array = [1, 2, 3]
arr.append(4)
arr.size()       # length
arr[0]           # index

var dict: Dictionary = {"name": "hero", "hp": 100}
dict["name"]
dict.get("key", default_value)
dict.has("key")
```

## Signals
```gdscript
# Define a signal
signal health_changed(new_value: int)

# Emit a signal
emit_signal("health_changed", current_health)
# or: health_changed.emit(current_health)

# Connect in code
some_node.health_changed.connect(_on_health_changed)

# Connect in _ready via @onready
func _ready():
    $Button.pressed.connect(_on_button_pressed)

func _on_button_pressed():
    print("button pressed")
```

## String Formatting
```gdscript
var msg = "Score: %d" % score
var msg2 = "Hello %s, you have %d HP" % [name, hp]
# Godot 4 also supports:
var msg3 = "Score: " + str(score)
```

## Type Casting
```gdscript
var node = get_node("Player")
var player = node as CharacterBody2D
if player:
    player.velocity = Vector2.ZERO
```

## Extending Nodes / extends keyword
```gdscript
extends CharacterBody2D  # script acts as this node type

extends Node
extends Sprite2D
extends Area2D
```

## Lambda / Callable
```gdscript
var fn = func(x): return x * 2
fn.call(3)  # returns 6

# Used with connect:
button.pressed.connect(func(): print("pressed"))
```

## Static functions and variables
```gdscript
static var count: int = 0
static func get_count() -> int:
    return count
```

## Await (async)
```gdscript
await get_tree().create_timer(1.0).timeout
await $AnimationPlayer.animation_finished
```
