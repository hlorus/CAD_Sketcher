
def AddSources(sources, driver_sources):
    if driver_sources is None:
        return
    for group in driver_sources:
        if not group is None:
            source = group.source
            if not source is None:
                sources.append(source)

    
def GetDriverSources(context, sketch):
    sources = []
    if not sketch is None:
        AddSources(sources, sketch.driver_sources)

    AddSources(sources, context.scene.sketcher.driver_sources)
    sources.sort(key=lambda s: s.name)
    return sources
