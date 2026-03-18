# Godot 4 UI Controls Reference

## Control Basics
All UI nodes must inherit from `Control`.
Use anchors and margins for resolution-independent layouts.

**Anchors & Layouts:**
- Full Screen: Anchor Preset → Full Rect
- Top Right: Anchor Preset → Top Right
- Center: Anchor Preset → Center

## Containers (Use These!)
Never place controls manually. Always use containers to manage layout.

1.  **VBoxContainer**: Stacks children vertically.
2.  **HBoxContainer**: Stacks children horizontally.
3.  **GridContainer**: Arranges children in a grid.
4.  **MarginContainer**: Adds padding around content.
5.  **CenterContainer**: Centers content.

**Example Structure (Main Menu):**
- Control (Full Rect) - "MainMenu"
  - TextureRect (Full Rect) - "Background"
  - CenterContainer (Full Rect) - "CenterBox"
    - VBoxContainer (Separation: 20) - "MenuButtons"
      - Label (Title: "Space Adventure")
      - Button (Text: "Start Game")
      - Button (Text: "Exit")

## Common Controls

**Label:**
- `text`: String content.
- `horizontal_alignment`: Left, Center, Right.
- `vertical_alignment`: Top, Center, Bottom.
- Use `LabelSettings` resource (not Theme overrides) for quick styling (font, color, shadow).

**Button:**
- `text`: Label on button.
- `pressed`: Signal when clicked.
- `icon`: Texture for button image.

**TextureRect:**
- Use for UI images (health bars background, avatars).
- Not `Sprite2D`! Use `TextureRect` inside `Control` nodes.

**ProgressBar:**
- `value`: 0-100 (float).
- `max_value`: 100.
- `step`: 1.

## Theme Overrides
To change fonts or colors:
1. Select node.
2. Inspector → Theme Overrides.
3. Colors → `font_color`.
4. Fonts → `font`.
5. Font Sizes → `font_size`.

## Signals
Connect buttons to scripts:

```gdscript
extends Control

func _on_start_button_pressed():
    get_tree().change_scene_to_file("res://scenes/level1.tscn")

func _on_exit_button_pressed():
    get_tree().quit()
```

## Integrating HUD with Game Logic
The HUD should listen to a `GameManager` autoload, not the player directly.

```gdscript
# hud.gd
extends CanvasLayer

@onready var score_label = $ScoreLabel
@onready var health_bar = $HealthBar

func _ready():
    # Connect to global signals
    GameManager.score_changed.connect(_on_score_changed)
    GameManager.health_changed.connect(_on_health_changed)
    
    # Initialize values
    score_label.text = "Score: " + str(GameManager.score)
    health_bar.value = GameManager.health

func _on_score_changed(new_score):
    score_label.text = "Score: " + str(new_score)

func _on_health_changed(new_health):
    health_bar.value = new_health
```
