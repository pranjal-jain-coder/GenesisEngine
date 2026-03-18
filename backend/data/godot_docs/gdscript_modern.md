# Modern GDScript (Godot 4) Best Practices

## Typed Arrays
Use typed arrays to avoid type errors and get autocompletion.

```gdscript
# Bad (Godot 3 style)
var enemies = []
enemies.append($Enemy)

# Good (Godot 4 style)
var enemies: Array[CharacterBody2D] = []
enemies.append($Enemy)
```

## Await and Coroutines
Use `await` for pausing execution without blocking the main thread.

```gdscript
# Wait for 1 second
await get_tree().create_timer(1.0).timeout

# Wait for a signal
await $AnimationPlayer.animation_finished

# Example: Cutscene logic
func play_intro():
    $AnimationPlayer.play("FadeIn")
    await $AnimationPlayer.animation_finished
    $DialogueBox.show_text("Welcome hero!")
    await $DialogueBox.text_finished
    $AnimationPlayer.play("FadeOut")
```

## Signal Connections (Callable Syntax)
Use the `.connect()` method with a Callable, not string names.

```gdscript
# Bad (Godot 3)
$Button.connect("pressed", self, "_on_button_pressed")

# Good (Godot 4)
$Button.pressed.connect(_on_button_pressed)

func _on_button_pressed():
    print("Clicked!")
```

## Global Signal Bus pattern
Create a `signal_bus.gd` autoload (Project Settings -> Autoads -> "SignalBus").
Decouples highly separated systems (e.g., UI updates when player dies).

1.  **signal_bus.gd**:
    ```gdscript
    extends Node
    signal player_damaged(health: int)
    signal score_updated(score: int)
    ```

2.  **Player (emitter)**:
    ```gdscript
    func take_damage(amount):
        health -= amount
        SignalBus.player_damaged.emit(health)
    ```

3.  **HUD (listener)**:
    ```gdscript
    func _ready():
        SignalBus.player_damaged.connect(_on_player_damaged)

    func _on_player_damaged(hp):
        $HealthBar.value = hp
    ```

## Annotations
Use `@export` tailored for inspectors.

```gdscript
@export_group("Stats")
@export var health: int = 100
@export var speed: float = 300.0

@export_group("Visuals")
@export_color_no_alpha var tint: Color = Color.WHITE
@export_file("*.png") var texture_path: String

@onready var sprite = $Sprite2D
```

## Static Typing
Always specify types for function arguments and return values.

```gdscript
func calculate_damage(base: int, multiplier: float) -> int:
    return int(base * multiplier)
```
