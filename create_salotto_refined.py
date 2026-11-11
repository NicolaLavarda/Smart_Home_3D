"""
create_salotto_refined.py (v4 - Perfected according to user feedback)

Key updates:
1. Table and chairs rotated 90°:
   - Long axis North-South (Y: -5.80 to -3.15, length 2.65m)
   - Width East-West (X: 2.45 to 3.50, width 1.05m)
   - Live edges along East and West long sides
   - Heavy solid slab legs at North and South
   - 3 chairs on West side (facing East), 3 chairs on East side (facing West)
   - 1 chair at South capotavola (facing North), 1 chair at North capotavola (facing South)
   - Fixed chair builder: constructed in local coordinates and rotated rigidly by matrix,
     eliminating any 90° pole misalignment!

2. West wall furniture shifted towards South:
   - South clearance to South wall is EXACTLY 40cm (starts at Y = -6.81 + 0.40 = -6.41)
   - North end of lowboard finishes EXACTLY 25cm south of the hearth quarter-circle floor plate
   - Lowboard: 3 modular sections (6 drawers in natural oak, white lacquer frame)
   - TV 65'' centered on media unit (with stand and remote)
   - Tall vitrine cabinet on South end
   - Wall shelf unit shifted accordingly above the TV

3. Radiator moved to SOUTH WALL:
   - Placed against the South wall (Y = -6.81, facing North +Y) in the SW corner

4. NW Corner 45° Drywall Wall & Wood Stove:
   - 45° drywall corner wall cutting the 90° inside corner behind the stove
   - Wood stove (Stufa a legna con forno) positioned in front of 45° wall, rotated -135° (SE)
   - Vertical black flue pipe rises 60cm above stove top (to Z = 2.16m)
   - 90° corrugated curved elbow goes directly into the 45° wall perpendicularly!
   - Black rosette collar at the wall penetration
   - Majolica ceramic relief panels with round medallions, baking oven, firebox with glowing fire,
     temperature gauge, air slider, log box, and fireplace tool stand.
"""

import bpy
import bmesh
from mathutils import Vector, Matrix, Euler
import math

print("=== Starting Refined Salotto Re-creation (v4) ===")

col_name = "09_Arredi_Principali"
col_furniture = bpy.data.collections.get(col_name)
if not col_furniture:
    col_furniture = bpy.data.collections.new(col_name)
    bpy.context.scene.collection.children.link(col_furniture)

col_lights = bpy.data.collections.get("08_Luci_e_Camere")
if not col_lights:
    col_lights = bpy.data.collections.new("08_Luci_e_Camere")
    bpy.context.scene.collection.children.link(col_lights)

# -------------------------------------------------------------
# 1. CLEAN PREVIOUS SALOTTO OBJECTS SAFELY
# -------------------------------------------------------------
old_salotto_prefixes = [
    'Mobile_TV_', 'Vetrina_', 'TV_Salotto_', 'Mensola_Salotto_',
    'Stufa_', 'Tavolo_Salotto_', 'Tavolo_Laptop_', 'Tavolo_Pacco_',
    'Sedia_Salotto_', 'Divano_', 'Scaletta_Cani_',
    'Tavolino_Angolo_', 'Lampada_Angolo_', 'Applique_Salotto_',
    'Salotto_', 'Termoarredo_Salotto_', 'Light_Salotto_',
    'Wall_Cartongesso_Angolo_', 'Madia_Salotto_'
]

preserve_list = [
    'Wall_Salotto_Cucina', 'Trave_Rustica', 'Door_Salotto', 'Win_', 'Floor_', 'Ceiling_'
]

removed_count = 0
for o in list(bpy.data.objects):
    name = o.name
    if any(k in name for k in preserve_list):
        continue
    if any(name.startswith(p) for p in old_salotto_prefixes):
        bpy.data.objects.remove(o, do_unlink=True)
        removed_count += 1

print(f"Cleaned {removed_count} old/stale salotto objects.")

# -------------------------------------------------------------
# 2. MATERIALS SETUP
# -------------------------------------------------------------
def get_or_create_mat(name, color, roughness=0.35, metallic=0.0, transmission=0.0, ior=1.45, alpha=1.0, emission_color=None, emission_strength=0.0):
    mat = bpy.data.materials.get(name)
    if not mat:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
    
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    
    if transmission > 0:
        if "Transmission Weight" in bsdf.inputs:
            bsdf.inputs["Transmission Weight"].default_value = transmission
        elif "Transmission" in bsdf.inputs:
            bsdf.inputs["Transmission"].default_value = transmission
        bsdf.inputs["IOR"].default_value = ior
        
    if emission_strength > 0 and emission_color:
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = emission_color
            bsdf.inputs["Emission Strength"].default_value = emission_strength
        elif "Emission" in bsdf.inputs:
            bsdf.inputs["Emission"].default_value = emission_color
            
    return mat

mat_white_lacquer = get_or_create_mat("Mat_Laccato_Bianco", (0.92, 0.92, 0.92, 1.0), roughness=0.25)
mat_dark_anthracite = get_or_create_mat("Mat_Infissi_Antracite", (0.12, 0.12, 0.12, 1.0), roughness=0.55)
mat_chrome = get_or_create_mat("Mat_Cromo", (0.95, 0.95, 0.95, 1.0), roughness=0.1, metallic=1.0)
mat_inox = get_or_create_mat("Mat_Acciaio_Inox_Frigo", (0.80, 0.80, 0.80, 1.0), roughness=0.25, metallic=0.9)
mat_glass = get_or_create_mat("Mat_Vetro", (0.95, 0.95, 0.95, 1.0), roughness=0.05, transmission=0.95, ior=1.52)
mat_glass_frosted = get_or_create_mat("Mat_Vetro_Satinato", (0.90, 0.92, 0.92, 1.0), roughness=0.45, transmission=0.85, ior=1.45)
mat_black_tv = get_or_create_mat("Mat_Vetro_Nero_TV", (0.02, 0.02, 0.02, 1.0), roughness=0.08, metallic=0.1)
mat_wall_int = get_or_create_mat("Mat_Intonaco_Interno_Light", (0.92, 0.90, 0.87, 1.0), roughness=0.85)

# Natural warm light oak (for lowboard drawer fronts & live-edge table)
mat_oak_natural = get_or_create_mat("Mat_Rovere_Naturale_Chiaro", (0.72, 0.54, 0.35, 1.0), roughness=0.38)
# Walnut/Cherry for chairs
mat_wood_chair = get_or_create_mat("Mat_Legno_Tavolo_Noce", (0.35, 0.20, 0.10, 1.0), roughness=0.40)
# Dark charcoal textured fabric for sofas
mat_sofa_fabric = get_or_create_mat("Mat_Divano_Tessuto_Grigio", (0.16, 0.17, 0.19, 1.0), roughness=0.85)
# Light gray fabric for cushions & pet ramp
mat_fabric_light = get_or_create_mat("Mat_Tessuto_Sedie", (0.45, 0.46, 0.47, 1.0), roughness=0.85)
# Blanket throw with rustic mountain pattern
mat_throw_blanket = get_or_create_mat("Mat_Copridivano_Pattern", (0.55, 0.53, 0.50, 1.0), roughness=0.90)
# Majolica ceramic tiles for stove (warm sand/honey terracotta)
mat_stove_majolica = get_or_create_mat("Mat_Stufa_Maiolica", (0.76, 0.65, 0.50, 1.0), roughness=0.28)
# Stove cast iron
mat_stove_cast_iron = get_or_create_mat("Mat_Focolare_Ghisa", (0.07, 0.07, 0.07, 1.0), roughness=0.65, metallic=0.7)
# Emissive fire
mat_stove_fire = get_or_create_mat("Mat_Stufa_Fuoco_Emissive", (1.0, 0.45, 0.05, 1.0), roughness=0.5, emission_color=(1.0, 0.42, 0.02, 1.0), emission_strength=14.0)
# Sconce light emissive lens
mat_sconce_emissive = get_or_create_mat("Mat_Sconce_Emissive", (1.0, 0.95, 0.85, 1.0), roughness=0.3, emission_color=(1.0, 0.94, 0.82, 1.0), emission_strength=6.0)
# Spot light emissive lens
mat_spot_emissive = get_or_create_mat("Mat_Spot_Emissive", (1.0, 0.98, 0.92, 1.0), roughness=0.2, emission_color=(1.0, 0.98, 0.92, 1.0), emission_strength=8.0)
# Emerald green glass for vase
mat_emerald_glass = get_or_create_mat("Mat_Vaso_Smeraldo", (0.02, 0.22, 0.12, 1.0), roughness=0.1, transmission=0.85, ior=1.55)
# Blue ceramic for corner table lamp
mat_blue_ceramic = get_or_create_mat("Mat_Ceramica_Blu", (0.12, 0.28, 0.55, 1.0), roughness=0.2)
# Cardboard parcel
mat_cardboard = get_or_create_mat("Mat_Cartone", (0.62, 0.48, 0.32, 1.0), roughness=0.75)

