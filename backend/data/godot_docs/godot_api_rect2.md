# Rect2

## Description

The Rect2 built-in Variant type represents an axis-aligned rectangle in a 2D space. It is defined by its position and size, which are Vector2. It is frequently used for fast overlap tests (see intersects()). Although Rect2 itself is axis-aligned, it can be combined with Transform2D to represent a rotated or skewed rectangle.

For integer coordinates, use Rect2i. The 3D equivalent to Rect2 is AABB.

Note: Negative values for size are not supported. With negative size, most Rect2 methods do not work correctly. Use abs() to get an equivalent Rect2 with a non-negative size.

Note: In a boolean context, a Rect2 evaluates to false if both position and size are zero (equal to Vector2.ZERO). Otherwise, it always evaluates to true.


## Properties

| Type | Name | Default |
| --- | --- | --- |
| Vector2 | `position` | Vector2(0,0) |
| Vector2 | `size` | Vector2(0,0) |


## Methods

| Return | Name |
| --- | --- |
| bool | `encloses(b:Rect2)const` |
| Rect2 | `expand(to:Vector2)const` |
| float | `get_area()const` |
| Vector2 | `get_center()const` |
| Vector2 | `get_support(direction:Vector2)const` |
| Rect2 | `grow(amount:float)const` |
| Rect2 | `grow_individual(left:float, top:float, right:float, bottom:float)const` |
| Rect2 | `grow_side(side:int, amount:float)const` |
| bool | `has_area()const` |
| bool | `has_point(point:Vector2)const` |
| Rect2 | `intersection(b:Rect2)const` |
| bool | `intersects(b:Rect2, include_borders:bool= false)const` |
| bool | `is_equal_approx(rect:Rect2)const` |
| bool | `is_finite()const` |
| Rect2 | `merge(b:Rect2)const` |

