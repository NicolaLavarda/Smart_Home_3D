import bpy
import math

# Adjust Antibagno door swing so it folds against the wall (85 degrees)
obj_door = bpy.data.objects.get("Door_Antibagno_Panel")
if obj_door:
    bpy.data.objects.remove(obj_door, do_unlink=True)

# Recreate door leaf folded against the right wall
hx_a = 9.40
hy_a = -3.68
rad_anti = math.radians(85.0)
p_w_anti = 0.66
p_h_anti = 2.08
p_t_anti = 0.04
c_loc_a = [(-p_w_anti, -p_t_anti/2), (0, -p_t_anti/2), (0, p_t_anti/2), (-p_w_anti, p_t_anti/2)]
c_rot_a = [(hx_a + x*math.cos(rad_anti) - y*math.sin(rad_anti), hy_a + x*math.sin(rad_anti) + y*math.cos(rad_anti)) for x, y in c_loc_a]

mesh_a = bpy.data.meshes.new("Door_Antibagno_Panel")
verts_a = [(c_rot_a[0][0], c_rot_a[0][1], 0.0), (c_rot_a[1][0], c_rot_a[1][1], 0.0),
           (c_rot_a[2][0], c_rot_a[2][1], 0.0), (c_rot_a[3][0], c_rot_a[3][1], 0.0),
           (c_rot_a[0][0], c_rot_a[0][1], p_h_anti), (c_rot_a[1][0], c_rot_a[1][1], p_h_anti),
           (c_rot_a[2][0], c_rot_a[2][1], p_h_anti), (c_rot_a[3][0], c_rot_a[3][1], p_h_anti)]
faces_a = [(0,3,2,1), (4,5,6,7), (0,1,5,4), (1,2,6,5), (2,3,7,6), (3,0,4,7)]
mesh_a.from_pydata(verts_a, [], faces_a)
mesh_a.update()
obj_a = bpy.data.objects.new("Door_Antibagno_Panel", mesh_a)
obj_a.data.materials.append(bpy.data.materials.get("Mat_Legno_Porta"))
bpy.data.collections.get("03_Infissi_Porte_Garage").objects.link(obj_a)

# Position camera inside doorway at y=-3.40 looking north towards the cupboard
cam_obj = bpy.data.objects.get("Camera_Antibagno_Inside")
if cam_obj:
    cam_obj.location = (9.07, -3.35, 1.25)
    cam_obj.rotation_euler = (math.radians(85.0), 0.0, 0.0)
    cam_obj.data.lens = 20

print("Door swung against wall and camera moved inside.")