# -------------------------------------------------------------
# HELPER FUNCTIONS
# -------------------------------------------------------------
def make_box(name, x_min, x_max, y_min, y_max, z_min, z_max, mat=None, collection=col_furniture):
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
    collection.objects.link(obj)
    return obj

def make_cylinder(name, x, y, z_min, z_max, radius, segments=16, mat=None, collection=col_furniture):
    bm = bmesh.new()
    depth = abs(z_max - z_min)
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=segments,
        radius1=radius,
        radius2=radius,
        depth=depth
    )
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    
    obj = bpy.data.objects.new(name, mesh)
    obj.location = (x, y, (z_min + z_max) / 2.0)
    if mat:
        obj.data.materials.append(mat)
    collection.objects.link(obj)
    return obj

def make_beveled_box(name, cx, cy, cz, dx, dy, dz, bevel=0.015, mat=None, collection=col_furniture):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(dx, dy, dz), verts=bm.verts)
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=bm.edges[:], offset=bevel, segments=2, profile=0.7)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    
    obj = bpy.data.objects.new(name, mesh)
    obj.location = (cx, cy, cz)
    if mat:
        obj.data.materials.append(mat)
    collection.objects.link(obj)
    return obj

# -------------------------------------------------------------
# 3. NORTH-WEST CORNER: 45° DRYWALL WALL & WOOD STOVE
# -------------------------------------------------------------
print("Building NW Corner 45° Drywall Wall & Wood Stove...")

# Corner of the room: X=0.30, Y=-0.30
# 45° Drywall wall cutting across the inside corner behind the stove:
# Starts at (0.30, -0.75) on the West wall and goes to (0.75, -0.30) on the North wall.
# Width = 0.45 * sqrt(2) = 0.636m.
bm_corner_wall = bmesh.new()
v_cw_bot = [
    bm_corner_wall.verts.new((0.30, -0.30, 0.00)),
    bm_corner_wall.verts.new((0.30, -0.75, 0.00)),
    bm_corner_wall.verts.new((0.75, -0.30, 0.00))
]
v_cw_top = [
    bm_corner_wall.verts.new((0.30, -0.30, 2.83)),
    bm_corner_wall.verts.new((0.30, -0.75, 2.83)),
    bm_corner_wall.verts.new((0.75, -0.30, 2.83))
]
# Bottom and Top faces
bm_corner_wall.faces.new(v_cw_bot)
bm_corner_wall.faces.new(list(reversed(v_cw_top)))
# 45° diagonal front face facing into the room: (0.30, -0.75) to (0.75, -0.30)
bm_corner_wall.faces.new([v_cw_bot[1], v_cw_bot[2], v_cw_top[2], v_cw_top[1]])
# Back faces against walls
bm_corner_wall.faces.new([v_cw_bot[0], v_cw_bot[1], v_cw_top[1], v_cw_top[0]])
bm_corner_wall.faces.new([v_cw_bot[2], v_cw_bot[0], v_cw_top[0], v_cw_top[2]])
bmesh.ops.recalc_face_normals(bm_corner_wall, faces=bm_corner_wall.faces)
mesh_corner_wall = bpy.data.meshes.new("Wall_Cartongesso_Angolo_Stufa")
bm_corner_wall.to_mesh(mesh_corner_wall)
bm_corner_wall.free()
obj_corner_wall = bpy.data.objects.new("Wall_Cartongesso_Angolo_Stufa", mesh_corner_wall)
obj_corner_wall.data.materials.append(mat_wall_int)
col_furniture.objects.link(obj_corner_wall)

# Center of 45° drywall face: (0.525, -0.525)
# Stove center: (0.80, -0.80), rotated -135° (facing SE into room)
st_cx, st_cy = 0.80, -0.80
st_w = 0.65
st_d = 0.52
st_h = 1.56
stove_rot_deg = -135

# A. Hearth Plate (Pedana salvapavimento curva a terra)
# Quarter-circle from corner (0.30, -0.30), radius R = 1.18m
# Southern edge on West wall is at Y = -0.30 - 1.18 = -1.48m
h_radius = 1.18
bm_hearth = bmesh.new()
n_hearth_pts = 16
hearth_pts = [(0.31, -0.31)]
for i in range(n_hearth_pts + 1):
    ang_rad = -math.pi/2.0 + i * (math.pi/2.0) / n_hearth_pts
    hx = 0.31 + h_radius * math.cos(ang_rad)
    hy = -0.31 + h_radius * math.sin(ang_rad)
    hearth_pts.append((hx, hy))

v_h_bot = [bm_hearth.verts.new((x, y, 0.001)) for x, y in hearth_pts]
v_h_top = [bm_hearth.verts.new((x, y, 0.008)) for x, y in hearth_pts]
bm_hearth.faces.new(v_h_bot)
bm_hearth.faces.new(list(reversed(v_h_top)))
for i in range(len(hearth_pts)):
    nxt = (i + 1) % len(hearth_pts)
    bm_hearth.faces.new([v_h_bot[i], v_h_bot[nxt], v_h_top[nxt], v_h_top[i]])
bmesh.ops.recalc_face_normals(bm_hearth, faces=bm_hearth.faces)
mesh_hearth = bpy.data.meshes.new("Stufa_Pedana_Salvapavimento")
bm_hearth.to_mesh(mesh_hearth)
bm_hearth.free()
obj_hearth = bpy.data.objects.new("Stufa_Pedana_Salvapavimento", mesh_hearth)
obj_hearth.data.materials.append(mat_inox)
col_furniture.objects.link(obj_hearth)

def make_stove_box(name, lx_min, lx_max, ly_min, ly_max, z_min, z_max, mat):
    w = lx_max - lx_min
    d = ly_max - ly_min
    h = z_max - z_min
    cx_loc = (lx_min + lx_max) / 2.0
    cy_loc = (ly_min + ly_max) / 2.0
    cz_loc = (z_min + z_max) / 2.0
    
    ang_rad = math.radians(stove_rot_deg)
    cos_a = math.cos(ang_rad)
    sin_a = math.sin(ang_rad)
    world_x = st_cx + (cx_loc * cos_a - cy_loc * sin_a)
    world_y = st_cy + (cx_loc * sin_a + cy_loc * cos_a)
    
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(w, d, h), verts=bm.verts)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    
    obj = bpy.data.objects.new(name, mesh)
    obj.location = (world_x, world_y, cz_loc)
    obj.rotation_euler = Euler((0, 0, ang_rad), 'XYZ')
    if mat:
        obj.data.materials.append(mat)
    col_furniture.objects.link(obj)
    return obj

def make_stove_cylinder(name, lx, ly, z_min, z_max, radius, segments=16, mat=None):
    ang_rad = math.radians(stove_rot_deg)
    cos_a = math.cos(ang_rad)
    sin_a = math.sin(ang_rad)
    world_x = st_cx + (lx * cos_a - ly * sin_a)
    world_y = st_cy + (lx * sin_a + ly * cos_a)
    
    bm = bmesh.new()
    depth = abs(z_max - z_min)
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments, radius1=radius, radius2=radius, depth=depth)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    
    obj = bpy.data.objects.new(name, mesh)
    obj.location = (world_x, world_y, (z_min + z_max) / 2.0)
    obj.rotation_euler = Euler((0, 0, ang_rad), 'XYZ')
    if mat:
        obj.data.materials.append(mat)
    col_furniture.objects.link(obj)
    return obj

# Stove Base plinth (cast iron)
make_stove_box("Stufa_Zoccolo_Base", -st_w/2, st_w/2, -st_d/2, st_d/2, 0.008, 0.12, mat_stove_cast_iron)
# Temperature gauge dial at bottom left
make_stove_cylinder("Stufa_Termometro_Quadrante", -st_w/2 + 0.10, st_d/2 + 0.015, 0.05, 0.07, 0.024, segments=16, mat=mat_inox)
# Air regulator slider at bottom center
make_stove_box("Stufa_Regolatore_Aria", -0.12, 0.12, st_d/2 + 0.012, st_d/2 + 0.022, 0.02, 0.04, mat_stove_cast_iron)

