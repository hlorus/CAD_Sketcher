Tools in Geometry Sketcher are either exposed as a workspacetool or as an operator. Note however
that either of those use the same [interaction system](interaction_system.md).

## Generic Tools
::: geometry_sketcher.operators.View3D_OT_slvs_add_sketch

::: geometry_sketcher.operators.View3D_OT_slvs_delete_entity

::: geometry_sketcher.operators.View3D_OT_slvs_delete_constraint


## Workspacetools
![!Workspacetools](images/workspacetools.png){style="height:160px; width:60px; object-fit:cover;" align=right}

Workspacetools are used to interactivley create entities. You can access them from
the viewport's "T"-panel. Check the [tools section](tools.md) to get familiar with
the behavior of BGS tools.

> **INFO:** Interaction with addon geometry is only possible when one of the
addon tools is active.





::: geometry_sketcher.operators.View3D_OT_slvs_select
**Keymap:**

|Key|Modifier|Action|
|---|---|---|
|LMB|-   |Toggle Select|
|ESC|-   |Deselect All|

> **INFO:** LMB in empty space will also deselect all.

::: geometry_sketcher.operators.View3D_OT_slvs_add_point3d

::: geometry_sketcher.operators.View3D_OT_slvs_add_line3d

::: geometry_sketcher.operators.View3D_OT_slvs_add_point2d

::: geometry_sketcher.operators.View3D_OT_slvs_add_line2d

::: geometry_sketcher.operators.View3D_OT_slvs_add_circle2d

::: geometry_sketcher.operators.View3D_OT_slvs_add_arc2d

::: geometry_sketcher.operators.View3D_OT_slvs_add_rectangle

::: geometry_sketcher.operators.View3D_OT_slvs_add_workplane
