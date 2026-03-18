# Godot 4 — Signals and Groups

## Defining and Emitting Signals
```gdscript
# Define in the class body:
signal died
signal health_changed(new_hp: int)
signal item_collected(item_name: String, amount: int)

# Emit:
died.emit()
health_changed.emit(current_hp)
item_collected.emit("coin", 5)
```

## Connecting Signals (Godot 4 style)
```gdscript
# In _ready():
func _ready():
    # Connect to a method on self:
    some_node.died.connect(_on_enemy_died)

    # Connect to a method on another node:
    $Enemy.health_changed.connect($HUD._on_health_changed)

    # Lambda (inline):
    $Button.pressed.connect(func(): print("clicked"))

    # Disconnect later:
    some_node.died.disconnect(_on_enemy_died)
```

## Signal handler naming convention
```gdscript
# Pattern: _on_NodeName_signal_name
func _on_enemy_died():
    score += 10

func _on_health_changed(new_hp: int):
    $HUD/HealthBar.value = new_hp
```

## is_connected check
```gdscript
if not some_signal.is_connected(my_method):
    some_signal.connect(my_method)
```

## Groups
Groups let you tag nodes and find/call them as a batch.
```gdscript
# Add to group via code:
add_to_group("enemies")
add_to_group("collectibles")

# Check membership:
is_in_group("enemies")

# Scene tree calls:
get_tree().call_group("enemies", "disable")     # calls disable() on all nodes in group
get_tree().get_nodes_in_group("enemies")         # returns Array of nodes
get_tree().set_group("enemies", "active", false) # sets property on all
```

## Signals for scene-wide events (via SceneTree)
```gdscript
# Triggered when scene tree pauses/resumes:
get_tree().paused = true
# Built-in SceneTree signals:
get_tree().node_added         # when any node enters
get_tree().node_removed       # when any node exits
```

## Autoload (Singleton) communication via signals
```gdscript
# In an autoload script "EventBus":
signal player_died
signal score_updated(new_score: int)

# Emitting from player.gd:
EventBus.player_died.emit()

# Listening in hud.gd:
func _ready():
    EventBus.score_updated.connect(_on_score_updated)
func _on_score_updated(score):
    $Label.text = str(score)
```

## Common built-in node signals

### Area2D
```gdscript
body_entered(body: Node2D)    # PhysicsBody entered the area
body_exited(body: Node2D)
area_entered(area: Area2D)
area_exited(area: Area2D)
```

### Timer
```gdscript
timeout  # emitted when timer hits 0
$Timer.start(2.0)  # start 2-second timer
await $Timer.timeout  # wait for timer in async context
```

### AnimationPlayer
```gdscript
animation_finished(anim_name: String)
animation_started(anim_name: String)
```

### Button / BaseButton
```gdscript
pressed        # on click
button_up
button_down
toggled(toggled_on: bool)
```

### RigidBody2D
```gdscript
body_entered(body: Node)  # when another body collides
body_exited(body: Node)
```

### CharacterBody2D (no built-in collision signal — use move_and_collide or check manually)
