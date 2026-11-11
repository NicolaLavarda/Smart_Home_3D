"""
Complete Updated 3D Architectural Scene in Blender matching Revit project:
- Salotto (Living Room): 5.76m x 6.51m
- Bagno: 2.09m x 3.26m
- Vano Scala / Disimpegno
- Sala da pranzo (Dining Room): 7.56m x 7.45m
- Lavanderia (Laundry): 4.15m x 2.60m (outer 4.65m x 3.00m)
- Garage: 7.21m x 5.00m (outer 7.81m x 5.60m) with 2.40m sectional overhead door, 0.92m north pedestrian door, north portico with 3 pillars, south windows, basement stair
- Portico: Paved patio and walkways connecting house, lavanderia, and garage
- Giardini: Giardino Area 1 (South), Giardino Area 2 (East private lawn), Giardino Area 3 (West expansive lawn)
- Driveway / Viale: Gravel road from "All'aperto" entrance curving towards the Garage
- Boundary fencing and walls
- Exact materials, lights, and cameras
"""

import bpy
import bmesh
from mathutils import Vector, Matrix
import math

print("=== Starting Full Architectural Update with Garage & Gardens ===")

# -------------------------------------------------------------
# 1. CLEAN SCENE
# -------------------------------------------------------------
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

for col in [bpy.data.meshes, bpy.data.materials, bpy.data.curves, bpy.data.lights, bpy.data.cameras]:
    for item in list(col):
        col.remove(item)

for col in list(bpy.data.collections):
    bpy.data.collections.remove(col)

scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1.0
scene.unit_settings.length_unit = 'METERS'

# Collections
col_walls = bpy.data.collections.new("01_Pareti")
col_floors = bpy.data.collections.new("02_Pavimenti_e_Giardini")
col_fixtures = bpy.data.collections.new("03_Infissi_Porte_Garage")
col_stairs = bpy.data.collections.new("04_Scale")
col_furniture = bpy.data.collections.new("05_Arredi_Sanitari")
col_labels = bpy.data.collections.new("06_Etichette_Stanze")
col_lighting = bpy.data.collections.new("07_Luci_e_Camera")

for c in [col_walls, col_floors, col_fixtures, col_stairs, col_furniture, col_labels, col_lighting]:
    bpy.context.scene.collection.children.link(c)

# -------------------------------------------------------------
# 2. HIGH QUALITY MATERIALS
# -------------------------------------------------------------
def create_mat(name, base_color, roughness=0.5, metallic=0.0, transmission=0.0, ior=1.45, alpha=1.0):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    
    bsdf.inputs["Base Color"].default_value = base_color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    
    if "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = transmission
    elif "Transmission" in bsdf.inputs:
        bsdf.inputs["Transmission"].default_value = transmission
        
    if "IOR" in bsdf.inputs:
        bsdf.inputs["IOR"].default_value = ior
        
    if alpha < 1.0:
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = alpha
        mat.blend_method = 'BLEND'
    return mat

# Architecture Materials matching Revit renders:
# Dark graphite / charcoal exterior walls
mat_wall_ext = create_mat("Mat_Muro_Esterno_Dark", (0.28, 0.29, 0.31, 1.0), roughness=0.85)
# Warm white interior walls
mat_wall_int = create_mat("Mat_Muro_Interno_Light", (0.95, 0.94, 0.92, 1.0), roughness=0.90)
# Parquet for Salotto & Sala da pranzo
mat_parquet = create_mat("Mat_Parquet_Rovere", (0.54, 0.37, 0.22, 1.0), roughness=0.32)
# Bathroom tiles
mat_tile = create_mat("Mat_Gres_Bagno", (0.70, 0.76, 0.82, 1.0), roughness=0.20)
# Laundry tiles
mat_laundry_floor = create_mat("Mat_Gres_Lavanderia", (0.65, 0.62, 0.58, 1.0), roughness=0.40)
# Garage concrete floor
mat_garage_floor = create_mat("Mat_Cemento_Garage", (0.42, 0.42, 0.43, 1.0), roughness=0.60)
# Paved Portico & Walkways (Grey stone)
mat_portico = create_mat("Mat_Lastricato_Portico", (0.62, 0.60, 0.57, 1.0), roughness=0.70)
# Vibrant Lawn / Grass (Giardino 1, 2, 3)
mat_grass = create_mat("Mat_Prato_Giardino", (0.25, 0.50, 0.15, 1.0), roughness=0.85)
# Gravel / Driveway (Ghiaia viale)
mat_gravel = create_mat("Mat_Ghiaia_Viale", (0.52, 0.50, 0.48, 1.0), roughness=0.90)
# Curbs / borders
mat_curb = create_mat("Mat_Cordolo_Pietra", (0.75, 0.74, 0.72, 1.0), roughness=0.60)
# Anthracite frames
mat_frame = create_mat("Mat_Infissi_Antracite", (0.12, 0.12, 0.13, 1.0), roughness=0.25, metallic=0.5)
# Glass
mat_glass = create_mat("Mat_Vetro", (0.95, 0.98, 1.0, 1.0), roughness=0.03, transmission=0.98, ior=1.52, alpha=0.35)
# Interior doors (natural oak)
mat_door_wood = create_mat("Mat_Legno_Porta", (0.44, 0.30, 0.17, 1.0), roughness=0.38)
# Garage sectional door
mat_garage_door = create_mat("Mat_Portone_Garage", (0.75, 0.76, 0.78, 1.0), roughness=0.35, metallic=0.3)
# Chrome
mat_chrome = create_mat("Mat_Cromo", (0.95, 0.95, 0.95, 1.0), roughness=0.10, metallic=1.0)
# White ceramic
mat_ceramic = create_mat("Mat_Ceramica_Sanitari", (0.97, 0.97, 0.97, 1.0), roughness=0.12)
# Stairs
mat_stairs = create_mat("Mat_Scale_Legno", (0.46, 0.31, 0.17, 1.0), roughness=0.38)
# Perimeter metal railing
mat_railing = create_mat("Mat_Ringhiera_Metallo", (0.15, 0.15, 0.16, 1.0), roughness=0.30, metallic=0.8)
# Text labels
mat_label = create_mat("Mat_Etichette", (0.15, 0.15, 0.18, 1.0), roughness=0.50)

