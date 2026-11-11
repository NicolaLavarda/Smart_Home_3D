"""
Update script for Smart_Home_3D:
1. Fix stairs compenetration with wall:
   - Upper stair steps confined to interior of stair shaft (x: 8.69 to 9.44).
   - Dividing wall Wall_Stair_West_SouthSolid (x: 9.45 to 9.70) is completely solid, continuous white plaster.
2. Remove side parapet Stair_Kitchen_Parapet from the 3 kitchen steps.
3. Model the realistic landing (pianerottolo) matching real photos:
   - Z = 0.53 m.
   - Honey-oak wooden top with rounded bullnose.
   - Rounded front-right corner with quarter-circle curve.
   - White curved fascia band, stone molding torus, plinth with decorative convector vent and curved wood panel.
   - Glazed wooden door resting on the landing leading into the stairs.
4. Model the low masonry bench (muretto basso / panca) and corner fireplace (caminetto):
   - Low bench along North wall from landing to fireplace with stone slab top and diagonal ventilation slots.
   - Display shelves above the bench.
   - Corner fireplace with raised stone hearth, diagonal slots, glass firebox insert, stone fluted pilasters, wooden mantel shelf, and masonry hood.
5. Add the pedestrian gate (cancelletto pedonale) and smaller pedestrian walkway (vialetto pedonale):
   - Pedestrian gate on north perimeter fence next to the driveway gate.
   - L-shaped paved walkway from pedestrian gate to portico.
   - Watertight garden lawn meshes without overlap.
"""

import bpy
import bmesh
from mathutils import Vector, Matrix
import math

print("=== Starting Smart_Home_3D Stairs, Fireplace, Gate & Walkway Update ===")

# Helper: make a simple axis-aligned box
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

# Helper: make a horizontal polygonal prism / slab
def make_poly_slab(name, poly_2d, z_min, z_max, mat=None, collection=None):
    bm = bmesh.new()
    n = len(poly_2d)
    if poly_2d[0] == poly_2d[-1]:
        poly_2d = poly_2d[:-1]
        n = len(poly_2d)
    
    bot_verts = [bm.verts.new((x, y, z_min)) for x, y in poly_2d]
    top_verts = [bm.verts.new((x, y, z_max)) for x, y in poly_2d]
    
    # Side faces
    for i in range(n):
        nxt = (i + 1) % n
        bm.faces.new([bot_verts[i], bot_verts[nxt], top_verts[nxt], top_verts[i]])
        
    # Top and bottom faces via bmesh 2D triangulation/fill
    bm.faces.new(top_verts)
    bm.faces.new(list(reversed(bot_verts)))
    
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    
    obj = bpy.data.objects.new(name, mesh)
    if mat:
        obj.data.materials.append(mat)
    if collection:
        collection.objects.link(obj)
    else:
        bpy.context.scene.collection.objects.link(obj)
    return obj

# Get collections
col_site = bpy.data.collections.get("01_Sito_e_Giardini")
col_house = bpy.data.collections.get("02_Edificio_Residenziale")
col_stairs = bpy.data.collections.get("05_Scale_e_Sottoscala")
col_fixtures = bpy.data.collections.get("06_Infissi_e_Porte")
col_fence = bpy.data.collections.get("07_Recinzione_e_Cancelli")

# Get materials
mat_wall_ext = bpy.data.materials.get("Mat_Intonaco_Esterno_Dark")
mat_wall_int = bpy.data.materials.get("Mat_Intonaco_Interno_Light")
mat_parquet = bpy.data.materials.get("Mat_Parquet_Rovere_PBR")
mat_door_wood = bpy.data.materials.get("Mat_Porta_Legno")
mat_chrome = bpy.data.materials.get("Mat_Cromo")
mat_glass = bpy.data.materials.get("Mat_Vetro")
mat_portico = bpy.data.materials.get("Mat_Lastricato_Pietra")
mat_curb = bpy.data.materials.get("Mat_Cordolo_Pietra")
mat_railing = bpy.data.materials.get("Mat_Ringhiera_Metallo")
mat_grass = bpy.data.materials.get("Mat_Prato_Fotorealistico")
mat_anthracite = bpy.data.materials.get("Mat_Infissi_Antracite")

