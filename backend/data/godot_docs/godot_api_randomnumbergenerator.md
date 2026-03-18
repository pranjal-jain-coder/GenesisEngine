# RandomNumberGenerator

## Description

RandomNumberGenerator is a class for generating pseudo-random numbers. It currently uses PCG32.

Note: The underlying algorithm is an implementation detail and should not be depended upon.

To generate a random float number (within a given range) based on a time-dependent seed:


## Properties

| Type | Name | Default |
| --- | --- | --- |
| int | `state` | 0 |


## Methods

| Return | Name |
| --- | --- |
| float | `randf()` |
| float | `randf_range(from:float, to:float)` |
| float | `randfn(mean:float= 0.0, deviation:float= 1.0)` |
| int | `randi()` |
| int | `randi_range(from:int, to:int)` |
| void | `randomize()` |