# -------------------------------------------------------------
# 3. DIRECT MESH BOX BUILDER
# -------------------------------------------------------------
def make_box(name, x_min, x_max, y_min, y_max, z_min, z_max, mat=None, collection=None):
    if x_min > x_max: x_min, x_max = x_max, x_min
    if y_min > y_max: y_min, y_max = y_max, y_min
    if z_min > z_max: z_min, z_max = z_max, z_min
    
    if abs(x_max - x_min) < 0.0001 or abs(y_max - y_min) < 0.0001 or abs(z_max - z_min) < 0.0001:
        return None
        
    mesh = bpy.data.meshes.new(name)
    verts = [
        (x_min, y_min, z_min), (x_max, y_min, z_min),
        (x_max, y_max, z_min), (x_min, y_max, z_min),
        (x_min, y_min, z_max), (x_max, y_min, z_max),
        (x_max, y_max, z_max), (x_min, y_max, z_max)
    ]
    faces = [
        (0, 3, 2, 1), # -z
        (4, 5, 6, 7), # +z
        (0, 1, 5, 4), # -y
        (1, 2, 6, 5), # +x
        (2, 3, 7, 6), # +y
        (3, 0, 4, 7)  # -x
    ]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    
    obj = bpy.data.objects.new(name, mesh)
    if mat:
        obj.data.materials.append(mat)
    if collection:
        collection.objects.link(obj)
    else:
        bpy.context.scene.collection.objects.link(obj)
    return obj

def add_window(name, x_min, x_max, y_min, y_max, sill_h, lintel_h, is_y_axis=False):
    t_frame = 0.05
    d_frame = 0.08
    if not is_y_axis:
        w = abs(x_max - x_min)
        y_c = (y_min + y_max) / 2.0
        make_box(f"{name}_Frame_Bottom", x_min, x_max, y_c - d_frame/2, y_c + d_frame/2, sill_h, sill_h + t_frame, mat_frame, col_fixtures)
        make_box(f"{name}_Frame_Top", x_min, x_max, y_c - d_frame/2, y_c + d_frame/2, lintel_h - t_frame, lintel_h, mat_frame, col_fixtures)
        make_box(f"{name}_Frame_Left", x_min, x_min + t_frame, y_c - d_frame/2, y_c + d_frame/2, sill_h + t_frame, lintel_h - t_frame, mat_frame, col_fixtures)
        make_box(f"{name}_Frame_Right", x_max - t_frame, x_max, y_c - d_frame/2, y_c + d_frame/2, sill_h + t_frame, lintel_h - t_frame, mat_frame, col_fixtures)
        if w > 0.70:
            x_m = (x_min + x_max) / 2.0
            make_box(f"{name}_Mullion", x_m - t_frame/2, x_m + t_frame/2, y_c - d_frame/2, y_c + d_frame/2, sill_h + t_frame, lintel_h - t_frame, mat_frame, col_fixtures)
        make_box(f"{name}_Glass", x_min + t_frame, x_max - t_frame, y_c - 0.01, y_c + 0.01, sill_h + t_frame, lintel_h - t_frame, mat_glass, col_fixtures)
    else:
        x_c = (x_min + x_max) / 2.0
        make_box(f"{name}_Frame_Bottom", x_c - d_frame/2, x_c + d_frame/2, y_min, y_max, sill_h, sill_h + t_frame, mat_frame, col_fixtures)
        make_box(f"{name}_Frame_Top", x_c - d_frame/2, x_c + d_frame/2, y_min, y_max, lintel_h - t_frame, lintel_h, mat_frame, col_fixtures)
        make_box(f"{name}_Frame_Front", x_c - d_frame/2, x_c + d_frame/2, y_min, y_min + t_frame, sill_h + t_frame, lintel_h - t_frame, mat_frame, col_fixtures)
        make_box(f"{name}_Frame_Back", x_c - d_frame/2, x_c + d_frame/2, y_max - t_frame, y_max, sill_h + t_frame, lintel_h - t_frame, mat_frame, col_fixtures)
        make_box(f"{name}_Glass", x_c - 0.01, x_c + 0.01, y_min + t_frame, y_max - t_frame, sill_h + t_frame, lintel_h - t_frame, mat_glass, col_fixtures)