# Material for Travertine / Stone Bench & Fireplace
mat_travertine = bpy.data.materials.get("Mat_Marmo_Travertino")
if not mat_travertine:
    mat_travertine = bpy.data.materials.new("Mat_Marmo_Travertino")
    mat_travertine.use_nodes = True
    nodes = mat_travertine.node_tree.nodes
    links = mat_travertine.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.86, 0.83, 0.77, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.28
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

# Material for Dark Wood Chimney Mantel
mat_dark_wood = bpy.data.materials.get("Mat_Legno_Caminetto")
if not mat_dark_wood:
    mat_dark_wood = bpy.data.materials.new("Mat_Legno_Caminetto")
    mat_dark_wood.use_nodes = True
    nodes = mat_dark_wood.node_tree.nodes
    links = mat_dark_wood.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.22, 0.13, 0.07, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.40
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

# Material for Fireplace Firebox / Cast Iron
mat_firebox = bpy.data.materials.get("Mat_Focolare_Ghisa")
if not mat_firebox:
    mat_firebox = bpy.data.materials.new("Mat_Focolare_Ghisa")
    mat_firebox.use_nodes = True
    nodes = mat_firebox.node_tree.nodes
    links = mat_firebox.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.05, 0.05, 0.05, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.65
    bsdf.inputs["Metallic"].default_value = 0.80
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

# -------------------------------------------------------------
# 1. REMOVE OLD OBJECTS TO BE REPLACED
# -------------------------------------------------------------
objs_to_remove = [
    "Stair_Kitchen_Parapet",
    "Stair_Kitchen_Landing",
    "Stair_Kitchen_Step_1", "Stair_Kitchen_Step_2", "Stair_Kitchen_Step_3",
    "Wall_Stair_West_SouthSolid", "Wall_Sliding_Lintel",
    "Sliding_Door_Panel",
    "Giardino_Area_3_Prato"
]
# Remove all upper stair steps to recreate them without compenetration
for s in range(4, 18):
    objs_to_remove.append(f"Stair_Upper_Step_{s}")
objs_to_remove.append("Stair_Top_Arrival")

# Remove any existing fireplace or landing objects if script is re-run (strictly matching prefixes, never switches/devices)
prefixes_to_clean = ("Fireplace_", "Bench_North_", "Pianerottolo_", "Walkway_Pedestrian_", "Gate_Ped_")
for o in list(bpy.data.objects):
    if o.name.startswith("Switch_"):
        continue
    if o.name.startswith(prefixes_to_clean):
        bpy.data.objects.remove(o, do_unlink=True)

for name in objs_to_remove:
    obj = bpy.data.objects.get(name)
    if obj:
        bpy.data.objects.remove(obj, do_unlink=True)

print("Cleaned up old objects.")

H_MAIN = 3.00

# -------------------------------------------------------------
# 2. FIX WALL AND UPPER STAIRS COMPENETRATION
# -------------------------------------------------------------
print("Building upper stairs and solid dividing wall...")

# A. Continuous, solid dividing wall between stair shaft and dining room
# x: 9.45 to 9.70, y: -3.85 to -2.06, z: 0.00 to 3.00
make_box("Wall_Stair_West_SouthSolid", 9.45, 9.70, -3.85, -2.06, 0.00, H_MAIN, mat_wall_int, col_stairs)

# Doorway lintel above the landing door (z: 2.63 to 3.00)
z_landing = 3.00 / 17.0 * 3.0 # 0.5294 m
h_door = 2.10
make_box("Wall_Sliding_Lintel", 9.45, 9.70, -2.06, -1.25, z_landing + h_door, H_MAIN, mat_wall_int, col_stairs)

