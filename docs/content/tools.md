Tools in CAD Sketcher are either exposed as a workspacetool or as an operator. Note however
that either of those use the same [interaction system](interaction_system.md).


## Generic Tools
::: CAD_Sketcher.operators.add_sketch.View3D_OT_slvs_add_sketch

::: CAD_Sketcher.operators.delete_entity.View3D_OT_slvs_delete_entity

::: CAD_Sketcher.operators.delete_constraint.View3D_OT_slvs_delete_constraint


## Workspacetools
![!Workspacetools](images/workspacetools.png){style="height:160px; width:60px; object-fit:cover;" align=right}

Workspacetools are used to interactively create entities. You can access them from
the viewport's "T"-panel. Check the [tools section](tools.md) to get familiar with
the behavior of CAD Sketcher tools.

> **INFO:** Interaction with extension geometry is only possible when one of the
extension tools is active.


### Workspacetool Access Keymap
Whenever one of the extension's tools is active the tool access keymap allows to quickly switch between the different tools.
These keys also work while a tool is running: the unfinished element is discarded and the new tool starts.
While typing a number, letters are read as units (e.g. `5cm`) instead.

|Key|Modifier|Action|
|:---:|---|---|
|Esc / Rmb|-   |Activate Tool: Select|
|P|-   |Invoke Tool: Add Point 2D|
|L|-   |Invoke Tool: Add Line 2D|
|C|-   |Invoke Tool: Add Circle|
|A|-   |Invoke Tool: Add Arc|
|R|-   |Invoke Tool: Add Rectangle|
|Y|-   |Invoke Tool: Trim|
|B|-   |Invoke Tool: Bevel|
|O|-   |Invoke Tool: Offset|
|D|-   |Invoke Tool: Dimension|
|J|-   |Invoke Tool: Project Geometry|

**Dimensional Constraints:**

These start the Dimension tool limited to one kind of dimension; plain D lets it
infer the kind from what you pick.

|Key|Modifier|Action|
|---|---|---|
|D|Alt   |Distance|
|V|Alt   |Vertical Distance|
|H|Alt   |Horizontal Distance|
|A|Alt   |Angle|
|O|Alt   |Diameter|
|R|Alt   |Radius|

**Geometric Constraints:**

|Key|Modifier|Action|
|---|---|---|
|C|Shift   |Coincident|
|V|Shift   |Vertical|
|H|Shift   |Horizontal|
|E|Shift   |Equal|
|A|Shift   |Parallel|
|P|Shift   |Perpendicular|
|T|Shift   |Tangent|
|M|Shift   |Midpoint|
|R|Shift   |Ratio|

### Editing Keymap
Available while any of the extension's tools is active.

|Key|Modifier|Action|
|:---:|---|---|
|X / Del|-|Delete selected entities|
|C|Ctrl|Copy|
|V|Ctrl|Paste|
|D|Shift|Duplicate & move|
|G|-|Move|
|V|-|Align view to the active entity|
|M|Alt|Merge points|
|C|Alt+Shift|Toggle construction mode|

### Fillet
Round picked edges of an object built from a sketch (or any mesh). Activate the
Fillet tool and keep clicking edges to round them; clicking a rounded edge again
drops it, and each pick is its own undo step. The picks are stored on the object's
Fillet modifier: Amount sets the width, and Segments the roundness (1, the
default, gives a flat fillet).

While the Fillet tool is active, filleted objects show without their fillet, so a
click always lands on the geometry the fillet reads and the picked edges keep
their numbering; confirming (Esc or right-click) goes back to Blender's Select tool and shows the
rounded result.

|Key|Modifier|Action|
|:---:|---|---|
|Lmb|-|Round the edge under the cursor, or drop it again|
|Esc / Rmb|-|Confirm: keep the picks and go back to Blender's Select tool|

### Global Shortcuts
Available in Object Mode regardless of the active tool, also while a tool is running.

