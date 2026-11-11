"""
Complete 3D Architectural Generation Script for Blender.
Strictly follows all dimensions from the uploaded architectural floor plan:
- Main House: 14.20m x 8.05m
- Bedroom/Office: 5.76m x 6.51m
- Bathroom: 2.09m x 3.26m
- Staircase: 0.76m/1.00m x 3.26m
- Living Room / Salon: 7.56m x 7.45m
- Large internal pocket door / opening: 2.00m
- Entrance partition: 0.22m x 1.10m
- Lower Dependance: 4.65m x 3.00m (inner 4.15m x 2.60m)
- Boundary Wall: 9.05m length
- Two columns: 0.30m x 0.30m
- All window sills and lintels matching plan callouts (100|283, 100|161, 0|213)
"""

import bpy
import bmesh
from mathutils import Vector, Matrix, Euler
import math

print("=== Starting 3D Architectural Model Generation ===")

# -------------------------------------------------------------
# 1. CLEAN CURRENT SCENE
# -------------------------------------------------------------
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

for col in [bpy.data.meshes, bpy.data.materials, bpy.data.curves, bpy.data.lights, bpy.data.cameras]:
    for item in list(col):
        col.remove(item)

for col in list(bpy.data.collections):
    bpy.data.collections.remove(col)

# Configure scene units (Meters)
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1.0
scene.unit_settings.length_unit = 'METERS'

# Collections
col_walls = bpy.data.collections.new("01_Pareti")
col_floors = bpy.data.collections.new("02_Pavimenti")
col_fixtures = bpy.data.collections.new("03_Infissi_e_Porte")
col_stairs = bpy.data.collections.new("04_Scale")
col_furniture = bpy.data.collections.new("05_Arredi_Sanitari")
col_labels = bpy.data.collections.new("06_Etichette_Stanze")
col_lighting = bpy.data.collections.new("07_Luci_e_Camera")

for c in [col_walls, col_floors, col_fixtures, col_stairs, col_furniture, col_labels, col_lighting]:
    bpy.context.scene.collection.children.link(c)

# -------------------------------------------------------------
# 2. SHADER MATERIALS
# -------------------------------------------------------------
def create_material(name, base_color, roughness=0.5, metallic=0.0, transmission=0.0, ior=1.45, alpha=1.0):
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

mat_wall_ext = create_material("Mat_Muro_Esterno", (0.92, 0.91, 0.88, 1.0), roughness=0.85)
mat_wall_int = create_material("Mat_Muro_Interno", (0.96, 0.95, 0.93, 1.0), roughness=0.90)
mat_parquet = create_material("Mat_Parquet_Rovere", (0.52, 0.35, 0.20, 1.0), roughness=0.32)
mat_tile = create_material("Mat_Gres_Bagno", (0.76, 0.78, 0.80, 1.0), roughness=0.20)
mat_dep_floor = create_material("Mat_Pavimento_Dependance", (0.62, 0.59, 0.55, 1.0), roughness=0.50)
mat_courtyard = create_material("Mat_Pietra_Cortile", (0.70, 0.68, 0.64, 1.0), roughness=0.80)
mat_frame = create_material("Mat_Alluminio_Antracite", (0.12, 0.12, 0.13, 1.0), roughness=0.25, metallic=0.5)
mat_glass = create_material("Mat_Vetro", (0.95, 0.98, 1.0, 1.0), roughness=0.03, transmission=0.98, ior=1.52, alpha=0.35)
mat_door_wood = create_material("Mat_Legno_Porta", (0.42, 0.28, 0.16, 1.0), roughness=0.38)
mat_chrome = create_material("Mat_Cromo", (0.95, 0.95, 0.95, 1.0), roughness=0.10, metallic=1.0)
mat_ceramic = create_material("Mat_Ceramica_Sanitari", (0.97, 0.97, 0.97, 1.0), roughness=0.12)
mat_stairs = create_material("Mat_Scale_Legno", (0.46, 0.31, 0.17, 1.0), roughness=0.38)
mat_label = create_material("Mat_Etichette", (0.20, 0.20, 0.22, 1.0), roughness=0.50)

