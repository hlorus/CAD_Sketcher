Tools in CAD Sketcher are either exposed as a workspacetool or as an operator. Note however
that either of those use the same [interaction system](interaction_system.md).


## Generic Tools
::: CAD_Sketcher.operators.View3D_OT_slvs_add_sketch

::: CAD_Sketcher.operators.View3D_OT_slvs_delete_entity

::: CAD_Sketcher.operators.View3D_OT_slvs_delete_constraint


## Workspacetools
![!Workspacetools](images/workspacetools.png){style="height:160px; width:60px; object-fit:cover;" align=right}

Workspacetools are used to interactively create entities. You can access them from
the viewport's "T"-panel. Check the [tools section](tools.md) to get familiar with
the behavior of BGS tools.

> **INFO:** Interaction with addon geometry is only possible when one of the
addon tools is active.


### Workspacetool Access Keymap
Whenever one of the addon's tools is active the tool access keymap allows to quickly switch between the different tools.

|Key|Modifier|Action|
|:---:|---|---|
|ESC|-   |Activate Tool: Select|
|P|-   |Activate Tool: Add Point 2D|
|L|-   |Activate Tool: Add Line 2D|
|C|-   |Activate Tool: Add Circle|
|A|-   |Activate Tool: Add Arc|
|R|-   |Activate Tool: Add Rectangle|
|S|-   |Activate Tool: Add Sketch|

**Constraints:**
|Key|Modifier|Action|
|---|---|---|
|Shift + D|-   |Distance|
|Shift + A|-   |Angle|
|Shift + O|-   |Diameter|
|Shift + C|-   |Coincident|
|Shift + V|-   |Vertical|
|Shift + H|-   |Horizontal|
|Shift + E|-   |Equal|
|Shift + P|-   |Parallel|
|Shift + N|-   |Perpendicular|
|Shift + T|-   |Tangent|
|Shift + M|-   |Midpoint|
|Shift + R|-   |Ratio|

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


::: CAD_Sketcher.operators.View3D_OT_slvs_select
**Keymap:**

|Key|Modifier|Action|
|---|---|---|
|LMB|-   |Toggle Select|
|ESC|-   |Deselect All|


> **INFO:** LMB in empty space will also deselect all.

::: CAD_Sketcher.operators.View3D_OT_slvs_add_point3d

::: CAD_Sketcher.operators.View3D_OT_slvs_add_line3d

::: CAD_Sketcher.operators.View3D_OT_slvs_add_point2d

::: CAD_Sketcher.operators.View3D_OT_slvs_add_line2d

::: CAD_Sketcher.operators.View3D_OT_slvs_add_circle2d

::: CAD_Sketcher.operators.View3D_OT_slvs_add_arc2d

::: CAD_Sketcher.operators.View3D_OT_slvs_add_rectangle

::: CAD_Sketcher.operators.View3D_OT_slvs_add_workplane
