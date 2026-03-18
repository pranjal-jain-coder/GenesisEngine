# Sprite2D

## Description

A node that displays a 2D texture. The texture displayed can be a region from a larger atlas texture, or a frame from a sprite sheet animation.


## Properties

| Type | Name | Default |
| --- | --- | --- |
| bool | `flip_h` | false |
| bool | `flip_v` | false |
| int | `frame` | 0 |
| Vector2i | `frame_coords` | Vector2i(0,0) |
| int | `hframes` | 1 |
| Vector2 | `offset` | Vector2(0,0) |
| bool | `region_enabled` | false |
| bool | `region_filter_clip_enabled` | false |
| Rect2 | `region_rect` | Rect2(0,0,0,0) |
| Texture2D | `texture` |  |
| int | `vframes` | 1 |


## Methods

| Return | Name |
| --- | --- |
| bool | `is_pixel_opaque(pos:Vector2)const` |


## Signals