# -------------------------------------------------------------
# 3. DIRECT MESH BUILDERS
# -------------------------------------------------------------
def make_box_obj(name, x_min, x_max, y_min, y_max, z_min, z_max, mat=None, collection=None):
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
        (0, 3, 2, 1), # bottom (-z)
        (4, 5, 6, 7), # top (+z)
        (0, 1, 5, 4), # front (-y)
        (1, 2, 6, 5), # right (+x)
        (2, 3, 7, 6), # back (+y)
        (3, 0, 4, 7)  # left (-x)
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
        # Frame
        make_box_obj(f"{name}_Frame_Bottom", x_min, x_max, y_c - d_frame/2, y_c + d_frame/2, sill_h, sill_h + t_frame, mat_frame, col_fixtures)
        make_box_obj(f"{name}_Frame_Top", x_min, x_max, y_c - d_frame/2, y_c + d_frame/2, lintel_h - t_frame, lintel_h, mat_frame, col_fixtures)
        make_box_obj(f"{name}_Frame_Left", x_min, x_min + t_frame, y_c - d_frame/2, y_c + d_frame/2, sill_h + t_frame, lintel_h - t_frame, mat_frame, col_fixtures)
        make_box_obj(f"{name}_Frame_Right", x_max - t_frame, x_max, y_c - d_frame/2, y_c + d_frame/2, sill_h + t_frame, lintel_h - t_frame, mat_frame, col_fixtures)
        if w > 0.70:
            x_m = (x_min + x_max) / 2.0
            make_box_obj(f"{name}_Mullion", x_m - t_frame/2, x_m + t_frame/2, y_c - d_frame/2, y_c + d_frame/2, sill_h + t_frame, lintel_h - t_frame, mat_frame, col_fixtures)
        # Glass
        make_box_obj(f"{name}_Glass", x_min + t_frame, x_max - t_frame, y_c - 0.01, y_c + 0.01, sill_h + t_frame, lintel_h - t_frame, mat_glass, col_fixtures)
    else:
        x_c = (x_min + x_max) / 2.0
        make_box_obj(f"{name}_Frame_Bottom", x_c - d_frame/2, x_c + d_frame/2, y_min, y_max, sill_h, sill_h + t_frame, mat_frame, col_fixtures)
        make_box_obj(f"{name}_Frame_Top", x_c - d_frame/2, x_c + d_frame/2, y_min, y_max, lintel_h - t_frame, lintel_h, mat_frame, col_fixtures)
        make_box_obj(f"{name}_Frame_Front", x_c - d_frame/2, x_c + d_frame/2, y_min, y_min + t_frame, sill_h + t_frame, lintel_h - t_frame, mat_frame, col_fixtures)
        make_box_obj(f"{name}_Frame_Back", x_c - d_frame/2, x_c + d_frame/2, y_max - t_frame, y_max, sill_h + t_frame, lintel_h - t_frame, mat_frame, col_fixtures)
        make_box_obj(f"{name}_Glass", x_c - 0.01, x_c + 0.01, y_min + t_frame, y_max - t_frame, sill_h + t_frame, lintel_h - t_frame, mat_glass, col_fixtures)

