# FileAccess

## Description

This class can be used to permanently store data in the user device's file system and to read from it. This is useful for storing game save data or player configuration files.

Example: How to write and read from a file. The file named "save_game.dat" will be stored in the user data folder, as specified in the Data paths documentation:

A FileAccess instance has its own file cursor, which is the position in bytes in the file where the next read/write operation will occur. Functions such as get_8(), get_16(), store_8(), and store_16() will move the file cursor forward by the number of bytes read/written. The file cursor can be moved to a specific position using seek() or seek_end(), and its position can be retrieved using get_position().

A FileAccess instance will close its file when the instance is freed. Since it inherits RefCounted, this happens automatically when it is no longer in use. close() can be called to close it earlier. In C#, the reference must be disposed manually, which can be done with the using statement or by calling the Dispose method directly.

Note: To access project resources once exported, it is recommended to use ResourceLoader instead of FileAccess, as some files are converted to engine-specific formats and their original source files might not be present in the exported PCK package. If using FileAccess, make sure the file is included in the export by changing its import mode to Keep File (exported as is) in the Import dock, or, for files where this option is not available, change the non-resource export filter in the Export dialog to include the file's extension (e.g. *.txt).

Note: Files are automatically closed only if the process exits "normally" (such as by clicking the window manager's close button or pressing Alt + F4). If you stop the project execution by pressing F8 while the project is running, the file won't be closed as the game process will be killed. You can work around this by calling flush() at regular intervals.


## Properties

| Type | Name | Default |
| --- | --- | --- |


## Methods

| Return | Name |
| --- | --- |
| FileAccess | `create_temp(mode_flags:ModeFlags, prefix:String= "", extension:String= "", keep:bool= false)static` |
| bool | `eof_reached()const` |
| bool | `file_exists(path:String)static` |
| void | `flush()` |
| int | `get_8()const` |
| int | `get_16()const` |
| int | `get_32()const` |
| int | `get_64()const` |
| int | `get_access_time(file:String)static` |
| String | `get_as_text()const` |
| PackedByteArray | `get_buffer(length:int)const` |
| PackedStringArray | `get_csv_line(delim:String= ",")const` |
| float | `get_double()const` |
| Error | `get_error()const` |
| PackedByteArray | `get_extended_attribute(file:String, attribute_name:String)static` |
| String | `get_extended_attribute_string(file:String, attribute_name:String)static` |
| PackedStringArray | `get_extended_attributes_list(file:String)static` |
| PackedByteArray | `get_file_as_bytes(path:String)static` |
| String | `get_file_as_string(path:String)static` |
| float | `get_float()const` |
| float | `get_half()const` |
| bool | `get_hidden_attribute(file:String)static` |
| int | `get_length()const` |
| String | `get_line()const` |
| String | `get_md5(path:String)static` |
| int | `get_modified_time(file:String)static` |
| Error | `get_open_error()static` |
| String | `get_pascal_string()` |
| String | `get_path()const` |
| String | `get_path_absolute()const` |
| int | `get_position()const` |
| bool | `get_read_only_attribute(file:String)static` |
| float | `get_real()const` |
| String | `get_sha256(path:String)static` |
| int | `get_size(file:String)static` |
| BitField[UnixPermissionFlags] | `get_unix_permissions(file:String)static` |
| Variant | `get_var(allow_objects:bool= false)const` |
| bool | `is_open()const` |
| FileAccess | `open(path:String, flags:ModeFlags)static` |
| FileAccess | `open_compressed(path:String, mode_flags:ModeFlags, compression_mode:CompressionMode= 0)static` |
| FileAccess | `open_encrypted(path:String, mode_flags:ModeFlags, key:PackedByteArray, iv:PackedByteArray= PackedByteArray())static` |
| FileAccess | `open_encrypted_with_pass(path:String, mode_flags:ModeFlags, pass:String)static` |
| Error | `remove_extended_attribute(file:String, attribute_name:String)static` |
| Error | `resize(length:int)` |
| void | `seek(position:int)` |
| void | `seek_end(position:int= 0)` |
| Error | `set_extended_attribute(file:String, attribute_name:String, data:PackedByteArray)static` |
| Error | `set_extended_attribute_string(file:String, attribute_name:String, data:String)static` |
| Error | `set_hidden_attribute(file:String, hidden:bool)static` |
| Error | `set_read_only_attribute(file:String, ro:bool)static` |
| Error | `set_unix_permissions(file:String, permissions:BitField[UnixPermissionFlags])static` |
| bool | `store_8(value:int)` |
| bool | `store_16(value:int)` |
| bool | `store_32(value:int)` |
| bool | `store_64(value:int)` |
| bool | `store_buffer(buffer:PackedByteArray)` |
| bool | `store_csv_line(values:PackedStringArray, delim:String= ",")` |
| bool | `store_double(value:float)` |
| bool | `store_float(value:float)` |
| bool | `store_half(value:float)` |
| bool | `store_line(line:String)` |
| bool | `store_pascal_string(string:String)` |
| bool | `store_real(value:float)` |
| bool | `store_string(string:String)` |
| bool | `store_var(value:Variant, full_objects:bool= false)` |

