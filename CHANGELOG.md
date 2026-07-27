# Changelog

Notes here feed two places automatically: the entry matching a release is
prepended to that version's GitHub release notes, and it is shown in the in-app
"What's new" dialog after the add-on updates. Before tagging a release, add a
`## X.Y.Z` section (matching the manifest version) with a short summary — CI
rejects a stable release that has no matching entry.

## 0.3.0
The data model of the extension has been fundamentally reworked for a closer integration
into Blender, better stability and performance.

- Native Blender Curves are now the source of truth for sketch geometry, which removes the conversion step
- Workplanes are now empties, so native Blender tools can be used to define sketch placement
- Workplanes on mesh faces now follow geometry edits and object transforms
- Sketch-mode specific tools are now only visible when a sketch is active
- Added auto-constraints toggle to add horizontal, vertical and coincident constraints while drawing; hold Shift to skip
- Snap sketch points to existing 3D geometry (vertices, edges, midpoints, face center); this is a static snap at placement time and does not track the underlying geometry afterwards
- Added Workspacetools for parametric Extrude and Linear Array
- Added extension auto-update via the extension repository
- New "What's New" dialog surfaces changes after each update
