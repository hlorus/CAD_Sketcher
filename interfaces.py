from abc import ABC, abstractmethod

import bpy


class BezierConversionInterface(ABC):
    @abstractmethod
    def to_bezier(self, curve_data: bpy.types.Curve, startpoint: bpy.types.CurvePoint, endpoint: bpy.types.CurvePoint, invert_direction: bool, **kwargs):
        pass
    
