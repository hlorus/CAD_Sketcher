import bpy

from ..drawing import selection
from ..model import sketch_ref
from ..utilities import custom_attributes

_TYPE_ITEMS = (
    ("BOOLEAN", "Boolean", "True / False"),
    ("INT", "Integer", "Whole number"),
    ("FLOAT", "Float", "Decimal number"),
)
_DOMAIN_ITEMS = (
    ("CURVE", "Segment", "Store one value per native sketch entity/segment"),
    ("POINT", "Point", "Store values on the selected entity's native points"),
)


def _value(op, data_type):
    if data_type == "BOOLEAN":
        return op.bool_value
    if data_type == "INT":
        return op.int_value
    return op.float_value


def _assign_value(op, data_type, value):
    if data_type == "BOOLEAN":
        op.bool_value = bool(value)
    elif data_type == "INT":
        op.int_value = int(value)
    else:
        op.float_value = float(value)


def _draw_value(op, layout, data_type):
    if data_type == "BOOLEAN":
        layout.prop(op, "bool_value")
    elif data_type == "INT":
        layout.prop(op, "int_value")
    else:
        layout.prop(op, "float_value")


def _seed_set_value(sketch, entry, curve_ids):
    """Return a safe initial value for the Set dialog.

    A common selected value is preserved. Mixed selections intentionally fall
    back to the attribute default, rather than silently replacing data with the
    operator property's Python zero value merely by opening/confirming the UI.
    """
    if not curve_ids:
        return entry["default"]

    values = []
    for curve_id in curve_ids:
        try:
            current = custom_attributes.get_attribute_value(
                sketch, entry["name"], curve_id=curve_id
            )
        except KeyError:
            return entry["default"]
        if isinstance(current, (list, tuple)):
            values.extend(current)
        else:
            values.append(current)

    if not values:
        return entry["default"]
    first = values[0]
    if all(value == first for value in values[1:]):
        return first
    return entry["default"]


class VIEW3D_OT_slvs_add_custom_attribute(bpy.types.Operator):
    bl_idname = "view3d.slvs_add_custom_attribute"
    bl_label = "Add Sketch Attribute"
    bl_description = "Define an attribute on the native sketch source geometry"
    bl_options = {"UNDO", "REGISTER"}

    name: bpy.props.StringProperty(name="Name", default="attribute")
    data_type: bpy.props.EnumProperty(name="Type", items=_TYPE_ITEMS, default="FLOAT")
    domain: bpy.props.EnumProperty(name="Domain", items=_DOMAIN_ITEMS, default="CURVE")
    bool_value: bpy.props.BoolProperty(name="Default", default=False)
    int_value: bpy.props.IntProperty(name="Default", default=0)
    float_value: bpy.props.FloatProperty(name="Default", default=0.0)

    @classmethod
    def poll(cls, context):
        return sketch_ref.get_active_sketch(context) is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "name")
        layout.prop(self, "data_type")
        layout.prop(self, "domain")
        _draw_value(self, layout, self.data_type)

    def execute(self, context):
        sketch = sketch_ref.get_active_sketch(context)
        try:
            custom_attributes.define_attribute(
                sketch,
                self.name,
                data_type=self.data_type,
                domain=self.domain,
                default=_value(self, self.data_type),
            )
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class VIEW3D_OT_slvs_set_custom_attribute(bpy.types.Operator):
    bl_idname = "view3d.slvs_set_custom_attribute"
    bl_label = "Set Sketch Attribute"
    bl_description = "Set this attribute on selected native sketch geometry"
    bl_options = {"UNDO", "REGISTER"}

    name: bpy.props.StringProperty(name="Name")
    bool_value: bpy.props.BoolProperty(name="Value", default=False)
    int_value: bpy.props.IntProperty(name="Value", default=0)
    float_value: bpy.props.FloatProperty(name="Value", default=0.0)

    @classmethod
    def poll(cls, context):
        return sketch_ref.get_active_sketch(context) is not None

    def invoke(self, context, event):
        sketch = sketch_ref.get_active_sketch(context)
        entry = custom_attributes.definition(sketch, self.name)
        if entry is None:
            return {"CANCELLED"}
        curve_ids = list(dict.fromkeys(selection.selected))
        seed = _seed_set_value(sketch, entry, curve_ids)
        _assign_value(self, entry["type"], seed)
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        entry = custom_attributes.definition(
            sketch_ref.get_active_sketch(context), self.name
        )
        if entry is None:
            self.layout.label(text="Attribute no longer exists")
            return
        self.layout.label(text=f"{entry['name']} ({entry['domain'].title()})")
        _draw_value(self, self.layout, entry["type"])

    def execute(self, context):
        sketch = sketch_ref.get_active_sketch(context)
        entry = custom_attributes.definition(sketch, self.name)
        if entry is None:
            self.report({"ERROR"}, "Attribute no longer exists")
            return {"CANCELLED"}

        curve_ids = list(dict.fromkeys(selection.selected))
        if not curve_ids:
            self.report({"WARNING"}, "Select one or more sketch entities first")
            return {"CANCELLED"}

        value = _value(self, entry["type"])
        for curve_id in curve_ids:
            custom_attributes.set_attribute_value(
                sketch, self.name, value, curve_id=curve_id
            )
        return {"FINISHED"}


class VIEW3D_OT_slvs_remove_custom_attribute(bpy.types.Operator):
    bl_idname = "view3d.slvs_remove_custom_attribute"
    bl_label = "Remove Sketch Attribute"
    bl_description = "Remove the attribute definition and its native source data"
    bl_options = {"UNDO", "REGISTER"}

    name: bpy.props.StringProperty(name="Name")

    @classmethod
    def poll(cls, context):
        return sketch_ref.get_active_sketch(context) is not None

    def execute(self, context):
        if not custom_attributes.remove_attribute(
            sketch_ref.get_active_sketch(context), self.name
        ):
            self.report({"WARNING"}, "Attribute no longer exists")
            return {"CANCELLED"}
        return {"FINISHED"}


register, unregister = bpy.utils.register_classes_factory(
    (
        VIEW3D_OT_slvs_add_custom_attribute,
        VIEW3D_OT_slvs_set_custom_attribute,
        VIEW3D_OT_slvs_remove_custom_attribute,
    )
)
