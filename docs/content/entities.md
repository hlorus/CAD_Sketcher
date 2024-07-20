Entities are the basic elements which are used to draw geometry in CAD Sketcher. They differ from regular blender mesh or curve elements which means native blender tools aren't able to interact with it as long as they aren't converted. See the chapter [integration](integration.md) for further details on how to process extension specific geometry.

Entities are defined by a set of parameters and pointers to other entities which are editable at any point in time. This allows non-destructive workflows and also ensures that geometry is resolution independent. A curve will always follow a given radius no matter how it's transformed. Entities can be created with the various [Workspacetools](user_interface.md#workspacetools).

<!-- TODO: DOF -->


## Active
An entity is considered to be active when the sketch it belongs to is set as the active
sketch or, for 3D entities, when no sketch is active.

## Visibility
Entities can be hidden. Access the setting from the entity's [context menu](user_interface#context-menu)
or from the [entity browser](user_interface#Entity-Browser).

## Construction
Entities have a construction parameter which can be set via the entity's [context menu](user_interface#context-menu). If it's set to true the entity will be ignored when converting the geometry however it's still used to solve the geometric system. It's generally good practice to mark entities as construction if they're not part of the final geometry.

## Fixed
Entities can be fixed via the entity's [context menu](user_interface#context-menu). A fixed entity won't have any degrees of freedom and therefor cannot be adjusted by the solver. It's good practice to base geometry on a fixed origin point.

> :warning:**Warning:** While this currently applies to all entities it's intended to be used with points only.


## Types
There are different types of entities, some of them apply in 2 dimensional space which requires a [sketch](#CAD_Sketcher.model.types.SlvsSketch) as a parameter.

>Entity types follow the implementation of [solvespace](https://solvespace.readthedocs.io/en/latest/entities/index.html).

> Only 2D entities can be converted later, check the chapter [integration](integration.md) for details.

::: CAD_Sketcher.model.types.SlvsPoint3D

::: CAD_Sketcher.model.types.SlvsLine3D

::: CAD_Sketcher.model.types.SlvsNormal3D

::: CAD_Sketcher.model.types.SlvsWorkplane

::: CAD_Sketcher.model.types.SlvsSketch

::: CAD_Sketcher.model.types.SlvsPoint2D

::: CAD_Sketcher.model.types.SlvsLine2D

::: CAD_Sketcher.model.types.SlvsArc

::: CAD_Sketcher.model.types.SlvsCircle
