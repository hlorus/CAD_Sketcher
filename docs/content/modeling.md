# Modeling Tools

The modeling tools act on objects rather than on sketch entities: they add a
node-group modifier to a [body](integration.md), so the solid they build keeps
following the sketch it came from and stays editable in the modifier afterwards.

Reach them from the toolbar while no sketch is active, or with their global
shortcut from anywhere in Object Mode (see the
[keymap](tools.md#global-shortcuts)). Each of them picks up what is already
selected, and returns to the Select tool once it is done. Everything you set
interactively can be corrected in the redo panel right after, and later on the
modifier itself.

## Extrude
::: CAD_Sketcher.operators.modifiers.View3D_OT_node_extrude

Pick a profile (a sketch's body, or a curve) and drag the depth, or type it.
**Mirror Extrude** grows the solid to both sides of the profile, and
**Asymmetric** lets the two sides differ.

A profile that isn't filled is extruded into open walls rather than a solid.

## Revolve
::: CAD_Sketcher.operators.modifiers.View3D_OT_node_revolve

Pick the profile, then the axis to turn it around: a mesh edge, a sketch or curve
line, or one of the part's own axes, which are drawn while the axis is being
picked. **Angle** is the sweep, **Flip Direction** turns it the other way, and
**Angular Resolution** sets the largest angle per segment, so the step count
adapts to the sweep.

## Arrays
Both arrays share one toolbar button and one shortcut, which starts whichever of
the two the toolbar shows. They copy the picked object with a node group, so the
copies follow the original as it changes.

::: CAD_Sketcher.operators.modifiers.View3D_OT_node_array_linear

Drag out the direction and the spacing. While dragging, the row follows an axis,
a mesh edge or a sketch line under the cursor, so it can be laid on an existing
direction instead of eyeballed. **Count** is the number of copies and **Use Total
Distance** makes the distance the whole span rather than the step between copies.
A second **Count** and offset turn the row into a grid, and **Merge by Distance**
welds copies that meet.

::: CAD_Sketcher.operators.modifiers.View3D_OT_node_array_circular

Pick the axis to turn around (a mesh edge, a sketch line or one of the part's own
axes, as for the revolve), then drag out the count. **Angle** is the whole sweep
the copies are spread over, or the turn between two of them with **Use Total
Angle** off. **Align Rotation** turns each copy with the pattern, as a bolt circle
does; with it off a copy keeps its orientation while travelling round.

## Boolean
::: CAD_Sketcher.operators.modifiers.View3D_OT_node_boolean

Pick the body that receives the boolean and the cutter to apply to it, either
beforehand by selecting both or in the viewport. **Operation** is Difference,
Union or Intersect, and **Boolean Solver** chooses between Exact and the much
faster Manifold (the default for new booleans is a preference).

A solid cutter would hide the result, so its viewport display is switched to
wireframe; set **Cutter Display** to Solid to keep it shaded. What a cutter looks
like in a part, and how it travels with the body it cuts, is covered in
[parts and assemblies](parts.md#cutter-display).

### Automatic booleans
A new Extrude or Revolve that overlaps existing bodies is booleaned into them
right away, so a pocket drawn on a face cuts what it sits on without a second
step. The tool's redo panel picks the operation, and the **Auto Boolean** toggle
in the tool settings bar turns the automatic detection off, leaving the new solid
separate.
