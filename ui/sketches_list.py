import bpy
from bpy.types import Context, PropertyGroup, UILayout, UIList

from ..declarations import Operators
from ..model.sketch_ref import Sketch, is_sketch_object


def _cutting_sketches(scene) -> set:
    """Names of the sketches whose body is currently feeding a boolean.

    Cutters are bodies, so each is traced back to the sketch it realises: the
    list shows sketches. Gathered in one pass because the list needs it per row,
    and a per-row scan of every object's modifiers would run as often as the
    panel redraws.
    """
    from ..operators.modifiers import boolean_cutters
    from ..utilities.body import sketch_of

    cutting = set()
    for body in scene.objects:
        for cutter in boolean_cutters(body):
            sketch = sketch_of(cutter)
            cutting.add(sketch.name if sketch is not None else cutter.name)
    return cutting


class VIEW3D_UL_sketches(UIList):
    """List of sketches in the scene.

    Bound to ``scene.objects`` and filtered down to sketch (Curves) objects via
    ``filter_items`` -- no separate backing collection is required. Each row lets
    you toggle visibility, enter, rename and delete the sketch.
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
        obj = item  # a Curves object (filtered by filter_items)

        if self.layout_type in {"DEFAULT", "COMPACT"}:
            if not obj:
                layout.label(text="", translate=False, icon="OUTLINER_DATA_GP_LAYER")
                return

            row = layout.row(align=True)

            if obj.name in getattr(self, "_cutting", ()):
                # Hidden because it is cutting: its solid would sit over the
                # result. Not the user's hide to give back, so show what is going
                # on rather than a toggle that the next solve would undo.
                row.label(text="", icon="MOD_BOOLEAN")
            else:
                # Visibility toggle (eye): the sketch's own curves, which are
                # hidden from the moment it is created. Not the body, which
                # carries the features and looks nothing like the profile.
                row.operator(
                    Operators.SetSketchVisibility,
                    text="",
                    icon="HIDE_ON" if obj.hide_viewport else "HIDE_OFF",
                    emboss=False,
                ).sketch_name = obj.name

            # Editable name -- expands to fill, pushing the icons below to the
            # right edge of the row (standard Blender UIList layout). The body's
            # name, since the sketch's is derived from it: typing one here would
            # be re-derived away on the next update.
            from ..utilities.body import body_of

            row.prop(body_of(obj) or obj, "name", text="", emboss=False)

            # Trailing controls: solver-state, enter (edit), delete
            if obj.get("solver_state", "OKAY") != "OKAY":
                state = Sketch(obj).get_solver_state()
                row.label(text="", icon=state.icon)
            row.operator(
                Operators.SetActiveSketch,
                text="",
                icon="OUTLINER_DATA_GP_LAYER",
                emboss=False,
            ).sketch_name = obj.name
            row.operator(
                Operators.DeleteSketch,
                text="",
                icon="X",
                emboss=False,
            ).sketch_name = obj.name

        elif self.layout_type in {"GRID"}:
            layout.alignment = "CENTER"
            layout.label(text="", icon="OUTLINER_DATA_GP_LAYER")

    def filter_items(self, context: Context, data, propname):
        """Show the sketches worth listing; honor the built-in name search box.

        Scoped to the part in focus when there is one, so the list says which
        part you are looking at instead of pooling every sketch in the file. With
        nothing in focus it lists them all, which is the old behaviour and the
        right one for a scene that has no parts yet.

        Runs once per draw, so it is also where the row-level lookups are
        gathered (which sketches are currently cutting something).
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

        self._cutting = _cutting_sketches(context.scene)
        root = focused_part(context)

        for i, obj in enumerate(objects):
            if not is_sketch_object(obj):
                flags[i] &= ~self.bitflag_filter_item
            elif root is not None and part_root_of(obj) != root:
                flags[i] &= ~self.bitflag_filter_item

        return flags, []
