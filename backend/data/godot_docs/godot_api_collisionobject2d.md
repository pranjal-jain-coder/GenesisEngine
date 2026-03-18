# CollisionObject2D

## Description

Abstract base class for 2D physics objects. CollisionObject2D can hold any number of Shape2Ds for collision. Each shape must be assigned to a shape owner. Shape owners are not nodes and do not appear in the editor, but are accessible through code using the shape_owner_* methods.

Note: Only collisions between objects within the same canvas (Viewport canvas or CanvasLayer) are supported. The behavior of collisions between objects in different canvases is undefined.


## Properties

| Type | Name | Default |
| --- | --- | --- |
| int | `collision_mask` | 1 |
| float | `collision_priority` | 1.0 |
| DisableMode | `disable_mode` | 0 |
| bool | `input_pickable` | true |


## Methods

| Return | Name |
| --- | --- |
| void | `_mouse_enter()virtual` |
| void | `_mouse_exit()virtual` |
| void | `_mouse_shape_enter(shape_idx:int)virtual` |
| void | `_mouse_shape_exit(shape_idx:int)virtual` |
| int | `create_shape_owner(owner:Object)` |
| bool | `get_collision_layer_value(layer_number:int)const` |
| bool | `get_collision_mask_value(layer_number:int)const` |
| RID | `get_rid()const` |
| float | `get_shape_owner_one_way_collision_margin(owner_id:int)const` |
| PackedInt32Array | `get_shape_owners()` |
| bool | `is_shape_owner_disabled(owner_id:int)const` |
| bool | `is_shape_owner_one_way_collision_enabled(owner_id:int)const` |
| void | `remove_shape_owner(owner_id:int)` |
| void | `set_collision_layer_value(layer_number:int, value:bool)` |
| void | `set_collision_mask_value(layer_number:int, value:bool)` |
| int | `shape_find_owner(shape_index:int)const` |
| void | `shape_owner_add_shape(owner_id:int, shape:Shape2D)` |
| void | `shape_owner_clear_shapes(owner_id:int)` |
| Object | `shape_owner_get_owner(owner_id:int)const` |
| Shape2D | `shape_owner_get_shape(owner_id:int, shape_id:int)const` |
| int | `shape_owner_get_shape_count(owner_id:int)const` |
| int | `shape_owner_get_shape_index(owner_id:int, shape_id:int)const` |
| Transform2D | `shape_owner_get_transform(owner_id:int)const` |
| void | `shape_owner_remove_shape(owner_id:int, shape_id:int)` |
| void | `shape_owner_set_disabled(owner_id:int, disabled:bool)` |
| void | `shape_owner_set_one_way_collision(owner_id:int, enable:bool)` |
| void | `shape_owner_set_one_way_collision_margin(owner_id:int, margin:float)` |
| void | `shape_owner_set_transform(owner_id:int, transform:Transform2D)` |


## Signals


