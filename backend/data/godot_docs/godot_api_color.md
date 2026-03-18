# Color

## Description

A color represented in RGBA format by a red (r), green (g), blue (b), and alpha (a) component. Each component is a 32-bit floating-point value, usually ranging from 0.0 to 1.0. Some properties (such as CanvasItem.modulate) may support values greater than 1.0, for overbright or HDR (High Dynamic Range) colors.

Colors can be created in a number of ways: By the various Color constructors, by static methods such as from_hsv(), and by using a name from the set of standardized colors based on X11 color names with the addition of TRANSPARENT.

Color constants cheatsheet

Although Color may be used to store values of any encoding, the red (r), green (g), and blue (b) properties of Color are expected by Godot to be encoded using the nonlinear sRGB transfer function unless otherwise stated. This color encoding is used by many traditional art and web tools, making it easy to match colors between Godot and these tools. Godot uses Rec. ITU-R BT.709 color primaries, which are used by the sRGB standard.

All physical simulation, such as lighting calculations, and colorimetry transformations, such as get_luminance(), must be performed on linearly encoded values to produce correct results. When performing these calculations, convert Color to and from linear encoding using srgb_to_linear() and linear_to_srgb().

Note: In a boolean context, a Color will evaluate to false if it is equal to Color(0, 0, 0, 1) (opaque black). Otherwise, a Color will always evaluate to true.


## Properties

| Type | Name | Default |
| --- | --- | --- |
| int | `a8` | 255 |
| float | `b` | 0.0 |
| int | `b8` | 0 |
| float | `g` | 0.0 |
| int | `g8` | 0 |
| float | `h` | 0.0 |
| float | `ok_hsl_h` | 0.0 |
| float | `ok_hsl_l` | 0.0 |
| float | `ok_hsl_s` | 0.0 |
| float | `r` | 0.0 |
| int | `r8` | 0 |
| float | `s` | 0.0 |
| float | `v` | 0.0 |


## Methods

| Return | Name |
| --- | --- |
| Color | `clamp(min:Color= Color(0, 0, 0, 0), max:Color= Color(1, 1, 1, 1))const` |
| Color | `darkened(amount:float)const` |
| Color | `from_hsv(h:float, s:float, v:float, alpha:float= 1.0)static` |
| Color | `from_ok_hsl(h:float, s:float, l:float, alpha:float= 1.0)static` |
| Color | `from_rgba8(r8:int, g8:int, b8:int, a8:int= 255)static` |
| Color | `from_rgbe9995(rgbe:int)static` |
| Color | `from_string(str:String, default:Color)static` |
| float | `get_luminance()const` |
| Color | `hex(hex:int)static` |
| Color | `hex64(hex:int)static` |
| Color | `html(rgba:String)static` |
| bool | `html_is_valid(color:String)static` |
| Color | `inverted()const` |
| bool | `is_equal_approx(to:Color)const` |
| Color | `lerp(to:Color, weight:float)const` |
| Color | `lightened(amount:float)const` |
| Color | `linear_to_srgb()const` |
| Color | `srgb_to_linear()const` |
| int | `to_abgr32()const` |
| int | `to_abgr64()const` |
| int | `to_argb32()const` |
| int | `to_argb64()const` |
| String | `to_html(with_alpha:bool= true)const` |
| int | `to_rgba32()const` |
| int | `to_rgba64()const` |

