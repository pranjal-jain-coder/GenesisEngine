# Vector3

## Description

A 3-element structure that can be used to represent 3D coordinates or any other triplet of numeric values.

It uses floating-point coordinates. By default, these floating-point values use 32-bit precision, unlike float which is always 64-bit. If double precision is needed, compile the engine with the option precision=double.

See Vector3i for its integer counterpart.

Note: In a boolean context, a Vector3 will evaluate to false if it's equal to Vector3(0, 0, 0). Otherwise, a Vector3 will always evaluate to true.


## Properties

| Type | Name | Default |
| --- | --- | --- |
| float | `y` | 0.0 |
| float | `z` | 0.0 |


## Methods

| Return | Name |
| --- | --- |
| float | `angle_to(to:Vector3)const` |
| Vector3 | `bezier_derivative(control_1:Vector3, control_2:Vector3, end:Vector3, t:float)const` |
| Vector3 | `bezier_interpolate(control_1:Vector3, control_2:Vector3, end:Vector3, t:float)const` |
| Vector3 | `bounce(n:Vector3)const` |
| Vector3 | `ceil()const` |
| Vector3 | `clamp(min:Vector3, max:Vector3)const` |
| Vector3 | `clampf(min:float, max:float)const` |
| Vector3 | `cross(with:Vector3)const` |
| Vector3 | `cubic_interpolate(b:Vector3, pre_a:Vector3, post_b:Vector3, weight:float)const` |
| Vector3 | `cubic_interpolate_in_time(b:Vector3, pre_a:Vector3, post_b:Vector3, weight:float, b_t:float, pre_a_t:float, post_b_t:float)const` |
| Vector3 | `direction_to(to:Vector3)const` |
| float | `distance_squared_to(to:Vector3)const` |
| float | `distance_to(to:Vector3)const` |
| float | `dot(with:Vector3)const` |
| Vector3 | `floor()const` |
| Vector3 | `inverse()const` |
| bool | `is_equal_approx(to:Vector3)const` |
| bool | `is_finite()const` |
| bool | `is_normalized()const` |
| bool | `is_zero_approx()const` |
| float | `length()const` |
| float | `length_squared()const` |
| Vector3 | `lerp(to:Vector3, weight:float)const` |
| Vector3 | `limit_length(length:float= 1.0)const` |
| Vector3 | `max(with:Vector3)const` |
| int | `max_axis_index()const` |
| Vector3 | `maxf(with:float)const` |
| Vector3 | `min(with:Vector3)const` |
| int | `min_axis_index()const` |
| Vector3 | `minf(with:float)const` |
| Vector3 | `move_toward(to:Vector3, delta:float)const` |
| Vector3 | `normalized()const` |
| Vector3 | `octahedron_decode(uv:Vector2)static` |
| Vector2 | `octahedron_encode()const` |
| Basis | `outer(with:Vector3)const` |
| Vector3 | `posmod(mod:float)const` |
| Vector3 | `posmodv(modv:Vector3)const` |
| Vector3 | `project(b:Vector3)const` |
| Vector3 | `reflect(n:Vector3)const` |
| Vector3 | `rotated(axis:Vector3, angle:float)const` |
| Vector3 | `round()const` |
| Vector3 | `sign()const` |
| float | `signed_angle_to(to:Vector3, axis:Vector3)const` |
| Vector3 | `slerp(to:Vector3, weight:float)const` |
| Vector3 | `slide(n:Vector3)const` |
| Vector3 | `snapped(step:Vector3)const` |
| Vector3 | `snappedf(step:float)const` |

