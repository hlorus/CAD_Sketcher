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

|Key|Modifier|Action|
|:---:|---|---|
|ESC|-   |Activate Tool: Select|
|P|-   |Invoke Tool: Add Point 2D|
|L|-   |Invoke Tool: Add Line 2D|
|C|-   |Invoke Tool: Add Circle|
|A|-   |Invoke Tool: Add Arc|
|R|-   |Invoke Tool: Add Rectangle|
|S|-   |Invoke Tool: Add Sketch|
|Y|-   |Invoke Tool: Trim|

**Dimensional Constraints:**

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
|P|Shift   |Parallel|
|N|Shift   |Perpendicular|
|T|Shift   |Tangent|
|M|Shift   |Midpoint|
|R|Shift   |Ratio|

### Basic Tool Keymap
The basic tool interaction is consistent between tools.

|Key|Modifier|Action|
|:---:|---|---|
|Tab|-|Jump to next tool state or property substate when in numerical edit|
|0-9 / (-)|-|Activate numeric edit|
|Enter / Lmb|-|Verify the operation|
|Esc / Rmb|-|Cancel the operation|

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
|LMB|-   |Toggle Select|
|ESC|-   |Deselect All|
|I|Ctrl |Inverse selection|
|E|Ctrl |Extend selection in chain|
|E|Ctrl+Shift   |Select full chain|

> **INFO:** LMB in empty space will also deselect all.

> **INFO:** Chain selection works with coincident constraints too

::: CAD_Sketcher.operators.add_point_3d.View3D_OT_slvs_add_point3d

::: CAD_Sketcher.operators.add_line_3d.View3D_OT_slvs_add_line3d

::: CAD_Sketcher.operators.add_point_2d.View3D_OT_slvs_add_point2d

::: CAD_Sketcher.operators.add_line_2d.View3D_OT_slvs_add_line2d

::: CAD_Sketcher.operators.add_circle.View3D_OT_slvs_add_circle2d

::: CAD_Sketcher.operators.add_arc.View3D_OT_slvs_add_arc2d

::: CAD_Sketcher.operators.add_rectangle.View3D_OT_slvs_add_rectangle

::: CAD_Sketcher.operators.add_workplane.View3D_OT_slvs_add_workplane

::: CAD_Sketcher.operators.add_workplane.View3D_OT_slvs_add_workplane_face

::: CAD_Sketcher.operators.trim.View3D_OT_slvs_trim
