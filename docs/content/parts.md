# Parts and Assemblies

A **part** is one thing you can move: a body together with the sketches and
workplanes that define it. An **assembly** is a group of parts you can move as a
whole. Both are just object parenting, so the outliner shows the real structure
and you edit it there.

## Moving a part

Leave the sketch (parts are moved in Object Mode), select the part's body and
press `G` or `R`. Its sketches, workplanes and cutters follow. Scale is locked:
the solver treats a sketch's plane as a rigid frame, so a scaled part would draw
and solve at different sizes.

The object you grab is the part's first sketch, which is also its body once
extruded, so you are moving the geometry you see rather than a helper object.

## What belongs to what

Membership is never a mode you switch. It follows from what you drew on, and it
is settled when the sketch becomes solid:

| You do this | Result |
|---|---|
| Sketch on a body's face or on a part's workplane | Joins that part right away |
| Sketch on a global XY/XZ/YZ plane | Stays **global**: no part, free to move |
| Extrude or revolve with nothing to cut | The sketch roots a part of its own |
| Extrude or revolve that cuts an existing body | Joins that body's part, as a cut feature |
| A cut reaching bodies in several parts | Belongs to no part; if those parts share an assembly it becomes a feature of the assembly |

A cut has to travel with the body it cuts, which is why it joins that part: were
it left behind, moving the body would silently change the result.

## Part workplanes

Select a part and the Add Sketch tool offers that part's own XY, XZ and YZ planes
(drawn smaller than the global ones) alongside the scene's. Use them when a part
has been moved or rotated and you want to sketch in *its* frame rather than the
world's.

## Changing membership by hand

Parenting **is** membership, so the override is Blender's own gesture: `Ctrl+P`
in the viewport, or a drag in the outliner.

- Parent a sketch onto a part's body to make it a feature of that part.
- Unparent it to make it global again.
- Parent a part onto an assembly root to put it in that assembly.

A sketch that becomes a feature is pinned in place; one that leaves a part is
free to move again. Objects you made yourself keep their freedom either way.

Deleting a part's body does not scatter the rest: its workplanes and sketches
keep their place and the next sketch in the part takes over as its body. The same
applies to an assembly, whose parts simply stand on their own again.

## Assemblies

Select the parts you want to group and use **Add Assembly** in the Sketcher
panel. Parts stay individually movable inside an assembly, and assemblies can
contain assemblies.

## Cutter display

A cutter tells you what it is doing:

- **Hidden** while it is cutting a body in its own part (its solid would sit over
  the result). Activate it from the sketch list to edit it.
- **Wireframe** when it cuts across parts, or when it means to cut but currently
  reaches nothing.
- **Shaded** when it has no boolean at all: then it is simply a body.

## Older files

Sketches saved before parts existed keep working, but cannot be moved as parts
until they are adopted. The Sketcher panel offers **Adopt into parts** when it
finds them: a sketch drawn on a body joins that body's part, and one that has
been made solid roots a part of its own. It is never done automatically on file
open, since it restructures the hierarchy.

## Collections

Each part gets its own collection, nested inside its assembly's, holding
everything in the part. Anything belonging to no part sits at the scene level.
The collections follow the parenting, so they are a view of the structure rather
than a second place to edit it. Never **exclude** one from the view layer:
excluding stops evaluation, which drops the sketch fill.
