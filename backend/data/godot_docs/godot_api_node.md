# Node

## Description

Nodes are Godot's building blocks. They can be assigned as the child of another node, resulting in a tree arrangement. A given node can contain any number of nodes as children with the requirement that all siblings (direct children of a node) should have unique names.

A tree of nodes is called a scene. Scenes can be saved to the disk and then instantiated into other scenes. This allows for very high flexibility in the architecture and data model of Godot projects.

Scene tree: The SceneTree contains the active tree of nodes. When a node is added to the scene tree, it receives the NOTIFICATION_ENTER_TREE notification and its _enter_tree() callback is triggered. Child nodes are always added after their parent node, i.e. the _enter_tree() callback of a parent node will be triggered before its child's.

Once all nodes have been added in the scene tree, they receive the NOTIFICATION_READY notification and their respective _ready() callbacks are triggered. For groups of nodes, the _ready() callback is called in reverse order, starting with the children and moving up to the parent nodes.

This means that when adding a node to the scene tree, the following order will be used for the callbacks: _enter_tree() of the parent, _enter_tree() of the children, _ready() of the children and finally _ready() of the parent (recursively for the entire scene tree).

Processing: Nodes can override the "process" state, so that they receive a callback on each frame requesting them to process (do something). Normal processing (callback _process(), toggled with set_process()) happens as fast as possible and is dependent on the frame rate, so the processing time delta (in seconds) is passed as an argument. Physics processing (callback _physics_process(), toggled with set_physics_process()) happens a fixed number of times per second (60 by default) and is useful for code related to the physics engine.

Nodes can also process input events. When present, the _input() function will be called for each input that the program receives. In many cases, this can be overkill (unless used for simple projects), and the _unhandled_input() function might be preferred; it is called when the input event was not handled by anyone else (typically, GUI Control nodes), ensuring that the node only receives the events that were meant for it.

To keep track of the scene hierarchy (especially when instantiating scenes into other scenes), an "owner" can be set for the node with the owner property. This keeps track of who instantiated what. This is mostly useful when writing editors and tools, though.

Finally, when a node is freed with Object.free() or queue_free(), it will also free all its children.

Groups: Nodes can be added to as many groups as you want to be easy to manage, you could create groups like "enemies" or "collectables" for example, depending on your game. See add_to_group(), is_in_group() and remove_from_group(). You can then retrieve all nodes in these groups, iterate them and even call methods on groups via the methods on SceneTree.

Networking with nodes: After connecting to a server (or making one, see ENetMultiplayerPeer), it is possible to use the built-in RPC (remote procedure call) system to communicate over the network. By calling rpc() with a method name, it will be called locally and in all connected peers (peers = clients and the server that accepts connections). To identify which node receives the RPC call, Godot will use its NodePath (make sure node names are the same on all peers). Also, take a look at the high-level networking tutorial and corresponding demos.

Note: The script property is part of the Object class, not Node. It isn't exposed like most properties but does have a setter and getter (see Object.set_script() and Object.get_script()).


## Properties

| Type | Name | Default |
| --- | --- | --- |
| String | `editor_description` | "" |
| MultiplayerAPI | `multiplayer` |  |
| StringName | `name` |  |
| Node | `owner` |  |
| PhysicsInterpolationMode | `physics_interpolation_mode` | 0 |
| ProcessMode | `process_mode` | 0 |
| int | `process_physics_priority` | 0 |
| int | `process_priority` | 0 |
| ProcessThreadGroup | `process_thread_group` | 0 |
| int | `process_thread_group_order` |  |
| BitField[ProcessThreadMessages] | `process_thread_messages` |  |
| String | `scene_file_path` |  |
| bool | `unique_name_in_owner` | false |


## Methods

