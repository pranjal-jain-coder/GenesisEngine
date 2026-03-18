# Vector2

## Description

A 2-element structure that can be used to represent 2D coordinates or any other pair of numeric values.

It uses floating-point coordinates. By default, these floating-point values use 32-bit precision, unlike float which is always 64-bit. If double precision is needed, compile the engine with the option precision=double.

See Vector2i for its integer counterpart.

Note: In a boolean context, a Vector2 will evaluate to false if it's equal to Vector2(0, 0). Otherwise, a Vector2 will always evaluate to true.


## Properties

| Type | Name | Default |
| --- | --- | --- |
| float | `y` | 0.0 |


## Methods

| Return | Name |
| --- | --- |
| float | `angle()const` |
| float | `angle_to(to:Vector2)const` |
| float | `angle_to_point(to:Vector2)const` |
| float | `aspect()const` |
| Vector2 | `bezier_derivative(control_1:Vector2, control_2:Vector2, end:Vector2, t:float)const` |
| Vector2 | `bezier_interpolate(control_1:Vector2, control_2:Vector2, end:Vector2, t:float)const` |
| Vector2 | `bounce(n:Vector2)const` |
| Vector2 | `ceil()const` |
| Vector2 | `clamp(min:Vector2, max:Vector2)const` |
| Vector2 | `clampf(min:float, max:float)const` |
| float | `cross(with:Vector2)const` |
| Vector2 | `cubic_interpolate(b:Vector2, pre_a:Vector2, post_b:Vector2, weight:float)const` |
| Vector2 | `cubic_interpolate_in_time(b:Vector2, pre_a:Vector2, post_b:Vector2, weight:float, b_t:float, pre_a_t:float, post_b_t:float)const` |
| Vector2 | `direction_to(to:Vector2)const` |
| float | `distance_squared_to(to:Vector2)const` |
| float | `distance_to(to:Vector2)const` |
| float | `dot(with:Vector2)const` |
| Vector2 | `floor()const` |
| Vector2 | `from_angle(angle:float)static` |
| bool | `is_equal_approx(to:Vector2)const` |
| bool | `is_finite()const` |
| bool | `is_normalized()const` |
| bool | `is_zero_approx()const` |
| float | `length()const` |
| float | `length_squared()const` |
| Vector2 | `lerp(to:Vector2, weight:float)const` |
| Vector2 | `limit_length(length:float= 1.0)const` |
| Vector2 | `max(with:Vector2)const` |
| int | `max_axis_index()const` |
| Vector2 | `maxf(with:float)const` |
| Vector2 | `min(with:Vector2)const` |
| int | `min_axis_index()const` |
| Vector2 | `minf(with:float)const` |
| Vector2 | `move_toward(to:Vector2, delta:float)const` |
| Vector2 | `normalized()const` |
| Vector2 | `orthogonal()const` |
| Vector2 | `posmod(mod:float)const` |
| Vector2 | `posmodv(modv:Vector2)const` |
| Vector2 | `project(b:Vector2)const` |
| Vector2 | `reflect(line:Vector2)const` |
| Vector2 | `rotated(angle:float)const` |
| Vector2 | `round()const` |
| Vector2 | `sign()const` |
| Vector2 | `slerp(to:Vector2, weight:float)const` |
| Vector2 | `slide(n:Vector2)const` |
| Vector2 | `snapped(step:Vector2)const` |
| Vector2 | `snappedf(step:float)const` |

