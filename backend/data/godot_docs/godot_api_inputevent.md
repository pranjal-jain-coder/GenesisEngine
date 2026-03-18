# InputEvent

## Description

Abstract base class of all types of input events. See Node._input().


## Properties

| Type | Name | Default |
| --- | --- | --- |


## Methods

| Return | Name |
| --- | --- |
| String | `as_text()const` |
| float | `get_action_strength(action:StringName, exact_match:bool= false)const` |
| bool | `is_action(action:StringName, exact_match:bool= false)const` |
| bool | `is_action_pressed(action:StringName, allow_echo:bool= false, exact_match:bool= false)const` |
| bool | `is_action_released(action:StringName, exact_match:bool= false)const` |
| bool | `is_action_type()const` |
| bool | `is_canceled()const` |
| bool | `is_echo()const` |
| bool | `is_match(event:InputEvent, exact_match:bool= true)const` |
| bool | `is_pressed()const` |
| bool | `is_released()const` |
| InputEvent | `xformed_by(xform:Transform2D, local_ofs:Vector2= Vector2(0, 0))const` |

