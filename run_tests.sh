#!/usr/bin/env bash

blender_bin="blender"
if [[ "${OSTYPE}" =~ ^darwin* ]]; then
  blender_bin="/Applications/Blender.app/Contents/MacOS/Blender"
fi

${blender_bin} --addons CAD_Sketcher --python ./testing/__init__.py -- --log_level=INFO
