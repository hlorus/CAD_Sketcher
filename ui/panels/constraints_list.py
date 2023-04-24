from bpy.types import Context, UILayout

from .. import declarations
from .. import types
from . import VIEW3D_PT_sketcher_base


def draw_constraint_listitem(
    context: Context, layout: UILayout, constraint: types.GenericConstraint
):
    """
    Creates a single row inside the ``layout`` describing
    the ``constraint``.
    """
    index = context.scene.sketcher.constraints.get_index(constraint)
    row = layout.row()

    # Visible/Hidden property
    row.prop(
        constraint,
        "visible",
        icon_only=True,
        icon=("HIDE_OFF" if constraint.visible else "HIDE_ON"),
        emboss=False,
    )

    # Failed hint
    row.label(
        text="",
        icon=("ERROR" if constraint.failed else "CHECKMARK"),
    )

    # Label
    row.prop(constraint, "name", text="")

    # Constraint Values
    middle_sub = row.row()

    for constraint_prop in constraint.props:
        middle_sub.prop(constraint, constraint_prop, text="")

    # Context menu, shows constraint name
    props = row.operator(
        declarations.Operators.ContextMenu,
        text="",
        icon="OUTLINER_DATA_GP_LAYER",
        emboss=False,
    )
    props.type = constraint.type
    props.index = index
    props.highlight_hover = True
    props.highlight_active = True
    props.highlight_members = True

    # Delete operator
    props = row.operator(
        declarations.Operators.DeleteConstraint,
        text="",
        icon="X",
        emboss=False,
    )
    props.type = constraint.type
    props.index = index
    props.highlight_hover = True
    props.highlight_members = True


class VIEW3D_PT_sketcher_constraints(VIEW3D_PT_sketcher_base):
    """
    Constraints Menu: List of entities in the sketch.
    Interactive
    """

    bl_label = "Constraints"
    bl_idname = declarations.Panels.SketcherConstraints
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: Context):
        layout = self.layout

        # Visibility Operators
        col = layout.column(align=True)
        col.operator_enum(
            declarations.Operators.SetAllConstraintsVisibility,
            "visibility",
        )

        # Dimensional Constraints
        layout.label(text="Dimensional:")
        box = layout.box()
        col = box.column(align=True)
        col.scale_y = 0.8

        sketch = context.scene.sketcher.active_sketch
        for c in context.scene.sketcher.constraints.dimensional:
            if not c.is_active(sketch):
                continue
            draw_constraint_listitem(context, col, c)

        # Geometric Constraints
        layout.label(text="Geometric:")
        box = layout.box()
        col = box.column(align=True)
        col.scale_y = 0.8

        sketch = context.scene.sketcher.active_sketch
        for c in context.scene.sketcher.constraints.geometric:
            if not c.is_active(sketch):
                continue
            draw_constraint_listitem(context, col, c)