# Side decorative majolica panels with 4 relief medallions
make_stove_box("Stufa_Pannello_Lat_L", -st_w/2, -st_w/2 + 0.04, -st_d/2 + 0.03, st_d/2 - 0.03, 0.12, st_h - 0.06, mat_stove_majolica)
make_stove_box("Stufa_Pannello_Lat_R", st_w/2 - 0.04, st_w/2, -st_d/2 + 0.03, st_d/2 - 0.03, 0.12, st_h - 0.06, mat_stove_majolica)
for m_z in [0.26, 0.65, 1.00, 1.30]:
    make_stove_cylinder(f"Stufa_Medaglione_Lat_L_{m_z}", -st_w/2 - 0.005, 0.0, m_z - 0.02, m_z + 0.02, 0.025, segments=12, mat=mat_stove_majolica)
    make_stove_cylinder(f"Stufa_Medaglione_Lat_R_{m_z}", st_w/2 + 0.005, 0.0, m_z - 0.02, m_z + 0.02, 0.025, segments=12, mat=mat_stove_majolica)

make_stove_box("Stufa_Schienale", -st_w/2, st_w/2, -st_d/2, -st_d/2 + 0.03, 0.12, st_h - 0.06, mat_stove_cast_iron)

# Corner cast iron pilasters
for cx_sign in [-1, 1]:
    for cy_sign in [-1, 1]:
        px = cx_sign * (st_w/2 - 0.025)
        py = cy_sign * (st_d/2 - 0.025)
        make_stove_box(f"Stufa_Pilastrino_{cx_sign}_{cy_sign}", px - 0.025, px + 0.025, py - 0.025, py + 0.025, 0.12, st_h - 0.06, mat_stove_cast_iron)

# Front tiers:
# 1. Lower drawer panel in ceramic with relief boss (Z: 0.14 to 0.38)
make_stove_box("Stufa_Cassetto_Cenere_Fronte", -st_w/2 + 0.06, st_w/2 - 0.06, st_d/2 - 0.02, st_d/2 + 0.015, 0.14, 0.38, mat_stove_majolica)
make_stove_box("Stufa_Cassetto_Cenere_Cornice", -st_w/2 + 0.05, st_w/2 - 0.05, st_d/2 - 0.01, st_d/2 + 0.01, 0.13, 0.39, mat_stove_cast_iron)
make_stove_cylinder("Stufa_Medaglione_1", 0.0, st_d/2 + 0.02, 0.24, 0.28, 0.03, segments=16, mat=mat_stove_majolica)

# 2. Firebox (Focolare) (Z: 0.42 to 0.88)
make_stove_box("Stufa_Focolare_Porta_Telaio", -st_w/2 + 0.05, st_w/2 - 0.05, st_d/2 - 0.02, st_d/2 + 0.018, 0.42, 0.88, mat_stove_cast_iron)
make_stove_box("Stufa_Focolare_Vetro", -st_w/2 + 0.11, st_w/2 - 0.11, st_d/2 + 0.005, st_d/2 + 0.015, 0.48, 0.82, mat_glass)
make_stove_box("Stufa_Fuoco_Fiamma", -st_w/2 + 0.14, st_w/2 - 0.14, st_d/2 - 0.18, st_d/2 - 0.04, 0.46, 0.76, mat_stove_fire)
make_stove_box("Stufa_Legna_Ardente", -st_w/2 + 0.12, st_w/2 - 0.12, st_d/2 - 0.22, st_d/2 - 0.06, 0.43, 0.50, mat_wood_chair)

# 3. Middle decorative ceramic panel with 2 drawers/handles (Z: 0.90 to 1.10)
make_stove_box("Stufa_Pannello_Centrale", -st_w/2 + 0.06, st_w/2 - 0.06, st_d/2 - 0.02, st_d/2 + 0.015, 0.90, 1.10, mat_stove_majolica)
make_stove_cylinder("Stufa_Medaglione_2A", 0.0, st_d/2 + 0.02, 0.93, 0.97, 0.025, segments=16, mat=mat_stove_majolica)
make_stove_cylinder("Stufa_Medaglione_2B", 0.0, st_d/2 + 0.02, 1.03, 1.07, 0.025, segments=16, mat=mat_stove_majolica)

# 4. Upper Baking Oven (Forno superiore) (Z: 1.14 to 1.48)
make_stove_box("Stufa_Forno_Porta_Telaio", -st_w/2 + 0.05, st_w/2 - 0.05, st_d/2 - 0.02, st_d/2 + 0.018, 1.14, 1.48, mat_stove_cast_iron)
make_stove_box("Stufa_Forno_Vetro", -st_w/2 + 0.11, st_w/2 - 0.11, st_d/2 + 0.005, st_d/2 + 0.015, 1.20, 1.42, mat_glass)
make_stove_cylinder("Stufa_Forno_Termometro", 0.0, st_d/2 + 0.016, 1.25, 1.27, 0.015, segments=12, mat=mat_inox)
make_stove_box("Stufa_Forno_Maniglia", -st_w/2 + 0.04, -st_w/2 + 0.07, st_d/2 + 0.02, st_d/2 + 0.06, 1.26, 1.36, mat_stove_cast_iron)

# 5. Top Shaped Crown (Piano in pietra/maiolica sagomata)
make_stove_box("Stufa_Top_Corona", -st_w/2 - 0.03, st_w/2 + 0.03, -st_d/2 - 0.03, st_d/2 + 0.03, st_h - 0.06, st_h, mat_stove_majolica)

# B. FLUE PIPE (Canna fumaria nera):
# Rises vertically 60cm above stove top (from Z = 1.56 to Z = 2.16m)
flue_x = st_cx
flue_y = st_cy
flue_r = 0.075

# 1. Straight vertical flue pipe (60cm)
make_cylinder("Stufa_Canna_Fumaria_Verticale", flue_x, flue_y, st_h, st_h + 0.60, flue_r, segments=24, mat=mat_stove_cast_iron)
# Collar ring at stove top joint
make_cylinder("Stufa_Canna_Fumaria_Collare_Base", flue_x, flue_y, st_h, st_h + 0.05, flue_r + 0.012, segments=24, mat=mat_stove_cast_iron)

# 2. Corrugated 90° curved elbow
# Curves from vertical (+Z) towards the 45° wall along direction (-1, 1)/sqrt(2)
r_bend = 0.12
n_segments = 8
bm_elbow = bmesh.new()

# Direction into the wall
dir_u = -1.0 / math.sqrt(2.0)
dir_v = 1.0 / math.sqrt(2.0)

# Center of curvature
cc_x = flue_x + r_bend * dir_u
cc_y = flue_y + r_bend * dir_v
cc_z = st_h + 0.60

rings_verts = []
for si in range(n_segments + 1):
    phi = (si / n_segments) * (math.pi / 2.0)
    # Center of this slice along circular arc
    cx = cc_x - r_bend * dir_u * math.cos(phi)
    cy = cc_y - r_bend * dir_v * math.cos(phi)
    cz = cc_z + r_bend * math.sin(phi)
    
    # Tangent vector of pipe at this slice: derivative with respect to phi
    tx = dir_u * math.sin(phi)
    ty = dir_v * math.sin(phi)
    tz = math.cos(phi)
    
    # Binormal vector: horizontal perpendicular to wall normal
    bx = -dir_v
    by = dir_u
    bz = 0.0
    
    # Normal vector in the vertical bend plane: cross(T, B)
    nx = ty * bz - tz * by
    ny = tz * bx - tx * bz
    nz = tx * by - ty * bx
    # Normalize
    n_len = math.sqrt(nx**2 + ny**2 + nz**2)
    nx /= n_len; ny /= n_len; nz /= n_len
    
    # Subtle corrugation ribbing
    curr_r = flue_r + (0.005 if (si % 2 == 1 and 0 < si < n_segments) else 0.0)
    
    ring = []
    n_pts = 16
    for pi in range(n_pts):
        theta = pi * (2.0 * math.pi / n_pts)
        vx = cx + curr_r * (math.cos(theta) * bx + math.sin(theta) * nx)
        vy = cy + curr_r * (math.cos(theta) * by + math.sin(theta) * ny)
        vz = cz + curr_r * (math.cos(theta) * bz + math.sin(theta) * nz)
        ring.append(bm_elbow.verts.new((vx, vy, vz)))
    rings_verts.append(ring)

for si in range(n_segments):
    r1 = rings_verts[si]
    r2 = rings_verts[si + 1]
    n_pts = len(r1)
    for pi in range(n_pts):
        nxt = (pi + 1) % n_pts
        bm_elbow.faces.new([r1[pi], r2[pi], r2[nxt], r1[nxt]])

