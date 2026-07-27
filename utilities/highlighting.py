from bpy.props import BoolProperty
from ..model.sketch_ref import get_active_constraints
from bpy.types import PropertyGroup, Context, Event

from .. import global_data


class HighlightElement:
    """
    Mix-in class to highlight the element this operator acts on. The element can
    either be an entity or a constraint. The element has to be specified by an index
    property for entities and additionally with a type property for constraints.

        index: IntProperty
        type: StringProperty


    Note that this defines the invoke and description functions, an operator that
    defines one of those has to manually make a call to either of the following:

        self.handle_highlight_active(context) -> from invoke()
        cls.handle_highlight_hover(context, properties) -> from description()


    Settings:
    highlight_hover -> highlights the element as soon as the tooltip is shown
    highlight_active -> highlights the element when the operator is invoked
    highlight_members -> highlights the element members e.g. the entity's dependencies or
                the entities the constraint acts on
    """

    highlight_hover: BoolProperty(name="Highlight Hover")
    highlight_active: BoolProperty(name="Highlight Hover")
    highlight_members: BoolProperty(name="Highlight Members")

    @classmethod
    def _do_highlight(cls, context: Context, properties: PropertyGroup):
        has_index = properties.is_property_set("index")
        has_curve_id = (
            hasattr(properties, "curve_id") and properties.is_property_set("curve_id")
        )
        if not has_index and not has_curve_id:
            return cls.__doc__

        # Clear previous highlights
        global_data.highlight_constraint = None
        global_data.highlight_entities = []
        global_data.highlight_curve_ids = []

        members = properties.highlight_members

        if hasattr(properties, "type") and properties.is_property_set("type"):
            # Constraint: highlight the gizmo and, optionally, the geometry it
            # acts on (curve highlighting is driven by curve_ids now, not
            # entity objects).
            c = get_active_constraints(context).get_from_type_index(
                properties.type, properties.index
            )
            if c:
                global_data.highlight_constraint = c
                if members:
                    global_data.highlight_curve_ids = c.curve_id_placements()
        else:
            # Entity operator: highlight the referenced curve.
            cid = properties.curve_id if has_curve_id else properties.index
            if isinstance(cid, str) and cid:
                global_data.highlight_curve_ids = [cid]

        if context.area:
            context.area.tag_redraw()
        return cls.__doc__

    def handle_highlight_active(self, context: Context):
        properties = self.properties
        if properties.highlight_active:
            self._do_highlight(context, properties)

    @classmethod
    def handle_highlight_hover(cls, context: Context, properties: PropertyGroup):
        if properties.highlight_hover:
            cls._do_highlight(context, properties)

    @classmethod
    def description(cls, context: Context, properties: PropertyGroup):
        cls.handle_highlight_hover(context, properties)

    def invoke(self, context, event: Event):
        self.handle_highlight_active(context)
        return self.execute(context)
