# Godot 4 — Common Game Patterns

## Health system
```gdscript
extends CharacterBody2D

@export var max_health: int = 100
var health: int = max_health
signal health_changed(new_hp: int)
signal died

func take_damage(amount: int) -> void:
    health -= amount
    health_changed.emit(health)
    if health <= 0:
        die()

func heal(amount: int) -> void:
    health = min(health + amount, max_health)
    health_changed.emit(health)

func die() -> void:
    died.emit()
    queue_free()
```

## Enemy AI — follow player
```gdscript
extends CharacterBody2D

const SPEED := 80.0
var player: Node2D = null

func _ready():
    player = get_tree().get_first_node_in_group("player")

func _physics_process(delta: float) -> void:
    if player == null:
        return
    var direction = (player.global_position - global_position).normalized()
    velocity = direction * SPEED
    move_and_slide()
```

## Enemy AI — patrol (left-right)
```gdscript
extends CharacterBody2D

const SPEED := 60.0
var direction := 1

func _physics_process(delta: float) -> void:
    if not is_on_floor():
        velocity += get_gravity() * delta
    velocity.x = direction * SPEED
    move_and_slide()
    if is_on_wall():
        direction *= -1  # reverse on wall hit
    $Sprite2D.flip_h = direction < 0
```

## Bullet / projectile pattern
```gdscript
# bullet.gd
extends Area2D

const SPEED := 400.0
var direction := Vector2.RIGHT

func _ready():
    body_entered.connect(_on_body_entered)

func _process(delta: float) -> void:
    position += direction * SPEED * delta

func _on_body_entered(body: Node) -> void:
    if body.has_method("take_damage"):
        body.take_damage(10)
    queue_free()
```

Spawning a bullet from player:
```gdscript
const BulletScene = preload("res://scenes/bullet.tscn")

func shoot():
    var b = BulletScene.instantiate()
    b.global_position = $Muzzle.global_position
    b.direction = Vector2.RIGHT if not $Sprite2D.flip_h else Vector2.LEFT
    get_parent().add_child(b)
```

## Coin / pickup collectible
```gdscript
extends Area2D

signal collected(value: int)
@export var value: int = 1

func _ready():
    body_entered.connect(_on_body_entered)

func _on_body_entered(body: Node) -> void:
    if body.is_in_group("player"):
        collected.emit(value)
        queue_free()
```

## Score manager (autoload pattern)
```gdscript
# score_manager.gd — added as Autoload "ScoreManager"
extends Node
var score: int = 0
signal score_changed(new_score: int)

func add(amount: int) -> void:
    score += amount
    score_changed.emit(score)

func reset() -> void:
    score = 0
    score_changed.emit(score)
```

## Game over / restart
```gdscript
func game_over():
    get_tree().paused = true
    $CanvasLayer/GameOverScreen.visible = true

func restart():
    get_tree().paused = false
    get_tree().reload_current_scene()
```

## Spawner / wave system
```gdscript
extends Node2D

const EnemyScene = preload("res://scenes/enemy.tscn")
@export var spawn_interval: float = 2.0
var timer: float = 0.0

func _process(delta: float) -> void:
    timer += delta
    if timer >= spawn_interval:
        timer = 0.0
        spawn_enemy()

func spawn_enemy() -> void:
    var e = EnemyScene.instantiate()
    e.global_position = $SpawnPoints.get_child(
        randi() % $SpawnPoints.get_child_count()
    ).global_position
    add_child(e)
```

## Singleton global state via Autoload
In Project Settings → Autoload:
- Script: `res://scripts/game_state.gd`
- Name: `GameState`

```gdscript
# game_state.gd
extends Node
var score: int = 0
var lives: int = 3
var current_level: int = 1
```
Access anywhere:
```gdscript
GameState.score += 10
```

## State machine (simple)
```gdscript
extends CharacterBody2D
enum State { IDLE, RUNNING, JUMPING, DEAD }
var state := State.IDLE

func _physics_process(delta):
    match state:
        State.IDLE:
            $AnimatedSprite2D.play("idle")
            if Input.get_axis("move_left", "move_right") != 0:
                state = State.RUNNING
        State.RUNNING:
            $AnimatedSprite2D.play("run")
            var dir = Input.get_axis("move_left", "move_right")
            velocity.x = dir * 200.0
            if dir == 0:
                state = State.IDLE
        State.JUMPING:
            $AnimatedSprite2D.play("jump")
            if is_on_floor():
                state = State.IDLE
    move_and_slide()
```

## Camera shake
```gdscript
extends Camera2D
var shake_amount: float = 0.0

func shake(amount: float, duration: float):
    shake_amount = amount
    var tween = create_tween()
    tween.tween_property(self, "shake_amount", 0.0, duration)

func _process(delta):
    if shake_amount > 0:
        offset = Vector2(
            randf_range(-shake_amount, shake_amount),
            randf_range(-shake_amount, shake_amount)
        )
    else:
        offset = Vector2.ZERO
```
