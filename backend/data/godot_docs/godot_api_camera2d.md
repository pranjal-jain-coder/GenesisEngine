# Camera2D

## Description

Camera node for 2D scenes. It forces the screen (current layer) to scroll following this node. This makes it easier (and faster) to program scrollable scenes than manually changing the position of CanvasItem-based nodes.

Cameras register themselves in the nearest Viewport node (when ascending the tree). Only one camera can be active per viewport. If no viewport is available ascending the tree, the camera will register in the global viewport.

This node is intended to be a simple helper to get things going quickly, but more functionality may be desired to change how the camera works. To make your own custom camera node, inherit it from Node2D and change the transform of the canvas by setting Viewport.canvas_transform in Viewport (you can obtain the current Viewport by using Node.get_viewport()).

Note that the Camera2D node's Node2D.global_position doesn't represent the actual position of the screen, which may differ due to applied smoothing or limits. You can use get_screen_center_position() to get the real position. Same for the node's Node2D.global_rotation which may be different due to applied rotation smoothing. You can use get_screen_rotation() to get the current rotation of the screen.


## Properties

| Type | Name | Default |
| --- | --- | --- |
| Node | `custom_viewport` |  |
| float | `drag_bottom_margin` | 0.2 |
| bool | `drag_horizontal_enabled` | false |
| float | `drag_horizontal_offset` | 0.0 |
| float | `drag_left_margin` | 0.2 |
| float | `drag_right_margin` | 0.2 |
| float | `drag_top_margin` | 0.2 |
| bool | `drag_vertical_enabled` | false |
| float | `drag_vertical_offset` | 0.0 |
| bool | `editor_draw_drag_margin` | false |
| bool | `editor_draw_limits` | false |
| bool | `editor_draw_screen` | true |
| bool | `enabled` | true |
| bool | `ignore_rotation` | true |
| int | `limit_bottom` | 10000000 |
| bool | `limit_enabled` | true |
| int | `limit_left` | -10000000 |
| int | `limit_right` | 10000000 |
| bool | `limit_smoothed` | false |
| int | `limit_top` | -10000000 |
| Vector2 | `offset` | Vector2(0,0) |
| bool | `position_smoothing_enabled` | false |
| float | `position_smoothing_speed` | 5.0 |
| Camera2DProcessCallback | `process_callback` | 1 |
| bool | `rotation_smoothing_enabled` | false |
| float | `rotation_smoothing_speed` | 5.0 |
| Vector2 | `zoom` | Vector2(1,1) |


## Methods

| Return | Name |
| --- | --- |
| void | `force_update_scroll()` |
| float | `get_drag_margin(margin:Side)const` |
| int | `get_limit(margin:Side)const` |
| Vector2 | `get_screen_center_position()const` |
| float | `get_screen_rotation()const` |
| Vector2 | `get_target_position()const` |
| bool | `is_current()const` |
| void | `make_current()` |
| void | `reset_smoothing()` |
| void | `set_drag_margin(margin:Side, drag_margin:float)` |
| void | `set_limit(margin:Side, limit:int)` |

