# Polygon2D

## Description

A Polygon2D is defined by a set of points. Each point is connected to the next, with the final point being connected to the first, resulting in a closed polygon. Polygon2Ds can be filled with color (solid or gradient) or filled with a given texture.


## Properties

| Type | Name | Default |
| --- | --- | --- |
| Color | `color` | Color(1,1,1,1) |
| int | `internal_vertex_count` | 0 |
| float | `invert_border` | 100.0 |
| bool | `invert_enabled` | false |
| Vector2 | `offset` | Vector2(0,0) |
| PackedVector2Array | `polygon` | PackedVector2Array() |
| Array | `polygons` | [] |
| NodePath | `skeleton` | NodePath("") |
| Texture2D | `texture` |  |
| Vector2 | `texture_offset` | Vector2(0,0) |
| float | `texture_rotation` | 0.0 |
| Vector2 | `texture_scale` | Vector2(1,1) |
| PackedVector2Array | `uv` | PackedVector2Array() |
| PackedColorArray | `vertex_colors` | PackedColorArray() |


## Methods

| Return | Name |
| --- | --- |
| void | `clear_bones()` |
| void | `erase_bone(index:int)` |
| int | `get_bone_count()const` |
| NodePath | `get_bone_path(index:int)const` |
| PackedFloat32Array | `get_bone_weights(index:int)const` |
| void | `set_bone_path(index:int, path:NodePath)` |
| void | `set_bone_weights(index:int, weights:PackedFloat32Array)` |