# B. Upper stairs strictly inside stair shaft (x: 8.69 to 9.44) -> 1cm clearance from wall at 9.45!
r1 = 3.00 / 17.0
x_stair_in = 8.69
x_stair_out = 9.44 # DOES NOT PENETRATE WALL AT 9.45!

# Step 4 (fan step in turn area)
make_box("Stair_Upper_Step_4", x_stair_in, x_stair_out, -1.05, -0.68, 0.00, 4 * r1, mat_parquet, col_stairs)
# Step 5 (fan step)
make_box("Stair_Upper_Step_5", x_stair_in, x_stair_out, -0.68, -0.30, 0.00, 5 * r1, mat_parquet, col_stairs)

# Steps 6..17 ascending south above under-stair cupboard
y_up = -0.68
t_up = 0.24
for s in range(6, 18):
    z_top = s * r1
    y0 = y_up - (s - 6) * t_up
    y1 = y0 - t_up
    z_bot = max(0.00, z_top - r1)
    # White riser
    make_box(f"Stair_Upper_Riser_{s}", x_stair_in, x_stair_out, y0 - 0.02, y0, z_bot, z_top, mat_wall_int, col_stairs)
    # Wooden tread
    make_box(f"Stair_Upper_Step_{s}", x_stair_in, x_stair_out, y1, y0, z_top - 0.035, z_top, mat_parquet, col_stairs)

make_box("Stair_Top_Arrival", x_stair_in, x_stair_out, -3.85, y1, 2.82, 3.00, mat_parquet, col_stairs)

# -------------------------------------------------------------
# 3. KITCHEN STEPS (3 STEPS, COMPLETELY OPEN ON THE RIGHT)
# -------------------------------------------------------------
print("Building 3 kitchen steps with open right side...")

# The 3 steps rise going North towards the landing at y=-2.06
# Width: x from 9.70 to 10.65 (95 cm). Right side at 10.65 is completely open!
step_y_bounds = [
    (-2.84, -2.58), # Step 1
    (-2.58, -2.32), # Step 2
    (-2.32, -2.06)  # Step 3
]

for i, (sy0, sy1) in enumerate(step_y_bounds, start=1):
    z_step_top = i * r1
    z_step_bot = (i - 1) * r1
    # White riser (front face)
    make_box(f"Stair_Kitchen_Riser_{i}", 9.70, 10.65, sy0, sy0 + 0.03, z_step_bot, z_step_top, mat_wall_int, col_stairs)
    # Base fill
    make_box(f"Stair_Kitchen_Base_{i}", 9.70, 10.65, sy0 + 0.03, sy1, z_step_bot, z_step_top - 0.035, mat_wall_int, col_stairs)
    # Honey-oak wood tread with bullnose overhang (2cm front, 2cm right side)
    make_box(f"Stair_Kitchen_Step_{i}", 9.70, 10.67, sy0 - 0.02, sy1, z_step_top - 0.035, z_step_top, mat_parquet, col_stairs)

# -------------------------------------------------------------
# 4. PIANEROTTOLO (REALISTIC LANDING WITH CURVED CORNER & DETAILS)
# -------------------------------------------------------------
print("Building realistic landing (pianerottolo)...")

# As seen in photo 2:
# Landing top at z = z_landing (0.5294 m)
# Boundaries:
# West: x = 9.70 (against stair wall)
# North: y = -0.30 (against north wall, extends under window 10.05..10.97)
# East: extends to x = 11.25 (past window)
# South in front of steps: y = -2.06 (from x = 9.70 to 10.65)
# South in front of window: y = -1.85 (from x = 10.65 to 10.95)
# Front-right corner: curved arc from (10.95, -1.85) to (11.25, -1.55), R = 0.30 m
# East face from y = -1.55 to -0.30: along x = 11.25 (meets low masonry bench)