def add_door(name, x_min, x_max, y_min, y_max, lintel_h=2.13, is_y_axis=False, open_deg=35.0):
    t_frame = 0.05
    d_frame = 0.10
    rad = math.radians(open_deg)
    if not is_y_axis:
        w = abs(x_max - x_min)
        y_c = (y_min + y_max) / 2.0
        make_box(f"{name}_Frame_Top", x_min, x_max, y_c - d_frame/2, y_c + d_frame/2, lintel_h - t_frame, lintel_h, mat_door_wood, col_fixtures)
        make_box(f"{name}_Frame_Left", x_min, x_min + t_frame, y_c - d_frame/2, y_c + d_frame/2, 0.0, lintel_h - t_frame, mat_door_wood, col_fixtures)
        make_box(f"{name}_Frame_Right", x_max - t_frame, x_max, y_c - d_frame/2, y_c + d_frame/2, 0.0, lintel_h - t_frame, mat_door_wood, col_fixtures)
        
        p_w = w - 2*t_frame
        p_t = 0.04
        p_h = lintel_h - t_frame
        hx = x_min + t_frame
        hy = y_c
        c_loc = [(0, -p_t/2), (p_w, -p_t/2), (p_w, p_t/2), (0, p_t/2)]
        c_rot = [(hx + x*math.cos(rad) - y*math.sin(rad), hy + x*math.sin(rad) + y*math.cos(rad)) for x, y in c_loc]
        
        mesh = bpy.data.meshes.new(f"{name}_Panel")
        verts = [(c_rot[0][0], c_rot[0][1], 0.0), (c_rot[1][0], c_rot[1][1], 0.0),
                 (c_rot[2][0], c_rot[2][1], 0.0), (c_rot[3][0], c_rot[3][1], 0.0),
                 (c_rot[0][0], c_rot[0][1], p_h), (c_rot[1][0], c_rot[1][1], p_h),
                 (c_rot[2][0], c_rot[2][1], p_h), (c_rot[3][0], c_rot[3][1], p_h)]
        faces = [(0,3,2,1), (4,5,6,7), (0,1,5,4), (1,2,6,5), (2,3,7,6), (3,0,4,7)]
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(f"{name}_Panel", mesh)
        obj.data.materials.append(mat_door_wood)
        col_fixtures.objects.link(obj)
        
        hand_dist = p_w - 0.08
        han_x = hx + hand_dist * math.cos(rad)
        han_y = hy + hand_dist * math.sin(rad)
        make_box(f"{name}_Handle", han_x - 0.06, han_x + 0.06, han_y - 0.02, han_y + 0.02, 0.98, 1.02, mat_chrome, col_fixtures)
    else:
        d = abs(y_max - y_min)
        x_c = (x_min + x_max) / 2.0
        make_box(f"{name}_Frame_Top", x_c - d_frame/2, x_c + d_frame/2, y_min, y_max, lintel_h - t_frame, lintel_h, mat_door_wood, col_fixtures)
        make_box(f"{name}_Frame_Front", x_c - d_frame/2, x_c + d_frame/2, y_min, y_min + t_frame, 0.0, lintel_h - t_frame, mat_door_wood, col_fixtures)
        make_box(f"{name}_Frame_Back", x_c - d_frame/2, x_c + d_frame/2, y_max - t_frame, y_max, 0.0, lintel_h - t_frame, mat_door_wood, col_fixtures)
        
        p_w = d - 2*t_frame
        p_t = 0.04
        p_h = lintel_h - t_frame
        hx = x_c
        hy = y_min + t_frame
        c_loc = [(-p_t/2, 0), (p_t/2, 0), (p_t/2, p_w), (-p_t/2, p_w)]
        c_rot = [(hx + x*math.cos(rad) - y*math.sin(rad), hy + x*math.sin(rad) + y*math.cos(rad)) for x, y in c_loc]
        mesh = bpy.data.meshes.new(f"{name}_Panel")
        verts = [(c_rot[0][0], c_rot[0][1], 0.0), (c_rot[1][0], c_rot[1][1], 0.0),
                 (c_rot[2][0], c_rot[2][1], 0.0), (c_rot[3][0], c_rot[3][1], 0.0),
                 (c_rot[0][0], c_rot[0][1], p_h), (c_rot[1][0], c_rot[1][1], p_h),
                 (c_rot[2][0], c_rot[2][1], p_h), (c_rot[3][0], c_rot[3][1], p_h)]
        faces = [(0,3,2,1), (4,5,6,7), (0,1,5,4), (1,2,6,5), (2,3,7,6), (3,0,4,7)]
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(f"{name}_Panel", mesh)
        obj.data.materials.append(mat_door_wood)
        col_fixtures.objects.link(obj)

# -------------------------------------------------------------
# 4. MAIN HOUSE (Salotto, Bagno, Scala, Sala da pranzo) H = 3.00m
# -------------------------------------------------------------
H_MAIN = 3.00

# PARETE NORD (y: -0.30 a 0.00, x: 0.00 a 14.20)
make_box("Wall_North_01", 0.00, 1.35, -0.30, 0.00, 0.0, H_MAIN, mat_wall_ext, col_walls)
make_box("Wall_North_Sill_1", 1.35, 2.27, -0.30, 0.00, 0.0, 1.00, mat_wall_ext, col_walls)
make_box("Wall_North_Lintel_1", 1.35, 2.27, -0.30, 0.00, 2.83, H_MAIN, mat_wall_ext, col_walls)
add_window("Win_N1", 1.35, 2.27, -0.30, 0.00, 1.00, 2.83)

make_box("Wall_North_02", 2.27, 4.00, -0.30, 0.00, 0.0, H_MAIN, mat_wall_ext, col_walls)
make_box("Wall_North_Sill_2", 4.00, 4.92, -0.30, 0.00, 0.0, 1.00, mat_wall_ext, col_walls)
make_box("Wall_North_Lintel_2", 4.00, 4.92, -0.30, 0.00, 2.83, H_MAIN, mat_wall_ext, col_walls)
add_window("Win_N2", 4.00, 4.92, -0.30, 0.00, 1.00, 2.83)

make_box("Wall_North_03", 4.92, 6.96, -0.30, 0.00, 0.0, H_MAIN, mat_wall_ext, col_walls)
make_box("Wall_North_Sill_3", 6.96, 7.88, -0.30, 0.00, 0.0, 1.00, mat_wall_ext, col_walls)
make_box("Wall_North_Lintel_3", 6.96, 7.88, -0.30, 0.00, 2.83, H_MAIN, mat_wall_ext, col_walls)
add_window("Win_N3", 6.96, 7.88, -0.30, 0.00, 1.00, 2.83)

make_box("Wall_North_04", 7.88, 10.05, -0.30, 0.00, 0.0, H_MAIN, mat_wall_ext, col_walls)
make_box("Wall_North_Sill_4", 10.05, 10.97, -0.30, 0.00, 0.0, 1.00, mat_wall_ext, col_walls)
make_box("Wall_North_Lintel_4", 10.05, 10.97, -0.30, 0.00, 2.83, H_MAIN, mat_wall_ext, col_walls)
add_window("Win_N4", 10.05, 10.97, -0.30, 0.00, 1.00, 2.83)

make_box("Wall_North_05", 10.97, 14.20, -0.30, 0.00, 0.0, H_MAIN, mat_wall_ext, col_walls)