def add_door(name, x_min, x_max, y_min, y_max, lintel_h=2.13, is_y_axis=False, open_deg=35.0):
    t_frame = 0.05
    d_frame = 0.10
    rad = math.radians(open_deg)
    
    if not is_y_axis:
        w = abs(x_max - x_min)
        y_c = (y_min + y_max) / 2.0
        # Frame
        make_box_obj(f"{name}_Frame_Top", x_min, x_max, y_c - d_frame/2, y_c + d_frame/2, lintel_h - t_frame, lintel_h, mat_door_wood, col_fixtures)
        make_box_obj(f"{name}_Frame_Left", x_min, x_min + t_frame, y_c - d_frame/2, y_c + d_frame/2, 0.0, lintel_h - t_frame, mat_door_wood, col_fixtures)
        make_box_obj(f"{name}_Frame_Right", x_max - t_frame, x_max, y_c - d_frame/2, y_c + d_frame/2, 0.0, lintel_h - t_frame, mat_door_wood, col_fixtures)
        
        # Door leaf rotated around hinge
        p_w = w - 2*t_frame
        p_t = 0.04
        p_h = lintel_h - t_frame
        hx = x_min + t_frame
        hy = y_c
        
        # 4 local corners
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
        
        # Handle
        hand_dist = p_w - 0.08
        han_x = hx + hand_dist * math.cos(rad)
        han_y = hy + hand_dist * math.sin(rad)
        make_box_obj(f"{name}_Handle", han_x - 0.06, han_x + 0.06, han_y - 0.02, han_y + 0.02, 0.98, 1.02, mat_chrome, col_fixtures)
    else:
        d = abs(y_max - y_min)
        x_c = (x_min + x_max) / 2.0
        make_box_obj(f"{name}_Frame_Top", x_c - d_frame/2, x_c + d_frame/2, y_min, y_max, lintel_h - t_frame, lintel_h, mat_door_wood, col_fixtures)
        make_box_obj(f"{name}_Frame_Front", x_c - d_frame/2, x_c + d_frame/2, y_min, y_min + t_frame, 0.0, lintel_h - t_frame, mat_door_wood, col_fixtures)
        make_box_obj(f"{name}_Frame_Back", x_c - d_frame/2, x_c + d_frame/2, y_max - t_frame, y_max, 0.0, lintel_h - t_frame, mat_door_wood, col_fixtures)
        
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
# 4. MAIN HOUSE WALLS (Altezza = 3.00 m)
# -------------------------------------------------------------
H_MAIN = 3.00

# PARETE NORD (y: -0.30 a 0.00, x: 0.00 a 14.20)
# Pilastro 1
make_box_obj("Wall_North_01", 0.00, 1.35, -0.30, 0.00, 0.0, H_MAIN, mat_wall_ext, col_walls)
# Finestra N1 (92 cm, 100|283)
make_box_obj("Wall_North_Sill_1", 1.35, 2.27, -0.30, 0.00, 0.0, 1.00, mat_wall_ext, col_walls)
make_box_obj("Wall_North_Lintel_1", 1.35, 2.27, -0.30, 0.00, 2.83, H_MAIN, mat_wall_ext, col_walls)
add_window("Win_N1", 1.35, 2.27, -0.30, 0.00, 1.00, 2.83)
# Pilastro 2 (173 cm)
make_box_obj("Wall_North_02", 2.27, 4.00, -0.30, 0.00, 0.0, H_MAIN, mat_wall_ext, col_walls)
# Finestra N2 (92 cm, 100|283)
make_box_obj("Wall_North_Sill_2", 4.00, 4.92, -0.30, 0.00, 0.0, 1.00, mat_wall_ext, col_walls)
make_box_obj("Wall_North_Lintel_2", 4.00, 4.92, -0.30, 0.00, 2.83, H_MAIN, mat_wall_ext, col_walls)
add_window("Win_N2", 4.00, 4.92, -0.30, 0.00, 1.00, 2.83)
# Pilastro 3 (115 cm + muro 30 + 59 cm bagno = 204 cm)
make_box_obj("Wall_North_03", 4.92, 6.96, -0.30, 0.00, 0.0, H_MAIN, mat_wall_ext, col_walls)
# Finestra N3 Bagno (92 cm, 100|283)
make_box_obj("Wall_North_Sill_3", 6.96, 7.88, -0.30, 0.00, 0.0, 1.00, mat_wall_ext, col_walls)
make_box_obj("Wall_North_Lintel_3", 6.96, 7.88, -0.30, 0.00, 2.83, H_MAIN, mat_wall_ext, col_walls)
add_window("Win_N3", 6.96, 7.88, -0.30, 0.00, 1.00, 2.83)
# Pilastro 4 (59 cm + scala 100 + spalla 35 = 217 cm)
make_box_obj("Wall_North_04", 7.88, 10.05, -0.30, 0.00, 0.0, H_MAIN, mat_wall_ext, col_walls)
# Finestra N4 Salone (92 cm, 100|283)
make_box_obj("Wall_North_Sill_4", 10.05, 10.97, -0.30, 0.00, 0.0, 1.00, mat_wall_ext, col_walls)
make_box_obj("Wall_North_Lintel_4", 10.05, 10.97, -0.30, 0.00, 2.83, H_MAIN, mat_wall_ext, col_walls)
add_window("Win_N4", 10.05, 10.97, -0.30, 0.00, 1.00, 2.83)
# Pilastro 5 (293 cm + angolo 30 = 323 cm)
make_box_obj("Wall_North_05", 10.97, 14.20, -0.30, 0.00, 0.0, H_MAIN, mat_wall_ext, col_walls)

