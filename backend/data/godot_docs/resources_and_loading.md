# Godot 4 — Resources and Asset Loading

## Loading textures and assets
```gdscript
# Synchronous (blocks main thread — ok for small files):
var texture = load("res://assets/sprites/player.png")
var scene = load("res://scenes/enemy.tscn")

# Preload (compile-time, for performance):
const PlayerTexture = preload("res://assets/sprites/player.png")
const EnemyScene = preload("res://scenes/enemy.tscn")
```

## CRITICAL: Texture assignment must happen in GDScript _ready()
Godot 4 requires .import files for textures to be available. These are created when
the project is first run, NOT at editor build time. So textures CANNOT be loaded
during the editor build phase — only inside `_ready()` at game runtime.

WRONG (may fail with "Cannot open file" during editor automation):
```
set_property("Sprite2D", "texture", "res://assets/player.png")
```

CORRECT — always load textures inside _ready() in a GDScript:
```gdscript
extends Sprite2D
func _ready():
    texture = load("res://assets/sprites/player.png")
```

Or with @onready:
```gdscript
extends CharacterBody2D
@onready var sprite: Sprite2D = $Sprite2D
func _ready():
    sprite.texture = load("res://assets/sprites/player.png")
```

## ImageTexture (fallback if .import not available)
```gdscript
var image = Image.load_from_file("res://assets/player.png")
var texture = ImageTexture.create_from_image(image)
sprite.texture = texture
```

## Resource types
```gdscript
# Texture2D — images (PNG, JPG, WebP, etc.)
var tex: Texture2D = load("res://icon.png")

# PackedScene — .tscn scene files
var scene: PackedScene = load("res://scenes/bullet.tscn")
var instance = scene.instantiate()

# AudioStream — .ogg, .wav, .mp3
var sfx: AudioStream = load("res://audio/jump.ogg")
$AudioStreamPlayer.stream = sfx
$AudioStreamPlayer.play()

# Font
var font: Font = load("res://fonts/pixel.ttf")
$Label.add_theme_font_override("font", font)

# SpriteFrames — for AnimatedSprite2D
var frames: SpriteFrames = load("res://animations/player.tres")
$AnimatedSprite2D.sprite_frames = frames
```

## Audio playback
```gdscript
# 2D positional audio (volume changes with distance):
@onready var sfx: AudioStreamPlayer2D = $AudioStreamPlayer2D
sfx.stream = load("res://audio/explosion.ogg")
sfx.play()

# Non-positional audio (UI sounds, music):
@onready var music: AudioStreamPlayer = $AudioStreamPlayer
music.stream = load("res://audio/theme.ogg")
music.volume_db = -10.0  # quieter
music.play()
```

## Saving and loading data (JSON)
```gdscript
# Save:
var data = {"score": 1000, "level": 3}
var file = FileAccess.open("user://save.json", FileAccess.WRITE)
file.store_string(JSON.stringify(data))
file.close()

# Load:
var file = FileAccess.open("user://save.json", FileAccess.READ)
var data = JSON.parse_string(file.get_as_text())
file.close()
var score = data["score"]
```

## user:// vs res://
- `res://` — read-only at runtime (game files), writable in editor only
- `user://` — writable at runtime (saves, configs, downloads)

## Checking if a file exists
```gdscript
if FileAccess.file_exists("user://save.json"):
    load_save_data()
if ResourceLoader.exists("res://scenes/player.tscn"):
    var scene = load("res://scenes/player.tscn")
```

## Autoload / Singleton (global data)
In Project Settings → Autoload, add a script as a singleton (e.g., "GameData"):
```gdscript
# game_data.gd (autoloaded as "GameData")
extends Node
var score: int = 0
var high_score: int = 0
signal score_changed(new_score: int)

func add_score(amount: int):
    score += amount
    score_changed.emit(score)
```
Access from any script:
```gdscript
GameData.add_score(10)
print(GameData.score)
```