# PARETE OVEST SALOTTO (x: 0.00 a 0.30, y: 0.00 a -8.21)
make_box("Wall_West_01", 0.00, 0.30, -3.50, 0.00, 0.0, H_MAIN, mat_wall_ext, col_walls)
make_box("Wall_West_Sill_1", 0.00, 0.30, -3.91, -3.50, 0.0, 1.00, mat_wall_ext, col_walls)
make_box("Wall_West_Lintel_1", 0.00, 0.30, -3.91, -3.50, 1.61, H_MAIN, mat_wall_ext, col_walls)
add_window("Win_W1", 0.00, 0.30, -3.91, -3.50, 1.00, 1.61, is_y_axis=True)
make_box("Wall_West_02", 0.00, 0.30, -8.21, -3.91, 0.0, H_MAIN, mat_wall_ext, col_walls)

# PARETE SUD SALOTTO (y: -7.11 a -6.81, x: 0.30 a 6.07)
make_box("Wall_South_West_01", 0.30, 1.44, -7.11, -6.81, 0.0, H_MAIN, mat_wall_ext, col_walls)
make_box("Wall_South_West_Sill_1", 1.44, 2.36, -7.11, -6.81, 0.0, 1.00, mat_wall_ext, col_walls)
make_box("Wall_South_West_Lintel_1", 1.44, 2.36, -7.11, -6.81, 2.83, H_MAIN, mat_wall_ext, col_walls)
add_window("Win_SW1", 1.44, 2.36, -7.11, -6.81, 1.00, 2.83)
make_box("Wall_South_West_02", 2.36, 3.50, -7.11, -6.81, 0.0, H_MAIN, mat_wall_ext, col_walls)
make_box("Wall_South_West_Door_Lintel", 3.50, 4.42, -7.11, -6.81, 2.13, H_MAIN, mat_wall_ext, col_walls)
add_door("Door_Salotto_Sud", 3.50, 4.42, -7.11, -6.81, lintel_h=2.13, open_deg=45.0)
make_box("Wall_South_West_03", 4.42, 6.07, -7.11, -6.81, 0.0, H_MAIN, mat_wall_ext, col_walls)

# MURO DIVISORIO SALOTTO / SALA DA PRANZO (x: 6.07 a 6.37)
make_box("Wall_Div_01", 6.07, 6.37, -3.85, -0.30, 0.0, H_MAIN, mat_wall_int, col_walls)
make_box("Wall_Div_Lintel", 6.07, 6.37, -5.85, -3.85, 2.83, H_MAIN, mat_wall_int, col_walls)
make_box("Wall_Div_02", 6.07, 6.37, -8.05, -5.85, 0.0, H_MAIN, mat_wall_int, col_walls)

# BAGNO (x: 6.37 a 8.46, y: -3.85 a -3.56)
make_box("Wall_Bath_South_Solid", 6.37, 7.66, -3.85, -3.56, 0.0, H_MAIN, mat_wall_int, col_walls)
make_box("Wall_Bath_South_Lintel", 7.66, 8.46, -3.85, -3.56, 2.13, H_MAIN, mat_wall_int, col_walls)
add_door("Door_Bagno", 7.66, 8.46, -3.85, -3.56, lintel_h=2.13, open_deg=-60.0)

# SCALA
make_box("Wall_Stair_West", 8.46, 8.69, -3.56, -0.30, 0.0, H_MAIN, mat_wall_int, col_walls)
make_box("Wall_Stair_East", 9.70, 10.05, -3.85, -0.30, 0.0, H_MAIN, mat_wall_int, col_walls)
make_box("Wall_Stair_Door_Lintel", 8.69, 9.45, -3.85, -3.56, 2.13, H_MAIN, mat_wall_int, col_walls)
make_box("Wall_Stair_Door_Post", 9.45, 9.70, -3.85, -3.56, 0.0, H_MAIN, mat_wall_int, col_walls)
add_door("Door_Scala", 8.69, 9.45, -3.85, -3.56, lintel_h=2.13, open_deg=-45.0)

# PARETE EST SALA DA PRANZO
make_box("Wall_East_Ext", 13.90, 14.20, -8.05, 0.00, 0.0, H_MAIN, mat_wall_ext, col_walls)

# PARETE SUD SALA DA PRANZO (y: -8.05 a -7.75, x: 6.37 a 13.90)
make_box("Wall_Dining_South_01", 6.37, 7.57, -8.05, -7.75, 0.0, H_MAIN, mat_wall_ext, col_walls)
make_box("Wall_Dining_South_Sill_1", 7.57, 8.49, -8.05, -7.75, 0.0, 1.00, mat_wall_ext, col_walls)
make_box("Wall_Dining_South_Lintel_1", 7.57, 8.49, -8.05, -7.75, 2.83, H_MAIN, mat_wall_ext, col_walls)
add_window("Win_Dining_S1", 7.57, 8.49, -8.05, -7.75, 1.00, 2.83)

make_box("Wall_Dining_South_02", 8.49, 11.15, -8.05, -7.75, 0.0, H_MAIN, mat_wall_ext, col_walls)
make_box("Wall_Dining_South_Door_Lintel", 11.15, 12.07, -8.05, -7.75, 2.13, H_MAIN, mat_wall_ext, col_walls)
add_door("Door_Dining_Main", 11.15, 12.07, -8.05, -7.75, lintel_h=2.13, open_deg=50.0)

make_box("Wall_Dining_South_03", 12.07, 12.82, -8.05, -7.75, 0.0, H_MAIN, mat_wall_ext, col_walls)
make_box("Wall_Dining_South_Sill_2", 12.82, 13.74, -8.05, -7.75, 0.0, 1.00, mat_wall_ext, col_walls)
make_box("Wall_Dining_South_Lintel_2", 12.82, 13.74, -8.05, -7.75, 2.83, H_MAIN, mat_wall_ext, col_walls)
add_window("Win_Dining_S2", 12.82, 13.74, -8.05, -7.75, 1.00, 2.83)
make_box("Wall_Dining_South_04", 13.74, 13.90, -8.05, -7.75, 0.0, H_MAIN, mat_wall_ext, col_walls)