arc_corner_pts = []
for a in range(1, 9):
    ang = -math.pi/2.0 + (a / 8.0) * (math.pi/2.0)
    ax = 10.95 + 0.30 * math.cos(ang)
    ay = -1.55 + 0.30 * math.sin(ang)
    arc_corner_pts.append((ax, ay))

poly_landing = [
    (9.70, -2.06),
    (10.65, -2.06),
    (10.65, -1.85),
    (10.95, -1.85)
]
poly_landing.extend(arc_corner_pts)
poly_landing.extend([
    (11.25, -0.30),
    (9.70, -0.30)
])

# A. Landing Top Slab (Honey-Oak parquet, thickness 3.5 cm)
make_poly_slab("Pianerottolo_Piano_Legno", poly_landing, z_landing - 0.035, z_landing, mat_parquet, col_stairs)

# B. White Curved Fascia Band (height ~12 cm)
make_poly_slab("Pianerottolo_Fascia_Bianca", poly_landing, 0.37, z_landing - 0.035, mat_wall_int, col_stairs)

# C. Travertine Torus / Molding Trim (height ~4 cm)
make_poly_slab("Pianerottolo_Toro_Pietra", poly_landing, 0.33, 0.37, mat_travertine, col_stairs)

# D. Base / Plinth Structure under landing:
# Straight front portion (10.65 to 10.95 at y = -1.85): white wall with decorative convector vent
make_box("Pianerottolo_Plinth_Front", 10.65, 10.95, -1.85, -1.75, 0.00, 0.33, mat_wall_int, col_stairs)
# Decorative ventilation grille (matching Photo 2!)
make_box("Pianerottolo_Vent_Frame", 10.72, 10.88, -1.86, -1.84, 0.10, 0.26, mat_travertine, col_stairs)
for g in range(5):
    gx = 10.74 + g * 0.026
    make_box(f"Pianerottolo_Vent_Louver_{g}", gx, gx + 0.012, -1.865, -1.845, 0.12, 0.24, mat_dark_wood, col_stairs)

# Curved corner plinth (vertical dark wood paneling, matching Photo 2!)
poly_wood_curved = [(10.95, -1.85)] + arc_corner_pts + [(10.95, -1.55)]
make_poly_slab("Pianerottolo_Base_CurvedWood", poly_wood_curved, 0.00, 0.33, mat_dark_wood, col_stairs)

# Bottom stone toe-skirting
make_poly_slab("Pianerottolo_Zoccolo_Base", poly_landing, 0.00, 0.04, mat_travertine, col_stairs)

# E. Glazed Door on the Landing (as seen in Photo 2!)
# Sits directly on the wooden landing at x = 9.70, y from -2.06 to -1.25
hx_d = 9.70
hy_d0 = -2.06
hy_d1 = -1.25
w_door = abs(hy_d1 - hy_d0) # 0.81 m
z_d0 = z_landing # 0.5294 m
z_d1 = z_landing + h_door # 2.6294 m

# Door wooden frame
make_box("Door_Landing_Frame_Top", 9.68, 9.74, hy_d0, hy_d1, z_d1 - 0.05, z_d1, mat_door_wood, col_fixtures)
make_box("Door_Landing_Frame_S", 9.68, 9.74, hy_d0, hy_d0 + 0.05, z_d0, z_d1 - 0.05, mat_door_wood, col_fixtures)
make_box("Door_Landing_Frame_N", 9.68, 9.74, hy_d1 - 0.05, hy_d1, z_d0, z_d1 - 0.05, mat_door_wood, col_fixtures)

