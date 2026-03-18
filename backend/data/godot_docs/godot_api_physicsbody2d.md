# PhysicsBody2D

## Description

PhysicsBody2D is an abstract base class for 2D game objects affected by physics. All 2D physics bodies inherit from it.


## Properties

| Type | Name | Default |
| --- | --- | --- |


## Methods

| Return | Name |
| --- | --- |
| Array[PhysicsBody2D] | `get_collision_exceptions()` |
| Vector2 | `get_gravity()const` |
| KinematicCollision2D | `move_and_collide(motion:Vector2, test_only:bool= false, safe_margin:float= 0.08, recovery_as_collision:bool= false)` |
| void | `remove_collision_exception_with(body:Node)` |
| bool | `test_move(from:Transform2D, motion:Vector2, collision:KinematicCollision2D= null, safe_margin:float= 0.08, recovery_as_collision:bool= false)` |