# PARETE OVEST (x: 0.00 a 0.30, y: 0.00 a -8.21)
make_box_obj("Wall_West_01", 0.00, 0.30, -3.50, 0.00, 0.0, H_MAIN, mat_wall_ext, col_walls)
# Finestrella ovest (41 cm, 100|161)
make_box_obj("Wall_West_Sill_1", 0.00, 0.30, -3.91, -3.50, 0.0, 1.00, mat_wall_ext, col_walls)
make_box_obj("Wall_West_Lintel_1", 0.00, 0.30, -3.91, -3.50, 1.61, H_MAIN, mat_wall_ext, col_walls)
add_window("Win_W1", 0.00, 0.30, -3.91, -3.50, 1.00, 1.61, is_y_axis=True)
# Parete continua e prolungamento di 110 cm verso il basso
make_box_obj("Wall_West_02", 0.00, 0.30, -8.21, -3.91, 0.0, H_MAIN, mat_wall_ext, col_walls)

# PARETE SUD CAMERA OVEST (y: -7.11 a -6.81, x: 0.30 a 6.07)
make_box_obj("Wall_South_West_01", 0.30, 1.44, -7.11, -6.81, 0.0, H_MAIN, mat_wall_ext, col_walls)
# Finestra SW (92 cm, 100|283)
make_box_obj("Wall_South_West_Sill_1", 1.44, 2.36, -7.11, -6.81, 0.0, 1.00, mat_wall_ext, col_walls)
make_box_obj("Wall_South_West_Lintel_1", 1.44, 2.36, -7.11, -6.81, 2.83, H_MAIN, mat_wall_ext, col_walls)
add_window("Win_SW1", 1.44, 2.36, -7.11, -6.81, 1.00, 2.83)
# Spalla tra finestra e porta
make_box_obj("Wall_South_West_02", 2.36, 3.50, -7.11, -6.81, 0.0, H_MAIN, mat_wall_ext, col_walls)
# Porta SW (92 cm, 0|213)
make_box_obj("Wall_South_West_Door_Lintel", 3.50, 4.42, -7.11, -6.81, 2.13, H_MAIN, mat_wall_ext, col_walls)
add_door("Door_SW1", 3.50, 4.42, -7.11, -6.81, lintel_h=2.13, open_deg=45.0)
make_box_obj("Wall_South_West_03", 4.42, 6.07, -7.11, -6.81, 0.0, H_MAIN, mat_wall_ext, col_walls)

# MURO DIVISORIO OVEST/EST (x: 6.07 a 6.37)
make_box_obj("Wall_Div_01", 6.07, 6.37, -3.85, -0.30, 0.0, H_MAIN, mat_wall_int, col_walls)
# Grande apertura passaggio (2.00 m)
make_box_obj("Wall_Div_Lintel", 6.07, 6.37, -5.85, -3.85, 2.83, H_MAIN, mat_wall_int, col_walls)
# Muro sotto apertura fino al raccordo parete sud salone (-8.05)
make_box_obj("Wall_Div_02", 6.07, 6.37, -8.05, -5.85, 0.0, H_MAIN, mat_wall_int, col_walls)