bmesh.ops.recalc_face_normals(bm_elbow, faces=bm_elbow.faces)
mesh_elbow = bpy.data.meshes.new("Stufa_Canna_Fumaria_Curva")
bm_elbow.to_mesh(mesh_elbow)
bm_elbow.free()
obj_elbow = bpy.data.objects.new("Stufa_Canna_Fumaria_Curva", mesh_elbow)
obj_elbow.data.materials.append(mat_stove_cast_iron)
col_furniture.objects.link(obj_elbow)

# 3. Horizontal pipe from elbow exit to 45° wall penetration
elbow_exit_x = cc_x
elbow_exit_y = cc_y
elbow_exit_z = cc_z + r_bend

wall_target_x = 0.525
wall_target_y = -0.525
wall_target_z = elbow_exit_z

h_pipe_dx = wall_target_x - elbow_exit_x
h_pipe_dy = wall_target_y - elbow_exit_y
h_pipe_len = math.sqrt(h_pipe_dx**2 + h_pipe_dy**2)
h_pipe_cx = (elbow_exit_x + wall_target_x) / 2.0
h_pipe_cy = (elbow_exit_y + wall_target_y) / 2.0

pipe_dir = Vector((wall_target_x - elbow_exit_x, wall_target_y - elbow_exit_y, 0.0)).normalized()
pipe_rot = pipe_dir.to_track_quat('Z', 'Y').to_euler()

bm_flue_h = bmesh.new()
bmesh.ops.create_cone(bm_flue_h, cap_ends=True, segments=24, radius1=flue_r, radius2=flue_r, depth=h_pipe_len)
mesh_flue_h = bpy.data.meshes.new("Stufa_Canna_Fumaria_Orizzontale")
bm_flue_h.to_mesh(mesh_flue_h)
bm_flue_h.free()
obj_flue_h = bpy.data.objects.new("Stufa_Canna_Fumaria_Orizzontale", mesh_flue_h)
obj_flue_h.location = (h_pipe_cx, h_pipe_cy, wall_target_z)
obj_flue_h.rotation_euler = pipe_rot
obj_flue_h.data.materials.append(mat_stove_cast_iron)
col_furniture.objects.link(obj_flue_h)

# Wall rosette collar on 45° wall (perpendicular to pipe direction)
bm_rosette = bmesh.new()
bmesh.ops.create_cone(bm_rosette, cap_ends=True, segments=24, radius1=0.13, radius2=0.13, depth=0.025)
mesh_rosette = bpy.data.meshes.new("Stufa_Rosone_Muro")
bm_rosette.to_mesh(mesh_rosette)
bm_rosette.free()
obj_rosette = bpy.data.objects.new("Stufa_Rosone_Muro", mesh_rosette)
obj_rosette.location = (wall_target_x, wall_target_y, wall_target_z)
obj_rosette.rotation_euler = pipe_rot
obj_rosette.data.materials.append(mat_stove_cast_iron)
col_furniture.objects.link(obj_rosette)

# Firewood Box (white bin with cut firewood logs) placed in front of stove
log_box_x = 1.05
log_box_y = -1.45
make_box("Stufa_Portalegna_Fondo", log_box_x - 0.22, log_box_x + 0.22, log_box_y - 0.15, log_box_y + 0.15, 0.008, 0.02, mat_white_lacquer)
make_box("Stufa_Portalegna_Bordo_S", log_box_x - 0.22, log_box_x + 0.22, log_box_y - 0.15, log_box_y - 0.13, 0.02, 0.24, mat_white_lacquer)
make_box("Stufa_Portalegna_Bordo_N", log_box_x - 0.22, log_box_x + 0.22, log_box_y + 0.13, log_box_y + 0.15, 0.02, 0.24, mat_white_lacquer)
make_box("Stufa_Portalegna_Bordo_W", log_box_x - 0.22, log_box_x - 0.20, log_box_y - 0.13, log_box_y + 0.13, 0.02, 0.24, mat_white_lacquer)
make_box("Stufa_Portalegna_Bordo_E", log_box_x + 0.20, log_box_x + 0.22, log_box_y - 0.13, log_box_y + 0.13, 0.02, 0.24, mat_white_lacquer)
for li in range(3):
    make_cylinder(f"Stufa_Ciocco_Legna_{li}", log_box_x + (li - 1)*0.10, log_box_y, 0.03, 0.20, 0.045, segments=12, mat=mat_cardboard)

# Fireplace Tool Set (black wrought iron stand with tools) to the right of stove
tool_x = 1.38
tool_y = -0.72
make_cylinder("Stufa_Set_Attrezzi_Base", tool_x, tool_y, 0.008, 0.03, 0.09, segments=16, mat=mat_stove_cast_iron)
make_cylinder("Stufa_Set_Attrezzi_Asta", tool_x, tool_y, 0.03, 0.78, 0.010, segments=8, mat=mat_stove_cast_iron)
for ti in range(3):
    tang = ti * (2*math.pi / 3)
    tx = tool_x + 0.04 * math.cos(tang)
    ty = tool_y + 0.04 * math.sin(tang)
    make_cylinder(f"Stufa_Attrezzo_{ti}", tx, ty, 0.12, 0.72, 0.006, segments=8, mat=mat_stove_cast_iron)

# -------------------------------------------------------------
# 4. WEST WALL UNIT SHIFTED SOUTH & SOUTH WALL RADIATOR
# -------------------------------------------------------------
print("Building West Wall Furniture (Shifted South) & South Wall Radiator...")

# A. DESIGNER VERTICAL RADIATOR MOUNTED ON SOUTH WALL
# South wall is at Y = -6.81. Placed in the SW corner against South wall!
rad_y = -6.75
rad_x_start = 0.38
for ri in range(8):
    rx = rad_x_start + ri * 0.04
    make_cylinder(f"Termoarredo_Salotto_Tubo_{ri}", rx, rad_y, 0.15, 2.15, 0.013, segments=12, mat=mat_white_lacquer)
make_box("Termoarredo_Salotto_Collettore_Top", rad_x_start - 0.02, rad_x_start + 7*0.04 + 0.02, rad_y - 0.015, rad_y + 0.015, 2.05, 2.09, mat_white_lacquer)
make_box("Termoarredo_Salotto_Collettore_Bot", rad_x_start - 0.02, rad_x_start + 7*0.04 + 0.02, rad_y - 0.015, rad_y + 0.015, 0.20, 0.24, mat_white_lacquer)
make_cylinder("Termoarredo_Salotto_Valvola", rad_x_start + 7*0.04 + 0.03, rad_y, 0.12, 0.22, 0.016, segments=12, mat=mat_chrome)

# B. WEST WALL FURNITURE SYSTEM COORDINATES
# South clearance: exactly 40cm from South wall (Y = -6.81) -> starts at Y = -6.41m
# North end: exactly 25cm south of hearth plate southern edge (Y = -1.48) -> finishes at Y = -1.73m
y_furn_south = -6.41
y_furn_north = -1.73
# Split: Tall Vitrine Cabinet is 1.50m wide -> from Y = -6.41 to Y = -4.91
# Suspended Lowboard is 3.18m wide -> from Y = -4.91 to Y = -1.73

vx0, vx1 = 0.32, 0.77
vy0, vy1 = y_furn_south, y_furn_south + 1.50 # -6.41 to -4.91
vz_top = 2.15

# Tall Vitrine Cabinet (Vetrina Salotto)
make_box("Vetrina_Salotto_Zoccolo", vx0, vx1 - 0.03, vy0, vy1, 0.00, 0.08, mat_white_lacquer)
make_box("Vetrina_Salotto_Top", vx0 - 0.01, vx1 + 0.01, vy0 - 0.01, vy1 + 0.01, vz_top - 0.03, vz_top, mat_white_lacquer)
make_box("Vetrina_Salotto_Fianco_S", vx0, vx1, vy0, vy0 + 0.03, 0.08, vz_top - 0.03, mat_white_lacquer)
make_box("Vetrina_Salotto_Fianco_N", vx0, vx1, vy1 - 0.03, vy1, 0.08, vz_top - 0.03, mat_white_lacquer)
make_box("Vetrina_Salotto_Schienale", vx0, vx0 + 0.02, vy0, vy1, 0.08, vz_top - 0.03, mat_white_lacquer)