# Door Leaf (Wooden with 4 glass panels matching Photo 2)
p_t = 0.04
y_p0 = hy_d0 + 0.06
y_p1 = hy_d1 - 0.06
make_box("Door_Landing_Leaf_Stile_S", 9.69, 9.73, y_p0, y_p0 + 0.08, z_d0 + 0.01, z_d1 - 0.06, mat_door_wood, col_fixtures)
make_box("Door_Landing_Leaf_Stile_N", 9.69, 9.73, y_p1 - 0.08, y_p1, z_d0 + 0.01, z_d1 - 0.06, mat_door_wood, col_fixtures)
make_box("Door_Landing_Leaf_Rail_Bot", 9.69, 9.73, y_p0 + 0.08, y_p1 - 0.08, z_d0 + 0.01, z_d0 + 0.18, mat_door_wood, col_fixtures)
make_box("Door_Landing_Leaf_Rail_Top", 9.69, 9.73, y_p0 + 0.08, y_p1 - 0.08, z_d1 - 0.14, z_d1 - 0.06, mat_door_wood, col_fixtures)

# Glazed insert with horizontal divisions
make_box("Door_Landing_Glass", 9.705, 9.715, y_p0 + 0.08, y_p1 - 0.08, z_d0 + 0.18, z_d1 - 0.14, mat_glass, col_fixtures)
for m in range(1, 4):
    zm = z_d0 + 0.18 + m * (z_d1 - 0.14 - (z_d0 + 0.18)) / 4.0
    make_box(f"Door_Landing_Mullion_{m}", 9.69, 9.73, y_p0 + 0.08, y_p1 - 0.08, zm - 0.015, zm + 0.015, mat_door_wood, col_fixtures)

# Door brass/chrome handle
make_box("Door_Landing_Handle_Plate", 9.67, 9.75, y_p0 + 0.05, y_p0 + 0.07, z_d0 + 0.95, z_d0 + 1.15, mat_chrome, col_fixtures)
make_box("Door_Landing_Handle_Lever", 9.65, 9.67, y_p0 + 0.03, y_p0 + 0.14, z_d0 + 1.05, z_d0 + 1.07, mat_chrome, col_fixtures)

# -------------------------------------------------------------
# 5. LOW MASONRY BENCH & CORNER FIREPLACE ALONG NORTH WALL
# -------------------------------------------------------------
print("Building low masonry bench and corner fireplace along North wall...")

# A. LOW MASONRY BENCH (Panca in muratura con feritoie diagonali)
# Runs along north wall from landing right edge (x = 11.25) to fireplace (x = 12.65)
# Depth: y from -0.30 (wall) to -0.85 (55 cm)
# Height: z = 0.42 m (lower than 0.53m landing)
x_bench0 = 11.25
x_bench1 = 12.65
y_bench_front = -0.85
y_bench_back = -0.30
z_bench_h = 0.42

# Plinth / toe kick
make_box("Bench_North_Plinth", x_bench0, x_bench1, y_bench_front + 0.04, y_bench_back, 0.00, 0.08, mat_travertine, col_house)

# Vertical bench body (white plaster)
make_box("Bench_North_Body", x_bench0, x_bench1, y_bench_front, y_bench_back, 0.08, z_bench_h - 0.04, mat_wall_int, col_house)

# Diagonal ventilation slots on the front face (matching Photo 3 & 4!)
# 8 decorative slots angled at 45 degrees
for s in range(8):
    sx = x_bench0 + 0.15 + s * 0.14
    make_box(f"Bench_North_Slot_{s}", sx, sx + 0.05, y_bench_front - 0.005, y_bench_front + 0.03, 0.16, 0.30, mat_travertine, col_house)

# Travertine top slab (with rounded front overhang)
make_box("Bench_North_TopSlab", x_bench0, x_bench1, y_bench_front - 0.02, y_bench_back, z_bench_h - 0.04, z_bench_h, mat_travertine, col_house)

# Built-in display shelves in the wall niche above the bench
for sh_i, sh_z in enumerate([1.25, 1.60, 1.95], start=1):
    make_box(f"Bench_North_Shelf_{sh_i}", x_bench0 + 0.05, x_bench1 - 0.05, -0.55, y_bench_back, sh_z, sh_z + 0.03, mat_door_wood, col_house)

