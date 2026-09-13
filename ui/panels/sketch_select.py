from bpy.types import Context, Menu, UILayout

from ...model.sketch_ref import get_active_sketch, get_sketches
from ...stateful_operator.constants import Operators as StatefulOps
from .. import declarations
from . import VIEW3D_PT_sketcher_base


class VIEW3D_MT_slvs_add_sketch(Menu):
    """Extra sketch-creation modes, kept out of the main row (currently the
    less-common free-3D sketch)."""

    bl_idname = declarations.Menus.AddSketch.value
    bl_label = "Add Sketch"

    def draw(self, context: Context):
        layout = self.layout
        # The 3D-sketch operator creates immediately (no placement gizmo), so it
        # is invoked directly rather than through a workspace tool.
        layout.operator(
            declarations.Operators.AddSketch3D.value,
            text="Add 3D Sketch",
            icon="ADD",
        )


def _draw_face_anchor(context: Context, layout: UILayout, sketch):
    """Show which mesh face the sketch's workplane follows, with ways to change it.

    An anchored workplane is moved back onto its face whenever the mesh updates,
    so a manual move silently reverts. Surfacing the anchor (not only once it
    breaks) lets the user see why, pick another face or free the workplane. The
    anchor belongs to the workplane, so say so when other sketches share it.
    """
    from ...utilities.face_anchor import (
        KEY_DETACHED,
        KEY_FACE_ID,
        KEY_SOURCE,
        is_origin_workplane,
    )

    wp = sketch.workplane_object
    if sketch.is_3d or not wp or is_origin_workplane(context.scene, wp):
        return

    shared = sum(1 for s in get_sketches(context) if s.workplane_object == wp)
    suffix = f" (shared by {shared} sketches)" if shared > 1 else ""
    ops = declarations.Operators
    anchored = KEY_FACE_ID in wp

    if anchored and wp.get(KEY_DETACHED):
        container = layout.box()
        container.alert = True
        container.label(text="Workplane detached from mesh face" + suffix, icon="ERROR")
    elif anchored:
        container = layout
        source = wp.get(KEY_SOURCE)
        container.label(
            text=f"Workplane anchored to {source.name if source else 'mesh face'}"
            + suffix,
            icon="SNAP_FACE",
        )
    else:
        container = layout

    row = container.row(align=True)
    row.operator(
        ops.ReattachWorkplane,
        text="Change Face" if anchored else "Anchor to Face",
        icon="EYEDROPPER",
    ).empty_name = wp.name
    if anchored:
        row.operator(
            ops.MakeWorkplaneFree, text="Make Free", icon="UNLINKED"
        ).empty_name = wp.name


def _draw_migration_prompt(context: Context, layout: UILayout):
    """Offer migration when the file holds legacy (entity-based) sketches.

    Such sketches don't render under the native-curve model, so without this
    prompt an old file would look empty. The check runs only while this panel is
    drawn -- never as a file-load handler for every user."""
    from ...utilities.migrate import scene_needs_migration

    if not scene_needs_migration(context):
        return

    box = layout.box()
    box.alert = True
    box.label(text="Legacy sketches detected", icon="ERROR")
    box.label(text="Saved by an older CAD Sketcher version.")
    box.operator(
        declarations.Operators.MigrateLegacy,
        text="Migrate to curves",
        icon="FILE_REFRESH",
    )


def sketch_selector(
    context: Context,
    layout: UILayout,
):
    row = layout.row(align=True)
    row.scale_y = 1.8
    active_sketch = get_active_sketch(context)

    if not active_sketch:
        # The common 2D sketch stays the prominent button; the free-3D mode is
        # demoted to a small dropdown beside it (still discoverable from the
        # panel, not just the toolbar fly-out / operator search).
        props = row.operator(
            StatefulOps.InvokeTool.value,
            text="Add Sketch",
            icon="ADD",
        )
        props.tool_name = declarations.WorkSpaceTools.AddSketch.value
        props.operator = declarations.Operators.AddSketch.value

        row.menu(declarations.Menus.AddSketch.value, text="", icon="DOWNARROW_HLT")

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

        _draw_migration_prompt(context, layout)
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

            _draw_face_anchor(context, layout, sketch)

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
