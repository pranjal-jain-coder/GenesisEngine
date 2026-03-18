# Godot 4 — Animation

## AnimationPlayer
Plays timeline-based animations defined in the editor.
```gdscript
@onready var anim: AnimationPlayer = $AnimationPlayer

func _ready():
    anim.play("idle")

func _physics_process(delta):
    if velocity.length() > 10:
        anim.play("run")
    else:
        anim.play("idle")

# Control:
anim.pause()
anim.stop()
anim.play_backwards("run")
anim.speed_scale = 2.0  # double speed
anim.current_animation     # name of currently playing animation
anim.is_playing()          # bool

# Signals:
anim.animation_finished.connect(_on_anim_finished)
func _on_anim_finished(anim_name: String):
    if anim_name == "death":
        queue_free()
```

## AnimatedSprite2D
Frame-by-frame sprite animation using a SpriteFrames resource.
```gdscript
@onready var anim_sprite: AnimatedSprite2D = $AnimatedSprite2D

func _ready():
    anim_sprite.play("idle")

# Methods:
anim_sprite.play("run")
anim_sprite.stop()
anim_sprite.animation = "idle"    # set without playing
anim_sprite.frame = 0             # set specific frame
anim_sprite.speed_scale = 1.5
anim_sprite.flip_h = velocity.x < 0  # face direction of movement

# Signals:
anim_sprite.animation_finished.connect(func(): anim_sprite.play("idle"))
```

## Tween (code-driven animation)
Tweens are lightweight one-off animations driven entirely by code.
```gdscript
# Godot 4 tween API:
var tween = create_tween()
tween.tween_property(self, "position:x", 500.0, 1.0)  # animate x to 500 in 1 second

# Chain multiple tweens:
var tween = create_tween().set_trans(Tween.TRANS_BOUNCE).set_ease(Tween.EASE_OUT)
tween.tween_property($Sprite, "scale", Vector2(2, 2), 0.5)
tween.tween_property($Sprite, "scale", Vector2(1, 1), 0.5)

# Animate modulate (color/alpha):
var tween = create_tween()
tween.tween_property(self, "modulate:a", 0.0, 1.0)  # fade out over 1 second
tween.tween_callback(queue_free)                       # then remove

# Parallel tweens (run simultaneously):
var tween = create_tween().set_parallel(true)
tween.tween_property(self, "position", Vector2(200, 0), 1.0)
tween.tween_property(self, "rotation", PI, 1.0)

# Loop:
tween.set_loops(0)  # 0 = infinite loop
```

## Transition types for Tween
```
TRANS_LINEAR    — constant speed
TRANS_QUAD      — quadratic ease
TRANS_CUBIC     — cubic ease
TRANS_BOUNCE    — bounce effect
TRANS_ELASTIC   — spring/elastic
TRANS_SINE      — sine wave
TRANS_EXPO      — exponential
```
Ease types:
```
EASE_IN         — start slow
EASE_OUT        — end slow (most natural)
EASE_IN_OUT     — slow at both ends
EASE_OUT_IN
```

## Timer
```gdscript
# Via scene:
@onready var timer: Timer = $Timer
func _ready():
    timer.wait_time = 2.0
    timer.one_shot = true
    timer.timeout.connect(_on_timer_timeout)
    timer.start()

func _on_timer_timeout():
    print("2 seconds passed")

# Or await:
await get_tree().create_timer(2.0).timeout
print("2 seconds passed")
```

## Blending animations (state machine)
Use AnimationTree node with AnimationStateMachine for complex character animation.
```gdscript
@onready var anim_tree: AnimationTree = $AnimationTree
func _ready():
    anim_tree.active = true

func _physics_process(delta):
    anim_tree["parameters/blend_position"] = velocity.normalized()
    anim_tree["parameters/conditions/is_on_floor"] = is_on_floor()
```
