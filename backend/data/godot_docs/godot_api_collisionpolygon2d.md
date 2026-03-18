# CollisionPolygon2D

## Description

A node that provides a polygon shape to a CollisionObject2D parent and allows it to be edited. The polygon can be concave or convex. This can give a detection shape to an Area2D, turn a PhysicsBody2D into a solid object, or give a hollow shape to a StaticBody2D.

Warning: A non-uniformly scaled CollisionPolygon2D will likely not behave as expected. Make sure to keep its scale the same on all axes and adjust its polygon instead.


## Properties

| Type | Name | Default |
| --- | --- | --- |
| bool | `disabled` | false |
| bool | `one_way_collision` | false |
| float | `one_way_collision_margin` | 1.0 |
| PackedVector2Array | `polygon` | PackedVector2Array() |

