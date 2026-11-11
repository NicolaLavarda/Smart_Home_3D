import bpy
import math

# Fix Door_Bagno_Panel: must swing INWARDS into the Bagno (X < 8.46)
obj_bath = bpy.data.objects.get("Door_Bagno_Panel")
if obj_bath:
    bpy.data.objects.remove(obj_bath, do_unlink=True)

# Hinge at north jamb (8.48, -2.76) or south jamb (8.48, -3.56)
# If hinge at south jamb (8.48, -3.56), swinging into bathroom (West):
# angle = +50 degrees into bathroom (towards -x)
hx_b = 8.46
hy_b = -3.56
p_w_b = 0.74
p_h_b = 2.08
p_t_b = 0.04
rad_b = math.radians(130.0) # swings towards -X into bathroom

c_loc_b = [(-p_t_b/2, 0), (p_t_b/2, 0), (p_t_b/2, p_w_b), (-p_t_b/2, p_w_b)]
c_rot_b = [(hx_b + x*math.cos(rad_b) - y*math.sin(rad_b), hy_b + x*math.sin(rad_b) + y*math.cos(rad_b)) for x, y in c_loc_b]

mesh_b = bpy.data.meshes.new("Door_Bagno_Panel")
verts_b = [(c_rot_b[0][0], c_rot_b[0][1], 0.0), (c_rot_b[1][0], c_rot_b[1][1], 0.0),
           (c_rot_b[2][0], c_rot_b[2][1], 0.0), (c_rot_b[3][0], c_rot_b[3][1], 0.0),
           (c_rot_b[0][0], c_rot_b[0][1], p_h_b), (c_rot_b[1][0], c_rot_b[1][1], p_h_b),
           (c_rot_b[2][0], c_rot_b[2][1], p_h_b), (c_rot_b[3][0], c_rot_b[3][1], p_h_b)]
faces_b = [(0,3,2,1), (4,5,6,7), (0,1,5,4), (1,2,6,5), (2,3,7,6), (3,0,4,7)]
mesh_b.from_pydata(verts_b, [], faces_b)
mesh_b.update()
obj_b = bpy.data.objects.new("Door_Bagno_Panel", mesh_b)
obj_b.data.materials.append(bpy.data.materials.get("Mat_Legno_Porta"))
bpy.data.collections.get("03_Infissi_Porte_Garage").objects.link(obj_b)

# Fix Door_Antibagno_Panel: swing against right wall (x=9.45, y from -3.68 to -3.02)
obj_anti = bpy.data.objects.get("Door_Antibagno_Panel")
if obj_anti:
    bpy.data.objects.remove(obj_anti, do_unlink=True)

hx_a = 9.41
hy_a = -3.68
p_w_a = 0.66
p_h_a = 2.08
p_t_a = 0.04
# Door leaf folded right against the east wall of antibagno
mesh_a = bpy.data.meshes.new("Door_Antibagno_Panel")
# Box along east wall
verts_a = [
    (9.38, -3.68, 0.0), (9.42, -3.68, 0.0),
    (9.42, -3.02, 0.0), (9.38, -3.02, 0.0),
    (9.38, -3.68, p_h_a), (9.42, -3.68, p_h_a),
    (9.42, -3.02, p_h_a), (9.38, -3.02, p_h_a)
]
faces_a = [(0,3,2,1), (4,5,6,7), (0,1,5,4), (1,2,6,5), (2,3,7,6), (3,0,4,7)]
mesh_a.from_pydata(verts_a, [], faces_a)
mesh_a.update()
obj_a = bpy.data.objects.new("Door_Antibagno_Panel", mesh_a)
obj_a.data.materials.append(bpy.data.materials.get("Mat_Legno_Porta"))
bpy.data.collections.get("03_Infissi_Porte_Garage").objects.link(obj_a)

# Camera looking into antibagno
cam_obj = bpy.data.objects.get("Camera_Antibagno_Inside")
if cam_obj:
    cam_obj.location = (9.07, -3.45, 1.15)
    cam_obj.rotation_euler = (math.radians(82.0), 0.0, 0.0)
    cam_obj.data.lens = 18

print("Both doors and camera adjusted correctly.")