# Muretto divisorio interno ingresso Sala da pranzo (22cm x 110cm)
make_box("Wall_Dining_Partition", 9.71, 9.93, -7.75, -6.65, 0.0, H_MAIN, mat_wall_int, col_walls)

# -------------------------------------------------------------
# 5. LAVANDERIA (Centrale) H = 2.70m
# -------------------------------------------------------------
H_LAV = 2.70
make_box("Wall_Lav_West", 0.00, 0.30, -15.43, -11.33, 0.0, H_LAV, mat_wall_ext, col_walls)
make_box("Wall_Lav_North_01", 0.30, 2.70, -12.63, -12.43, 0.0, H_LAV, mat_wall_ext, col_walls)
make_box("Wall_Lav_North_Door_Lintel", 2.70, 3.62, -12.63, -12.43, 2.13, H_LAV, mat_wall_ext, col_walls)
add_door("Door_Lav_North", 2.70, 3.62, -12.63, -12.43, lintel_h=2.13, open_deg=40.0)
make_box("Wall_Lav_North_02", 3.62, 4.65, -12.63, -12.43, 0.0, H_LAV, mat_wall_ext, col_walls)
make_box("Wall_Lav_East", 4.45, 4.65, -15.43, -12.63, 0.0, H_LAV, mat_wall_ext, col_walls)

make_box("Wall_Lav_South_01", 0.30, 0.82, -15.43, -15.23, 0.0, H_LAV, mat_wall_ext, col_walls)
make_box("Wall_Lav_South_Sill_1", 0.82, 1.43, -15.43, -15.23, 0.0, 1.00, mat_wall_ext, col_walls)
make_box("Wall_Lav_South_Lintel_1", 0.82, 1.43, -15.43, -15.23, 1.61, H_LAV, mat_wall_ext, col_walls)
add_window("Win_Lav_1", 0.82, 1.43, -15.43, -15.23, 1.00, 1.61)

make_box("Wall_Lav_South_02", 1.43, 3.08, -15.43, -15.23, 0.0, H_LAV, mat_wall_ext, col_walls)
make_box("Wall_Lav_South_Sill_2", 3.08, 3.69, -15.43, -15.23, 0.0, 1.00, mat_wall_ext, col_walls)
make_box("Wall_Lav_South_Lintel_2", 3.08, 3.69, -15.43, -15.23, 1.61, H_LAV, mat_wall_ext, col_walls)
add_window("Win_Lav_2", 3.08, 3.69, -15.43, -15.23, 1.00, 1.61)

make_box("Wall_Lav_South_03", 3.69, 4.45, -15.43, -15.23, 0.0, H_LAV, mat_wall_ext, col_walls)

# Tramezze interne lavanderia
make_box("Wall_Lav_Part_V1", 1.43, 1.65, -15.23, -14.46, 0.0, H_LAV, mat_wall_int, col_walls)
make_box("Wall_Lav_Part_H1", 1.43, 2.50, -14.46, -14.24, 0.0, H_LAV, mat_wall_int, col_walls)
make_box("Wall_Lav_Part_V2", 3.08, 3.30, -15.23, -14.46, 0.0, H_LAV, mat_wall_int, col_walls)

# Due pilastri del portico tra Lavanderia e Giardino 2 (30x30 cm)
make_box("Pillar_Court_1", 5.25, 5.55, -12.73, -12.43, 0.0, H_LAV, mat_wall_ext, col_walls)
make_box("Pillar_Court_2", 5.25, 5.55, -15.23, -14.93, 0.0, H_LAV, mat_wall_ext, col_walls)

# -------------------------------------------------------------
# 6. GARAGE (Sud-Est)
# Misure da foglio 4:
# X esterno: da x=6.39 a x=14.20 (larghezza 7.81 m, spessore pareti 30 cm)
# Y esterno: da y=-23.73 a y=-18.13 (profondità 5.60 m, interno 5.00 m)
# Portone carrabile su parete Ovest (larghezza 2.40 m, h 2.10 m)
# Porta pedonale su parete Nord (larghezza 0.92 m, 0|213)
# Portico a Nord con 3 pilastri da 50x30 cm
# Due finestre a Nord e due finestre a Sud (61 cm, 100|161)
# -------------------------------------------------------------
H_GAR = 2.80
x_gar_min = 6.39
x_gar_max = 14.20
y_gar_north_wall_out = -18.13
y_gar_north_wall_in = -18.43
y_gar_south_wall_in = -23.43
y_gar_south_wall_out = -23.73

# Parete Est Garage (continua con muro di cinta)
make_box("Wall_Garage_East", 13.90, 14.20, y_gar_south_wall_out, y_gar_north_wall_out, 0.0, H_GAR, mat_wall_ext, col_walls)

# Parete Ovest Garage con Portone Sezionale (x: 6.39 a 6.69)
# y:
# Prolungamento Nord: da -17.13 a -18.13 (100 cm)
make_box("Wall_Garage_West_Ext", x_gar_min, x_gar_min + 0.30, -18.13, -17.13, 0.0, H_GAR, mat_wall_ext, col_walls)
# Spalla Nord: da -18.13 a -19.53 (140 cm)
make_box("Wall_Garage_West_01", x_gar_min, x_gar_min + 0.30, -19.53, -18.13, 0.0, H_GAR, mat_wall_ext, col_walls)
# Lintel Portone Garage (da -19.53 a -21.93, larghezza 2.40 m)
make_box("Wall_Garage_West_Door_Lintel", x_gar_min, x_gar_min + 0.30, -21.93, -19.53, 2.10, H_GAR, mat_wall_ext, col_walls)
# Spalla Sud: da -21.93 a -23.73 (180 cm)
make_box("Wall_Garage_West_02", x_gar_min, x_gar_min + 0.30, y_gar_south_wall_out, -21.93, 0.0, H_GAR, mat_wall_ext, col_walls)

