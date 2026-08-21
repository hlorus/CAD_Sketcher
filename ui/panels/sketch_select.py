from bpy.types import Context, UILayout

from ...model.sketch_ref import get_active_sketch, get_sketches
from ...stateful_operator.constants import Operators as StatefulOps
from .. import declarations
from . import VIEW3D_PT_sketcher_base


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
        # Keep both creation modes explicit in the sidebar. The workspace tools
        # remain grouped in the toolbar, but relying on that fly-out alone makes
        # the native 3D entry point effectively undiscoverable from the panel
        # and operator search on some Blender versions.
        props = row.operator(
            StatefulOps.InvokeTool.value,
            text="Add Sketch",
            icon="ADD",
        )
        props.tool_name = declarations.WorkSpaceTools.AddSketch.value
        props.operator = declarations.Operators.AddSketch.value

        props_3d = row.operator(
            StatefulOps.InvokeTool.value,
            text="Add 3D Sketch",
            icon="ADD",
        )
        props_3d.tool_name = declarations.WorkSpaceTools.AddSketch3D.value
        props_3d.operator = declarations.Operators.AddSketch3D.value

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
            row.prop(sketch.target_object, "name", text="Name")

        else:
            # Sketch list — a scrollable UIList over scene.objects, filtered to
            # sketch objects (see VIEW3D_UL_sketches.filter_items).
            if any(True for _ in get_sketches(context)):
                layout.template_list(
                    "VIEW3D_UL_sketches",
                    "",
                    context.scene,
                    "objects",
                    context.scene.sketcher,
                    "ui_active_sketch",
                    rows=3,
                )
