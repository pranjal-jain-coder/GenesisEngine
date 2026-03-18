# StaticBody2D

## Description

A static 2D physics body. It can't be moved by external forces or contacts, but can be moved manually by other means such as code, AnimationMixers (with AnimationMixer.callback_mode_process set to AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_PHYSICS), and RemoteTransform2D.

When StaticBody2D is moved, it is teleported to its new position without affecting other physics bodies in its path. If this is not desired, use AnimatableBody2D instead.

StaticBody2D is useful for completely static objects like floors and walls, as well as moving surfaces like conveyor belts and circular revolving platforms (by using constant_linear_velocity and constant_angular_velocity).


## Properties

| Type | Name | Default |
| --- | --- | --- |
| Vector2 | `constant_linear_velocity` | Vector2(0,0) |
| PhysicsMaterial | `physics_material_override` |  |

