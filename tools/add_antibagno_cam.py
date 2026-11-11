import bpy
import math

cam_data = bpy.data.cameras.new(name="Camera_Antibagno_Inside")
cam_data.lens = 22
cam_obj = bpy.data.objects.new(name="Camera_Antibagno_Inside", object_data=cam_data)
# Right in front of the door looking into antibagno
cam_obj.location = (9.07, -4.5, 1.35)
cam_obj.rotation_euler = (math.radians(82.0), 0.0, 0.0)

bpy.data.collections.get("07_Luci_e_Camera").objects.link(cam_obj)
bpy.context.scene.camera = cam_obj

# Add a point light inside antibagno so it is well lit
light_data = bpy.data.lights.new(name="Light_Antibagno", type='POINT')
light_data.energy = 50.0
light_data.color = (1.0, 0.95, 0.88)
light_obj = bpy.data.objects.new(name="Light_Antibagno", object_data=light_data)
light_obj.location = (9.07, -2.8, 2.2)
bpy.data.collections.get("07_Luci_e_Camera").objects.link(light_obj)

print("Antibagno camera and light set.")

