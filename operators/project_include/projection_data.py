from bpy.types import TransformOrientation
from mathutils import Quaternion

from ...model.group_entities import SlvsEntities, SlvsPoint3D, SlvsSketch
from ...model.workplane import SlvsWorkplane


class ProjectionData:
    def __init__(
        self,
        sketcher_entities: SlvsEntities,
        sketch: SlvsSketch,
        object_translation: TransformOrientation,
    ):

        self.sketcher_entities = sketcher_entities
        self.sketch = sketch
        self.object_translation = object_translation

    @property
    def wp(self) -> SlvsWorkplane:
        wp: SlvsWorkplane = self.sketch.wp
        return wp

    @property
    def workplane_origin(self) -> SlvsPoint3D:
        slvs_point3d: SlvsPoint3D = self.wp.p1
        return slvs_point3d.location

    @property
    def workplane_quaternion(self) -> Quaternion:
        return self.wp.nm.orientation
