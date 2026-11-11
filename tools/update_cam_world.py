import bpy
import math

# Adjust World Background to bright architectural studio / sky
world = bpy.context.scene.world
if not world:
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
world.use_nodes = True
bg_node = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
bg_node.inputs["Color"].default_value = (0.94, 0.96, 0.98, 1.0)
bg_node.inputs["Strength"].default_value = 1.0

# Adjust Camera Overview to frame everything perfectly
cam_obj = bpy.data.objects.get("Camera_3D_Isometric")
if cam_obj:
    # Target center of entire property is around x=7.5, y=-9.0, z=1.5
    # Position camera at high isometric angle
    cam_obj.location = (23.0, -24.0, 24.0)
    cam_obj.rotation_euler = (math.radians(55.0), 0.0, math.radians(45.0))
    cam_obj.data.lens = 42

print("Camera and World updated.")

