# Object

## Description

An advanced Variant type. All classes in the engine inherit from Object. Each class may define new properties, methods or signals, which are available to all inheriting classes. For example, a Sprite2D instance is able to call Node.add_child() because it inherits from Node.

You can create new instances, using Object.new() in GDScript, or new GodotObject in C#.

To delete an Object instance, call free(). This is necessary for most classes inheriting Object, because they do not manage memory on their own, and will otherwise cause memory leaks when no longer in use. There are a few classes that perform memory management. For example, RefCounted (and by extension Resource) deletes itself when no longer referenced, and Node deletes its children when freed.

Objects can have a Script attached to them. Once the Script is instantiated, it effectively acts as an extension to the base class, allowing it to define and inherit new properties, methods and signals.

Inside a Script, _get_property_list() may be overridden to customize properties in several ways. This allows them to be available to the editor, display as lists of options, sub-divide into groups, save on disk, etc. Scripting languages offer easier ways to customize properties, such as with the @GDScript.@export annotation.

Godot is very dynamic. An object's script, and therefore its properties, methods and signals, can be changed at run-time. Because of this, there can be occasions where, for example, a property required by a method may not exist. To prevent run-time errors, see methods such as set(), get(), call(), has_method(), has_signal(), etc. Note that these methods are much slower than direct references.

In GDScript, you can also check if a given property, method, or signal name exists in an object with the in operator:

Notifications are int constants commonly sent and received by objects. For example, on every rendered frame, the SceneTree notifies nodes inside the tree with a Node.NOTIFICATION_PROCESS. The nodes receive it and may call Node._process() to update. To make use of notifications, see notification() and _notification().

Lastly, every object can also contain metadata (data about data). set_meta() can be useful to store information that the object itself does not depend on. To keep your code clean, making excessive use of metadata is discouraged.

Note: Unlike references to a RefCounted, references to an object stored in a variable can become invalid without being set to null. To check if an object has been deleted, do not compare it against null. Instead, use @GlobalScope.is_instance_valid(). It's also recommended to inherit from RefCounted for classes storing data instead of Object.

Note: The script is not exposed like most properties. To set or get an object's Script in code, use set_script() and get_script(), respectively.

Note: In a boolean context, an Object will evaluate to false if it is equal to null or it has been freed. Otherwise, an Object will always evaluate to true. See also @GlobalScope.is_instance_valid().


## Methods

| Return | Name |
| --- | --- |
| Array[Dictionary] | `_get_property_list()virtual` |
| void | `_init()virtual` |
| Variant | `_iter_get(iter:Variant)virtual` |
| bool | `_iter_init(iter:Array)virtual` |
| bool | `_iter_next(iter:Array)virtual` |
| void | `_notification(what:int)virtual` |
| bool | `_property_can_revert(property:StringName)virtual` |
| Variant | `_property_get_revert(property:StringName)virtual` |
| bool | `_set(property:StringName, value:Variant)virtual` |
| String | `_to_string()virtual` |
| void | `_validate_property(property:Dictionary)virtual` |
| void | `add_user_signal(signal:String, arguments:Array= [])` |
| Variant | `call(method:StringName, ...)vararg` |
| Variant | `call_deferred(method:StringName, ...)vararg` |
| Variant | `callv(method:StringName, arg_array:Array)` |
| bool | `can_translate_messages()const` |
| void | `cancel_free()` |
| Error | `connect(signal:StringName, callable:Callable, flags:int= 0)` |
| void | `disconnect(signal:StringName, callable:Callable)` |
| Error | `emit_signal(signal:StringName, ...)vararg` |
| void | `free()` |
| Variant | `get(property:StringName)const` |
| String | `get_class()const` |
| Array[Dictionary] | `get_incoming_connections()const` |
| Variant | `get_indexed(property_path:NodePath)const` |
| int | `get_instance_id()const` |
| Variant | `get_meta(name:StringName, default:Variant= null)const` |
| Array[StringName] | `get_meta_list()const` |
| int | `get_method_argument_count(method:StringName)const` |
| Array[Dictionary] | `get_method_list()const` |
| Array[Dictionary] | `get_property_list()const` |
| Variant | `get_script()const` |
| Array[Dictionary] | `get_signal_connection_list(signal:StringName)const` |
| Array[Dictionary] | `get_signal_list()const` |
| StringName | `get_translation_domain()const` |
| bool | `has_connections(signal:StringName)const` |
| bool | `has_meta(name:StringName)const` |
| bool | `has_method(method:StringName)const` |
| bool | `has_signal(signal:StringName)const` |
| bool | `has_user_signal(signal:StringName)const` |
| bool | `is_blocking_signals()const` |
| bool | `is_class(class:String)const` |
| bool | `is_connected(signal:StringName, callable:Callable)const` |
| bool | `is_queued_for_deletion()const` |
| void | `notification(what:int, reversed:bool= false)` |
| void | `notify_property_list_changed()` |
| bool | `property_can_revert(property:StringName)const` |
| Variant | `property_get_revert(property:StringName)const` |
| void | `remove_meta(name:StringName)` |
| void | `remove_user_signal(signal:StringName)` |
| void | `set(property:StringName, value:Variant)` |
| void | `set_block_signals(enable:bool)` |
| void | `set_deferred(property:StringName, value:Variant)` |
| void | `set_indexed(property_path:NodePath, value:Variant)` |
| void | `set_message_translation(enable:bool)` |
| void | `set_meta(name:StringName, value:Variant)` |
| void | `set_script(script:Variant)` |
| void | `set_translation_domain(domain:StringName)` |
| String | `to_string()` |
| String | `tr(message:StringName, context:StringName= &"")const` |
| String | `tr_n(message:StringName, plural_message:StringName, n:int, context:StringName= &"")const` |


## Signals


