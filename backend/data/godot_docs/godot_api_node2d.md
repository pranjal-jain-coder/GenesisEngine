# Node2D

## Description

A 2D game object, with a transform (position, rotation, and scale). All 2D nodes, including physics objects and sprites, inherit from Node2D. Use Node2D as a parent node to move, scale and rotate children in a 2D project. Also gives control of the node's render order.

Note: Since both Node2D and Control inherit from CanvasItem, they share several concepts from the class such as the CanvasItem.z_index and CanvasItem.visible properties.


## Properties

| Type | Name | Default |
| --- | --- | --- |
| float | `global_rotation` |  |
| float | `global_rotation_degrees` |  |
| Vector2 | `global_scale` |  |
| float | `global_skew` |  |
| Transform2D | `global_transform` |  |
| Vector2 | `position` | Vector2(0,0) |
| float | `rotation` | 0.0 |
| float | `rotation_degrees` |  |
| Vector2 | `scale` | Vector2(1,1) |
| float | `skew` | 0.0 |
| Transform2D | `transform` |  |


## Methods

| Return | Name |
| --- | --- |
| float | `get_angle_to(point:Vector2)const` |
| Transform2D | `get_relative_transform_to_parent(parent:Node)const` |
| void | `global_translate(offset:Vector2)` |
| void | `look_at(point:Vector2)` |
| void | `move_local_x(delta:float, scaled:bool= false)` |
| void | `move_local_y(delta:float, scaled:bool= false)` |
| void | `rotate(radians:float)` |
| Vector2 | `to_global(local_point:Vector2)const` |
| Vector2 | `to_local(global_point:Vector2)const` |
| void | `translate(offset:Vector2)` |

