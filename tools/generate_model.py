"""
Script to recreate the floor plan in 3D in Blender.
Strictly follows all measurements from the architectural drawing.
"""

import bpy
import bmesh
from mathutils import Vector, Matrix
import math

def clean_scene():
    raise RuntimeError("SAFETY ABORT: tools/generate_model.py is an obsolete scene wiper. DO NOT RUN.")

clean_scene()