# PARETE SUD BAGNO E PORTA (y: -3.85 a -3.56, x: 6.37 a 8.46)
make_box_obj("Wall_Bath_South_Solid", 6.37, 7.66, -3.85, -3.56, 0.0, H_MAIN, mat_wall_int, col_walls)
make_box_obj("Wall_Bath_South_Lintel", 7.66, 8.46, -3.85, -3.56, 2.13, H_MAIN, mat_wall_int, col_walls)
add_door("Door_Bathroom", 7.66, 8.46, -3.85, -3.56, lintel_h=2.13, open_deg=-60.0)

# VANO SCALA: PARETE OVEST (x: 8.46 a 8.69, y: -3.56 a -0.30)
make_box_obj("Wall_Stair_West", 8.46, 8.69, -3.56, -0.30, 0.0, H_MAIN, mat_wall_int, col_walls)

# VANO SCALA: PARETE EST (x: 9.70 a 10.05, y: -3.85 a -0.30)
make_box_obj("Wall_Stair_East", 9.70, 10.05, -3.85, -0.30, 0.0, H_MAIN, mat_wall_int, col_walls)

# VANO SCALA: PORTA DI ACCESSO (y: -3.85 a -3.56, x: 8.69 a 9.70)
make_box_obj("Wall_Stair_Door_Lintel", 8.69, 9.45, -3.85, -3.56, 2.13, H_MAIN, mat_wall_int, col_walls)
make_box_obj("Wall_Stair_Door_Post", 9.45, 9.70, -3.85, -3.56, 0.0, H_MAIN, mat_wall_int, col_walls)
add_door("Door_Stair", 8.69, 9.45, -3.85, -3.56, lintel_h=2.13, open_deg=-45.0)

# PARETE EST ESTERNA (x: 13.90 a 14.20, y: -8.05 a 0.00)
make_box_obj("Wall_East_Ext", 13.90, 14.20, -8.05, 0.00, 0.0, H_MAIN, mat_wall_ext, col_walls)

# PARETE SUD SALONE (y: -8.05 a -7.75, x: 6.37 a 13.90)
make_box_obj("Wall_Living_South_01", 6.37, 7.57, -8.05, -7.75, 0.0, H_MAIN, mat_wall_ext, col_walls)
# Finestra S2 (92 cm, 100|283)
make_box_obj("Wall_Living_South_Sill_1", 7.57, 8.49, -8.05, -7.75, 0.0, 1.00, mat_wall_ext, col_walls)
make_box_obj("Wall_Living_South_Lintel_1", 7.57, 8.49, -8.05, -7.75, 2.83, H_MAIN, mat_wall_ext, col_walls)
add_window("Win_Living_S1", 7.57, 8.49, -8.05, -7.75, 1.00, 2.83)

make_box_obj("Wall_Living_South_02", 8.49, 11.15, -8.05, -7.75, 0.0, H_MAIN, mat_wall_ext, col_walls)
# Porta Ingresso Salone (92 cm, 0|213)
make_box_obj("Wall_Living_South_Door_Lintel", 11.15, 12.07, -8.05, -7.75, 2.13, H_MAIN, mat_wall_ext, col_walls)
add_door("Door_Living_Main", 11.15, 12.07, -8.05, -7.75, lintel_h=2.13, open_deg=50.0)

make_box_obj("Wall_Living_South_03", 12.07, 12.82, -8.05, -7.75, 0.0, H_MAIN, mat_wall_ext, col_walls)
# Finestra S3 (92 cm, 100|283)
make_box_obj("Wall_Living_South_Sill_2", 12.82, 13.74, -8.05, -7.75, 0.0, 1.00, mat_wall_ext, col_walls)
make_box_obj("Wall_Living_South_Lintel_2", 12.82, 13.74, -8.05, -7.75, 2.83, H_MAIN, mat_wall_ext, col_walls)
add_window("Win_Living_S2", 12.82, 13.74, -8.05, -7.75, 1.00, 2.83)
make_box_obj("Wall_Living_South_04", 13.74, 13.90, -8.05, -7.75, 0.0, H_MAIN, mat_wall_ext, col_walls)

