import bpy
import math

cam_data = bpy.data.cameras.new(name="Camera_Stairs_Axonometric")
cam_data.lens = 42
cam_obj = bpy.data.objects.new(name="Camera_Stairs_Axonometric", object_data=cam_data)
# Elevated axonometric view of the entire Bathroom + Antibagno + Staircase complex
cam_obj.location = (13.5, -7.0, 7.2)
cam_obj.rotation_euler = (math.radians(52.0), 0.0, math.radians(45.0))

bpy.data.collections.get("07_Luci_e_Camera").objects.link(cam_obj)
bpy.context.scene.camera = cam_obj

print("Stairs axonometric camera ready.")

