# Resource

## Description

Resource is the base class for all Godot-specific resource types, serving primarily as data containers. Since they inherit from RefCounted, resources are reference-counted and freed when no longer in use. They can also be nested within other resources, and saved on disk. PackedScene, one of the most common Objects in a Godot project, is also a resource, uniquely capable of storing and instantiating the Nodes it contains as many times as desired.

In GDScript, resources can loaded from disk by their resource_path using @GDScript.load() or @GDScript.preload().

The engine keeps a global cache of all loaded resources, referenced by paths (see ResourceLoader.has_cached()). A resource will be cached when loaded for the first time and removed from cache once all references are released. When a resource is cached, subsequent loads using its path will return the cached reference.

Note: In C#, resources will not be freed instantly after they are no longer in use. Instead, garbage collection will run periodically and will free resources that are no longer in use. This means that unused resources will remain in memory for a while before being removed.


## Properties

| Type | Name | Default |
| --- | --- | --- |
| String | `resource_name` | "" |
| String | `resource_path` | "" |
| String | `resource_scene_unique_id` |  |


## Methods

| Return | Name |
| --- | --- |
| void | `_reset_state()virtual` |
| void | `_set_path_cache(path:String)virtualconst` |
| void | `_setup_local_to_scene()virtual` |
| Resource | `duplicate(deep:bool= false)const` |
| Resource | `duplicate_deep(deep_subresources_mode:DeepDuplicateMode= 1)const` |
| void | `emit_changed()` |
| String | `generate_scene_unique_id()static` |
| String | `get_id_for_path(path:String)const` |
| Node | `get_local_scene()const` |
| RID | `get_rid()const` |
| bool | `is_built_in()const` |
| void | `reset_state()` |
| void | `set_id_for_path(path:String, id:String)` |
| void | `set_path_cache(path:String)` |
| void | `setup_local_to_scene()` |
| void | `take_over_path(path:String)` |


## Signals


