"""
Semantic grouping of sketch entities for IFC and other integrations.

A SketchGroup is a named collection of entity references (by slvs_index) stored
on a sketch, carrying an IFC class tag and optional GUIDs.  The same entity can
belong to multiple groups with different tags, enabling one-geometry / many-IFC-
elements patterns without duplicating CAD geometry.

Classes
-------
SketchGroupMember
    The *relationship* between one entity and one group.  Holds the entity's
    slvs_index plus the per-context GUID (e.g. the IfcWall GlobalId that this
    specific line represents within a wall-run group).

SketchGroup
    One semantic group: a name, a shared IFC class tag, an optional group-level
    GUID (for IFC container abstractions), and an ordered list of members.
"""

from bpy.props import CollectionProperty, IntProperty, StringProperty
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory


class SketchGroupMember(PropertyGroup):
    """One entity's participation in a SketchGroup.

    The GUID stored here is the IFC GlobalId of *this entity instance* within
    the group's IFC class context.  It may be empty when no individual IFC
    element GUID exists for this piece (e.g. a sub-segment of a slab boundary).
    """

    entity_index: IntProperty(
        name="Entity Index",
        description="slvs_index of the member entity",
        default=-1,
    )
    guid: StringProperty(
        name="GUID",
        description=(
            "IFC GlobalId of this entity instance within the group's IFC class "
            "context.  Leave empty if no individual IFC element GUID applies"
        ),
        default="",
    )


class SketchGroup(PropertyGroup):
    """A named semantic group of sketch entities.

    All members share the same IFC class (tag).  The same entity may appear as
    a member of multiple groups, each with a different tag and GUID, allowing
    the same CAD geometry to represent several IFC elements simultaneously.
    """

    name: StringProperty(
        name="Name",
        description="Human-readable label for this group",
        default="Group",
    )
    tag: StringProperty(
        name="Tag",
        description=(
            "IFC class shared by all members of this group "
            "(e.g. IfcWall, IfcSlab, IfcCovering)"
        ),
        default="",
    )
    guid: StringProperty(
        name="Group GUID",
        description=(
            "IFC GlobalId of a container-level abstraction for this group "
            "(optional; leave empty if no such IFC element exists)"
        ),
        default="",
    )
    members: CollectionProperty(
        name="Members",
        type=SketchGroupMember,
    )
    active_member_index: IntProperty(
        name="Active Member",
        default=-1,
    )

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def add_member(self, slvs_index: int) -> SketchGroupMember:
        """Append *slvs_index* as a new member and return the new record."""
        m = self.members.add()
        m.entity_index = slvs_index
        return m

    def remove_member(self, member_index: int) -> None:
        """Remove the member at *member_index* (collection position)."""
        self.members.remove(member_index)

    def get_member(self, slvs_index: int):
        """Return the :class:`SketchGroupMember` for *slvs_index*, or ``None``."""
        for m in self.members:
            if m.entity_index == slvs_index:
                return m
        return None

    def contains(self, slvs_index: int) -> bool:
        """Return ``True`` if *slvs_index* is already a member of this group."""
        return self.get_member(slvs_index) is not None

    def entities(self, context):
        """Yield ``(entity, member)`` pairs for every member of this group.

        Silently skips stale entries whose slvs_index no longer resolves to a
        live entity (e.g. after the entity was deleted).
        """
        sse = context.scene.sketcher.entities
        for m in self.members:
            e = sse.get(m.entity_index)
            if e is not None:
                yield e, m


register, unregister = register_classes_factory((SketchGroupMember, SketchGroup))