# Column 1 (Left: Y from -6.41 to -5.91, solid tall door)
make_box("Vetrina_Salotto_Divisorio_1", vx0 + 0.02, vx1 - 0.03, -5.92, -5.89, 0.08, vz_top - 0.03, mat_white_lacquer)
make_box("Vetrina_Salotto_Anta_Piena", vx1 - 0.02, vx1, -6.38, -5.92, 0.10, vz_top - 0.05, mat_white_lacquer)
make_cylinder("Vetrina_Salotto_Maniglia_1", vx1 + 0.01, -5.95, 1.00, 1.25, 0.008, segments=8, mat=mat_chrome)

# Column 2 (Middle: Y from -5.89 to -5.41, open display niche + bottom 2 drawers)
make_box("Vetrina_Salotto_Divisorio_2", vx0 + 0.02, vx1 - 0.03, -5.42, -5.39, 0.08, vz_top - 0.03, mat_white_lacquer)
make_box("Vetrina_Salotto_Ripiano_Medio_Base", vx0 + 0.02, vx1 - 0.03, -5.89, -5.42, 0.65, 0.67, mat_white_lacquer)
make_box("Vetrina_Salotto_Cassetto_1", vx1 - 0.02, vx1, -5.88, -5.43, 0.10, 0.36, mat_white_lacquer)
make_box("Vetrina_Salotto_Cassetto_2", vx1 - 0.02, vx1, -5.88, -5.43, 0.38, 0.64, mat_white_lacquer)
make_cylinder("Vetrina_Salotto_Pomolo_Cass_1", vx1 + 0.01, -5.65, 0.22, 0.24, 0.012, segments=12, mat=mat_chrome)
make_cylinder("Vetrina_Salotto_Pomolo_Cass_2", vx1 + 0.01, -5.65, 0.50, 0.52, 0.012, segments=12, mat=mat_chrome)
for si, sz in enumerate([1.02, 1.40, 1.78]):
    make_box(f"Vetrina_Salotto_Ripiano_Open_{si}", vx0 + 0.02, vx1 - 0.04, -5.89, -5.42, sz, sz + 0.02, mat_white_lacquer)

# Column 3 (Right: Y from -5.39 to -4.91, glass display door with interior glass shelves)
make_box("Vetrina_Salotto_Anta_Vetro_Telaio_L", vx1 - 0.02, vx1, -5.39, -5.34, 0.10, vz_top - 0.05, mat_white_lacquer)
make_box("Vetrina_Salotto_Anta_Vetro_Telaio_R", vx1 - 0.02, vx1, -4.96, -4.91, 0.10, vz_top - 0.05, mat_white_lacquer)
make_box("Vetrina_Salotto_Anta_Vetro_Telaio_Top", vx1 - 0.02, vx1, -5.34, -4.96, vz_top - 0.10, vz_top - 0.05, mat_white_lacquer)
make_box("Vetrina_Salotto_Anta_Vetro_Telaio_Bot", vx1 - 0.02, vx1, -5.34, -4.96, 0.10, 0.15, mat_white_lacquer)
make_box("Vetrina_Salotto_Anta_Vetro_Pannello", vx1 - 0.015, vx1 - 0.005, -5.34, -4.96, 0.15, vz_top - 0.10, mat_glass)
make_cylinder("Vetrina_Salotto_Maniglia_Vetro", vx1 + 0.01, -5.32, 1.00, 1.25, 0.008, segments=8, mat=mat_chrome)
for gi, gz in enumerate([0.55, 0.95, 1.35, 1.75]):
    make_box(f"Vetrina_Salotto_Ripiano_Cristallo_{gi}", vx0 + 0.04, vx1 - 0.05, -5.38, -4.92, gz, gz + 0.008, mat_glass)

for wi, wy in enumerate([-5.25, -5.15, -5.05]):
    make_cylinder(f"Vetrina_Calice_Stelo_{wi}", 0.52, wy, 1.36, 1.48, 0.004, segments=8, mat=mat_glass)
    make_cylinder(f"Vetrina_Calice_Coppa_{wi}", 0.52, wy, 1.44, 1.54, 0.028, segments=12, mat=mat_glass)

# Presence sensor / dome camera on top of cabinet
make_cylinder("Salotto_Sensore_RuView_Base", 0.55, -5.65, vz_top, vz_top + 0.035, 0.032, segments=16, mat=mat_white_lacquer)
make_cylinder("Salotto_Sensore_RuView_Dome", 0.55, -5.65, vz_top + 0.035, vz_top + 0.065, 0.025, segments=16, mat=mat_dark_anthracite)

# C. SUSPENDED / RECESSED-PLINTH MODULAR LOWBOARD (Mobile Basso Ovest)
# Runs from Y = -4.91 to Y = -1.74 (total length = 3.17m, terminates exactly 25cm south of hearth plate).
# Top height = 0.65m.
mb_x0, mb_x1 = 0.32, 0.82
mb_y0, mb_y1 = -4.91, -1.755
mb_z_plinth = 0.10
mb_z_top = 0.65

make_box("Mobile_TV_Base_Zoccolo", mb_x0, mb_x1 - 0.05, mb_y0 + 0.05, mb_y1 - 0.05, 0.00, mb_z_plinth, mat_dark_anthracite)
make_box("Mobile_TV_Base_Fondo", mb_x0, mb_x1, mb_y0, mb_y1, mb_z_plinth, mb_z_plinth + 0.02, mat_white_lacquer)
make_box("Mobile_TV_Base_Top", mb_x0, mb_x1 + 0.015, mb_y0, mb_y1 + 0.015, mb_z_top - 0.02, mb_z_top, mat_white_lacquer)
make_box("Mobile_TV_Base_Fianco_Nord", mb_x0, mb_x1 + 0.015, mb_y1, mb_y1 + 0.015, mb_z_plinth, mb_z_top, mat_white_lacquer)
make_box("Mobile_TV_Base_Schienale", mb_x0, mb_x0 + 0.02, mb_y0, mb_y1, mb_z_plinth, mb_z_top, mat_white_lacquer)

# 3 Modules of 2 stacked horizontal drawers each:
# Module 1: Y from -4.89 to -3.85 (width 1.04m, under window)
# Module 2: Y from -3.83 to -2.79 (width 1.04m)
# Module 3: Y from -2.77 to -1.76 (width 1.01m, under TV)
modules_y = [
    ("Mod1", -4.89, -3.85),
    ("Mod2", -3.83, -2.79),
    ("Mod3", -2.77, -1.76)
]

for mod_name, y_start, y_end in modules_y:
    make_box(f"Mobile_TV_Frontale_{mod_name}_Bot", mb_x1, mb_x1 + 0.018, y_start, y_end, 0.13, 0.36, mat_oak_natural)
    make_box(f"Mobile_TV_Frontale_{mod_name}_Top", mb_x1, mb_x1 + 0.018, y_start, y_end, 0.38, 0.62, mat_oak_natural)

# D. DECORATIVE ACCESSORIES ON LOWBOARD UNDER SQUARE WINDOW (Window Y: -3.91 to -3.50)
make_cylinder("Salotto_Vaso_Verde_Base", 0.58, -3.80, mb_z_top, mb_z_top + 0.22, 0.09, segments=20, mat=mat_emerald_glass)
make_cylinder("Salotto_Vaso_Verde_Collo", 0.58, -3.80, mb_z_top + 0.22, mb_z_top + 0.34, 0.04, segments=20, mat=mat_emerald_glass)

for li, ly in enumerate([-3.58, -3.42], start=1):
    make_cylinder(f"Salotto_Lampada_Tavolo_Base_{li}", 0.58, ly, mb_z_top, mb_z_top + 0.18, 0.035, segments=16, mat=mat_white_lacquer)
    bm_shade = bmesh.new()
    bmesh.ops.create_cone(bm_shade, cap_ends=True, segments=20, radius1=0.08, radius2=0.03, depth=0.08)
    mesh_shade = bpy.data.meshes.new(f"Salotto_Lampada_Tavolo_Paralume_{li}")
    bm_shade.to_mesh(mesh_shade)
    bm_shade.free()
    obj_shade = bpy.data.objects.new(f"Salotto_Lampada_Tavolo_Paralume_{li}", mesh_shade)
    obj_shade.location = (0.58, ly, mb_z_top + 0.22)
    obj_shade.data.materials.append(mat_white_lacquer)
    col_furniture.objects.link(obj_shade)

# E. SMART TV 65'' (TV_Salotto_Screen & TV_Salotto_Bezel)
# Shifted south (più a sinistra / più giù in Y), centered at Y = -2.65
tv_center_y = -2.65
tv_width = 1.45
tv_height = 0.83
tv_y0 = tv_center_y - tv_width / 2.0 # -3.375
tv_y1 = tv_center_y + tv_width / 2.0 # -1.925
tv_z_bot = mb_z_top + 0.07 # 0.72m
tv_z_top = tv_z_bot + tv_height # 1.55m
tv_x = 0.58