# Portone Sezionale Garage 3D (pannelli orizzontali alluminio cannettato)
for pan in range(5):
    z_pan_0 = pan * (2.05 / 5.0)
    z_pan_1 = z_pan_0 + (2.05 / 5.0) - 0.015
    make_box(f"Garage_Door_Panel_{pan+1}", x_gar_min + 0.12, x_gar_min + 0.18, -21.90, -19.56, z_pan_0, z_pan_1, mat_garage_door, col_fixtures)

# Parete Nord Garage (y: -18.43 a -18.13)
# Spalla Ovest (80 cm da x=6.69 a 7.49)
make_box("Wall_Garage_North_01", 6.69, 7.49, y_gar_north_wall_in, y_gar_north_wall_out, 0.0, H_GAR, mat_wall_ext, col_walls)
# Porta pedonale Garage (92 cm da x=7.49 a 8.41)
make_box("Wall_Garage_North_Door_Lintel", 7.49, 8.41, y_gar_north_wall_in, y_gar_north_wall_out, 2.13, H_GAR, mat_wall_ext, col_walls)
add_door("Door_Garage_Pedestrian", 7.49, 8.41, y_gar_north_wall_in, y_gar_north_wall_out, lintel_h=2.13, open_deg=40.0)

# Muro con due finestre alte su parete Nord (61 cm ciascuna, 100|161)
# Solid da 8.41 a 9.02 (61 cm)
make_box("Wall_Garage_North_02", 8.41, 9.02, y_gar_north_wall_in, y_gar_north_wall_out, 0.0, H_GAR, mat_wall_ext, col_walls)
# Finestra N1 (da 9.02 a 9.63, 61 cm)
make_box("Wall_Garage_North_Sill_1", 9.02, 9.63, y_gar_north_wall_in, y_gar_north_wall_out, 0.0, 1.00, mat_wall_ext, col_walls)
make_box("Wall_Garage_North_Lintel_1", 9.02, 9.63, y_gar_north_wall_in, y_gar_north_wall_out, 1.61, H_GAR, mat_wall_ext, col_walls)
add_window("Win_Garage_N1", 9.02, 9.63, y_gar_north_wall_in, y_gar_north_wall_out, 1.00, 1.61)

# Solid intermedio (da 9.63 a 11.83, 220 cm)
make_box("Wall_Garage_North_03", 9.63, 11.83, y_gar_north_wall_in, y_gar_north_wall_out, 0.0, H_GAR, mat_wall_ext, col_walls)
# Finestra N2 (da 11.83 a 12.44, 61 cm)
make_box("Wall_Garage_North_Sill_2", 11.83, 12.44, y_gar_north_wall_in, y_gar_north_wall_out, 0.0, 1.00, mat_wall_ext, col_walls)
make_box("Wall_Garage_North_Lintel_2", 11.83, 12.44, y_gar_north_wall_in, y_gar_north_wall_out, 1.61, H_GAR, mat_wall_ext, col_walls)
add_window("Win_Garage_N2", 11.83, 12.44, y_gar_north_wall_in, y_gar_north_wall_out, 1.00, 1.61)

# Solid finale fino al muro Est (da 12.44 a 13.90)
make_box("Wall_Garage_North_04", 12.44, 13.90, y_gar_north_wall_in, y_gar_north_wall_out, 0.0, H_GAR, mat_wall_ext, col_walls)

# Porticato a Nord del Garage con 3 pilastri da 50x30 cm a y=-17.43..-17.13
make_box("Pillar_Garage_1", 8.41, 8.91, -17.43, -17.13, 0.0, H_GAR, mat_wall_ext, col_walls)
make_box("Pillar_Garage_2", 10.60, 11.10, -17.43, -17.13, 0.0, H_GAR, mat_wall_ext, col_walls)
make_box("Pillar_Garage_3", 13.40, 13.90, -17.43, -17.13, 0.0, H_GAR, mat_wall_ext, col_walls)
# Trave superiore portico garage
make_box("Beam_Portico_Garage", 6.39, 13.90, -17.43, -17.13, 2.50, H_GAR, mat_wall_ext, col_walls)

# Parete Sud Garage con due finestre (61 cm, 100|161)
# y: -23.73 a -23.43
make_box("Wall_Garage_South_01", 6.69, 9.41, y_gar_south_wall_out, y_gar_south_wall_in, 0.0, H_GAR, mat_wall_ext, col_walls)
make_box("Wall_Garage_South_Sill_1", 9.41, 10.02, y_gar_south_wall_out, y_gar_south_wall_in, 0.0, 1.00, mat_wall_ext, col_walls)
make_box("Wall_Garage_South_Lintel_1", 9.41, 10.02, y_gar_south_wall_out, y_gar_south_wall_in, 1.61, H_GAR, mat_wall_ext, col_walls)
add_window("Win_Garage_S1", 9.41, 10.02, y_gar_south_wall_out, y_gar_south_wall_in, 1.00, 1.61)

make_box("Wall_Garage_South_02", 10.02, 12.49, y_gar_south_wall_out, y_gar_south_wall_in, 0.0, H_GAR, mat_wall_ext, col_walls)
make_box("Wall_Garage_South_Sill_2", 12.49, 13.10, y_gar_south_wall_out, y_gar_south_wall_in, 0.0, 1.00, mat_wall_ext, col_walls)
make_box("Wall_Garage_South_Lintel_2", 12.49, 13.10, y_gar_south_wall_out, y_gar_south_wall_in, 1.61, H_GAR, mat_wall_ext, col_walls)
add_window("Win_Garage_S2", 12.49, 13.10, y_gar_south_wall_out, y_gar_south_wall_in, 1.00, 1.61)

make_box("Wall_Garage_South_03", 13.10, 13.90, y_gar_south_wall_out, y_gar_south_wall_in, 0.0, H_GAR, mat_wall_ext, col_walls)

