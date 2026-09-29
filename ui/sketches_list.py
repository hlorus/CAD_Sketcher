import bpy
from bpy.types import Context, PropertyGroup, UILayout, UIList

from ..declarations import Operators
from ..model.sketch_ref import Sketch, is_sketch_object


def cutting_bodies(scene) -> set:
    """Names of the bodies currently feeding a boolean, so cutting rows say so.

    Gathered in one pass because the list needs it per row, and a per-row scan of
    every object's modifiers would run as often as the panel redraws.
    """
    from ..operators.modifiers import boolean_cutters

    cutting = set()
    for body in scene.objects:
        for cutter in boolean_cutters(body):
            cutting.add(cutter.name)
    return cutting


def row_parts(obj):
    """(body, sketch) for a row: what it is built from, and what drew it.

    Rows are bodies -- the body is what a part is built from, what carries the
    features, and what the name belongs to -- but either half can be missing. A
    mesh joined to a part by hand was never drawn, so it has no sketch; a file
    from before every sketch got a body holds a sketch with no body.
    """
    from ..utilities.body import is_body, sketch_of

    if is_body(obj):
        return obj, sketch_of(obj)
    if is_sketch_object(obj):
        return None, obj
    return obj, None


def is_feature_row(obj) -> bool:
    """Whether ``obj`` earns a row of its own.

    A body, a mesh that belongs to a part without being one (imported geometry
    joined by hand), or a bodyless sketch from an older file. A sketch that has a
    body is listed through it, not twice.
    """
    from ..utilities.body import body_of, is_body
    from ..utilities.part import is_part_root, part_root_of

    if is_body(obj):
        return True
    if is_sketch_object(obj):
        return body_of(obj) is None
    return obj.type == "MESH" and (is_part_root(obj) or part_root_of(obj) is not None)


class VIEW3D_UL_sketches(UIList):
    """List of the bodies (features) in the scene, or in the part in focus.

    Bound to ``scene.objects`` and filtered down in ``filter_items`` -- no
    separate backing collection is required. Each row lets you toggle what is
    shown, enter the sketch behind it, rename and delete it.
    """

    def draw_item(
        self,
        context: Context,
        layout: UILayout,
        data: PropertyGroup,
        item: PropertyGroup,
        icon: int,
        active_data: PropertyGroup,
        active_propname: str,
        index: int = 0,
    ):
        obj = item

        if self.layout_type in {"DEFAULT", "COMPACT"}:
            if not obj:
                layout.label(text="", translate=False, icon="OUTLINER_OB_MESH")
                return

            body, sketch = row_parts(obj)
            row = layout.row(align=True)

            if sketch is not None:
                # Visibility toggle (eye): the sketch's own curves, which are
                # hidden from the moment it is created. Not the body, which
                # carries the features and looks nothing like the profile.
                row.operator(
                    Operators.SetSketchVisibility,
                    text="",
                    icon="HIDE_ON" if sketch.hide_viewport else "HIDE_OFF",
                    emboss=False,
                ).sketch_name = sketch.name
            else:
                # A body with no sketch (an imported mesh made a part by hand):
                # there is no profile to show or hide.
                row.label(text="", icon="MESH_DATA")

            # The cutter is the body, or the sketch itself in a file from before
            # bodies existed, which carried the stack on the sketch.
            cutter = body or sketch
            if cutter is not None and cutter.name in getattr(self, "_cutting", ()):
                # A cutter is hidden while it cuts, so its solid has no other
                # control anywhere: without this the body looks deleted.
                row.operator(
                    Operators.SetCutterVisibility,
                    text="",
                    icon="RESTRICT_VIEW_ON"
                    if cutter.hide_viewport
                    else "RESTRICT_VIEW_OFF",
                    emboss=False,
                ).body_name = cutter.name

            # Editable name -- expands to fill, pushing the icons below to the
            # right edge of the row (standard Blender UIList layout). The body's
            # name, since the sketch's is derived from it: typing one here would
            # be re-derived away on the next update.
            row.prop(body or sketch, "name", text="", emboss=False)

            # Trailing controls: solver-state, enter (edit), delete
            if sketch is not None and sketch.get("solver_state", "OKAY") != "OKAY":
                state = Sketch(sketch).get_solver_state()
                row.label(text="", icon=state.icon)

            enter = row.row(align=True)
            enter.enabled = sketch is not None
            enter.operator(
                Operators.SetActiveSketch,
                text="",
                icon="OUTLINER_DATA_GP_LAYER",
                emboss=False,
            ).sketch_name = sketch.name if sketch is not None else ""

            self._draw_delete(row, body, sketch)

        elif self.layout_type in {"GRID"}:
            layout.alignment = "CENTER"
            layout.label(text="", icon="OUTLINER_OB_MESH")

    @staticmethod
    def _draw_delete(row, body, sketch) -> None:
        """Delete the row as the thing it is: a feature, a part, or a sketch."""
        from ..operators.delete_part import feature_root
        from ..utilities.part import is_part_root

        if body is not None and feature_root(body) is not None:
            row.operator(
                Operators.DeleteFeature, text="", icon="X", emboss=False
            ).feature_name = body.name
            return
        if body is not None and is_part_root(body):
            row.operator(
                Operators.DeletePart, text="", icon="X", emboss=False
            ).part_name = body.name
            return
        if sketch is not None:
            row.operator(
                Operators.DeleteSketch, text="", icon="X", emboss=False
            ).sketch_name = sketch.name

    def filter_items(self, context: Context, data, propname):
        """Show the bodies worth listing; honor the built-in name search box.

        Scoped to the part in focus when there is one, so the list says which
        part you are looking at instead of pooling every body in the file. With
        nothing in focus it lists them all, which is the old behaviour and the
        right one for a scene that has no parts yet.

        Runs once per draw, so it is also where the row-level lookups are
        gathered (which bodies are currently cutting something).
        """
        from ..utilities.part import focused_part, part_root_of

        objects = getattr(data, propname)
        helper = bpy.types.UI_UL_list

        if self.filter_name:
            flags = helper.filter_items_by_name(
                self.filter_name, self.bitflag_filter_item, objects, "name"
            )
        else:
            flags = [self.bitflag_filter_item] * len(objects)

        self._cutting = cutting_bodies(context.scene)
        root = focused_part(context)

        for i, obj in enumerate(objects):
            if not is_feature_row(obj):
                flags[i] &= ~self.bitflag_filter_item
            elif root is not None and part_root_of(obj) != root:
                flags[i] &= ~self.bitflag_filter_item

        return flags, []
