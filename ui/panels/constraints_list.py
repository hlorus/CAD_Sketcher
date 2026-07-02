from bpy.types import Context, UILayout

from .. import declarations
from .. import types
from . import VIEW3D_PT_sketcher_base
from ...model.sketch_ref import get_active_sketch


def draw_constraint_listitem(
    context: Context, layout: UILayout, constraint: types.GenericConstraint
):
    sketch = get_active_sketch(context)
    if not sketch:
        return
    index = sketch.constraints.get_index(constraint)
    row = layout.row()

    # Visible/Hidden property
    row.prop(
        constraint,
        "visible",
        icon_only=True,
        icon=("HIDE_OFF" if constraint.visible else "HIDE_ON"),
        emboss=False,
    )
    row.label(text=str(constraint))

    # Failed indicator
    if constraint.failed:
        row.label(text="", icon="ERROR")

    # Delete button
    props = row.operator(
        declarations.Operators.DeleteConstraint,
        text="",
        icon="X",
        emboss=False,
    )
    props.type = constraint.type
    props.index = index


class VIEW3D_PT_sketcher_constraints(VIEW3D_PT_sketcher_base):
    bl_label = "Constraints"
    bl_idname = declarations.Panels.SketcherConstraints

    @classmethod
    def poll(cls, context):
        return get_active_sketch(context) is not None

    def draw(self, context: Context):
        layout = self.layout
        sketch = get_active_sketch(context)
        if not sketch:
            return

        layout.operator(
            declarations.Operators.SetAllConstraintsVisibility,
            text="",
            icon="VIS_SEL_11",
        ).visibility = "SHOW"
        layout.operator(
            declarations.Operators.SetAllConstraintsVisibility,
            text="",
            icon="VIS_SEL_01",
        ).visibility = "HIDE"
        layout.prop(
            context.scene.sketcher,
            "selectable_constraints",
            text="",
            icon_only=True,
            icon="RESTRICT_SELECT_OFF",
        )

        row = layout.row()
        row.operator(
            declarations.Operators.SetAllConstraintsVisibility,
            text="Show All",
        ).visibility = "SHOW"
        row.operator(
            declarations.Operators.SetAllConstraintsVisibility,
            text="Hide All",
        ).visibility = "HIDE"
        layout.prop(
            context.scene.sketcher,
            "selectable_constraints",
            text="Selectable",
        )

        # Dimensional Constraints
        layout.label(text="Dimensional:")
        box = layout.box()
        col = box.column(align=True)
        col.scale_y = 0.8

        for c in sketch.constraints.dimensional:
            draw_constraint_listitem(context, col, c)

        # Geometric Constraints
        layout.label(text="Geometric:")
        box = layout.box()
        col = box.column(align=True)
        col.scale_y = 0.8

        for c in sketch.constraints.geometric:
            draw_constraint_listitem(context, col, c)