# Scala interna Garage verso interrato (lunghezza 3.41 m, larghezza 0.90 m lungo parete Sud)
x_st_gar_0 = 9.40
for st in range(12):
    x_s_0 = x_st_gar_0 + st * (3.41 / 12.0)
    x_s_1 = x_s_0 + (3.41 / 12.0)
    z_s_top = 0.0 - st * 0.16
    make_box(f"Stair_Garage_Step_{st+1}", x_s_0, x_s_1, -23.40, -22.50, z_s_top - 0.16, z_s_top, mat_stairs, col_stairs)

# -------------------------------------------------------------
# 7. PAVIMENTI INTERNI
# -------------------------------------------------------------
# Salotto (Parquet)
make_box("Floor_Salotto", 0.30, 6.07, -6.81, -0.30, -0.06, 0.00, mat_parquet, col_floors)
# Bagno (Piastrelle azzurro/grigio)
make_box("Floor_Bagno", 6.37, 8.46, -3.56, -0.30, -0.06, 0.00, mat_tile, col_floors)
# Scala
make_box("Floor_Scala", 8.69, 9.70, -3.56, -0.30, -0.06, 0.00, mat_stairs, col_floors)
# Sala da pranzo (Parquet)
make_box("Floor_Dining_Main", 6.37, 13.90, -7.75, -3.85, -0.06, 0.00, mat_parquet, col_floors)
make_box("Floor_Dining_NorthWing", 10.05, 13.90, -3.85, -0.30, -0.06, 0.00, mat_parquet, col_floors)
make_box("Floor_Dining_Passage", 6.37, 10.05, -3.85, -3.56, -0.06, 0.00, mat_parquet, col_floors)
# Lavanderia (Piastrelle)
make_box("Floor_Lavanderia", 0.30, 4.45, -15.23, -12.63, -0.06, 0.00, mat_laundry_floor, col_floors)
# Garage (Cemento industriale)
make_box("Floor_Garage", 6.69, 13.90, -23.43, -18.43, -0.06, 0.00, mat_garage_floor, col_floors)

# Scala casa principale
for i in range(9):
    z_top = (i + 1) * (3.00 / 17.0)
    y0 = -3.56 + i * 0.25
    y1 = y0 + 0.25
    make_box(f"Stair_Tread_{i+1}", 8.69, 9.70, y0, y1, 0.0, z_top, mat_stairs, col_stairs)
make_box("Stair_Landing", 8.69, 9.70, -3.56 + 9 * 0.25, -0.30, 0.0, 9 * (3.00 / 17.0), mat_stairs, col_stairs)

# Sanitari bagno
wc_x = 8.10
wc_y = -2.00
make_box("WC_Flush_Plate", 8.44, 8.46, wc_y - 0.12, wc_y + 0.12, 1.05, 1.25, mat_chrome, col_furniture)
make_box("WC_Bowl", wc_x, wc_x + 0.35, wc_y - 0.18, wc_y + 0.18, 0.15, 0.42, mat_ceramic, col_furniture)
make_box("WC_Seat", wc_x - 0.02, wc_x + 0.36, wc_y - 0.19, wc_y + 0.19, 0.42, 0.45, mat_ceramic, col_furniture)

make_box("Vanity_Cabinet", 6.40, 7.15, -1.10, -0.32, 0.0, 0.82, mat_door_wood, col_furniture)
make_box("Vanity_Basin", 6.45, 7.10, -1.05, -0.35, 0.82, 0.86, mat_ceramic, col_furniture)
make_box("Vanity_Tap", 6.75, 6.80, -0.42, -0.37, 0.86, 1.02, mat_chrome, col_furniture)
make_box("Vanity_Mirror", 6.45, 7.10, -0.32, -0.30, 1.15, 1.95, mat_glass, col_furniture)

# -------------------------------------------------------------
# 8. SISTEMAZIONE ESTERNA: PORTICO, GIARDINI, VIALI
# -------------------------------------------------------------
# A. PORTICO E CORTE PAVIMENTATA (Lastricato Grigio)
# 1. Spazio patio tra Salotto, Sala da pranzo e Lavanderia
make_box("Portico_Patio_Main", 0.30, 6.39, -12.43, -7.11, -0.06, 0.00, mat_portico, col_floors)
# 2. Viale di collegamento pedonale verso il Garage
make_box("Portico_Walkway_Garage", 4.65, 6.39, -18.13, -12.43, -0.06, 0.00, mat_portico, col_floors)
# 3. Portico coperto fronte Garage
make_box("Portico_Garage_Floor", 6.39, 14.20, -18.13, -17.13, -0.06, 0.00, mat_portico, col_floors)
# 4. Spiazzo manovra fronte portone Garage
make_box("Piazzale_Garage_Fronte", 4.00, 6.39, -22.50, -18.13, -0.06, 0.00, mat_portico, col_floors)
# 5. Marciapiede perimetrale Ovest ed Est lavanderia
make_box("Marciapiede_Lav_West", -0.40, 0.00, -15.80, -11.00, -0.06, 0.00, mat_portico, col_floors)

# B. GIARDINO AREA 2 (Corte interna / Giardino privato ad Est)
# Tra Sala da pranzo (Nord), Garage (Sud), Muro di cinta (Est), e Viale portico (Ovest)
make_box("Giardino_Area_2_Prato", 6.39, 13.90, -17.13, -8.05, -0.06, 0.00, mat_grass, col_floors)

# C. VIALE CARRABILE IN GHIAIA (Accesso da "All'aperto" verso il Garage)
# Tratto 1: Ingresso Nord-Ovest ("All'aperto")
make_box("Viale_AllAperto_Ghiaia", -8.00, -5.00, -5.00, 0.00, -0.06, 0.00, mat_gravel, col_floors)
# Tratto 2: Curva e discesa verso Sud lungo il lato Ovest
make_box("Viale_Ovest_Tratto_1", -8.00, -5.50, -15.00, -5.00, -0.06, 0.00, mat_gravel, col_floors)
# Tratto 3: Curva e traversa verso Est verso il Garage
make_box("Viale_Curva_SudOvest", -8.00, -3.00, -19.50, -15.00, -0.06, 0.00, mat_gravel, col_floors)
make_box("Viale_Traversa_Est", -3.00, 4.00, -21.00, -18.00, -0.06, 0.00, mat_gravel, col_floors)

