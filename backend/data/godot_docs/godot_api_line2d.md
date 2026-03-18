# Line2D

## Description

This node draws a 2D polyline, i.e. a shape consisting of several points connected by segments. Line2D is not a mathematical polyline, i.e. the segments are not infinitely thin. It is intended for rendering and it can be colored and optionally textured.

Warning: Certain configurations may be impossible to draw nicely, such as very sharp angles. In these situations, the node uses fallback drawing logic to look decent.

Note: Line2D is drawn using a 2D mesh.


## Properties

| Type | Name | Default |
| --- | --- | --- |
| LineCapMode | `begin_cap_mode` | 0 |
| bool | `closed` | false |
| Color | `default_color` | Color(1,1,1,1) |
| LineCapMode | `end_cap_mode` | 0 |
| Gradient | `gradient` |  |
| LineJointMode | `joint_mode` | 0 |
| PackedVector2Array | `points` | PackedVector2Array() |
| int | `round_precision` | 8 |
| float | `sharp_limit` | 2.0 |
| Texture2D | `texture` |  |
| LineTextureMode | `texture_mode` | 0 |
| float | `width` | 10.0 |
| Curve | `width_curve` |  |


## Methods

| Return | Name |
| --- | --- |
| void | `clear_points()` |
| int | `get_point_count()const` |
| Vector2 | `get_point_position(index:int)const` |
| void | `remove_point(index:int)` |
| void | `set_point_position(index:int, position:Vector2)` |

