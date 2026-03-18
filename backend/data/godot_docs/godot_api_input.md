# Input

## Description

The Input singleton handles key presses, mouse buttons and movement, gamepads, and input actions. Actions and their events can be set in the Input Map tab in Project > Project Settings, or with the InputMap class.

Note: Input's methods reflect the global input state and are not affected by Control.accept_event() or Viewport.set_input_as_handled(), as those methods only deal with the way input is propagated in the SceneTree.


## Properties

| Type | Name | Default |
| --- | --- | --- |


## Methods

| Return | Name |
| --- | --- |
| void | `action_release(action:StringName)` |
| void | `add_joy_mapping(mapping:String, update_existing:bool= false)` |
| void | `flush_buffered_events()` |
| Vector3 | `get_accelerometer()const` |
| float | `get_action_raw_strength(action:StringName, exact_match:bool= false)const` |
| float | `get_action_strength(action:StringName, exact_match:bool= false)const` |
| float | `get_axis(negative_action:StringName, positive_action:StringName)const` |
| Array[int] | `get_connected_joypads()` |
| CursorShape | `get_current_cursor_shape()const` |
| Vector3 | `get_gravity()const` |
| Vector3 | `get_gyroscope()const` |
| float | `get_joy_axis(device:int, axis:JoyAxis)const` |
| String | `get_joy_guid(device:int)const` |
| Dictionary | `get_joy_info(device:int)const` |
| String | `get_joy_name(device:int)` |
| float | `get_joy_vibration_duration(device:int)` |
| Vector2 | `get_joy_vibration_strength(device:int)` |
| Vector2 | `get_last_mouse_screen_velocity()` |
| Vector2 | `get_last_mouse_velocity()` |
| Vector3 | `get_magnetometer()const` |
| BitField[MouseButtonMask] | `get_mouse_button_mask()const` |
| Vector2 | `get_vector(negative_x:StringName, positive_x:StringName, negative_y:StringName, positive_y:StringName, deadzone:float= -1.0)const` |
| bool | `has_joy_light(device:int)const` |
| bool | `is_action_just_pressed(action:StringName, exact_match:bool= false)const` |
| bool | `is_action_just_pressed_by_event(action:StringName, event:InputEvent, exact_match:bool= false)const` |
| bool | `is_action_just_released(action:StringName, exact_match:bool= false)const` |
| bool | `is_action_just_released_by_event(action:StringName, event:InputEvent, exact_match:bool= false)const` |
| bool | `is_action_pressed(action:StringName, exact_match:bool= false)const` |
| bool | `is_anything_pressed()const` |
| bool | `is_joy_button_pressed(device:int, button:JoyButton)const` |
| bool | `is_joy_known(device:int)` |
| bool | `is_key_label_pressed(keycode:Key)const` |
| bool | `is_key_pressed(keycode:Key)const` |
| bool | `is_mouse_button_pressed(button:MouseButton)const` |
| bool | `is_physical_key_pressed(keycode:Key)const` |
| void | `parse_input_event(event:InputEvent)` |
| void | `remove_joy_mapping(guid:String)` |
| void | `set_accelerometer(value:Vector3)` |
| void | `set_custom_mouse_cursor(image:Resource, shape:CursorShape= 0, hotspot:Vector2= Vector2(0, 0))` |
| void | `set_default_cursor_shape(shape:CursorShape= 0)` |
| void | `set_gravity(value:Vector3)` |
| void | `set_gyroscope(value:Vector3)` |
| void | `set_joy_light(device:int, color:Color)` |
| void | `set_magnetometer(value:Vector3)` |
| bool | `should_ignore_device(vendor_id:int, product_id:int)const` |
| void | `start_joy_vibration(device:int, weak_magnitude:float, strong_magnitude:float, duration:float= 0)` |
| void | `stop_joy_vibration(device:int)` |
| void | `vibrate_handheld(duration_ms:int= 500, amplitude:float= -1.0)` |
| void | `warp_mouse(position:Vector2)` |


## Signals


