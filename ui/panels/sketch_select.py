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


def _anchor_name(wp) -> str:
    """Name the anchor as "<mesh>, face <index>" (or "<n> faces" once split)."""
    from ...utilities.face_anchor import KEY_FACE_ID, KEY_SOURCE, anchor_face_indices

    source = wp.get(KEY_SOURCE)
    if source is None:
        return "mesh face"
    faces = []
    # Edit-mode mesh data is stale until the mode is left; just name the object.
    if source.type == "MESH" and source.mode != "EDIT":
        faces = anchor_face_indices(source.data, wp[KEY_FACE_ID])
    if len(faces) == 1:
        return f"{source.name}, face {faces[0]}"
    if faces:
        return f"{source.name}, {len(faces)} faces"
    return source.name


class VIEW3D_MT_slvs_sketch_workplane(Menu):
    """Occasional actions on the active sketch's workplane."""

    bl_idname = declarations.Menus.SketchWorkplane.value
    bl_label = "Workplane"

    def draw(self, context: Context):
        from ...utilities.face_anchor import KEY_FACE_ID

        layout = self.layout
        ops = declarations.Operators
        layout.operator(ops.ChangeSketchWorkplane, icon="EYEDROPPER")
        sketch = get_active_sketch(context)
        wp = sketch.workplane_object if sketch else None
        if wp is not None and KEY_FACE_ID in wp:
            layout.operator(
                ops.MakeWorkplaneFree, icon="UNLINKED"
            ).sketch_name = sketch.target_object.name


def _has_selected_part(context: Context) -> bool:
    """Whether the selection holds anything that belongs to a part."""
    from ...utilities.part import part_root_of

    return any(part_root_of(obj) is not None for obj in context.selected_objects)


def _draw_workplane(context: Context, layout: UILayout, sketch):
    """Show the sketch's workplane and its face anchor, actions in a dropdown.

    An anchored workplane is moved back onto its face whenever the mesh updates,
    so a manual move silently reverts. Surfacing the anchor (not only once it
    breaks) lets the user see why and free the workplane.
    """
    from ...utilities.face_anchor import KEY_DETACHED, KEY_FACE_ID

    if sketch.is_3d:
        return
    wp = sketch.workplane_object
    anchored = wp is not None and KEY_FACE_ID in wp

    # Same label/value split as the Name row above.
    split = layout.split(factor=0.4)
    left = split.row()
    left.alignment = "RIGHT"
    left.label(text="Workplane")
    row = split.row(align=True)

    if anchored and wp.get(KEY_DETACHED):
        row.alert = True
        row.label(text="Detached from face", icon="ERROR")
    elif anchored:
        row.label(text=_anchor_name(wp), icon="LINKED")
    else:
        # No workplane object means the sketch *is* its own plane (it owns its
        # transform), which is not the same as missing one.
        row.label(text=wp.name if wp else "Own frame")
    row.menu(declarations.Menus.SketchWorkplane.value, text="", icon="DOWNARROW_HLT")


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

            layout.separator()

            row = layout.row()
            row.prop(sketch.target_object, "name", text="Name")
            _draw_workplane(context, layout, sketch)

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

            # Grouping parts is a scene-level act, so it belongs here rather than
            # inside a sketch: it takes the selected parts into one assembly.
            layout.separator()
            row = layout.row()
            row.enabled = _has_selected_part(context)
            row.operator(
                declarations.Operators.AddAssembly.value,
                text="Add Assembly",
                icon="OUTLINER_OB_GROUP_INSTANCE",
            )
