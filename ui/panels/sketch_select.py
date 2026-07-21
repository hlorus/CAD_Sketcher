from bpy.types import Context, UILayout

from .. import declarations
from . import VIEW3D_PT_sketcher_base
from ...model.sketch_ref import get_active_sketch, get_sketches
from ...stateful_operator.constants import Operators as StatefulOps


def _draw_detached_warning(layout: UILayout, sketch):
    """Warn when the sketch's workplane lost its anchoring mesh face."""
    from ...utilities.face_anchor import KEY_DETACHED

    wp = sketch.workplane_object
    if not wp or not wp.get(KEY_DETACHED):
        return

    box = layout.box()
    box.alert = True
    box.label(text="Workplane detached from mesh face", icon="ERROR")
    row = box.row(align=True)
    row.operator(
        declarations.Operators.ReattachWorkplane, text="Re-attach", icon="EYEDROPPER"
    ).empty_name = wp.name
    row.operator(
        declarations.Operators.MakeWorkplaneFree, text="Make Free", icon="UNLINKED"
    ).empty_name = wp.name


def sketch_selector(
    context: Context,
    layout: UILayout,
):
    row = layout.row(align=True)
    row.scale_y = 1.8
    active_sketch = get_active_sketch(context)

    if not active_sketch:
        # Switch to the Add Sketch tool (which shows the workplane gizmo) and
        # invoke the operator; a pre-selected workplane empty creates the sketch
        # immediately, otherwise the user picks one interactively.
        props = row.operator(
            StatefulOps.InvokeTool.value,
            text="Add Sketch",
            icon="ADD",
        )
        props.tool_name = declarations.WorkSpaceTools.AddSketch.value
        props.operator = declarations.Operators.AddSketch.value

    else:
        row.operator(
            declarations.Operators.SetActiveSketch,
            text="Leave: " + active_sketch.name,
            icon="BACK",
            depress=True,
        ).sketch_name = ""
        row.active = True

    row.alert = bool(active_sketch and not active_sketch.geometry_solved)
    row.operator(declarations.Operators.Update, icon="FILE_REFRESH", text="")


class VIEW3D_PT_sketcher(VIEW3D_PT_sketcher_base):
    """Menu for selecting the sketch you want to enter into"""

    bl_label = "Sketcher"
    bl_idname = declarations.Panels.Sketcher

    def draw(self, context: Context):
        layout = self.layout

        sketch_selector(context, layout)
        sketch = get_active_sketch(context)
        layout.use_property_split = True
        layout.use_property_decorate = False

        if sketch:
            # Sketch info
            row = layout.row()
            row.alignment = "CENTER"
            row.scale_y = 1.2

            if sketch.solver_state != "OKAY":
                state = sketch.get_solver_state()
                row.label(text=state.name, icon=state.icon)
            else:
                dof = sketch.dof
                dof_ok = dof <= 0
                dof_msg = (
                    "Fully defined sketch"
                    if dof_ok
                    else "Degrees of freedom: " + str(dof)
                )
                dof_icon = "CHECKMARK" if dof_ok else "ERROR"
                row.label(text=dof_msg, icon=dof_icon)

            _draw_detached_warning(layout, sketch)

            layout.separator()

            row = layout.row()
            row.label(text=sketch.name)

        else:
            # Sketch list
            sketches = list(get_sketches(context))
            if sketches:
                col = layout.box().column(align=True)
                for sk in sketches:
                    row = col.row(align=True)

                    # Edit sketch (left aligned)
                    sub = row.row()
                    sub.alignment = "LEFT"
                    op = sub.operator(
                        declarations.Operators.SetActiveSketch,
                        text=sk.name,
                        icon="OUTLINER_DATA_GP_LAYER",
                        emboss=False,
                    )
                    op.sketch_name = sk.name

                    # Delete sketch (right aligned)
                    sub = row.row()
                    sub.alignment = "RIGHT"
                    op = sub.operator(
                        declarations.Operators.DeleteSketch,
                        text="",
                        icon="X",
                        emboss=False,
                    )
                    op.sketch_name = sk.name
