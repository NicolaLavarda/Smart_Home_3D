"""
Script to recreate the floor plan in 3D in Blender.
Strictly follows all measurements from the architectural drawing.
"""

import bpy
import bmesh
from mathutils import Vector, Matrix
import math

def clean_scene():
    # Remove all objects
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    
    # Remove orphaned data
    for col in [bpy.data.meshes, bpy.data.materials, bpy.data.curves, bpy.data.lights, bpy.data.cameras]:
        for item in list(col):
            col.remove(item)
            
    # Remove collections except Master Collection
    for col in list(bpy.data.collections):
        bpy.data.collections.remove(col)
        
    print("Scene completely cleared.")

clean_scene()