make_box("TV_Salotto_Stand_Base", tv_x - 0.15, tv_x + 0.15, tv_center_y - 0.25, tv_center_y + 0.25, mb_z_top, mb_z_top + 0.015, mat_inox)
make_box("TV_Salotto_Stand_Collo", tv_x - 0.04, tv_x + 0.04, tv_center_y - 0.08, tv_center_y + 0.08, mb_z_top + 0.015, tv_z_bot + 0.10, mat_dark_anthracite)

obj_tv_bezel = make_box("TV_Salotto_Bezel", tv_x - 0.012, tv_x + 0.005, tv_y0 - 0.008, tv_y1 + 0.008, tv_z_bot - 0.008, tv_z_top + 0.008, mat_inox)
obj_tv_screen = make_box("TV_Salotto_Screen", tv_x + 0.004, tv_x + 0.012, tv_y0, tv_y1, tv_z_bot, tv_z_top, mat_black_tv)

for obj_tv, role in [(obj_tv_screen, "tv_display"), (obj_tv_bezel, "tv_frame")]:
    if obj_tv:
        obj_tv["ha_entity"] = "media_player.smart_tv_lg_oled_2"
        obj_tv["ha_action"] = "modal"
        obj_tv["ha_ui_type"] = role
        obj_tv["ha_name"] = "Smart TV LG OLED"

make_box("TV_Salotto_Telecomando", 0.68, 0.73, -2.50, -2.35, mb_z_top, mb_z_top + 0.012, mat_dark_anthracite)

# F. WALL-MOUNTED SHELF UNIT ABOVE TV (Mensola Parete Ovest)
# Centered directly above TV at Y = -2.65: Y from -3.25 to -2.05
sh_y0, sh_y1 = -3.25, -2.05
sh_z0, sh_z1 = 1.78, 2.02
sh_x0, sh_x1 = 0.32, 0.54
make_box("Mensola_Salotto_Fondo", sh_x0, sh_x1, sh_y0, sh_y1, sh_z0, sh_z0 + 0.02, mat_white_lacquer)
make_box("Mensola_Salotto_Schienale", sh_x0, sh_x0 + 0.018, sh_y0, sh_y1, sh_z0, sh_z1, mat_white_lacquer)
make_box("Mensola_Salotto_Fianco_S", sh_x0, sh_x1, sh_y0, sh_y0 + 0.02, sh_z0, sh_z1, mat_white_lacquer)
make_box("Mensola_Salotto_Fianco_N", sh_x0, sh_x1, sh_y1 - 0.02, sh_y1, sh_z0, sh_z1, mat_white_lacquer)
make_box("Mensola_Salotto_Top", sh_x0, sh_x1, sh_y0, sh_y1, sh_z1 - 0.02, sh_z1, mat_white_lacquer)
make_box("Mensola_Salotto_Div_1", sh_x0 + 0.02, sh_x1 - 0.01, -2.85, -2.83, sh_z0 + 0.02, sh_z1 - 0.02, mat_white_lacquer)
make_box("Mensola_Salotto_Div_2", sh_x0 + 0.02, sh_x1 - 0.01, -2.45, -2.43, sh_z0 + 0.02, sh_z1 - 0.02, mat_white_lacquer)
make_box("Mensola_Salotto_Sacchetto_Regalo", 0.36, 0.48, -2.35, -2.15, sh_z0 + 0.02, sh_z0 + 0.18, mat_cardboard)
make_cylinder("Mensola_Salotto_Tazzina_1", 0.42, -2.65, sh_z0 + 0.02, sh_z0 + 0.08, 0.03, segments=12, mat=mat_white_lacquer)
make_cylinder("Mensola_Salotto_Tazzina_2", 0.42, -3.05, sh_z0 + 0.02, sh_z0 + 0.08, 0.03, segments=12, mat=mat_white_lacquer)

# -------------------------------------------------------------
# 5. NORTH WALL & EAST WALL SOFAS, CORNER TABLE, APPLIQUES
# -------------------------------------------------------------
print("Building Sofas & Appliques...")

# North Wall Sofa (Divano_Nord)
# Placed along North wall (Y = -0.30), starting at X = 2.40 to X = 4.60 (width 2.20m).
# Leaves Window 1 (X: 1.35 to 2.27) uncovered on the left!
dn_x0, dn_x1 = 2.40, 4.60
dn_y0, dn_y1 = -1.22, -0.32
dn_seat_h = 0.44
dn_total_h = 0.86

make_beveled_box("Divano_Nord_Struttura", (dn_x0+dn_x1)/2.0, (dn_y0+dn_y1)/2.0, 0.15, (dn_x1-dn_x0), (dn_y1-dn_y0), 0.24, bevel=0.02, mat=mat_sofa_fabric)
make_beveled_box("Divano_Nord_Schienale_Struttura", (dn_x0+dn_x1)/2.0, dn_y1 - 0.12, (dn_seat_h+dn_total_h)/2.0, (dn_x1-dn_x0), 0.22, (dn_total_h-dn_seat_h+0.1), bevel=0.03, mat=mat_sofa_fabric)
make_beveled_box("Divano_Nord_Bracciolo_L", dn_x0 + 0.11, (dn_y0+dn_y1)/2.0, 0.38, 0.20, (dn_y1-dn_y0) - 0.04, 0.32, bevel=0.03, mat=mat_sofa_fabric)
make_beveled_box("Divano_Nord_Bracciolo_R", dn_x1 - 0.11, (dn_y0+dn_y1)/2.0, 0.38, 0.20, (dn_y1-dn_y0) - 0.04, 0.32, bevel=0.03, mat=mat_sofa_fabric)

cushion_w = (dn_x1 - dn_x0 - 0.44) / 3.0
for ci in range(3):
    cx_c = (dn_x0 + 0.22) + (ci + 0.5) * cushion_w
    make_beveled_box(f"Divano_Nord_Seduta_{ci}", cx_c, (dn_y0 + dn_y1)/2.0 - 0.06, dn_seat_h, cushion_w - 0.02, (dn_y1-dn_y0) - 0.24, 0.16, bevel=0.03, mat=mat_sofa_fabric)
    make_beveled_box(f"Divano_Nord_Cuscino_Schienale_{ci}", cx_c, dn_y1 - 0.20, dn_seat_h + 0.22, cushion_w - 0.02, 0.16, 0.36, bevel=0.03, mat=mat_sofa_fabric)

make_box("Divano_Nord_Copridivano", dn_x0 + 0.35, dn_x0 + 1.45, dn_y0 + 0.04, dn_y1 - 0.08, dn_seat_h + 0.08, dn_seat_h + 0.09, mat_throw_blanket)
make_beveled_box("Divano_Nord_Cuscino_Arredo_1", dn_x0 + 0.32, dn_y1 - 0.32, dn_seat_h + 0.14, 0.38, 0.14, 0.34, bevel=0.025, mat=mat_fabric_light)
make_beveled_box("Divano_Nord_Cuscino_Arredo_2", dn_x1 - 0.32, dn_y1 - 0.32, dn_seat_h + 0.14, 0.38, 0.14, 0.34, bevel=0.025, mat=mat_fabric_light)

# Pet Steps / Ramp for dogs (Scaletta per cagnolino under Window 1)
step_x0, step_x1 = 1.70, 2.10
step_y0, step_y1 = -1.15, -0.65
make_box("Scaletta_Cani_Step_1", step_x0, step_x1, -1.15, -0.98, 0.00, 0.14, mat_fabric_light)
make_box("Scaletta_Cani_Step_2", step_x0, step_x1, -0.98, -0.81, 0.00, 0.28, mat_fabric_light)
make_box("Scaletta_Cani_Step_3", step_x0, step_x1, -0.81, -0.65, 0.00, 0.42, mat_fabric_light)

# North Wall Sconce Light (Applique_Salotto_Nord -> light.2)
ap_n_x = 3.13
ap_n_y = -0.30
ap_n_z = 1.95
obj_ap_n = make_box("Applique_Salotto_Nord", ap_n_x - 0.06, ap_n_x + 0.06, ap_n_y, ap_n_y - 0.08, ap_n_z - 0.14, ap_n_z + 0.14, mat_white_lacquer)
make_box("Applique_Salotto_Nord_Diffuser_Top", ap_n_x - 0.05, ap_n_x + 0.05, ap_n_y - 0.01, ap_n_y - 0.07, ap_n_z + 0.14, ap_n_z + 0.155, mat_sconce_emissive)
make_box("Applique_Salotto_Nord_Diffuser_Bot", ap_n_x - 0.05, ap_n_x + 0.05, ap_n_y - 0.01, ap_n_y - 0.07, ap_n_z - 0.155, ap_n_z - 0.14, mat_sconce_emissive)
if obj_ap_n:
    obj_ap_n["ha_entity"] = "light.2"
    obj_ap_n["ha_ui_type"] = "light_emissive"
    obj_ap_n["ha_action"] = "toggle"
    obj_ap_n["ha_name"] = "Applique Salotto Nord"

