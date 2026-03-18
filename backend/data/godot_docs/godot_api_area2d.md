# Area2D

## Description

Area2D is a region of 2D space defined by one or multiple CollisionShape2D or CollisionPolygon2D child nodes. It detects when other CollisionObject2Ds enter or exit it, and it also keeps track of which collision objects haven't exited it yet (i.e. which one are overlapping it).

This node can also locally alter or override physics parameters (gravity, damping) and route audio to custom audio buses.

Note: Areas and bodies created with PhysicsServer2D might not interact as expected with Area2Ds, and might not emit signals or track objects correctly.


## Properties

| Type | Name | Default |
| --- | --- | --- |
| SpaceOverride | `angular_damp_space_override` | 0 |
| StringName | `audio_bus_name` | &"Master" |
| bool | `audio_bus_override` | false |
| float | `gravity` | 980.0 |
| Vector2 | `gravity_direction` | Vector2(0,1) |
| bool | `gravity_point` | false |
| Vector2 | `gravity_point_center` | Vector2(0,1) |
| float | `gravity_point_unit_distance` | 0.0 |
| SpaceOverride | `gravity_space_override` | 0 |
| float | `linear_damp` | 0.1 |
| SpaceOverride | `linear_damp_space_override` | 0 |
| bool | `monitorable` | true |
| bool | `monitoring` | true |
| int | `priority` | 0 |


## Methods

| Return | Name |
| --- | --- |
| Array[Node2D] | `get_overlapping_bodies()const` |
| bool | `has_overlapping_areas()const` |
| bool | `has_overlapping_bodies()const` |
| bool | `overlaps_area(area:Node)const` |
| bool | `overlaps_body(body:Node)const` |


## Signals


