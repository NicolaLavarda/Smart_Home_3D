import bpy

print("=== RENDERING KITCHEN DISHWASHER PREVIEW ===")

# Posiziona temporaneamente una camera per inquadrare da vicino lavello, lavastoviglie, cassetti e angolo
cam = bpy.data.objects.get("Cam_Preview_Dishwasher")
if not cam:
    cam_data = bpy.data.cameras.new("Cam_Preview_Dishwasher")
    cam = bpy.data.objects.new("Cam_Preview_Dishwasher", cam_data)
    bpy.context.scene.collection.objects.link(cam)

cam.location = (8.15, -5.20, 1.25)
cam.rotation_euler = (1.35, 0.0, 3.14159) # puntata verso sud (-Y) leggermente inclinata verso il basso

bpy.context.scene.camera = cam
bpy.context.scene.render.resolution_x = 960
bpy.context.scene.render.resolution_y = 540
bpy.context.scene.render.engine = 'BLENDER_EEVEE'
bpy.context.scene.render.filepath = "C:/Users/Nicola Lavarda/Jupyter/Domotica/Smart_Home_3D/public/models/preview_dishwasher.png"

bpy.ops.render.render(write_still=True)
print("Rendered preview saved to public/models/preview_dishwasher.png")
