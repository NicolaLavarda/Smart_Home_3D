import bpy
import math

cam_obj = bpy.data.objects.get("Camera_Stairs_Perspective")
if cam_obj:
    cam_obj.location = (13.8, -5.8, 4.0)
    cam_obj.rotation_euler = (math.radians(58.0), 0.0, math.radians(45.0))
    cam_obj.data.lens = 26

print("Camera adjusted.")