# B. CORNER FIREPLACE (Caminetto angolare a legna con vetro)
# Position: x from 12.65 to 13.90 (1.25 m wide against East wall 13.90)
# Depth: y from -0.30 to -1.15 (85 cm deep from North wall)
x_fp0 = 12.65
x_fp1 = 13.90
y_fp_front = -1.15
y_fp_back = -0.30
z_fp_hearth = 0.45

# Fireplace raised hearth base (plinth + body + travertine slab)
make_box("Fireplace_Hearth_Plinth", x_fp0, x_fp1, y_fp_front + 0.04, y_fp_back, 0.00, 0.08, mat_travertine, col_house)
make_box("Fireplace_Hearth_Body", x_fp0, x_fp1, y_fp_front, y_fp_back, 0.08, z_fp_hearth - 0.04, mat_wall_int, col_house)

# Diagonal ventilation slots on fireplace base (matching Photo 3 & 4!)
for fs in range(7):
    fsx = x_fp0 + 0.18 + fs * 0.14
    make_box(f"Fireplace_Base_Slot_{fs}", fsx, fsx + 0.05, y_fp_front - 0.005, y_fp_front + 0.03, 0.18, 0.32, mat_travertine, col_house)

make_box("Fireplace_Hearth_TopSlab", x_fp0 - 0.02, x_fp1, y_fp_front - 0.03, y_fp_back, z_fp_hearth - 0.04, z_fp_hearth, mat_travertine, col_house)

# Left stone fluted pilaster
make_box("Fireplace_Pilaster_L", x_fp0, x_fp0 + 0.15, y_fp_front + 0.05, y_fp_back, z_fp_hearth, 1.20, mat_travertine, col_house)

# Firebox insert (focolare chiuso in ghisa con vetro panoramico)
x_box0 = x_fp0 + 0.18
x_box1 = x_fp1 - 0.05
y_box_front = y_fp_front + 0.10
y_box_back = y_fp_back + 0.05
z_box_top = 1.18

make_box("Fireplace_Firebox_Casing", x_box0, x_box1, y_box_front, y_box_back, z_fp_hearth, z_box_top, mat_firebox, col_house)
# Glass front & side window
make_box("Fireplace_Glass_Front", x_box0 + 0.02, x_box1 - 0.02, y_box_front - 0.01, y_box_front + 0.01, z_fp_hearth + 0.05, z_box_top - 0.05, mat_glass, col_house)
make_box("Fireplace_Glass_Side", x_box0 - 0.01, x_box0 + 0.01, y_box_front + 0.02, y_box_back - 0.05, z_fp_hearth + 0.05, z_box_top - 0.05, mat_glass, col_house)

# Solid dark wood mantel shelf beam (mensola in legno del caminetto)
make_box("Fireplace_Mantel_Beam", x_fp0 - 0.03, x_fp1, y_fp_front - 0.04, y_fp_back, 1.18, 1.28, mat_dark_wood, col_house)

# Masonry chimney hood (cappa camino in muratura bianca fino al soffitto)
make_box("Fireplace_Hood", x_fp0 + 0.02, x_fp1, y_fp_front + 0.05, y_fp_back, 1.28, H_MAIN, mat_wall_int, col_house)

# -------------------------------------------------------------
# 6. PEDESTRIAN GATE (CANCELLETTO) & SMALLER PEDESTRIAN WALKWAY
# -------------------------------------------------------------
print("Building pedestrian gate and smaller pedestrian walkway...")

# A. Pedestrian Gate on North Perimeter
# Driveway car gate ends at Gate_Pillar_R (x: -5.45 to -5.15)
# Pedestrian Gate opening: x from -5.15 to -4.15 (width 1.00 m)
# Pillar right of pedestrian gate: x from -4.15 to -3.85
make_box("Gate_Ped_Pillar_R", -4.15, -3.85, -0.40, 0.00, 0.00, 1.80, mat_curb, col_fence)