# D. GIARDINO AREA 3 (Grande prato a Ovest/Centro)
# Suddiviso in settori per coprire l'intera L verde
make_box("Giardino_Area_3_Nord", -5.00, 0.00, -7.11, 0.00, -0.06, 0.00, mat_grass, col_floors)
make_box("Giardino_Area_3_Centro", -5.50, 0.00, -15.00, -7.11, -0.06, 0.00, mat_grass, col_floors)
make_box("Giardino_Area_3_Sud", -3.00, 4.00, -18.00, -15.43, -0.06, 0.00, mat_grass, col_floors)

# E. GIARDINO AREA 1 (Grande prato a Sud della proprietà)
make_box("Giardino_Area_1_Prato", -8.00, 14.20, -27.50, -21.00, -0.06, 0.00, mat_grass, col_floors)

# F. MURO DI CINTA EST E RECINZIONE PERIMETRALE
# Muro di cinta Est (completo da Salone al confine Sud)
make_box("Muro_Cinta_Est", 13.90, 14.20, -27.50, -8.05, 0.0, 2.20, mat_wall_ext, col_walls)

# Muretto basso perimetrale con ringhiera metallica
def add_fence_wall(name, x0, x1, y0, y1):
    make_box(f"{name}_Base", x0, x1, y0, y1, 0.0, 0.35, mat_curb, col_walls)
    # Ringhiera
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    if dx > dy:
        make_box(f"{name}_Rail", x0, x1, (y0+y1)/2 - 0.02, (y0+y1)/2 + 0.02, 0.35, 1.10, mat_railing, col_walls)
    else:
        make_box(f"{name}_Rail", (x0+x1)/2 - 0.02, (x0+x1)/2 + 0.02, y0, y1, 0.35, 1.10, mat_railing, col_walls)

add_fence_wall("Fence_South", -8.00, 13.90, -27.50, -27.30)
add_fence_wall("Fence_West", -8.20, -8.00, -27.50, 0.00)
add_fence_wall("Fence_North_West", -8.00, 0.00, 0.00, 0.20)

# Piattaforma basamento globale
make_box("Site_Platform_Ground", -9.00, 15.00, -28.50, 1.50, -0.30, -0.06, mat_portico, col_floors)

# -------------------------------------------------------------
# 9. ETICHETTE TESTUALI 3D SUL PAVIMENTO
# -------------------------------------------------------------
def add_label(text, x, y, size=0.45):
    font_curve = bpy.data.curves.new(type="FONT", name=f"Label_{text}")
    font_curve.body = text
    font_curve.size = size
    font_curve.extrude = 0.02
    obj = bpy.data.objects.new(name=f"Label_{text}", object_data=font_curve)
    obj.location = (x, y, 0.01)
    obj.data.materials.append(mat_label)
    col_labels.objects.link(obj)

add_label("SALOTTO (5.76 x 6.51 m)", 1.20, -3.80, size=0.38)
add_label("BAGNO", 6.80, -2.20, size=0.30)
add_label("SCALA", 8.85, -2.20, size=0.25)
add_label("SALA DA PRANZO (7.56 x 7.45 m)", 7.80, -5.80, size=0.40)
add_label("PORTICO", 2.20, -9.50, size=0.45)
add_label("LAVANDERIA", 1.20, -13.80, size=0.32)
add_label("GARAGE", 9.50, -21.00, size=0.48)
add_label("GIARDINO AREA 2", 8.50, -13.00, size=0.42)
add_label("GIARDINO AREA 3", -4.50, -11.00, size=0.45)
add_label("GIARDINO AREA 1", 1.00, -24.50, size=0.50)
add_label("ALL'APERTO", -7.50, -2.50, size=0.40)

# -------------------------------------------------------------
# 10. ILLUMINAZIONE E TELECAMERA PANORAMICA
# -------------------------------------------------------------
# Sole
sun_data = bpy.data.lights.new(name="Sun_Key", type='SUN')
sun_data.energy = 4.2
sun_data.color = (1.0, 0.98, 0.94)
sun_data.angle = math.radians(12.0)
sun_obj = bpy.data.objects.new(name="Sun_Key", object_data=sun_data)
sun_obj.location = (20.0, -15.0, 25.0)
sun_obj.rotation_euler = (math.radians(52.0), math.radians(15.0), math.radians(-38.0))
col_lighting.objects.link(sun_obj)

# Schiarita
fill_data = bpy.data.lights.new(name="Sun_Fill", type='SUN')
fill_data.energy = 1.4
fill_data.color = (0.85, 0.92, 1.0)
fill_obj = bpy.data.objects.new(name="Sun_Fill", object_data=fill_data)
fill_obj.location = (-15.0, 15.0, 18.0)
fill_obj.rotation_euler = (math.radians(45.0), math.radians(-20.0), math.radians(140.0))
col_lighting.objects.link(fill_obj)

# World background
world = bpy.context.scene.world
if not world:
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
world.use_nodes = True
bg_node = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
bg_node.inputs["Color"].default_value = (0.94, 0.96, 0.98, 1.0)
bg_node.inputs["Strength"].default_value = 1.0

# Telecamera Assonometrica 3D
cam_data = bpy.data.cameras.new(name="Camera_Revit_Overview")
cam_data.lens = 38
cam_obj = bpy.data.objects.new(name="Camera_Revit_Overview", object_data=cam_data)
# Inquadra l'intero lotto da Sud-Ovest / Sud-Est
cam_obj.location = (25.0, -32.0, 26.0)
cam_obj.rotation_euler = (math.radians(54.0), 0.0, math.radians(45.0))
col_lighting.objects.link(cam_obj)
bpy.context.scene.camera = cam_obj

print("=== Full Architectural Scene Generation Completed ===")

