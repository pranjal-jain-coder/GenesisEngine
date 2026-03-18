# VisibleOnScreenNotifier2D

## Description

VisibleOnScreenNotifier2D represents a rectangular region of 2D space. When any part of this region becomes visible on screen or in a viewport, it will emit a screen_entered signal, and likewise it will emit a screen_exited signal when no part of it remains visible.

If you want a node to be enabled automatically when this region is visible on screen, use VisibleOnScreenEnabler2D.

Note: VisibleOnScreenNotifier2D uses the render culling code to determine whether it's visible on screen, so it won't function unless CanvasItem.visible is set to true.


## Properties

| Type | Name | Default |
| --- | --- | --- |
| bool | `show_rect` | true |


## Methods

| Return | Name |
| --- | --- |


## Signals