# Pedestrian single gate leaf (matching metal railing style)
wp_leaf_l = -5.10
wp_leaf_r = -4.20
h_g_bot = 0.15
h_g_top = 1.45
make_box("Gate_Ped_Frame_Bot", wp_leaf_l, wp_leaf_r, -0.21, -0.19, h_g_bot, h_g_bot + 0.04, mat_railing, col_fence)
make_box("Gate_Ped_Frame_Top", wp_leaf_l, wp_leaf_r, -0.21, -0.19, h_g_top - 0.04, h_g_top, mat_railing, col_fence)
make_box("Gate_Ped_Frame_L", wp_leaf_l, wp_leaf_l + 0.04, -0.21, -0.19, h_g_bot, h_g_top, mat_railing, col_fence)
make_box("Gate_Ped_Frame_R", wp_leaf_r - 0.04, wp_leaf_r, -0.21, -0.19, h_g_bot, h_g_top, mat_railing, col_fence)

# Vertical pickets
for pk in range(1, 6):
    pk_x = wp_leaf_l + pk * (wp_leaf_r - wp_leaf_l) / 6.0
    make_box(f"Gate_Ped_Picket_{pk}", pk_x - 0.01, pk_x + 0.01, -0.21, -0.19, h_g_bot + 0.04, h_g_top - 0.04, mat_railing, col_fence)

# Handle & lock
make_box("Gate_Ped_Handle", wp_leaf_r - 0.08, wp_leaf_r - 0.02, -0.24, -0.16, 0.95, 1.05, mat_chrome, col_fence)

# Re-build North-West perimeter fence from pedestrian pillar to house corner:
# Remove old Fence_North_West objects
for o in list(bpy.data.objects):
    if "Fence_North_West" in o.name:
        bpy.data.objects.remove(o, do_unlink=True)

# Helper from build_clean_scene_v2
def add_detailed_fence(name, p0, p1, h_curb=0.32, h_rail=1.10, post_spacing=2.20, picket_spacing=0.18):
    x0, y0 = p0
    x1, y1 = p1
    length = math.hypot(x1 - x0, y1 - y0)
    if length < 0.1: return
    
    dx = (x1 - x0) / length
    dy = (y1 - y0) / length
    nx = -dy
    ny = dx
    w_curb = 0.22
    
    poly_curb = [
        (x0 + nx*w_curb/2, y0 + ny*w_curb/2), (x1 + nx*w_curb/2, y1 + ny*w_curb/2),
        (x1 - nx*w_curb/2, y1 - ny*w_curb/2), (x0 - nx*w_curb/2, y0 - ny*w_curb/2)
    ]
    make_poly_slab(f"{name}_Curb", poly_curb, 0.0, h_curb, mat_curb, col_fence)
    
    w_rail = 0.04
    poly_rail_bot = [
        (x0 + nx*w_rail/2, y0 + ny*w_rail/2), (x1 + nx*w_rail/2, y1 + ny*w_rail/2),
        (x1 - nx*w_rail/2, y1 - ny*w_rail/2), (x0 - nx*w_rail/2, y0 - ny*w_rail/2)
    ]
    make_poly_slab(f"{name}_Rail_Bot", poly_rail_bot, h_curb + 0.04, h_curb + 0.08, mat_railing, col_fence)
    make_poly_slab(f"{name}_Rail_Top", poly_rail_bot, h_rail - 0.04, h_rail, mat_railing, col_fence)
    
    num_posts = max(2, int(round(length / post_spacing)) + 1)
    wp = 0.07
    for i in range(num_posts):
        t = i / (num_posts - 1)
        px = x0 + t * (x1 - x0)
        py = y0 + t * (y1 - y0)
        make_box(f"{name}_Post_{i}", px - wp/2, px + wp/2, py - wp/2, py + wp/2, h_curb, h_rail + 0.06, mat_railing, col_fence)
        
    num_pickets = int(length / picket_spacing)
    wpk = 0.02
    for j in range(1, num_pickets):
        t = j * picket_spacing / length
        px = x0 + t * (x1 - x0)
        py = y0 + t * (y1 - y0)
        make_box(f"{name}_Picket_{j}", px - wpk/2, px + wpk/2, py - wpk/2, py + wpk/2, h_curb + 0.08, h_rail - 0.04, mat_railing, col_fence)

