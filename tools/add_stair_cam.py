import bpy
import math

cam_data = bpy.data.cameras.new(name="Camera_Stairs_Perspective")
cam_data.lens = 32
cam_obj = bpy.data.objects.new(name="Camera_Stairs_Perspective", object_data=cam_data)
# Position in Cucina looking North-West towards the stair and antibagno entrance
cam_obj.location = (12.2, -4.8, 3.2)
cam_obj.rotation_euler = (math.radians(62.0), 0.0, math.radians(45.0))

bpy.data.collections.get("07_Luci_e_Camera").objects.link(cam_obj)
bpy.context.scene.camera = cam_obj

print("Stairs detail camera created.")

