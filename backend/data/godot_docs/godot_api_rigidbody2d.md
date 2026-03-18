# RigidBody2D

## Description

RigidBody2D implements full 2D physics. It cannot be controlled directly, instead, you must apply forces to it (gravity, impulses, etc.), and the physics simulation will calculate the resulting movement, rotation, react to collisions, and affect other physics bodies in its path.

The body's behavior can be adjusted via lock_rotation, freeze, and freeze_mode. By changing various properties of the object, such as mass, you can control how the physics simulation acts on it.

A rigid body will always maintain its shape and size, even when forces are applied to it. It is useful for objects that can be interacted with in an environment, such as a tree that can be knocked over or a stack of crates that can be pushed around.

If you need to directly affect the body, prefer _integrate_forces() as it allows you to directly access the physics state.

If you need to override the default physics behavior, you can write a custom force integration function. See custom_integrator.

Note: Changing the 2D transform or linear_velocity of a RigidBody2D very often may lead to some unpredictable behaviors. This also happens when a RigidBody2D is the descendant of a constantly moving node, like another RigidBody2D, as that will cause its global transform to be set whenever its ancestor moves.


## Properties

| Type | Name | Default |
| --- | --- | --- |
| DampMode | `angular_damp_mode` | 0 |
| float | `angular_velocity` | 0.0 |
| bool | `can_sleep` | true |
| Vector2 | `center_of_mass` | Vector2(0,0) |
| CenterOfMassMode | `center_of_mass_mode` | 0 |
| Vector2 | `constant_force` | Vector2(0,0) |
| float | `constant_torque` | 0.0 |
| bool | `contact_monitor` | false |
| CCDMode | `continuous_cd` | 0 |
| bool | `custom_integrator` | false |
| bool | `freeze` | false |
| FreezeMode | `freeze_mode` | 0 |
| float | `gravity_scale` | 1.0 |
| float | `inertia` | 0.0 |
| float | `linear_damp` | 0.0 |
| DampMode | `linear_damp_mode` | 0 |
| Vector2 | `linear_velocity` | Vector2(0,0) |
| bool | `lock_rotation` | false |
| float | `mass` | 1.0 |
| int | `max_contacts_reported` | 0 |
| PhysicsMaterial | `physics_material_override` |  |
| bool | `sleeping` | false |


## Methods

| Return | Name |
| --- | --- |
| void | `add_constant_central_force(force:Vector2)` |
| void | `add_constant_force(force:Vector2, position:Vector2= Vector2(0, 0))` |
| void | `add_constant_torque(torque:float)` |
| void | `apply_central_force(force:Vector2)` |
| void | `apply_central_impulse(impulse:Vector2= Vector2(0, 0))` |
| void | `apply_force(force:Vector2, position:Vector2= Vector2(0, 0))` |
| void | `apply_impulse(impulse:Vector2, position:Vector2= Vector2(0, 0))` |
| void | `apply_torque(torque:float)` |
| void | `apply_torque_impulse(torque:float)` |
| Array[Node2D] | `get_colliding_bodies()const` |
| int | `get_contact_count()const` |
| void | `set_axis_velocity(axis_velocity:Vector2)` |


## Signals