# Muretto divisorio interno ingresso salone (spessore 22 cm, lunghezza 1.10 m)
make_box_obj("Wall_Living_Partition", 9.71, 9.93, -7.75, -6.65, 0.0, H_MAIN, mat_wall_int, col_walls)

# -------------------------------------------------------------
# 5. DEPENDANCE / ANNESSO INFERIORE (Altezza = 2.70 m)
# -------------------------------------------------------------
H_DEP = 2.70

# Parete Ovest e prolungamento verso l'alto (110 cm)
make_box_obj("Wall_Dep_West", 0.00, 0.30, -15.43, -11.33, 0.0, H_DEP, mat_wall_ext, col_walls)

# Parete Nord Dependance con porta ingresso (92 cm, 0|213)
make_box_obj("Wall_Dep_North_01", 0.30, 2.70, -12.63, -12.43, 0.0, H_DEP, mat_wall_ext, col_walls)
make_box_obj("Wall_Dep_North_Door_Lintel", 2.70, 3.62, -12.63, -12.43, 2.13, H_DEP, mat_wall_ext, col_walls)
add_door("Door_Dep_North", 2.70, 3.62, -12.63, -12.43, lintel_h=2.13, open_deg=40.0)
make_box_obj("Wall_Dep_North_02", 3.62, 4.65, -12.63, -12.43, 0.0, H_DEP, mat_wall_ext, col_walls)

# Parete Est Dependance
make_box_obj("Wall_Dep_East", 4.45, 4.65, -15.43, -12.63, 0.0, H_DEP, mat_wall_ext, col_walls)

# Parete Sud Dependance con due finestrelle (61 cm, 100|161)
make_box_obj("Wall_Dep_South_01", 0.30, 0.82, -15.43, -15.23, 0.0, H_DEP, mat_wall_ext, col_walls)
make_box_obj("Wall_Dep_South_Sill_1", 0.82, 1.43, -15.43, -15.23, 0.0, 1.00, mat_wall_ext, col_walls)
make_box_obj("Wall_Dep_South_Lintel_1", 0.82, 1.43, -15.43, -15.23, 1.61, H_DEP, mat_wall_ext, col_walls)
add_window("Win_Dep_1", 0.82, 1.43, -15.43, -15.23, 1.00, 1.61)

make_box_obj("Wall_Dep_South_02", 1.43, 3.08, -15.43, -15.23, 0.0, H_DEP, mat_wall_ext, col_walls)
make_box_obj("Wall_Dep_South_Sill_2", 3.08, 3.69, -15.43, -15.23, 0.0, 1.00, mat_wall_ext, col_walls)
make_box_obj("Wall_Dep_South_Lintel_2", 3.08, 3.69, -15.43, -15.23, 1.61, H_DEP, mat_wall_ext, col_walls)
add_window("Win_Dep_2", 3.08, 3.69, -15.43, -15.23, 1.00, 1.61)

make_box_obj("Wall_Dep_South_03", 3.69, 4.45, -15.43, -15.23, 0.0, H_DEP, mat_wall_ext, col_walls)

# Tramezze interne Dependance (spessore 22 cm)
make_box_obj("Wall_Dep_Part_V1", 1.43, 1.65, -15.23, -14.46, 0.0, H_DEP, mat_wall_int, col_walls)
make_box_obj("Wall_Dep_Part_H1", 1.43, 2.50, -14.46, -14.24, 0.0, H_DEP, mat_wall_int, col_walls)
make_box_obj("Wall_Dep_Part_V2", 3.08, 3.30, -15.23, -14.46, 0.0, H_DEP, mat_wall_int, col_walls)

# Pilastri quadrati cortile (30x30 cm)
make_box_obj("Pillar_Court_1", 5.25, 5.55, -12.73, -12.43, 0.0, H_DEP, mat_wall_ext, col_walls)
make_box_obj("Pillar_Court_2", 5.25, 5.55, -15.23, -14.93, 0.0, H_DEP, mat_wall_ext, col_walls)