# Corner Table with blue lamp (NE corner: X ~ 5.65, Y ~ -0.75)
ct_x, ct_y = 5.65, -0.75
make_cylinder("Tavolino_Angolo_Base", ct_x, ct_y, 0.00, 0.02, 0.20, segments=20, mat=mat_white_lacquer)
make_cylinder("Tavolino_Angolo_Fusto", ct_x, ct_y, 0.02, 0.52, 0.018, segments=12, mat=mat_chrome)
make_cylinder("Tavolino_Angolo_Top", ct_x, ct_y, 0.52, 0.55, 0.22, segments=24, mat=mat_glass)

make_cylinder("Lampada_Angolo_Base", ct_x, ct_y, 0.55, 0.68, 0.055, segments=16, mat=mat_blue_ceramic)
make_cylinder("Lampada_Angolo_Stelo", ct_x, ct_y, 0.68, 0.74, 0.008, segments=8, mat=mat_chrome)
bm_lamp_shade = bmesh.new()
bmesh.ops.create_cone(bm_lamp_shade, cap_ends=True, segments=20, radius1=0.08, radius2=0.04, depth=0.12)
mesh_lamp_shade = bpy.data.meshes.new("Lampada_Angolo_Paralume")
bm_lamp_shade.to_mesh(mesh_lamp_shade)
bm_lamp_shade.free()
obj_lamp_shade = bpy.data.objects.new("Lampada_Angolo_Paralume", mesh_lamp_shade)
obj_lamp_shade.location = (ct_x, ct_y, 0.80)
obj_lamp_shade.data.materials.append(mat_white_lacquer)
col_furniture.objects.link(obj_lamp_shade)

# East Wall 2-Seater Sofa (Divano_Est)
de_y0, de_y1 = -3.00, -1.40
de_x0, de_x1 = 5.17, 6.05
de_seat_h = 0.44
de_total_h = 0.86

make_beveled_box("Divano_Est_Struttura", (de_x0+de_x1)/2.0, (de_y0+de_y1)/2.0, 0.15, (de_x1-de_x0), (de_y1-de_y0), 0.24, bevel=0.02, mat=mat_sofa_fabric)
make_beveled_box("Divano_Est_Schienale_Struttura", de_x1 - 0.12, (de_y0+de_y1)/2.0, (de_seat_h+de_total_h)/2.0, 0.22, (de_y1-de_y0), (de_total_h-de_seat_h+0.1), bevel=0.03, mat=mat_sofa_fabric)
make_beveled_box("Divano_Est_Bracciolo_N", (de_x0+de_x1)/2.0, de_y1 - 0.11, 0.38, (de_x1-de_x0) - 0.04, 0.20, 0.32, bevel=0.03, mat=mat_sofa_fabric)
make_beveled_box("Divano_Est_Bracciolo_S", (de_x0+de_x1)/2.0, de_y0 + 0.11, 0.38, (de_x1-de_x0) - 0.04, 0.20, 0.32, bevel=0.03, mat=mat_sofa_fabric)

cushion_e_w = (de_y1 - de_y0 - 0.44) / 2.0
for ci in range(2):
    cy_c = (de_y0 + 0.22) + (ci + 0.5) * cushion_e_w
    make_beveled_box(f"Divano_Est_Seduta_{ci}", (de_x0+de_x1)/2.0 - 0.06, cy_c, de_seat_h, (de_x1-de_x0) - 0.24, cushion_e_w - 0.02, 0.16, bevel=0.03, mat=mat_sofa_fabric)
    make_beveled_box(f"Divano_Est_Cuscino_Schienale_{ci}", de_x1 - 0.20, cy_c, de_seat_h + 0.22, 0.16, cushion_e_w - 0.02, 0.36, bevel=0.03, mat=mat_sofa_fabric)

make_beveled_box("Divano_Est_Cuscino_Arredo_1", de_x1 - 0.32, de_y0 + 0.32, de_seat_h + 0.14, 0.14, 0.38, 0.34, bevel=0.025, mat=mat_fabric_light)
make_beveled_box("Divano_Est_Cuscino_Arredo_2", de_x1 - 0.32, de_y1 - 0.32, de_seat_h + 0.14, 0.14, 0.38, 0.34, bevel=0.025, mat=mat_fabric_light)

# East Wall Sconce Light (Applique_Salotto_Est -> light.1)
ap_e_x = 6.07
ap_e_y = -2.20
ap_e_z = 1.95
obj_ap_e = make_box("Applique_Salotto_Est", ap_e_x - 0.08, ap_e_x, ap_e_y - 0.06, ap_e_y + 0.06, ap_e_z - 0.14, ap_e_z + 0.14, mat_white_lacquer)
make_box("Applique_Salotto_Est_Diffuser_Top", ap_e_x - 0.07, ap_e_x - 0.01, ap_e_y - 0.05, ap_e_y + 0.05, ap_e_z + 0.14, ap_e_z + 0.155, mat_sconce_emissive)
make_box("Applique_Salotto_Est_Diffuser_Bot", ap_e_x - 0.07, ap_e_x - 0.01, ap_e_y - 0.05, ap_e_y + 0.05, ap_e_z - 0.155, ap_e_z - 0.14, mat_sconce_emissive)
if obj_ap_e:
    obj_ap_e["ha_entity"] = "light.1"
    obj_ap_e["ha_ui_type"] = "light_emissive"
    obj_ap_e["ha_action"] = "toggle"
    obj_ap_e["ha_name"] = "Applique Salotto Est"

# -------------------------------------------------------------
# 6. CENTRAL SOLID OAK TABLE (ROTATED 90° - NORTH-SOUTH)
# -------------------------------------------------------------
print("Building Central Solid Oak Table (Rotated 90°: North-South) & Chairs...")

# Long axis is along North-South (Y axis): from Y = -5.80 to Y = -3.15 (Length = 2.65m)
# Width is along East-West (X axis): from X = 2.45 to X = 3.50 (Width = 1.05m)
tx0, tx1 = 2.45, 3.50
ty0, ty1 = -5.80, -3.15
tz_top = 0.76
tz_thick = 0.055

# Natural organic live-edge tabletop slab along the long sides (West edge X=tx0 and East edge X=tx1)
bm_table = bmesh.new()
n_table_segs = 24
west_pts = []
for i in range(n_table_segs + 1):
    u = i / n_table_segs
    y = ty0 + u * (ty1 - ty0)
    x = tx0 + 0.018 * math.sin(u * 2.5 * math.pi) - 0.008 * math.cos(u * 5 * math.pi)
    west_pts.append((x, y))

east_pts = []
for i in range(n_table_segs + 1):
    u = i / n_table_segs
    y = ty1 - u * (ty1 - ty0)
    x = tx1 + 0.015 * math.sin(u * 3 * math.pi + 1.0)
    east_pts.append((x, y))

poly_table = west_pts + east_pts
v_t_bot = [bm_table.verts.new((x, y, tz_top - tz_thick)) for x, y in poly_table]
v_t_top = [bm_table.verts.new((x, y, tz_top)) for x, y in poly_table]

bm_table.faces.new(v_t_bot)
bm_table.faces.new(list(reversed(v_t_top)))
n_poly = len(poly_table)
for i in range(n_poly):
    nxt = (i + 1) % n_poly
    bm_table.faces.new([v_t_bot[i], v_t_bot[nxt], v_t_top[nxt], v_t_top[i]])

bmesh.ops.triangulate(bm_table, faces=[f for f in bm_table.faces if len(f.verts) > 4])
bmesh.ops.recalc_face_normals(bm_table, faces=bm_table.faces)
mesh_table = bpy.data.meshes.new("Tavolo_Salotto_Piano")
bm_table.to_mesh(mesh_table)
bm_table.free()
obj_table = bpy.data.objects.new("Tavolo_Salotto_Piano", mesh_table)
obj_table.data.materials.append(mat_oak_natural)
col_furniture.objects.link(obj_table)

