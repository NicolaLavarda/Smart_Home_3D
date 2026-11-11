import bpy
import bmesh
from mathutils import Euler
import math

def get_or_create_mat(name, color, roughness=0.35, metallic=0.0):
    mat = bpy.data.materials.get(name)
    if not mat:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()
        out = nodes.new("ShaderNodeOutputMaterial")
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
        mat.diffuse_color = color
    return mat

mat_wood_chair = get_or_create_mat("Mat_Legno_Tavolo_Noce", (0.35, 0.20, 0.10, 1.0), roughness=0.40)
mat_fabric = get_or_create_mat("Mat_Tessuto_Sedie", (0.78, 0.75, 0.68, 1.0), roughness=0.80)

col_furniture = bpy.data.collections.get("09_Arredi_Principali")
if not col_furniture:
    col_furniture = bpy.data.collections.new("09_Arredi_Principali")
    bpy.context.scene.collection.children.link(col_furniture)

# Remove any existing Sedia_Pranzo objects
for o in list(bpy.data.objects):
    if o.name.startswith("Sedia_Pranzo_"):
        bpy.data.objects.remove(o, do_unlink=True)

def create_chair(name, cx, cy, facing='N'):
    if facing == 'N': rot_z = 0.0
    elif facing == 'S': rot_z = math.pi
    elif facing == 'E': rot_z = -math.pi / 2.0
    elif facing == 'W': rot_z = math.pi / 2.0
    
    seat_w = 0.44
    seat_d = 0.42
    seat_h = 0.45
    back_h = 0.94
    back_y = -seat_d / 2.0 + 0.03
    
    bm = bmesh.new()
    
    # 1. Four Legs
    leg_coords = [
        (-seat_w/2 + 0.03, -seat_d/2 + 0.03),
        (seat_w/2 - 0.03, -seat_d/2 + 0.03),
        (-seat_w/2 + 0.03, seat_d/2 - 0.03),
        (seat_w/2 - 0.03, seat_d/2 - 0.03)
    ]
    for lx, ly in leg_coords:
        res = bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.016, radius2=0.016, depth=seat_h - 0.02)
        bmesh.ops.translate(bm, vec=(lx, ly, (seat_h - 0.02) / 2.0), verts=res['verts'])
        
    # 2. Leg Stretchers
    for side_x in [-seat_w/2 + 0.03, seat_w/2 - 0.03]:
        res = bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=(0.014, seat_d - 0.06, 0.014), verts=res['verts'])
        bmesh.ops.translate(bm, vec=(side_x, 0.0, 0.12), verts=res['verts'])
    res_f = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(seat_w - 0.06, 0.014, 0.014), verts=res_f['verts'])
    bmesh.ops.translate(bm, vec=(0.0, seat_d/2 - 0.03, 0.09), verts=res_f['verts'])
    res_b = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(seat_w - 0.06, 0.014, 0.014), verts=res_b['verts'])
    bmesh.ops.translate(bm, vec=(0.0, -seat_d/2 + 0.03, 0.14), verts=res_b['verts'])

    # 3. Wooden Seat Apron Frame
    res_apron = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(seat_w - 0.02, seat_d - 0.02, 0.035), verts=res_apron['verts'])
    bmesh.ops.translate(bm, vec=(0.0, 0.0, seat_h - 0.02), verts=res_apron['verts'])

    # 4. Backrest Uprights
    for side_x in [-seat_w/2 + 0.03, seat_w/2 - 0.03]:
        res = bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.015, radius2=0.015, depth=back_h - seat_h)
        bmesh.ops.translate(bm, vec=(side_x, back_y, seat_h + (back_h - seat_h) / 2.0), verts=res['verts'])
        
    # 5. Top Horizontal Rail
    res_rail = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(seat_w, 0.024, 0.065), verts=res_rail['verts'])
    bmesh.ops.translate(bm, vec=(0.0, back_y, back_h - 0.032), verts=res_rail['verts'])
    
    # 6. 4 Vertical Slats
    for si in range(4):
        slat_x = ((si - 1.5) / 1.5) * 0.13
        res = bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.009, radius2=0.009, depth=back_h - seat_h - 0.10)
        bmesh.ops.translate(bm, vec=(slat_x, back_y, seat_h + 0.04 + (back_h - seat_h - 0.10) / 2.0), verts=res['verts'])
        
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh_wood = bpy.data.meshes.new(f"{name}_Wood")
    bm.to_mesh(mesh_wood)
    bm.free()
    
    obj_wood = bpy.data.objects.new(name, mesh_wood)
    obj_wood.location = (cx, cy, 0.0)
    obj_wood.rotation_euler = Euler((0.0, 0.0, rot_z), 'XYZ')
    obj_wood.data.materials.append(mat_wood_chair)
    col_furniture.objects.link(obj_wood)
    
    # Padded Seat Cushion
    bm_seat = bmesh.new()
    res_cushion = bmesh.ops.create_cube(bm_seat, size=1.0)
    bmesh.ops.scale(bm_seat, vec=(seat_w, seat_d, 0.045), verts=res_cushion['verts'])
    bmesh.ops.bevel(bm_seat, geom=bm_seat.edges[:], offset=0.015, segments=2)
    bmesh.ops.recalc_face_normals(bm_seat, faces=bm_seat.faces)
    mesh_seat = bpy.data.meshes.new(f"{name}_Seat")
    bm_seat.to_mesh(mesh_seat)
    bm_seat.free()
    
    obj_seat = bpy.data.objects.new(f"{name}_Seat", mesh_seat)
    obj_seat.location = (cx, cy, seat_h)
    obj_seat.rotation_euler = Euler((0.0, 0.0, rot_z), 'XYZ')
    obj_seat.data.materials.append(mat_fabric)
    col_furniture.objects.link(obj_seat)
    
    return obj_wood

# Table dimensions: dt_x0=11.07, dt_x1=12.03, dt_y0=-6.35, dt_y1=-4.45
# Center: cx = 11.55, cy = -5.40
dt_x0, dt_x1 = 11.07, 12.03
dt_y0, dt_y1 = -6.35, -4.45

# 2 chairs on West side facing East towards the table
create_chair("Sedia_Pranzo_W_1", dt_x0 - 0.30, -5.85, facing='E')
create_chair("Sedia_Pranzo_W_2", dt_x0 - 0.30, -4.95, facing='E')

# 2 chairs on East side facing West towards the table
create_chair("Sedia_Pranzo_E_1", dt_x1 + 0.30, -5.85, facing='W')
create_chair("Sedia_Pranzo_E_2", dt_x1 + 0.30, -4.95, facing='W')

# Capotavola North facing South towards table
create_chair("Sedia_Pranzo_Capotavola_N", (dt_x0 + dt_x1)/2.0, dt_y1 + 0.30, facing='S')

# Capotavola South facing North towards table
create_chair("Sedia_Pranzo_Capotavola_S", (dt_x0 + dt_x1)/2.0, dt_y0 - 0.30, facing='N')

print("Created 6 dining chairs around dining table!")
bpy.ops.wm.save_mainfile()
print("Saved Smart_Home_3D.blend successfully!")

