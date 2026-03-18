# AnimatedSprite2D

## Description

AnimatedSprite2D is similar to the Sprite2D node, except it carries multiple textures as animation frames. Animations are created using a SpriteFrames resource, which allows you to import image files (or a folder containing said files) to provide the animation frames for the sprite. The SpriteFrames resource can be configured in the editor via the SpriteFrames bottom panel.


## Properties

| Type | Name | Default |
| --- | --- | --- |
| String | `autoplay` | "" |
| bool | `centered` | true |
| bool | `flip_h` | false |
| bool | `flip_v` | false |
| int | `frame` | 0 |
| float | `frame_progress` | 0.0 |
| Vector2 | `offset` | Vector2(0,0) |
| float | `speed_scale` | 1.0 |
| SpriteFrames | `sprite_frames` |  |


## Methods

| Return | Name |
| --- | --- |
| bool | `is_playing()const` |
| void | `pause()` |
| void | `play(name:StringName= &"", custom_speed:float= 1.0, from_end:bool= false)` |
| void | `play_backwards(name:StringName= &"")` |
| void | `set_frame_and_progress(frame:int, progress:float)` |
| void | `stop()` |


## Signals