# Muro perimetrale est (lunghezza 9.05 m, spessore 30 cm, altezza 2.20 m)
make_box_obj("Wall_Boundary_East", 14.70, 15.00, -17.90, -8.85, 0.0, 2.20, mat_wall_ext, col_walls)

# -------------------------------------------------------------
# 6. PAVIMENTI DETTAGLIATI
# -------------------------------------------------------------
# Pavimento Camera Ovest (Parquet Rovere)
make_box_obj("Floor_Camera_Ovest", 0.30, 6.07, -6.81, -0.30, -0.06, 0.00, mat_parquet, col_floors)

# Pavimento Bagno (Gres Porcellanato)
make_box_obj("Floor_Bagno", 6.37, 8.46, -3.56, -0.30, -0.06, 0.00, mat_tile, col_floors)

# Pavimento Vano Scala
make_box_obj("Floor_Stair", 8.69, 9.70, -3.56, -0.30, -0.06, 0.00, mat_stairs, col_floors)

# Pavimento Salone / Living (Parquet Rovere)
make_box_obj("Floor_Living_Main", 6.37, 13.90, -7.75, -3.85, -0.06, 0.00, mat_parquet, col_floors)
make_box_obj("Floor_Living_NorthWing", 10.05, 13.90, -3.85, -0.30, -0.06, 0.00, mat_parquet, col_floors)
make_box_obj("Floor_Living_Passage", 6.37, 10.05, -3.85, -3.56, -0.06, 0.00, mat_parquet, col_floors)

# Pavimento Dependance (Resina levigata)
make_box_obj("Floor_Dependance", 0.30, 4.45, -15.23, -12.63, -0.06, 0.00, mat_dep_floor, col_floors)

# Pavimentazione Cortile / Piattaforma Esterna
make_box_obj("Floor_Courtyard_Platform", -1.00, 16.00, -18.50, 1.00, -0.20, -0.06, mat_courtyard, col_floors)

# -------------------------------------------------------------
# 7. SCALA ARCHITETTONICA 3D
# -------------------------------------------------------------
num_steps = 9
tread_d = 0.25
riser_h = 3.00 / 17.0 # ~17.6 cm

for i in range(num_steps):
    z_top = (i + 1) * riser_h
    y0 = -3.56 + i * tread_d
    y1 = y0 + tread_d
    make_box_obj(f"Stair_Tread_{i+1}", 8.69, 9.70, y0, y1, 0.0, z_top, mat_stairs, col_stairs)

landing_z = num_steps * riser_h
make_box_obj("Stair_Landing", 8.69, 9.70, -3.56 + num_steps * tread_d, -0.30, 0.0, landing_z, mat_stairs, col_stairs)

# -------------------------------------------------------------
# 8. SANITARI BAGNO
# -------------------------------------------------------------
# WC sospeso (parete est bagno x=8.46, y=-2.00)
wc_x = 8.10
wc_y = -2.00
make_box_obj("WC_Flush_Plate", 8.44, 8.46, wc_y - 0.12, wc_y + 0.12, 1.05, 1.25, mat_chrome, col_furniture)
make_box_obj("WC_Bowl", wc_x, wc_x + 0.35, wc_y - 0.18, wc_y + 0.18, 0.15, 0.42, mat_ceramic, col_furniture)
make_box_obj("WC_Seat", wc_x - 0.02, wc_x + 0.36, wc_y - 0.19, wc_y + 0.19, 0.42, 0.45, mat_ceramic, col_furniture)

# Mobile lavabo moderno
make_box_obj("Vanity_Cabinet", 6.40, 7.15, -1.10, -0.32, 0.0, 0.82, mat_door_wood, col_furniture)
make_box_obj("Vanity_Basin", 6.45, 7.10, -1.05, -0.35, 0.82, 0.86, mat_ceramic, col_furniture)
make_box_obj("Vanity_Tap", 6.75, 6.80, -0.42, -0.37, 0.86, 1.02, mat_chrome, col_furniture)
make_box_obj("Vanity_Mirror", 6.45, 7.10, -0.32, -0.30, 1.15, 1.95, mat_glass, col_furniture)

