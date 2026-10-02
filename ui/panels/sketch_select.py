from bpy.types import Context, Menu, UILayout

from ...model.sketch_ref import get_active_sketch
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


def _draw_list_header(context, layout) -> None:
    """Say what the list below is showing, and act on it.

    Always the same row -- what it is, then the menu -- so the menu does not come
    and go with the selection: it is where a part is made in the first place, and
    where a hidden one is brought back.

    The part itself lives here: its name, whether it is shown, and the verbs that
    act on the whole of it. What it is *made of* stays in the list below, base
    feature included, so the delete that would take the whole part is never in
    the same column as one that takes a single feature.
    """
    from ...ui.feature_list import ASSEMBLY, PART, list_scope

    scope, root = list_scope(context)
    row = layout.row(align=True)

    if scope == PART:
        row.operator(
            declarations.Operators.SetPartVisibility,
            text="",
            icon="HIDE_ON" if root.hide_get() else "HIDE_OFF",
            emboss=False,
        ).part_name = root.name
        row.prop(root, "name", text="", emboss=False)
    elif scope == ASSEMBLY:
        row.label(text="", icon="OUTLINER_OB_GROUP_INSTANCE")
        row.prop(root, "name", text="", emboss=False)
    else:
        row.label(text="", icon="OUTLINER_COLLECTION")
        row.label(text="All Parts")

    # Everything that acts on this part, from the same menu the context menus and
    # the sidebar draw. Present whatever the list is showing: with no part it is
    # how one is made.
    row.menu(declarations.Menus.Part.value, text="", icon="DOWNARROW_HLT")

    if scope == ASSEMBLY:
        layout.label(text="Parts in this assembly")


def part_sketches(context, root):
    """The sketches of the part rooted at ``root``, the root's own first.

    The sketch the root body is made from leads, since that is the part itself;
    the rest follow in name order so the menu is stable while you work. Before
    the source/body split the root *was* a sketch and led by being itself, which
    a mesh root never is.
    """
    from ...model.sketch_ref import is_sketch_object
    from ...utilities.body import sketch_of
    from ...utilities.part import part_root_of

    members = [
        obj
        for obj in context.scene.objects
        if is_sketch_object(obj) and part_root_of(obj) == root
    ]
    own = sketch_of(root)
    members.sort(key=lambda obj: (obj != own and obj != root, obj.name))
    return members


class VIEW3D_MT_slvs_part_sketches(Menu):
    """The sketches of the part under the cursor, so any of them can be edited.

    A part holds more than the sketch that made it: cutters live in it too, and
    those are hidden while they cut, so this menu is how they are reached from
    the viewport at all.
    """

    bl_idname = declarations.Menus.PartSketches.value
    bl_label = "Edit Sketch"

    def draw(self, context: Context):
        from ...model.sketch_ref import is_sketch_object
        from ...ui.feature_list import cutting_bodies
        from ...utilities.body import body_of
        from ...utilities.part import part_root_of

        obj = context.active_object
        root = part_root_of(obj) or (obj if is_sketch_object(obj) else None)
        if root is None:
            return

        layout = self.layout
        # The list is keyed on bodies; this menu lists the sketches behind them,
        # so each is traced to its body to say whether it is cutting.
        cutting = cutting_bodies(context.scene)
        for sketch_obj in part_sketches(context, root):
            body = body_of(sketch_obj)
            marks = {sketch_obj.name} | ({body.name} if body is not None else set())
            icon = "MOD_BOOLEAN" if marks & cutting else "OUTLINER_DATA_GP_LAYER"
            layout.operator(
                declarations.Operators.SetActiveSketch,
                text=sketch_obj.name,
                icon=icon,
            ).sketch_name = sketch_obj.name


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
    """Offer to update a file that an older version saved.

    Said in the file's terms rather than the feature's: what a given version
    changed is not the user's problem, and one button applies whatever this file
    needs. The severity is worth distinguishing though, since sketches from an
    entity-based version do not render at all until they are converted, while
    everything else keeps working meanwhile.

    The checks run only while this panel is drawn, never as a file-load handler
    for every user."""
    from ...utilities.migrate import scene_needs_migration
    from ...utilities.part import needs_part_migration

    unreadable = scene_needs_migration(context)
    if not unreadable and not needs_part_migration(context.scene):
        return

    box = layout.box()
    box.alert = unreadable
    box.label(
        text="Saved by an older version",
        icon="ERROR" if unreadable else "INFO",
    )
    if unreadable:
        box.label(text="Its sketches stay hidden until it is updated.")
    box.operator(
        declarations.Operators.MigrateLegacy,
        text="Update File",
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
            # The part row is drawn whether or not there is a list under it: it
            # carries the menu, and that is where a part is made in the first
            # place -- gating it on the parts that exist would leave a file with
            # none no way to start one.
            _draw_list_header(context, layout)

            # Feature list — a scrollable UIList over scene.objects, filtered to
            # the bodies worth listing (see VIEW3D_UL_features.filter_items).
            # Gated on the rows the list would draw, not on a sketch existing: a
            # part built from imported geometry has bodies and no sketch at all.
            from ...ui.feature_list import is_feature_row

            if any(is_feature_row(obj) for obj in context.scene.objects):
                layout.template_list(
                    "VIEW3D_UL_features",
                    "",
                    context.scene,
                    "objects",
                    context.scene.sketcher,
                    "ui_active_feature",
                    # Each feature brings a second row for the sketch that draws
                    # it, so three is barely one feature.
                    rows=6,
                )
