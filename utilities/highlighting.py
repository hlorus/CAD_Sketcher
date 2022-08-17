from bpy.props import BoolProperty
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
        if not properties.is_property_set("index"):
            return cls.__doc__

        # Clear previous highlights
        global_data.highlight_constraint = None
        global_data.highlight_entities = []

        index = properties.index
        members = properties.highlight_members

        if hasattr(properties, "type") and properties.is_property_set("type"):
            type = properties.type
            c = context.scene.sketcher.constraints.get_from_type_index(type, index)

            global_data.highlight_constraint = c
            if members:
                global_data.highlight_entities.extend(c.entities())

        else:
            # Set hover so this could be used as selection
            global_data.hover = properties.index
            if members:
                e = context.scene.sketcher.entities.get(index)
                global_data.highlight_entities.extend(e.dependencies())

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
