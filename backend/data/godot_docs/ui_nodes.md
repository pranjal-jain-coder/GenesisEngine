# Godot 4 — UI Nodes (Control nodes)

## Overview
UI nodes extend Control (not Node2D). They use anchors and offsets for layout.
Always put UI inside a CanvasLayer to render it on top of everything.

## CanvasLayer (HUD container)
```gdscript
# Add as a child of root, put UI nodes inside it.
# layer = 1 means above the game world
extends CanvasLayer
```

## Label
```gdscript
@onready var label: Label = $Label
func _ready():
    label.text = "Score: 0"
    label.add_theme_font_size_override("font_size", 32)
    label.add_theme_color_override("font_color", Color.WHITE)

func update_score(score: int):
    label.text = "Score: " + str(score)
```

## Button
```gdscript
@onready var btn: Button = $Button
func _ready():
    btn.text = "Start Game"
    btn.pressed.connect(_on_button_pressed)

func _on_button_pressed():
    get_tree().change_scene_to_file("res://scenes/game.tscn")
```

## ProgressBar / HealthBar
```gdscript
@onready var health_bar: ProgressBar = $HealthBar
func _ready():
    health_bar.min_value = 0
    health_bar.max_value = 100
    health_bar.value = 100

func take_damage(amount: int):
    health_bar.value -= amount
```

## TextureRect (display an image in UI)
```gdscript
@onready var icon: TextureRect = $TextureRect
func _ready():
    icon.texture = load("res://assets/icons/coin.png")
    icon.expand_mode = TextureRect.EXPAND_FIT_WIDTH
```

## VBoxContainer / HBoxContainer (layout)
```gdscript
# Automatically arranges children vertically (V) or horizontally (H)
# Add children in the editor or via:
var label = Label.new()
label.text = "Item"
$VBoxContainer.add_child(label)
```

## Panel (background box)
```gdscript
# Use as a visible background for HUD sections
# Style via theme or:
var style = StyleBoxFlat.new()
style.bg_color = Color(0, 0, 0, 0.5)  # semi-transparent black
$Panel.add_theme_stylebox_override("panel", style)
```

## Anchors and Layout
```gdscript
# Full-rect (fill parent):
$Control.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
# Center:
$Control.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
# Top-left corner:
$Control.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
# Bottom-right:
$Control.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_RIGHT)
```

## Showing and hiding UI
```gdscript
$HUD.visible = true
$HUD.visible = false
$HUD.hide()
$HUD.show()
```

## Typical HUD structure
```
CanvasLayer
  └── VBoxContainer (top-left anchor)
       ├── Label (score)
       └── ProgressBar (health)
```

## RichTextLabel (formatted text)
```gdscript
@onready var rtl: RichTextLabel = $RichTextLabel
func _ready():
    rtl.bbcode_enabled = true
    rtl.text = "[b]Bold[/b] and [color=red]red[/color] text"
```

## LineEdit (text input)
```gdscript
@onready var input: LineEdit = $LineEdit
func _ready():
    input.placeholder_text = "Enter name..."
    input.text_submitted.connect(_on_name_submitted)

func _on_name_submitted(text: String):
    player_name = text
```

## UI scene pattern (main menu example)
```gdscript
extends Control  # root of a menu scene

func _ready():
    $VBoxContainer/StartButton.pressed.connect(_on_start)
    $VBoxContainer/QuitButton.pressed.connect(_on_quit)

func _on_start():
    get_tree().change_scene_to_file("res://scenes/game.tscn")

func _on_quit():
    get_tree().quit()
```
