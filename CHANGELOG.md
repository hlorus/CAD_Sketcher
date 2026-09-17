# Changelog

Notes here feed two places automatically: the entry matching a release is
prepended to that version's GitHub release notes, and it is shown in the in-app
"What's new" dialog after the add-on updates. Add a `## X.Y.Z` section (matching
the manifest version) with a short summary for anything user-facing. It is
optional: a release with no matching entry just uses GitHub's auto-generated
notes and shows no "What's new" (e.g. a packaging-only patch).

## 0.32.0
This release makes large sketches much faster to draw in and edit, adds control over curve resolution and the boolean solver, and refines drawing, bevel and constraint display.

New
- Curve resolution: set how finely arcs and circles are meshed, per sketch and as a preference for new sketches
- Boolean solver choice: switch a boolean between Exact and the much faster Manifold solver, with a preference for the default
- Linear Array can take a second direction to build grids of copies
- Change Sketch Workplane: move a sketch onto another workplane, a mesh face or an origin plane, and see in the sketch panel which face a workplane is anchored to
- Option to stop new Extrude and Revolve solids from automatically booleaning into overlapping bodies
- Duplicating a sketch with Alt+D creates a linked copy of its result instead of a second sketch
- Drawing tools accept press, drag and release, e.g. drag out a line or a circle's radius

Improved
- Much faster hovering, dragging and drawing in large sketches, and faster redraws with many constraints
- Geometry in under-constrained sketches no longer drifts slightly on every solve
- Constraint icons on the same element or overlapping on screen are grouped into one icon with a count; hover it to expand
- Brighter constraint colors, sharper icons and a light theme preset for light viewports
- Bevel: the radius follows the cursor and is clamped to what fits, the corner is kept when a constraint uses it, and tangent joints are no longer beveled
- Entities and constraints lists show type icons
- A tool's redo panel shows picked elements by name instead of an internal id

Fixed
- Duplicated workplanes no longer snap back onto the face of the original; affected files are repaired on load
- A cutter sketch anchored to the face it cuts no longer shifts its workplane
- Clicking to bevel selected corners no longer adds an extra point
- Linear Array could be added to a workplane empty

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
