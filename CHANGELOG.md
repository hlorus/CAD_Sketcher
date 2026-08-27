# Changelog

Notes here feed two places automatically: the entry matching a release is
prepended to that version's GitHub release notes, and it is shown in the in-app
"What's new" dialog after the add-on updates. Before tagging a release, add a
`## X.Y.Z` section (matching the manifest version) with a short summary — CI
rejects a stable release that has no matching entry.

## 0.31.0
This release adds nondestructive Boolean modeling, custom sketch attributes and refines the Extrude, Revolve and Projection tools.

New
- Nondestructive Boolean modeling: Extrude and Revolve can cut, union or intersect their result into overlapping bodies, with automatic target detection
- Custom sketch attributes
- Live Snapping: pick existing curve and mesh elements as references while drawing, they will be implicitly projected and update after future geometry changes

Improved
- Revolve can now build from a source object, with automatic boolean detection
- Project Geometry is now a dedicated tool, and can project individual elements and sketch sources
- Node tools (Extrude, Revolve, Array) return to the Select tool after finishing
- The tools panel now shows the tools relevant to the current sketch mode
- Auto-constraints while drawing are validated so they no longer over-constrain the sketch
- Legacy files are migrated on demand via a button in the Sketcher panel, instead of automatically on file load

Fixed
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
