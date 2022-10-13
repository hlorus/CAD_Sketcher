class SketcherElement:
    
    def to_dict(self):
        d = dict(self).copy()
        d["type"] = self.__class__.__name__
        return d