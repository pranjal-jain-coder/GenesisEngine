# CanvasItem

## Description

Abstract base class for everything in 2D space. Canvas items are laid out in a tree; children inherit and extend their parent's transform. CanvasItem is extended by Control for GUI-related nodes, and by Node2D for 2D game objects.

Any CanvasItem can draw. For this, queue_redraw() is called by the engine, then NOTIFICATION_DRAW will be received on idle time to request a redraw. Because of this, canvas items don't need to be redrawn on every frame, improving the performance significantly. Several functions for drawing on the CanvasItem are provided (see draw_* functions). However, they can only be used inside _draw(), its corresponding Object._notification() or methods connected to the draw signal.

Canvas items are drawn in tree order on their canvas layer. By default, children are on top of their parents, so a root CanvasItem will be drawn behind everything. This behavior can be changed on a per-item basis.

A CanvasItem can be hidden, which will also hide its children. By adjusting various other properties of a CanvasItem, you can also modulate its color (via modulate or self_modulate), change its Z-index, blend mode, and more.

Note that properties like transform, modulation, and visibility are only propagated to direct CanvasItem child nodes. If there is a non-CanvasItem node in between, like Node or AnimationPlayer, the CanvasItem nodes below will have an independent position and modulate chain. See also top_level.


## Properties

| Type | Name | Default |
| --- | --- | --- |
| int | `light_mask` | 1 |
| Material | `material` |  |
| Color | `modulate` | Color(1,1,1,1) |
| Color | `self_modulate` | Color(1,1,1,1) |
| bool | `show_behind_parent` | false |
| TextureFilter | `texture_filter` | 0 |
| TextureRepeat | `texture_repeat` | 0 |
| bool | `top_level` | false |
| bool | `use_parent_material` | false |
| int | `visibility_layer` | 1 |
| bool | `visible` | true |
| bool | `y_sort_enabled` | false |
| bool | `z_as_relative` | true |
| int | `z_index` | 0 |


## Methods

