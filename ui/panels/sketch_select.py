from bpy.types import Context, UILayout

from .. import declarations
from . import VIEW3D_PT_sketcher_base
from ...model.sketch_ref import get_active_sketch, get_sketches


def sketch_selector(
    context: Context,
    layout: UILayout,
):
    row = layout.row(align=True)
    row.scale_y = 1.8
    active_sketch = get_active_sketch(context)

    if not active_sketch:
        row.operator(
            declarations.Operators.AddSketch,
            icon="ADD"
        ).wait_for_input = True

    else:
        row.operator(
            declarations.Operators.SetActiveSketch,
            text="Leave: " + active_sketch.name,
            icon="BACK",
            depress=True,
        ).sketch_name = ""
        row.active = True

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