# -------------------------------------------------------------
# 9. ETICHETTE TESTUALI 3D SUL PAVIMENTO
# -------------------------------------------------------------
def add_floor_label(text, x, y, size=0.45):
    font_curve = bpy.data.curves.new(type="FONT", name=f"Label_{text}")
    font_curve.body = text
    font_curve.size = size
    font_curve.extrude = 0.015
    obj = bpy.data.objects.new(name=f"Label_{text}", object_data=font_curve)
    obj.location = (x, y, 0.01)
    obj.data.materials.append(mat_label)
    col_labels.objects.link(obj)

add_floor_label("CAMERA / STUDIO (5.76 x 6.51 m)", 0.80, -3.80, size=0.35)
add_floor_label("BAGNO (2.09 x 3.26 m)", 6.50, -2.50, size=0.22)
add_floor_label("SCALA", 8.80, -2.60, size=0.20)
add_floor_label("SALONE / LIVING (7.56 x 7.45 m)", 7.20, -5.80, size=0.40)
add_floor_label("DEPENDANCE (4.15 x 2.60 m)", 0.60, -13.80, size=0.30)
add_floor_label("CORTILE", 7.00, -11.00, size=0.50)

# -------------------------------------------------------------
# 10. ILLUMINAZIONE E TELECAMERA
# -------------------------------------------------------------
# Sole
sun_data = bpy.data.lights.new(name="Sun_Key", type='SUN')
sun_data.energy = 4.2
sun_data.color = (1.0, 0.98, 0.94)
sun_data.angle = math.radians(12.0)
sun_obj = bpy.data.objects.new(name="Sun_Key", object_data=sun_data)
sun_obj.location = (15.0, -12.0, 18.0)
sun_obj.rotation_euler = (math.radians(50.0), math.radians(12.0), math.radians(-38.0))
col_lighting.objects.link(sun_obj)

# Luce di schiarita morbida
fill_data = bpy.data.lights.new(name="Sun_Fill", type='SUN')
fill_data.energy = 1.2
fill_data.color = (0.85, 0.90, 1.0)
fill_obj = bpy.data.objects.new(name="Sun_Fill", object_data=fill_data)
fill_obj.location = (-10.0, 10.0, 12.0)
fill_obj.rotation_euler = (math.radians(45.0), math.radians(-20.0), math.radians(140.0))
col_lighting.objects.link(fill_obj)

# Luci ambientali interne
def add_interior_light(name, x, y, z, size, power):
    l_data = bpy.data.lights.new(name=name, type='AREA')
    l_data.energy = power
    l_data.color = (1.0, 0.96, 0.90)
    l_data.size = size
    obj = bpy.data.objects.new(name=name, object_data=l_data)
    obj.location = (x, y, z)
    col_lighting.objects.link(obj)

add_interior_light("Light_Salone", 10.5, -5.5, 2.85, 3.5, 140.0)
add_interior_light("Light_Camera", 3.2, -3.5, 2.85, 2.8, 100.0)
add_interior_light("Light_Bagno", 7.4, -1.8, 2.85, 1.2, 45.0)
add_interior_light("Light_Dependance", 2.5, -13.9, 2.55, 2.0, 70.0)

# Telecamera Panoramica Assonometrica / 3D
cam_data = bpy.data.cameras.new(name="Camera_3D_Isometric")
cam_data.lens = 42
cam_obj = bpy.data.objects.new(name="Camera_3D_Isometric", object_data=cam_data)
cam_obj.location = (20.5, -20.5, 21.0)
cam_obj.rotation_euler = (math.radians(52.0), 0.0, math.radians(45.0))
col_lighting.objects.link(cam_obj)
bpy.context.scene.camera = cam_obj

# Setup render settings for clean viewport preview
scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in [i.identifier for i in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else scene.render.engine

print("=== 3D Architectural Model Completed Successfully ===")