|Key|Modifier|Action|
|:---:|---|---|
|A|Ctrl+Shift|Add sketch / leave the active sketch|
|E|Ctrl+Shift|Extrude|
|R|Ctrl+Shift|Revolve|
|D|Ctrl+Shift|Linear array|
|B|Ctrl+Shift|Boolean|
|F|Ctrl+Shift|Fillet picked edges|
|M|Ctrl+Shift|Open the CAD Sketcher pie menu (drawing tools and constraints)|
|Esc|Shift|Switch to Blender's Select tool|

### Basic Tool Keymap
The basic tool interaction is consistent between tools.

|Key|Modifier|Action|
|:---:|---|---|
|Tab|-|Jump to next tool state or property substate when in numerical edit|
|0-9 / (-)|-|Activate numeric edit|
|Enter / Lmb|-|Verify the operation|
|Lmb (drag)|-|Draw by dragging: press, drag past the Drag Threshold (Preferences > Input), release|
|Esc / Rmb|-|Cancel the operation|
|Z|Ctrl|Cancel the operation (like Esc); press again to undo|

**While numeric edit is active**

|Key|Modifier|Action|
|:---:|---|---|
|Tab|-|Jump to next tool property substate|
|0-9|-|Activate numeric edit|
|Minus(-)|-|Toggle between positive and negative values|

### Selection tools
::: CAD_Sketcher.operators.select.View3D_OT_slvs_select

::: CAD_Sketcher.operators.select.View3D_OT_slvs_select_all

::: CAD_Sketcher.operators.select.View3D_OT_slvs_select_invert

::: CAD_Sketcher.operators.select.View3D_OT_slvs_select_extend

::: CAD_Sketcher.operators.select.View3D_OT_slvs_select_extend_all

**Keymap:**

|Key|Modifier|Action|
|---|---|---|
|LMB (click)|-   |Toggle select|
|LMB (click)|Shift|Extend selection|
|LMB (click)|Ctrl|Subtract from selection|
|LMB (click)|Alt|Select the next entity in the overlapping stack under the cursor|
|Wheel|Alt|Cycle the hovered entity through overlapping ones without selecting|
|LMB (drag)|-|Box select, or tweak the hovered entity|
|LMB (drag)|Shift|Box select (extend)|
|LMB (drag)|Ctrl|Box select (subtract)|
|A|Ctrl|Select all|
|Esc|-   |Deselect all|
|I|Ctrl |Invert selection|
|E|Ctrl |Extend selection in chain|
|E|Ctrl+Shift   |Select full chain|
|Rmb|-|Open the context menu|

> **INFO:** LMB in empty space will also deselect all.

> **INFO:** Chain selection works with coincident constraints too

> **INFO:** When entities overlap, a plain click grabs the nearest one. Alt+click
steps to the next entity down (repeat to dig through the stack), and Alt+wheel
cycles the hovered entity so you can preview before clicking. This also works
while picking geometry inside a drawing or constraint tool.

::: CAD_Sketcher.operators.add_point_2d.View3D_OT_slvs_add_point2d

::: CAD_Sketcher.operators.add_line_2d.View3D_OT_slvs_add_line2d

::: CAD_Sketcher.operators.add_circle.View3D_OT_slvs_add_circle2d

::: CAD_Sketcher.operators.add_arc.View3D_OT_slvs_add_arc2d

::: CAD_Sketcher.operators.add_arc.View3D_OT_slvs_add_arc3pt2d

::: CAD_Sketcher.operators.add_rectangle.View3D_OT_slvs_add_rectangle

::: CAD_Sketcher.operators.trim.View3D_OT_slvs_trim

::: CAD_Sketcher.operators.project_geometry.VIEW3D_OT_slvs_project_geometry

Project Geometry brings a mesh object's edges into the active sketch as native
construction points and lines. The projected points stay linked to their source
vertices, so editing or transforming the source object updates the projection.

### Workplane tools
A workplane is any Blender object whose transform defines the sketch plane (see
[code documentation](code_docs.md)). These operators manage the workplane an
active sketch is anchored to.

::: CAD_Sketcher.operators.align_workplane.View3D_OT_slvs_align_workplane_cursor

::: CAD_Sketcher.operators.workplane_anchor.View3D_OT_slvs_make_workplane_free

::: CAD_Sketcher.operators.workplane_anchor.View3D_OT_slvs_reattach_workplane