| Return | Name |
| --- | --- |
| void | `draw_animation_slice(animation_length:float, slice_begin:float, slice_end:float, offset:float= 0.0)` |
| void | `draw_arc(center:Vector2, radius:float, start_angle:float, end_angle:float, point_count:int, color:Color, width:float= -1.0, antialiased:bool= false)` |
| void | `draw_char(font:Font, pos:Vector2, char:String, font_size:int= 16, modulate:Color= Color(1, 1, 1, 1), oversampling:float= 0.0)const` |
| void | `draw_char_outline(font:Font, pos:Vector2, char:String, font_size:int= 16, size:int= -1, modulate:Color= Color(1, 1, 1, 1), oversampling:float= 0.0)const` |
| void | `draw_circle(position:Vector2, radius:float, color:Color, filled:bool= true, width:float= -1.0, antialiased:bool= false)` |
| void | `draw_colored_polygon(points:PackedVector2Array, color:Color, uvs:PackedVector2Array= PackedVector2Array(), texture:Texture2D= null)` |
| void | `draw_dashed_line(from:Vector2, to:Vector2, color:Color, width:float= -1.0, dash:float= 2.0, aligned:bool= true, antialiased:bool= false)` |
| void | `draw_ellipse(position:Vector2, major:float, minor:float, color:Color, filled:bool= true, width:float= -1.0, antialiased:bool= false)` |
| void | `draw_ellipse_arc(center:Vector2, major:float, minor:float, start_angle:float, end_angle:float, point_count:int, color:Color, width:float= -1.0, antialiased:bool= false)` |
| void | `draw_end_animation()` |
| void | `draw_lcd_texture_rect_region(texture:Texture2D, rect:Rect2, src_rect:Rect2, modulate:Color= Color(1, 1, 1, 1))` |
| void | `draw_line(from:Vector2, to:Vector2, color:Color, width:float= -1.0, antialiased:bool= false)` |
| void | `draw_mesh(mesh:Mesh, texture:Texture2D, transform:Transform2D= Transform2D(1, 0, 0, 1, 0, 0), modulate:Color= Color(1, 1, 1, 1))` |
| void | `draw_msdf_texture_rect_region(texture:Texture2D, rect:Rect2, src_rect:Rect2, modulate:Color= Color(1, 1, 1, 1), outline:float= 0.0, pixel_range:float= 4.0, scale:float= 1.0)` |
| void | `draw_multiline(points:PackedVector2Array, color:Color, width:float= -1.0, antialiased:bool= false)` |
| void | `draw_multiline_colors(points:PackedVector2Array, colors:PackedColorArray, width:float= -1.0, antialiased:bool= false)` |
| void | `draw_multiline_string(font:Font, pos:Vector2, text:String, alignment:HorizontalAlignment= 0, width:float= -1, font_size:int= 16, max_lines:int= -1, modulate:Color= Color(1, 1, 1, 1), brk_flags:BitField[LineBreakFlag] = 3, justification_flags:BitField[JustificationFlag] = 3, direction:Direction= 0, orientation:Orientation= 0, oversampling:float= 0.0)const` |
| void | `draw_multiline_string_outline(font:Font, pos:Vector2, text:String, alignment:HorizontalAlignment= 0, width:float= -1, font_size:int= 16, max_lines:int= -1, size:int= 1, modulate:Color= Color(1, 1, 1, 1), brk_flags:BitField[LineBreakFlag] = 3, justification_flags:BitField[JustificationFlag] = 3, direction:Direction= 0, orientation:Orientation= 0, oversampling:float= 0.0)const` |
| void | `draw_multimesh(multimesh:MultiMesh, texture:Texture2D)` |
| void | `draw_polygon(points:PackedVector2Array, colors:PackedColorArray, uvs:PackedVector2Array= PackedVector2Array(), texture:Texture2D= null)` |
| void | `draw_polyline(points:PackedVector2Array, color:Color, width:float= -1.0, antialiased:bool= false)` |
| void | `draw_polyline_colors(points:PackedVector2Array, colors:PackedColorArray, width:float= -1.0, antialiased:bool= false)` |
| void | `draw_primitive(points:PackedVector2Array, colors:PackedColorArray, uvs:PackedVector2Array, texture:Texture2D= null)` |
| void | `draw_rect(rect:Rect2, color:Color, filled:bool= true, width:float= -1.0, antialiased:bool= false)` |
| void | `draw_set_transform(position:Vector2, rotation:float= 0.0, scale:Vector2= Vector2(1, 1))` |
| void | `draw_set_transform_matrix(xform:Transform2D)` |
| void | `draw_string(font:Font, pos:Vector2, text:String, alignment:HorizontalAlignment= 0, width:float= -1, font_size:int= 16, modulate:Color= Color(1, 1, 1, 1), justification_flags:BitField[JustificationFlag] = 3, direction:Direction= 0, orientation:Orientation= 0, oversampling:float= 0.0)const` |
| void | `draw_string_outline(font:Font, pos:Vector2, text:String, alignment:HorizontalAlignment= 0, width:float= -1, font_size:int= 16, size:int= 1, modulate:Color= Color(1, 1, 1, 1), justification_flags:BitField[JustificationFlag] = 3, direction:Direction= 0, orientation:Orientation= 0, oversampling:float= 0.0)const` |
| void | `draw_style_box(style_box:StyleBox, rect:Rect2)` |
| void | `draw_texture(texture:Texture2D, position:Vector2, modulate:Color= Color(1, 1, 1, 1))` |
| void | `draw_texture_rect(texture:Texture2D, rect:Rect2, tile:bool, modulate:Color= Color(1, 1, 1, 1), transpose:bool= false)` |
| void | `draw_texture_rect_region(texture:Texture2D, rect:Rect2, src_rect:Rect2, modulate:Color= Color(1, 1, 1, 1), transpose:bool= false, clip_uv:bool= true)` |
| void | `force_update_transform()` |
| RID | `get_canvas()const` |
| RID | `get_canvas_item()const` |
| CanvasLayer | `get_canvas_layer_node()const` |
| Transform2D | `get_canvas_transform()const` |
| Vector2 | `get_global_mouse_position()const` |
| Transform2D | `get_global_transform()const` |
| Transform2D | `get_global_transform_with_canvas()const` |
| Variant | `get_instance_shader_parameter(name:StringName)const` |
| Vector2 | `get_local_mouse_position()const` |
| Transform2D | `get_screen_transform()const` |
| Transform2D | `get_transform()const` |
| Rect2 | `get_viewport_rect()const` |
| Transform2D | `get_viewport_transform()const` |
| bool | `get_visibility_layer_bit(layer:int)const` |
| World2D | `get_world_2d()const` |
| void | `hide()` |
| bool | `is_local_transform_notification_enabled()const` |
| bool | `is_transform_notification_enabled()const` |
| bool | `is_visible_in_tree()const` |
| Vector2 | `make_canvas_position_local(viewport_point:Vector2)const` |
| InputEvent | `make_input_local(event:InputEvent)const` |
| void | `move_to_front()` |
| void | `queue_redraw()` |
| void | `set_instance_shader_parameter(name:StringName, value:Variant)` |
| void | `set_notify_local_transform(enable:bool)` |
| void | `set_notify_transform(enable:bool)` |
| void | `set_visibility_layer_bit(layer:int, enabled:bool)` |
| void | `show()` |


## Signals


