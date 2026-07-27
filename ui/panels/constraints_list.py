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

    # Editable name
    row.prop(constraint, "name", text="")

    # Editable value(s). Dimensional constraints store their value in a scene
    # custom property (scene["slvs:c:{uid}"]); draw that endpoint so it stays
    # editable and driver-friendly. Other props fall back to a direct field.
    value_sub = row.row()
    for constraint_prop in constraint.props:
        key = None
        if constraint_prop == "value" and getattr(constraint, "constraint_uid", ""):
            key = context.scene.sketcher.get_constraint_value_endpoint(constraint)
        if key:
            value_sub.prop(context.scene, f'["{key}"]', text="")
        else:
            value_sub.prop(constraint, constraint_prop, text="")

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
    # Highlight the constraint and the geometry it acts on while hovering.
    props.highlight_hover = True
    props.highlight_members = True


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

        row = layout.row(align=True)
        row.operator(
            declarations.Operators.SetAllConstraintsVisibility,
            text="Show All",
        ).visibility = "SHOW"
        row.operator(
            declarations.Operators.SetAllConstraintsVisibility,
            text="Hide All",
        ).visibility = "HIDE"

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
