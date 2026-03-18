# Time

## Description

The Time singleton allows converting time between various formats and also getting time information from the system.

This class conforms with as many of the ISO 8601 standards as possible. All dates follow the Proleptic Gregorian calendar. As such, the day before 1582-10-15 is 1582-10-14, not 1582-10-04. The year before 1 AD (aka 1 BC) is number 0, with the year before that (2 BC) being -1, etc.

Conversion methods assume "the same timezone", and do not handle timezone conversions or DST automatically. Leap seconds are also not handled, they must be done manually if desired. Suffixes such as "Z" are not handled, you need to strip them away manually.

When getting time information from the system, the time can either be in the local timezone or UTC depending on the utc parameter. However, the get_unix_time_from_system() method always uses UTC as it returns the seconds passed since the Unix epoch.

Important: The _from_system methods use the system clock that the user can manually set. Never use this method for precise time calculation since its results are subject to automatic adjustments by the user or the operating system. Always use get_ticks_usec() or get_ticks_msec() for precise time calculation instead, since they are guaranteed to be monotonic (i.e. never decrease).


## Methods

| Return | Name |
| --- | --- |
| Dictionary | `get_date_dict_from_unix_time(unix_time_val:int)const` |
| String | `get_date_string_from_system(utc:bool= false)const` |
| String | `get_date_string_from_unix_time(unix_time_val:int)const` |
| Dictionary | `get_datetime_dict_from_datetime_string(datetime:String, weekday:bool)const` |
| Dictionary | `get_datetime_dict_from_system(utc:bool= false)const` |
| Dictionary | `get_datetime_dict_from_unix_time(unix_time_val:int)const` |
| String | `get_datetime_string_from_datetime_dict(datetime:Dictionary, use_space:bool)const` |
| String | `get_datetime_string_from_system(utc:bool= false, use_space:bool= false)const` |
| String | `get_datetime_string_from_unix_time(unix_time_val:int, use_space:bool= false)const` |
| String | `get_offset_string_from_offset_minutes(offset_minutes:int)const` |
| int | `get_ticks_msec()const` |
| int | `get_ticks_usec()const` |
| Dictionary | `get_time_dict_from_system(utc:bool= false)const` |
| Dictionary | `get_time_dict_from_unix_time(unix_time_val:int)const` |
| String | `get_time_string_from_system(utc:bool= false)const` |
| String | `get_time_string_from_unix_time(unix_time_val:int)const` |
| Dictionary | `get_time_zone_from_system()const` |
| int | `get_unix_time_from_datetime_dict(datetime:Dictionary)const` |
| int | `get_unix_time_from_datetime_string(datetime:String)const` |
| float | `get_unix_time_from_system()const` |

