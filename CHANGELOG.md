# Changelog

Notes here feed two places automatically: the entry matching a release is
prepended to that version's GitHub release notes, and it is shown in the in-app
"What's new" dialog after the add-on updates. Add a `## X.Y.Z` section (matching
the manifest version) with a short summary for anything user-facing. It is
optional: a release with no matching entry just uses GitHub's auto-generated
notes and shows no "What's new" (e.g. a packaging-only patch).

## 0.32.0
This release introduces parts and assemblies, makes a sketch's result a real mesh you can move, apply and export, adds new drawing and array tools, and makes large sketches much faster to draw in and edit.

New
- Parts and assemblies: a part is the geometry a sketch makes together with the sketches and workplanes that define it, and you can move it freely, group parts into assemblies, and duplicate or instance either; the outliner shows the structure
- A sketch's result is a real mesh object: apply the modifiers, export it, or edit it with any mesh tool, and add your own modifiers on top
- Each part has its own XY, XZ and YZ workplanes, offered in place of the scene's while the part is selected
- Revolve can turn geometry around a part's own axis, not only around a picked edge
- 3-point arc tool, and center and 3-point rectangle tools
- Re-pick a constraint's entities, or a drawing tool's points, from the redo panel
- Tool and constraint shortcuts work while another tool is running, as do undo and the construction-mode toggle
- Curve resolution: set how finely arcs and circles are meshed, per sketch and as a preference for new sketches
- Boolean solver choice: switch a boolean between Exact and the much faster Manifold solver, with a preference for the default
- Circular Array tool: pick what to copy and an axis (a mesh edge, a sketch line or one of a part's own axes), then drag out the count; copies are spread over a total angle or placed that angle apart, and can turn with the pattern or keep their orientation
- Linear Array can take a second direction to build grids of copies
- Change Sketch Workplane: move a sketch onto another workplane, a mesh face or an origin plane, and see in the sketch panel which face a workplane is anchored to
- Option to stop new Extrude and Revolve solids from automatically booleaning into overlapping bodies
- Duplicating a sketch with Alt+D creates a linked copy of its result instead of a second sketch
- Drawing tools accept press, drag and release, e.g. drag out a line or a circle's radius

Improved
- Renaming a part renames its sketch, workplanes and mesh with it
- Points lying on a line are hovered before the line, so they can be picked without cycling
- An arc is previewed while you place its last point
- Drawing by dragging needs a deliberate drag, so a click no longer starts one
- Sketches linked from another file are left to the file that owns them
- Much faster hovering, dragging and drawing in large sketches, and faster redraws with many constraints
- Geometry in under-constrained sketches no longer drifts slightly on every solve
- Constraint icons on the same element or overlapping on screen are grouped into one icon with a count; hover it to expand
- Brighter constraint colors, sharper icons and a light theme preset for light viewports
- Bevel: the radius follows the cursor and is clamped to what fits, the corner is kept when a constraint uses it, and tangent joints are no longer beveled
- Entities and constraints lists show type icons
- A tool's redo panel shows picked elements by name instead of an internal id
- Both array tools share one toolbar button, and Linear Array follows an axis, edge or sketch line under the cursor while dragging, so a row can be laid on an existing direction
- Offset geometry stays tied to what it came from: editing the source moves the offset with it, its segments keep one common distance, and that distance can be typed exactly
- A tool group's shortcut starts the tool its toolbar button shows, the one last used
- Distance, Angle and Diameter are now the Dimension tool with a preset kind, so every dimension behaves the same; their shortcuts and menu entries are unchanged
- Number entry only reads a letter as a unit once a digit has been typed, and `thou`, `foot`, `meters` and `degrees` can be typed
- Tool shortcut hints show remapped keys

Fixed
- A sketch's result can be applied as a modifier again, so it reaches exporters, `to_mesh` and mesh tools
- Cutting a flat profile with a solid deleted it instead of making a hole; existing files are repaired by Update File
- Moving a circle's center no longer changes its radius
- Dimension values stay with their sketch
- A midpoint constraint is marked once instead of twice
- Duplicated workplanes no longer snap back onto the face of the original; affected files are repaired on load
- A cutter sketch anchored to the face it cuts no longer shifts its workplane
- Clicking to bevel selected corners no longer adds an extra point
- Linear Array could be added to a workplane empty
- Blender could crash while drawing on a sketch that projects geometry
- The Dimension tool's redo panel crashed Blender; it now adjusts the value, alignment, flip, radius and supplementary angle

Files made with an earlier version keep working; use **Update File** in the Sketcher panel to bring them into the new structure.

## 0.31.0
This release adds a unified Dimension tool, native 3D sketches, nondestructive Boolean modeling and custom sketch attributes, organizes a project's objects into clean collections, and refines the Extrude, Revolve and Projection tools.

New
- Dimension tool: a single tool that adds the right dimensional constraint for what you select — line length, distance, angle, diameter, or edge-to-edge — then drag to place the label or type a value
- Native 3D sketches: draw points and lines freely in 3D space, anchored to an origin instead of a workplane
- Nondestructive Boolean modeling: Extrude and Revolve can cut, union or intersect their result into overlapping bodies, with automatic target detection
- Custom sketch attributes
- Live Snapping: pick existing curve and mesh elements as references while drawing, they will be implicitly projected and update after future geometry changes
- Project-centric collections: a project's sketches, workplanes and results are organized into a clean per-part collection layout instead of cluttering the scene root

Improved
- Constraints are shown as an icon grid in the sidebar, split into dimensional and geometric, with theme-aware icons
- Revolve can now build from a source object, with automatic boolean detection
- Project Geometry is now a dedicated tool, and can project individual elements and sketch sources
- Node tools (Extrude, Revolve, Array) return to the Select tool after finishing
- The tools panel now shows the tools relevant to the current sketch mode
- Auto-constraints while drawing are validated so they no longer over-constrain the sketch
- Legacy files are migrated on demand via a button in the Sketcher panel, instead of automatically on file load

Fixed
- Orthogonal sketch planes no longer collapse onto the XY plane
- Add Sketch can target the faces of extruded and filled sketches again
- Crash when a boolean cutter referenced itself
- Extrude of unfilled profiles now builds open walls instead of nothing
- Revolve of profiles with holes
- Copy/paste of constraints
- Merging of coincident self-referencing points
- Sketch-conversion topology, and node weld on Blender 5.0

## 0.30.0
The data model of the extension has been fundamentally reworked for a closer integration
into Blender, better stability and performance.

- Native Blender Curves are now the source of truth for sketch geometry, which removes the conversion step
- Workplanes are now empties, so native Blender tools can be used to define sketch placement
- Workplanes on mesh faces now follow geometry edits and object transforms
- Sketch-mode specific tools are now only visible when a sketch is active
- Added auto-constraints toggle to add horizontal, vertical and coincident constraints while drawing; hold Shift to skip
- Snap sketch points to existing 3D geometry (vertices, edges, midpoints, face center); this is a static snap at placement time and does not track the underlying geometry afterwards
- Added Workspacetools for parametric Extrude and Linear Array
- Added Project Geometry: bring an external object's edges into the active sketch as construction geometry that stays linked to the source and follows its edits
- Added a pie menu (Ctrl+Shift+M) for quick access to drawing tools and constraints
- Dimensional constraints (distance, angle, diameter) are placed in one step: pick the geometry, drag the label into position, and optionally type the value
- Select overlapping entities under the cursor: Alt+click steps through the stack, Alt+wheel cycles the highlight without selecting
- Added extension auto-update via the extension repository
- New "What's New" dialog surfaces changes after each update