# Heavy Solid Wood Slab Portal Legs across the width (East-West slabs)
# North leg at Y = -3.60, South leg at Y = -5.35
for leg_name, ly in [("Tavolo_Salotto_Gamba_Nord", -3.60), ("Tavolo_Salotto_Gamba_Sud", -5.35)]:
    make_beveled_box(leg_name, (tx0 + tx1)/2.0, ly, (tz_top - tz_thick)/2.0, (tx1 - tx0) - 0.26, 0.11, tz_top - tz_thick, bevel=0.01, mat=mat_oak_natural)

# Laptop and parcel on the table
# Centered on the table, oriented naturally
laptop_cx = (tx0 + tx1) / 2.0
laptop_cy = -4.40
make_box("Tavolo_Laptop_Base", laptop_cx - 0.15, laptop_cx + 0.15, laptop_cy - 0.10, laptop_cy + 0.10, tz_top, tz_top + 0.012, mat_inox)
bm_screen = bmesh.new()
bmesh.ops.create_cube(bm_screen, size=1.0)
bmesh.ops.scale(bm_screen, vec=(0.30, 0.008, 0.20), verts=bm_screen.verts)
bmesh.ops.rotate(bm_screen, cent=(0,0,0), matrix=Matrix.Rotation(math.radians(-25), 3, 'X'))
mesh_screen = bpy.data.meshes.new("Tavolo_Laptop_Schermo")
bm_screen.to_mesh(mesh_screen)
bm_screen.free()
obj_screen = bpy.data.objects.new("Tavolo_Laptop_Schermo", mesh_screen)
obj_screen.location = (laptop_cx, laptop_cy + 0.08, tz_top + 0.10)
obj_screen.data.materials.append(mat_inox)
col_furniture.objects.link(obj_screen)

make_box("Tavolo_Pacco_Cartone", laptop_cx - 0.13, laptop_cx + 0.13, -5.20, -4.95, tz_top, tz_top + 0.14, mat_cardboard)

# -------------------------------------------------------------
# 7. ROBUST CHAIR BUILDER (100% RIGID TRANSFORM, ZERO ROTATION BUGS)
# -------------------------------------------------------------
print("Building Chairs with perfectly aligned rigid geometry...")

def create_chair(name, cx, cy, facing='N'):
    """
    Constructs the entire chair rigidly in local object coordinates:
      - Chair seat center at (0, 0, seat_h)
      - Facing 'N' means sitting person looks +Y, back is at -Y
      - All legs, uprights, rail, and slats are strictly modeled in local coordinates
      - Rotated rigidly as an object by rot_z:
          facing='N' -> rot_z = 0
          facing='S' -> rot_z = 180°
          facing='E' -> rot_z = -90° (looks +X, back at -X)
          facing='W' -> rot_z = +90° (looks -X, back at +X)
    """
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
        
    # 2. Leg Stretchers / Rungs (traversi inferiori)
    # Side rungs (between front and back leg)
    for side_x in [-seat_w/2 + 0.03, seat_w/2 - 0.03]:
        res = bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=(0.014, seat_d - 0.06, 0.014), verts=res['verts'])
        bmesh.ops.translate(bm, vec=(side_x, 0.0, 0.12), verts=res['verts'])
    # Front and back rungs
    res_f = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(seat_w - 0.06, 0.014, 0.014), verts=res_f['verts'])
    bmesh.ops.translate(bm, vec=(0.0, seat_d/2 - 0.03, 0.09), verts=res_f['verts'])
    res_b = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(seat_w - 0.06, 0.014, 0.014), verts=res_b['verts'])
    bmesh.ops.translate(bm, vec=(0.0, -seat_d/2 + 0.03, 0.14), verts=res_b['verts'])

    # 3. Wooden Seat Apron Frame (fascia sotto seduta)
    res_apron = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(seat_w - 0.02, seat_d - 0.02, 0.035), verts=res_apron['verts'])
    bmesh.ops.translate(bm, vec=(0.0, 0.0, seat_h - 0.02), verts=res_apron['verts'])

    # 4. Backrest Uprights (2 vertical posts at back corners)
    for side_x in [-seat_w/2 + 0.03, seat_w/2 - 0.03]:
        res = bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.015, radius2=0.015, depth=back_h - seat_h)
        bmesh.ops.translate(bm, vec=(side_x, back_y, seat_h + (back_h - seat_h) / 2.0), verts=res['verts'])
        
    # 5. Top Horizontal Rail spanning East-West across the two uprights
    # Length along X = seat_w, depth along Y = 0.024, height along Z = 0.065
    res_rail = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(seat_w, 0.024, 0.065), verts=res_rail['verts'])
    bmesh.ops.translate(bm, vec=(0.0, back_y, back_h - 0.032), verts=res_rail['verts'])
    
    # 6. 4 Vertical Slats (doghe) connecting to the top rail
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
    obj_seat.data.materials.append(mat_fabric_light)
    col_furniture.objects.link(obj_seat)
    
    return obj_wood

# Chairs around the rotated table:
# Long side West: 3 chairs facing East towards the table (X = 2.15)
chair_y_positions = [-5.15, -4.48, -3.80]
for i, ypos in enumerate(chair_y_positions, start=1):
    create_chair(f"Sedia_Salotto_W_{i}", 2.15, ypos, facing='E')

# Long side East: 3 chairs facing West towards the table (X = 3.80)
for i, ypos in enumerate(chair_y_positions, start=1):
    create_chair(f"Sedia_Salotto_E_{i}", 3.80, ypos, facing='W')

# Capotavola South: 1 chair facing North towards the table (Y = -6.15)
create_chair("Sedia_Salotto_Capotavola_S", (tx0 + tx1)/2.0, -6.15, facing='N')

# Capotavola North: 1 chair facing South towards the table (Y = -2.80)
create_chair("Sedia_Salotto_Capotavola_N", (tx0 + tx1)/2.0, -2.80, facing='S')

# -------------------------------------------------------------
# 8. CEILING RECESSED SPOTLIGHTS (Faretti incassati a soffitto)
# -------------------------------------------------------------
print("Building Ceiling Recessed Spotlights...")

ceiling_z = 2.82
spot_coords = [
    (1.70, -1.80), (3.20, -1.80), (4.70, -1.80),
    (1.70, -4.70), (3.20, -4.70), (4.70, -4.70)
]

for idx, (sx, sy) in enumerate(spot_coords, start=1):
    make_cylinder(f"Salotto_Faretto_{idx}_Ghiera", sx, sy, ceiling_z - 0.006, ceiling_z, 0.055, segments=16, mat=mat_chrome)
    obj_spot = make_cylinder(f"Salotto_Faretto_{idx}", sx, sy, ceiling_z - 0.008, ceiling_z - 0.004, 0.038, segments=16, mat=mat_spot_emissive)
    if obj_spot:
        obj_spot["ha_entity"] = "light.smart_plug_in_unit_switch_3"
        obj_spot["ha_ui_type"] = "light_emissive"
        obj_spot["ha_action"] = "toggle"
        obj_spot["ha_name"] = f"Faretto Soffitto Salotto {idx}"

# -------------------------------------------------------------
# 9. BLENDER LIGHTS FOR GORGEOUS RENDERS & PREVIEWS
# -------------------------------------------------------------
print("Setting up Blender soft scene lights...")

def create_point_light(name, pos, color, energy, radius=0.25):
    light_data = bpy.data.lights.get(name)
    if not light_data:
        light_data = bpy.data.lights.new(name=name, type='POINT')
    light_data.color = color
    light_data.energy = energy
    light_data.shadow_soft_size = radius
    
    light_obj = bpy.data.objects.get(name)
    if not light_obj:
        light_obj = bpy.data.objects.new(name=name, object_data=light_data)
        col_lights.objects.link(light_obj)
    light_obj.location = Vector(pos)
    return light_obj

create_point_light("Light_Salotto_Faretti_Nord", (3.20, -2.00, 2.65), (1.0, 0.96, 0.90), 80.0, 0.3)
create_point_light("Light_Salotto_Faretti_Sud", (3.20, -4.50, 2.65), (1.0, 0.96, 0.90), 80.0, 0.3)
create_point_light("Light_Salotto_Applique_Nord", (3.13, -0.45, 1.95), (1.0, 0.92, 0.82), 40.0, 0.15)
create_point_light("Light_Salotto_Applique_Est", (5.90, -2.20, 1.95), (1.0, 0.92, 0.82), 40.0, 0.15)
create_point_light("Light_Salotto_Stufa_Fuoco", (st_cx, st_cy, 0.60), (1.0, 0.42, 0.05), 35.0, 0.15)

print("=== Refined Salotto Re-creation (v4) Completed Successfully! ===")
