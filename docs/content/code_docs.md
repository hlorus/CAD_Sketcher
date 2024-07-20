# Code Documentation
## Core
At the base of the extension there's the properties structure. The [model subpackage](https://github.com/hlorus/CAD_Sketcher/tree/main/model) defines
a set of blender [PropertyGroups](https://docs.blender.org/api/current/bpy.types.PropertyGroup.html). This is needed so that values are stored to disk on file save. These PropertyGroups have to be registered
and then be pointed to from somewhere by a PointerProperty.

Additionally to pure properties PropertyGroups can also hold methods and attributes,
the extension makes heavy use of that as it leads to a convenient way of working with the data.

The root of the extension's data structure is SketcherProps which is registered on blender's
Scene type and can therefore be accessed as follows:
```
bpy.context.scene.sketcher
```

From there the structure looks as follows:

sketcher
  - entities
    - points3D (CollectionProperty of 3D Points)
    - lines3D (CollectionProperty of 3D Lines)
    - sketches
    - ...

  - constraints
    - coincident (CollectionProperty of coincident constraints)
    - equal
    - ...

>**Note:** The nesting of PropertyGroups is done by defining PointerProperties inside
of a PropertyGroup.

## Entities
Entities always inherit from the SlvsGenericEntity class which implements the basic
properties (like properties to store if an entity is visible, construction, origin etc.)
and logic (like the draw method which draws itself based on its geometry batch) entities have.

### Index system
As an entity can depend on other entities there has to be a way to point to an entity.
This is done by storing an unique index on each entity (entity.slvs_index) which is
set when an entity is created through its "add_*" method on the SlvsEntities class.

Pointing to an entity is done by storing the entity's index in a IntProperty, the
entity itself can then be looked up by:
```
entity = bpy.context.scene.sketcher.entities.get(index)
```

For convenience there's the slvs_entity_pointer function which registers the IntProperty
with a "_i" prefix and adds getter/setter methods to directly get the entity without
having to deal with the index itself.

### Drawing
Entities are drawn in the viewport by utilizing blenders [GPU Module](https://docs.blender.org/api/current/gpu.html).
Every entity type has an update function which is responsible for creating the geometry
batch that is used for drawing. As this can be expensive to compute the batches are stored
based on the entity's index in global_data.batches. There's an initial tagging system in place
to tag entities as dirty however this is currently still disabled by default.

> **NOTE:** In order to draw anything a draw handler has to be registered on the viewport type.
This usually happens from an operator that the user invokes. As this is rather bad UX the
extension registers the handler when the extension is registered. More precisely, as the
the context at register time is limited, a [Application Timer](https://docs.blender.org/api/current/bpy.app.timers.html) is used to register
the draw handler shortly after the extension has been registered.

### Selection
Entity selection is done by simply drawing entities a second time in an [Offscreen Texture](https://docs.blender.org/api/current/gpu.html#generate-a-texture-using-offscreen-rendering). The color however is used
to identify the entity. The two functions index_to_rgb() and rgb_to_index() inside functions.py
are used to convert between the entity's "slvs_index" and the color value that is written to the texture.

This concept is explained [here](http://www.opengl-tutorial.org/miscellaneous/clicking-on-objects/picking-with-an-opengl-hack/).

> **NOTE:** There's the "Write Selection Texture" operator in the debug panel which
can be used to write the current selection texture to an image data-block in order
to inspect it.

### Preselection
The extension makes great use of preselection highlighting. To achieve that the
VIEW3D_GT_slvs_preselection gizmo is used which looks up the currently hovered pixel and writes
the index to global_data.hover whenever the "test_select" method is called.

> **NOTE:** The [test_select](https://docs.blender.org/api/current/bpy.types.Gizmo.html#bpy.types.Gizmo.test_select) method of gizmos is used as it
receives the cursor location and is called whenever the cursor moves.

## Constraints
Constraints always inherit from the GenericConstraint class which implements the basic
properties (like properties to store if a constraint is visible or has failed to solve etc.)
and some basic logic that constraints have.

Unlike entities the constraints are not implemented completely from scratch but rather
make use of the [Gizmo API](https://docs.blender.org/api/current/bpy.types.Gizmo.html) to display themselves and handle other interactions like selection.

## Interaction
There's a set of operators defined in operators.py which are used to create the
interaction between the user and the extension. Note that the extension also has to define
operators for basic interactions like selection or calling the context menu due to
the fact that entities are implemented from scratch.

Most of the viewport operators inherit from the StatefulOperator class which is a
framework to allow defining complex tools in a declarative fashion. Besides the
base class itself which implements logic for native blender types there's also
the GenericEntityOp which adds support for extension specific types. Have a look at
the [interaction chapter](interaction_system.md) in the docs.

The extension also makes heavy use of workspacetools. Note that they depend on some
functionality defined in the StatefulOperator class to display the correct description
and get the tools shortcuts.

> **NOTE:** Tools that need to be able to select entities have to use the preselection gizmo
in order to get updated selection.

## Solver
The extension uses the [Python Binding](https://pypi.org/project/py-slvs/) of [Solvespace](https://solvespace.com/index.pl). As the solver module isn't well documented it's best to inspect it through
the an interactive python interpreter. This can be done inside blender's python console
when the solver module has been installed, something like this:
```
from py_slvs import slvs
sys = slvs.System()
```

On the system object you'll find all the methods to add entities and constraints.
You can use the inspect module to get more info like the signature of a function:
```
import inspect
inspect.signature(sys.addEqual)
```

The solver data isn't persistent, so whenever the solver is triggered it will create a
new "py_slvs.slvs.System" object.Then the solver will go through the relevant entities and
call their create_slvs_data method and pass the system object to it. Same applies
to the constraints.

The create_slvs_data has to return the solver handles of the elements it adds to
the solver. This is later used to check which constraints have failed to solve.

When the solver was successful it will again go through all the entities and call their
update_from_slvs methods to update the blender data from the solver system.

## Converter
Currently there is only one native converter implemented, namely the BezierConverter
defined in converters.py. When converting to mesh the target bezier object is simply
converted again with blenders to_mesh function. This is a design choice to workaround
the problem of finding the area to fill for a given shape.

As a bezier spline is defined by a list of bezier control-points entities we have to
create a list of connected entities. This is done by the BezierConverter.walker() method.
After that we cam simply loop through these connected entities and call their to_bezier() method.


## FAQ
### What happens when a button is pressed?
In blender every user interaction happens through an operator. You can enable python
tooltips to find the corresponding operator from a button. Check [blenders API Docs](https://docs.blender.org/api/current/info_quickstart.html) for more information.


## Gotcha's
### Entity pointers loose their assigned values
> AttributeError: 'NoneType' object has no attribute "slvs_index"

As described [here](https://docs.blender.org/api/current/info_gotcha.html#stale-data) data might not directly update after edit. This usually isn't a problem for interactive operators however it can be the case with operators, scripts or tests which add multiple entities/constraints at once.
This can be solved by calling context.view_layer.update() before adding an element that depends on an element that was just created. Just be aware that this might have a negative performance impact.
A better approach is to use the "index_reference" mode of the entity "add_" methods. If set to True the method will return the index of the entity rather than the object itself. All "add_" methods will allow passing entities by index, additionally they also accept passing parameters.

```
entities = context.scene.sketcher.entities

p1 = entities.add_point_3d((0, 0, 0), index_reference=True)
p2 = entities.add_point_3d((1, 1, 0), index_reference=True)
line = entities.add_line_3d(p1, p2, construction=True, index_reference=True)

assert type(p1) == int
```

### Propertie's update callbacks

Some properties of entities or constraints have an update callback assigned which will be triggered whenever the property is changed, it's mainly used to trigger the solver or update the view. Example of this are the point entity's location property or the value property of dimensional constraints which will both trigger the solver when the property is changed.
This behaiviour is not always welcome. When writing a tool it's almost always better to avoid triggering these callbacks and manually solving the system, updating the view etc.

To avoid it, either set all properties in the "add_*" methods or change the value of properties like so:

> entity["some_prop"] = value