| Return | Name |
| --- | --- |
| void | `_exit_tree()virtual` |
| PackedStringArray | `_get_accessibility_configuration_warnings()virtualconst` |
| PackedStringArray | `_get_configuration_warnings()virtualconst` |
| RID | `_get_focused_accessibility_element()virtualconst` |
| void | `_input(event:InputEvent)virtual` |
| void | `_physics_process(delta:float)virtual` |
| void | `_process(delta:float)virtual` |
| void | `_ready()virtual` |
| void | `_shortcut_input(event:InputEvent)virtual` |
| void | `_unhandled_input(event:InputEvent)virtual` |
| void | `_unhandled_key_input(event:InputEvent)virtual` |
| void | `add_child(node:Node, force_readable_name:bool= false, internal:InternalMode= 0)` |
| void | `add_sibling(sibling:Node, force_readable_name:bool= false)` |
| void | `add_to_group(group:StringName, persistent:bool= false)` |
| String | `atr(message:String, context:StringName= "")const` |
| String | `atr_n(message:String, plural_message:StringName, n:int, context:StringName= "")const` |
| Variant | `call_deferred_thread_group(method:StringName, ...)vararg` |
| Variant | `call_thread_safe(method:StringName, ...)vararg` |
| bool | `can_auto_translate()const` |
| bool | `can_process()const` |
| Tween | `create_tween()` |
| Node | `duplicate(flags:int= 15)const` |
| Node | `find_child(pattern:String, recursive:bool= true, owned:bool= true)const` |
| Array[Node] | `find_children(pattern:String, type:String= "", recursive:bool= true, owned:bool= true)const` |
| Node | `find_parent(pattern:String)const` |
| RID | `get_accessibility_element()const` |
| Node | `get_child(idx:int, include_internal:bool= false)const` |
| int | `get_child_count(include_internal:bool= false)const` |
| Array[Node] | `get_children(include_internal:bool= false)const` |
| Array[StringName] | `get_groups()const` |
| int | `get_index(include_internal:bool= false)const` |
| Window | `get_last_exclusive_window()const` |
| int | `get_multiplayer_authority()const` |
| Node | `get_node(path:NodePath)const` |
| Array | `get_node_and_resource(path:NodePath)` |
| Node | `get_node_or_null(path:NodePath)const` |
| Variant | `get_node_rpc_config()const` |
| Array[int] | `get_orphan_node_ids()static` |
| Node | `get_parent()const` |
| NodePath | `get_path()const` |
| NodePath | `get_path_to(node:Node, use_unique_path:bool= false)const` |
| float | `get_physics_process_delta_time()const` |
| float | `get_process_delta_time()const` |
| bool | `get_scene_instance_load_placeholder()const` |
| SceneTree | `get_tree()const` |
| String | `get_tree_string()` |
| String | `get_tree_string_pretty()` |
| Viewport | `get_viewport()const` |
| Window | `get_window()const` |
| bool | `has_node(path:NodePath)const` |
| bool | `has_node_and_resource(path:NodePath)const` |
| bool | `is_ancestor_of(node:Node)const` |
| bool | `is_displayed_folded()const` |
| bool | `is_editable_instance(node:Node)const` |
| bool | `is_greater_than(node:Node)const` |
| bool | `is_in_group(group:StringName)const` |
| bool | `is_inside_tree()const` |
| bool | `is_multiplayer_authority()const` |
| bool | `is_node_ready()const` |
| bool | `is_part_of_edited_scene()const` |
| bool | `is_physics_interpolated()const` |
| bool | `is_physics_interpolated_and_enabled()const` |
| bool | `is_physics_processing()const` |
| bool | `is_physics_processing_internal()const` |
| bool | `is_processing()const` |
| bool | `is_processing_input()const` |
| bool | `is_processing_internal()const` |
| bool | `is_processing_shortcut_input()const` |
| bool | `is_processing_unhandled_input()const` |
| bool | `is_processing_unhandled_key_input()const` |
| void | `move_child(child_node:Node, to_index:int)` |
| void | `notify_deferred_thread_group(what:int)` |
| void | `notify_thread_safe(what:int)` |
| void | `print_orphan_nodes()static` |
| void | `print_tree()` |
| void | `print_tree_pretty()` |
| void | `propagate_call(method:StringName, args:Array= [], parent_first:bool= false)` |
| void | `propagate_notification(what:int)` |
| void | `queue_accessibility_update()` |
| void | `queue_free()` |
| void | `remove_child(node:Node)` |
| void | `remove_from_group(group:StringName)` |
| void | `reparent(new_parent:Node, keep_global_transform:bool= true)` |
| void | `replace_by(node:Node, keep_groups:bool= false)` |
| void | `request_ready()` |
| void | `reset_physics_interpolation()` |
| Error | `rpc(method:StringName, ...)vararg` |
| void | `rpc_config(method:StringName, config:Variant)` |
| Error | `rpc_id(peer_id:int, method:StringName, ...)vararg` |
| void | `set_deferred_thread_group(property:StringName, value:Variant)` |
| void | `set_display_folded(fold:bool)` |
| void | `set_editable_instance(node:Node, is_editable:bool)` |
| void | `set_multiplayer_authority(id:int, recursive:bool= true)` |
| void | `set_physics_process(enable:bool)` |
| void | `set_physics_process_internal(enable:bool)` |
| void | `set_process(enable:bool)` |
| void | `set_process_input(enable:bool)` |
| void | `set_process_internal(enable:bool)` |
| void | `set_process_shortcut_input(enable:bool)` |
| void | `set_process_unhandled_input(enable:bool)` |
| void | `set_process_unhandled_key_input(enable:bool)` |
| void | `set_scene_instance_load_placeholder(load_placeholder:bool)` |
| void | `set_thread_safe(property:StringName, value:Variant)` |
| void | `set_translation_domain_inherited()` |
| void | `update_configuration_warnings()` |


## Signals