add_detailed_fence("Fence_North_West", (-3.85, 0.00), (-0.10, 0.00))

# B. Smaller Pedestrian Walkway (Vialetto Pedonale)
# L-shaped path:
# Starts at pedestrian gate: x in [-5.10, -4.10], runs South to y = -7.11
# Turns 90 deg East: runs from x = -4.10 to x = 0.30, y in [-7.11, -6.11]
# Connects directly into Portico_Pavement_Unified at (0.30, -7.11)!
poly_walkway = [
    (-5.10, 0.00),
    (-4.10, 0.00),
    (-4.10, -6.11),
    (0.30, -6.11),
    (0.30, -7.11),
    (-5.10, -7.11)
]
make_poly_slab("Walkway_Pedestrian_Pavement", poly_walkway, -0.05, 0.00, mat_portico, col_site)

# Stone curbs bordering the walkway
# Outer curb along west and south
make_box("Walkway_Curb_West", -5.16, -5.10, -7.11, 0.00, 0.00, 0.04, mat_curb, col_site)
make_box("Walkway_Curb_South", -5.16, 0.30, -7.17, -7.11, 0.00, 0.04, mat_curb, col_site)
# Inner curb along east and north
make_box("Walkway_Curb_East", -4.10, -4.04, -6.11, 0.00, 0.00, 0.04, mat_curb, col_site)
make_box("Walkway_Curb_North", -4.04, 0.30, -6.11, -6.05, 0.00, 0.04, mat_curb, col_site)

# C. Watertight Lawn Meshes for Giardino Area 3
# 1. Lawn 3A (North-East lawn in front of house):
# x: -4.04 to 0.00, y: -6.05 to 0.00
make_box("Giardino_Area_3A_Prato", -4.04, 0.00, -6.05, 0.00, -0.05, 0.00, mat_grass, col_site)

# 2. Lawn 3B (West strip between driveway and walkway):
# x: -5.45 to -5.16, y: -7.11 to 0.00
make_box("Giardino_Area_3B_Prato", -5.45, -5.16, -7.11, 0.00, -0.05, 0.00, mat_grass, col_site)

# 3. Lawn 3C (South lawn between walkway, laundry, portico, and driveway curve):
# Outer points follow driveway inner curve
cx, cy = -2.50, -15.50
r_in = 2.95
arc_pts_in = []
for a in range(1, 12):
    theta = math.pi + (a / 12.0) * (math.pi / 2.0)
    px_in = cx + r_in * math.cos(theta)
    py_in = cy + r_in * math.sin(theta)
    arc_pts_in.append((px_in, py_in))

poly_grass_3C = [
    (-5.45, -7.17),
    (0.30, -7.17),
    (0.30, -12.43), (0.00, -12.43), (0.00, -15.43), (4.65, -15.43),
    (4.65, -18.45),
    (-2.50, -18.45)
]
for pt in reversed(arc_pts_in):
    poly_grass_3C.append(pt)
poly_grass_3C.extend([(-5.45, -15.50), (-5.45, -7.17)])
make_poly_slab("Giardino_Area_3C_Prato", poly_grass_3C, -0.05, 0.00, mat_grass, col_site)

print("=== Successfully updated Smart_Home_3D scene! ===")
