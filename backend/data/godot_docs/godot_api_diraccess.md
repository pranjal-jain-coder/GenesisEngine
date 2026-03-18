# DirAccess

## Description

This class is used to manage directories and their content, even outside of the project folder.

DirAccess can't be instantiated directly. Instead it is created with a static method that takes a path for which it will be opened.

Most of the methods have a static alternative that can be used without creating a DirAccess. Static methods only support absolute paths (including res:// and user://).

Note: Accessing project ("res://") directories once exported may behave unexpectedly as some files are converted to engine-specific formats and their original source files may not be present in the expected PCK package. Because of this, to access resources in an exported project, it is recommended to use ResourceLoader instead of FileAccess.

Here is an example on how to iterate through the files of a directory:

Keep in mind that file names may change or be remapped after export. If you want to see the actual resource file list as it appears in the editor, use ResourceLoader.list_directory() instead.


## Properties

| Type | Name | Default |
| --- | --- | --- |


## Methods

| Return | Name |
| --- | --- |
| Error | `copy(from:String, to:String, chmod_flags:int= -1)` |
| Error | `copy_absolute(from:String, to:String, chmod_flags:int= -1)static` |
| Error | `create_link(source:String, target:String)` |
| DirAccess | `create_temp(prefix:String= "", keep:bool= false)static` |
| bool | `current_is_dir()const` |
| bool | `dir_exists(path:String)` |
| bool | `dir_exists_absolute(path:String)static` |
| bool | `file_exists(path:String)` |
| String | `get_current_dir(include_drive:bool= true)const` |
| int | `get_current_drive()` |
| PackedStringArray | `get_directories()` |
| PackedStringArray | `get_directories_at(path:String)static` |
| int | `get_drive_count()static` |
| String | `get_drive_name(idx:int)static` |
| PackedStringArray | `get_files()` |
| PackedStringArray | `get_files_at(path:String)static` |
| String | `get_filesystem_type()const` |
| String | `get_next()` |
| Error | `get_open_error()static` |
| int | `get_space_left()` |
| bool | `is_bundle(path:String)const` |
| bool | `is_case_sensitive(path:String)const` |
| bool | `is_equivalent(path_a:String, path_b:String)const` |
| bool | `is_link(path:String)` |
| Error | `list_dir_begin()` |
| void | `list_dir_end()` |
| Error | `make_dir(path:String)` |
| Error | `make_dir_absolute(path:String)static` |
| Error | `make_dir_recursive(path:String)` |
| Error | `make_dir_recursive_absolute(path:String)static` |
| DirAccess | `open(path:String)static` |
| String | `read_link(path:String)` |
| Error | `remove(path:String)` |
| Error | `remove_absolute(path:String)static` |
| Error | `rename(from:String, to:String)` |
| Error | `rename_absolute(from:String, to:String)static` |

