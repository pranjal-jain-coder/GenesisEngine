# CharacterBody2D

## Description

CharacterBody2D is a specialized class for physics bodies that are meant to be user-controlled. They are not affected by physics at all, but they affect other physics bodies in their path. They are mainly used to provide high-level API to move objects with wall and slope detection (move_and_slide() method) in addition to the general collision detection provided by PhysicsBody2D.move_and_collide(). This makes it useful for highly configurable physics bodies that must move in specific ways and collide with the world, as is often the case with user-controlled characters.

For game objects that don't require complex movement or collision detection, such as moving platforms, AnimatableBody2D is simpler to configure.


## Properties

| Type | Name | Default |
| --- | --- | --- |
| bool | `floor_constant_speed` | false |
| float | `floor_max_angle` | 0.7853982 |
| float | `floor_snap_length` | 1.0 |
| bool | `floor_stop_on_slope` | true |
| int | `max_slides` | 4 |
| MotionMode | `motion_mode` | 0 |
| int | `platform_floor_layers` | 4294967295 |
| PlatformOnLeave | `platform_on_leave` | 0 |
| int | `platform_wall_layers` | 0 |
| float | `safe_margin` | 0.08 |
| bool | `slide_on_ceiling` | true |
| Vector2 | `up_direction` | Vector2(0,-1) |
| Vector2 | `velocity` | Vector2(0,0) |
| float | `wall_min_slide_angle` | 0.2617994 |


## Methods

| Return | Name |
| --- | --- |
| float | `get_floor_angle(up_direction:Vector2= Vector2(0, -1))const` |
| Vector2 | `get_floor_normal()const` |
| Vector2 | `get_last_motion()const` |
| KinematicCollision2D | `get_last_slide_collision()` |
| Vector2 | `get_platform_velocity()const` |
| Vector2 | `get_position_delta()const` |
| Vector2 | `get_real_velocity()const` |
| KinematicCollision2D | `get_slide_collision(slide_idx:int)` |
| int | `get_slide_collision_count()const` |
| Vector2 | `get_wall_normal()const` |
| bool | `is_on_ceiling()const` |
| bool | `is_on_ceiling_only()const` |
| bool | `is_on_floor()const` |
| bool | `is_on_floor_only()const` |
| bool | `is_on_wall()const` |
| bool | `is_on_wall_only()const` |
| bool | `move_and_slide()` |

