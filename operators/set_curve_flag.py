from bpy.props import BoolProperty, StringProperty
from bpy.types import Context, Event, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..drawing import selection
from ..model.curve_ref import curve_ref


class View3D_OT_slvs_set_curve_flag(Operator):
    """Toggle a flag on a curve"""

    bl_idname = Operators.SetCurveFlag
    bl_label = "Set Curve Flag"
    bl_options = {"UNDO"}

    curve_id: StringProperty()
    flag: StringProperty()
    value: BoolProperty()

    def execute(self, context: Context):
        from ..model.sketch_ref import get_active_sketch

        sketch = get_active_sketch(context)
        if not sketch:
            return {"CANCELLED"}

        # A specific curve_id targets one curve; otherwise apply to the whole
        # current selection (used by the selected-elements context menu).
        curve_ids = [self.curve_id] if self.curve_id else list(selection.selected)
        changed = False
        for cid in curve_ids:
            ref = curve_ref(sketch, cid)
            if ref.valid:
                setattr(ref, self.flag, self.value)
                changed = True

        if not changed:
            return {"CANCELLED"}
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class View3D_OT_slvs_rename_curve(Operator):
    """Rename this entity"""

    bl_idname = Operators.RenameCurve
    bl_label = "Rename Entity"
    bl_options = {"UNDO"}

    curve_id: StringProperty()
    new_name: StringProperty(name="Name")

    def invoke(self, context: Context, event: Event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: Context):
        self.layout.prop(self, "new_name")

    def execute(self, context: Context):
        from ..model.sketch_ref import get_active_sketch

        sketch = get_active_sketch(context)
        if not sketch:
            return {"CANCELLED"}
        ref = curve_ref(sketch, self.curve_id)
        if not ref.valid:
            return {"CANCELLED"}
        ref.name = self.new_name
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


def _solve_and_refresh(context: Context, sketch) -> None:
    """Re-solve the sketch and rebuild its display geometry after an edit."""
    from ..curve_solver import solve_system
    from ..utilities.curve_data import refresh_curve_geometry

    sketch.geometry_solved = False
    solve_system(context, sketch=sketch)
    refresh_curve_geometry(sketch)
    if context.area:
        context.area.tag_redraw()


class View3D_OT_slvs_flip_arc(Operator):
    """Connect the arc's endpoints in the inverted order"""

    bl_idname = Operators.FlipArc
    bl_label = "Invert Direction"
    bl_options = {"UNDO"}

    curve_id: StringProperty()

    def execute(self, context: Context):
        from ..model.sketch_ref import get_active_sketch
        from ..utilities.curve_data import rebuild_segments

        sketch = get_active_sketch(context)
        if not sketch:
            return {"CANCELLED"}
        ref = curve_ref(sketch, self.curve_id)
        if not ref.valid or not ref.is_arc():
            return {"CANCELLED"}

        # Arc geometry always sweeps CCW from start to end, so swapping the
        # endpoint references yields the complementary arc between the same
        # points. rebuild_segments re-bakes it (adapting the control-point count
        # to the new sweep angle).
        start = ref._get_attr_value("start_point_id", "")
        end = ref._get_attr_value("end_point_id", "")
        ref._set_attr_value("start_point_id", end)
        ref._set_attr_value("end_point_id", start)
        rebuild_segments(sketch)

        _solve_and_refresh(context, sketch)
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (
        View3D_OT_slvs_set_curve_flag,
        View3D_OT_slvs_rename_curve,
        View3D_OT_slvs_flip_arc,
    )
)
