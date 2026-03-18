# PathFollow2D

## Description

This node takes its parent Path2D, and returns the coordinates of a point within it, given a distance from the first vertex.

It is useful for making other nodes follow a path, without coding the movement pattern. For that, the nodes must be children of this node. The descendant nodes will then move accordingly when setting the progress in this node.


## Properties

| Type | Name | Default |
| --- | --- | --- |
| float | `h_offset` | 0.0 |
| bool | `loop` | true |
| float | `progress` | 0.0 |
| float | `progress_ratio` | 0.0 |
| bool | `rotates` | true |
| float | `v_offset` | 0.0 |

