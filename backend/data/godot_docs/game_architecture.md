# Godot 4 — Complete Game Architecture

## Required scene tree for a complete 2D game
```
Main (Node2D)  ← set as main scene via set_main_scene()
├── Background (Sprite2D or ParallaxBackground)
├── TileMap  ← for tile-based levels (optional)
├── Player (instance of res://scenes/player.tscn)
├── Enemies (Node2D container)
│   └── Enemy1 (instance of res://scenes/enemy.tscn)
├── Collectibles (Node2D container)
├── Camera2D  ← child of Player OR child of Main with follow script
├── HUD (CanvasLayer)          ← MUST be CanvasLayer to stay fixed on screen
│   ├── ScoreLabel (Label)
│   ├── HealthBar (ProgressBar)
│   └── GameOverScreen (Control, initially hidden)
│       └── RestartButton (Button)
```

## GameManager autoload pattern
Register in Project Settings → Autoload, or via execute_godot_script:
```gdscript
ProjectSettings.set_setting("autoload/GameManager", "*res://scripts/game_manager.gd")
ProjectSettings.save()
```
The `*` prefix makes Godot treat it as a singleton Node (available everywhere as `GameManager`).

```gdscript
# scripts/game_manager.gd
extends Node

signal score_changed(new_score: int)
signal lives_changed(new_lives: int)
signal game_over

var score: int = 0
var lives: int = 3

func add_score(amount: int) -> void:
    score += amount
    score_changed.emit(score)

func lose_life() -> void:
    lives -= 1
    lives_changed.emit(lives)
    if lives <= 0:
        game_over.emit()
        get_tree().paused = true

func restart() -> void:
    score = 0
    lives = 3
    get_tree().paused = false
    get_tree().reload_current_scene()
```

## HUD connected to GameManager signals
```gdscript
# scripts/hud.gd
extends CanvasLayer

@onready var score_label: Label = $ScoreLabel
@onready var health_bar: ProgressBar = $HealthBar
@onready var game_over_screen: Control = $GameOverScreen

func _ready() -> void:
    GameManager.score_changed.connect(_on_score_changed)
    GameManager.lives_changed.connect(_on_lives_changed)
    GameManager.game_over.connect(_on_game_over)
    game_over_screen.visible = false
    $GameOverScreen/RestartButton.pressed.connect(GameManager.restart)

func _on_score_changed(new_score: int) -> void:
    score_label.text = "Score: %d" % new_score

func _on_lives_changed(new_lives: int) -> void:
    health_bar.value = new_lives

func _on_game_over() -> void:
    game_over_screen.visible = true
```

## Player scene structure
```
Player (CharacterBody2D)   ← root node, collision_layer = 1
├── Sprite2D               ← texture loaded in _ready() via load()
├── CollisionShape2D       ← shape MUST be set (CapsuleShape2D for humanoids)
└── Camera2D               ← optional; set position_smoothing_enabled = true
```

## Player script template (Godot 4.x)
```gdscript
extends CharacterBody2D

const SPEED := 200.0
const JUMP_VELOCITY := -400.0
@export var max_health: int = 3
var health: int = max_health

@onready var sprite: Sprite2D = $Sprite2D

func _ready() -> void:
    sprite.texture = load("res://assets/sprites/player.png")
    add_to_group("player")
    collision_layer = 1
    collision_mask = 8  # detect environment/platforms

func _physics_process(delta: float) -> void:
    if not is_on_floor():
        velocity += get_gravity() * delta
    if Input.is_action_just_pressed("ui_accept") and is_on_floor():
        velocity.y = JUMP_VELOCITY
    var direction := Input.get_axis("ui_left", "ui_right")
    velocity.x = direction * SPEED if direction else move_toward(velocity.x, 0, SPEED)
    sprite.flip_h = velocity.x < 0
    move_and_slide()

func take_damage(amount: int) -> void:
    health -= amount
    if health <= 0:
        GameManager.lose_life()
        queue_free()
```

## Enemy script template
```gdscript
extends CharacterBody2D

const SPEED := 80.0
var direction := 1

@onready var sprite: Sprite2D = $Sprite2D

func _ready() -> void:
    sprite.texture = load("res://assets/sprites/enemy.png")
    collision_layer = 2
    collision_mask = 9  # detect environment (8) + player (1)

func _physics_process(delta: float) -> void:
    velocity.x = direction * SPEED
    if not is_on_floor():
        velocity += get_gravity() * delta
    move_and_slide()
    # Reverse direction on wall collision
    if is_on_wall():
        direction *= -1
        sprite.flip_h = direction < 0

func _on_body_entered(body: Node2D) -> void:
    if body.is_in_group("player"):
        body.take_damage(1)
```

## Main scene composition (use instance_scene tool)
```
# Steps for the AI to compose the main scene:
1. create_scene("res://scenes/main.tscn", "Node2D")
2. instance_scene("res://scenes/player.tscn", ".", "Player")
3. instance_scene("res://scenes/enemy.tscn", ".", "Enemy1")
4. add_node(".", "CanvasLayer", "HUD")
5. attach_script("HUD", "res://scripts/hud.gd")
6. add_node(".", "Camera2D", "Camera2D")
7. create_script("res://scripts/main.gd", <follows player with Camera2D>)
8. attach_script(".", "res://scripts/main.gd")
9. save_scene()
10. set_main_scene("res://scenes/main.tscn")
```

## Camera2D following the player
```gdscript
# Simplest approach: make Camera2D a direct child of the Player scene.
# In player.tscn, add Camera2D as a child node, then configure:
#   position_smoothing_enabled = true
#   position_smoothing_speed = 5.0
#   limit_left = 0 / limit_right = 3200 (world width) etc.
```

## Collision layer conventions
```gdscript
# Layer 1 (value 1):  Player body
# Layer 2 (value 2):  Enemies
# Layer 4 (value 4):  Collectibles / pickups
# Layer 8 (value 8):  Environment / platforms (StaticBody2D)

# In _ready():
collision_layer = 1   # what THIS body IS on
collision_mask  = 8   # what THIS body DETECTS (e.g. platforms)
```

## Area2D for collectibles
```gdscript
extends Area2D  # collision_layer = 4, collision_mask = 1

func _ready() -> void:
    body_entered.connect(_on_body_entered)

func _on_body_entered(body: Node2D) -> void:
    if body.is_in_group("player"):
        GameManager.add_score(10)
        queue_free()
```

## Minimum viable complete game checklist
- [ ] player.tscn: CharacterBody2D, Sprite2D, CollisionShape2D (shape set), movement+health script
- [ ] enemy.tscn: CharacterBody2D or Area2D, Sprite2D, behavior script
- [ ] main.tscn: player instanced, enemies spawned, Camera2D, HUD CanvasLayer
- [ ] game_manager.gd registered as Autoload with score/lives/game_over/restart
- [ ] hud.gd connected to GameManager signals, CanvasLayer parent
- [ ] set_main_scene("res://scenes/main.tscn") called
- [ ] Collision layers consistent across all scenes
- [ ] Game-over triggers on player death, restart working via RestartButton
