"""
Script to refine Bagno + Antibagno + Sgabuzzino + Scale:
- Bagno: South wall is completely solid, door is on the East wall to Antibagno.
- Antibagno: Accessible from Cucina via South door (76cm, 0|213).
- Sgabuzzino Sottoscala: North wall of Antibagno has a 2-door cupboard under the stairs.
- Scala Cucina: 3 steps rising North to an intermediate landing (Z=0.53m).
- Porta Scorrevole: In the dividing wall, a pocket sliding door connecting landing to upper stair.
- Scalinata Superiore: Above the sgabuzzino, ascending from landing to upper floor (Z=3.00m).
"""

import bpy
import bmesh
from mathutils import Vector, Matrix
import math

print("=== Updating Bagno, Antibagno, Sgabuzzino, and Scale ===")

# Helpers
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

# Get collections
col_walls = bpy.data.collections.get("01_Pareti")
col_floors = bpy.data.collections.get("02_Pavimenti_e_Giardini")
col_fixtures = bpy.data.collections.get("03_Infissi_Porte_Garage")
col_stairs = bpy.data.collections.get("04_Scale")
col_furniture = bpy.data.collections.get("05_Arredi_Sanitari")

# Materials
mat_wall_ext = bpy.data.materials.get("Mat_Muro_Esterno_Dark")
mat_wall_int = bpy.data.materials.get("Mat_Muro_Interno_Light")
mat_stairs = bpy.data.materials.get("Mat_Scale_Legno")
mat_door_wood = bpy.data.materials.get("Mat_Legno_Porta")
mat_chrome = bpy.data.materials.get("Mat_Cromo")
mat_tile = bpy.data.materials.get("Mat_Gres_Bagno")
mat_white_wood = bpy.data.materials.get("Mat_Muro_Interno_Light")

# 1. Remove old objects related to stairs, old bathroom south door, old stair walls
old_names = [
    "Wall_Bath_South_Solid", "Wall_Bath_South_Lintel", "Door_Bathroom", "Door_Bathroom_Panel", "Door_Bathroom_Handle",
    "Door_Bagno", "Door_Bagno_Panel", "Door_Bagno_Handle",
    "Wall_Stair_West", "Wall_Stair_East", "Wall_Stair_Door_Lintel", "Wall_Stair_Door_Post",
    "Door_Scala", "Door_Scala_Panel", "Door_Scala_Handle",
    "Door_Stair", "Door_Stair_Panel", "Door_Stair_Handle",
    "Stair_Landing", "Floor_Stair", "Floor_Scala"
]
for i in range(1, 25):
    old_names.extend([f"Stair_Step_1_{i}", f"Stair_Step_2_{i}", f"Stair_Tread_{i}"])

for name in old_names:
    obj = bpy.data.objects.get(name)
    if obj:
        bpy.data.objects.remove(obj, do_unlink=True)

# Also remove any leftover children panels or handles
for obj in list(bpy.data.objects):
    if "Door_Bagno" in obj.name or "Door_Scala" in obj.name or "Stair_Tread" in obj.name:
        bpy.data.objects.remove(obj, do_unlink=True)

H_MAIN = 3.00

# -------------------------------------------------------------
# A. PARETE SUD BAGNO: COMPLETAMENTE SOLIDA E CONTINUA
# x: 6.37 a 8.46, y: -3.85 a -3.56, H = 3.00 m
# -------------------------------------------------------------
make_box("Wall_Bath_South_Solid", 6.37, 8.46, -3.85, -3.56, 0.0, H_MAIN, mat_wall_int, col_walls)

# -------------------------------------------------------------
# B. PARETE DIVISORIA BAGNO / ANTIBAGNO E SCALA (x: 8.46 a 8.69)
# y da -3.85 a -0.30
# Contiene la porta del Bagno da y=-3.56 a -2.76 (larghezza 80 cm, h 2.13 m)
# -------------------------------------------------------------
# Giunzione Sud (da -3.85 a -3.56)
make_box("Wall_Bath_East_Junction", 8.46, 8.69, -3.85, -3.56, 0.0, H_MAIN, mat_wall_int, col_walls)
# Lintel porta Bagno (da -3.56 a -2.76, z da 2.13 a 3.00)
make_box("Wall_Bath_Door_Lintel", 8.46, 8.69, -3.56, -2.76, 2.13, H_MAIN, mat_wall_int, col_walls)
# Muro solido a nord della porta del Bagno (da -2.76 a -0.30)
make_box("Wall_Bath_East_NorthSolid", 8.46, 8.69, -2.76, -0.30, 0.0, H_MAIN, mat_wall_int, col_walls)

# Porta a battente del Bagno che si apre verso l'interno del bagno (angolo -50 gradi)
# Cerniera a (8.46, -3.56)
rad_bath = math.radians(-50.0)
p_w_bath = 0.74
p_h_bath = 2.08
p_t_bath = 0.04
hx_b = 8.52
hy_b = -3.56
# Frame
make_box("Door_Bagno_Frame_Top", 8.44, 8.71, -3.56, -2.76, 2.08, 2.13, mat_door_wood, col_fixtures)
make_box("Door_Bagno_Frame_S", 8.44, 8.71, -3.56, -3.51, 0.0, 2.08, mat_door_wood, col_fixtures)
make_box("Door_Bagno_Frame_N", 8.44, 8.71, -2.81, -2.76, 0.0, 2.08, mat_door_wood, col_fixtures)

# Anta
c_loc_b = [(-p_t_bath/2, 0), (p_t_bath/2, 0), (p_t_bath/2, p_w_bath), (-p_t_bath/2, p_w_bath)]
c_rot_b = [(hx_b + x*math.cos(rad_bath) - y*math.sin(rad_bath), hy_b + x*math.sin(rad_bath) + y*math.cos(rad_bath)) for x, y in c_loc_b]
mesh_b = bpy.data.meshes.new("Door_Bagno_Panel")
verts_b = [(c_rot_b[0][0], c_rot_b[0][1], 0.0), (c_rot_b[1][0], c_rot_b[1][1], 0.0),
           (c_rot_b[2][0], c_rot_b[2][1], 0.0), (c_rot_b[3][0], c_rot_b[3][1], 0.0),
           (c_rot_b[0][0], c_rot_b[0][1], p_h_bath), (c_rot_b[1][0], c_rot_b[1][1], p_h_bath),
           (c_rot_b[2][0], c_rot_b[2][1], p_h_bath), (c_rot_b[3][0], c_rot_b[3][1], p_h_bath)]
faces_b = [(0,3,2,1), (4,5,6,7), (0,1,5,4), (1,2,6,5), (2,3,7,6), (3,0,4,7)]
mesh_b.from_pydata(verts_b, [], faces_b)
mesh_b.update()
obj_b = bpy.data.objects.new("Door_Bagno_Panel", mesh_b)
obj_b.data.materials.append(mat_door_wood)
col_fixtures.objects.link(obj_b)

# -------------------------------------------------------------
# C. PORTA DI INGRESSO DA CUCINA AD ANTIBAGNO
# In parete Sud antibagno: x da 8.69 a 9.45 (larghezza 76 cm, 0|213)
# -------------------------------------------------------------
make_box("Wall_Antibagno_South_Lintel", 8.69, 9.45, -3.85, -3.56, 2.13, H_MAIN, mat_wall_int, col_walls)

# Telaio
make_box("Door_Anti_Frame_Top", 8.69, 9.45, -3.73, -3.63, 2.08, 2.13, mat_door_wood, col_fixtures)
make_box("Door_Anti_Frame_L", 8.69, 8.74, -3.73, -3.63, 0.0, 2.08, mat_door_wood, col_fixtures)
make_box("Door_Anti_Frame_R", 9.40, 9.45, -3.73, -3.63, 0.0, 2.08, mat_door_wood, col_fixtures)

# Anta che si apre verso l'interno dell'antibagno (a battente contro la parete destra)
# Cerniera a destra (x=9.40, y=-3.68), swing angolo +65 gradi verso nord-ovest
rad_anti = math.radians(65.0)
p_w_anti = 0.66
p_h_anti = 2.08
p_t_anti = 0.04
hx_a = 9.40
hy_a = -3.68
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
obj_a.data.materials.append(mat_door_wood)
col_fixtures.objects.link(obj_a)

# Pavimento antibagno (piastrelle in continuità con bagno)
make_box("Floor_Antibagno", 8.69, 9.45, -3.56, -2.06, -0.06, 0.00, mat_tile, col_floors)

# -------------------------------------------------------------
# D. RIPOSTIGLIO SOTTOSCALA A DUE ANTE (A Nord dell'Antibagno)
# y a circa -2.06, larghezza da x=8.69 a 9.45 (76 cm)
# Ante alte circa 1.45 m sotto l'inclinazione della scala
# -------------------------------------------------------------
h_cupboard = 1.45
# Telaio armadio sottoscala
make_box("Cupboard_Frame_Top", 8.69, 9.45, -2.10, -2.06, h_cupboard - 0.04, h_cupboard, mat_door_wood, col_furniture)
make_box("Cupboard_Frame_L", 8.69, 8.73, -2.10, -2.06, 0.0, h_cupboard, mat_door_wood, col_furniture)
make_box("Cupboard_Frame_R", 9.41, 9.45, -2.10, -2.06, 0.0, h_cupboard, mat_door_wood, col_furniture)

# Anta Sinistra (semi-aperta a 20 gradi)
w_door_cup = (0.76 - 0.08) / 2.0 # 34 cm
rad_cup_l = math.radians(20.0)
hx_cl = 8.73
hy_cl = -2.08
make_box("Cupboard_Door_L", hx_cl, hx_cl + w_door_cup, -2.10, -2.06, 0.02, h_cupboard - 0.02, mat_door_wood, col_furniture)
make_box("Cupboard_Handle_L", hx_cl + w_door_cup - 0.04, hx_cl + w_door_cup - 0.02, -2.12, -2.10, 0.85, 0.95, mat_chrome, col_furniture)

# Anta Destra
hx_cr = 8.73 + w_door_cup
make_box("Cupboard_Door_R", hx_cr, hx_cr + w_door_cup, -2.10, -2.06, 0.02, h_cupboard - 0.02, mat_door_wood, col_furniture)
make_box("Cupboard_Handle_R", hx_cr + 0.02, hx_cr + 0.04, -2.12, -2.10, 0.85, 0.95, mat_chrome, col_furniture)

# Muretto o chiusura tamponamento sopra l'armadio sottoscala
make_box("Cupboard_Wall_Above", 8.69, 9.45, -2.10, -2.06, h_cupboard, 1.80, mat_wall_int, col_walls)

# -------------------------------------------------------------
# E. MURO DIVISORIO CON SCRIGNO E PORTA SCORREVOLE
# x da 9.45 a 9.70 (spessore 25 cm)
# -------------------------------------------------------------
# Tronco Sud fino a y=-2.06 (H = 3.00 m)
make_box("Wall_Stair_West_SouthSolid", 9.45, 9.70, -3.85, -2.06, 0.0, H_MAIN, mat_wall_int, col_walls)

# Vano passaggio porta scorrevole da y=-2.06 a -1.25 (larghezza 81 cm)
# La soglia della porta scorrevole è a livello del pianerottolo (z = 0.53 m!)
z_landing = 3 * (3.00 / 17.0) # ~ 0.53 m
h_sliding_door = 2.10
# Architrave sopra la porta scorrevole
make_box("Wall_Sliding_Door_Lintel", 9.45, 9.70, -2.06, -1.25, z_landing + h_sliding_door, H_MAIN, mat_wall_int, col_walls)

# Parete a Nord dove alloggia lo scrigno/tasca (da y=-1.25 a -0.30)
# Struttura cava per la porta a scomparsa
make_box("Wall_Pocket_WestFace", 9.45, 9.50, -1.25, -0.30, 0.0, H_MAIN, mat_wall_int, col_walls)
make_box("Wall_Pocket_EastFace", 9.65, 9.70, -1.25, -0.30, 0.0, H_MAIN, mat_wall_int, col_walls)
make_box("Wall_Pocket_Header", 9.45, 9.70, -1.25, -0.30, z_landing + h_sliding_door, H_MAIN, mat_wall_int, col_walls)

# Pannello Porta Scorrevole (Wood door panel, parzialmente estratta di 45 cm dal cassonetto)
make_box("Sliding_Door_Panel", 9.53, 9.58, -1.75, -0.95, z_landing + 0.02, z_landing + h_sliding_door - 0.02, mat_door_wood, col_fixtures)
make_box("Sliding_Door_Handle", 9.51, 9.60, -1.70, -1.67, z_landing + 0.95, z_landing + 1.10, mat_chrome, col_fixtures)

# -------------------------------------------------------------
# F. SCALA IN CUCINA: 3 GRADINI + PIANEROTTOLO (Rampa 1)
# Larghezza scala in cucina: x da 9.70 a 10.65 (95 cm)
# -------------------------------------------------------------
riser_1 = 3.00 / 17.0 # ~ 0.176 m
tread_1 = 0.26

# Gradino 1
make_box("Stair_Kitchen_Step_1", 9.70, 10.65, -2.84, -2.58, 0.0, riser_1, mat_stairs, col_stairs)
# Gradino 2
make_box("Stair_Kitchen_Step_2", 9.70, 10.65, -2.58, -2.32, 0.0, 2 * riser_1, mat_stairs, col_stairs)
# Gradino 3
make_box("Stair_Kitchen_Step_3", 9.70, 10.65, -2.32, -2.06, 0.0, 3 * riser_1, mat_stairs, col_stairs)

# Pianerottolo (Landing 1 a z = 0.53 m)
# da y=-2.06 a -1.05 (profondità 101 cm, larghezza 95 cm)
make_box("Stair_Kitchen_Landing_1", 9.70, 10.65, -2.06, -1.05, 0.0, z_landing, mat_stairs, col_stairs)

# Muretto o parapetto laterale di sicurezza a destra della scala in cucina
make_box("Stair_Kitchen_SideRailing", 10.65, 10.72, -2.84, -1.05, 0.0, z_landing + 0.90, mat_wall_int, col_walls)

# -------------------------------------------------------------
# G. SCALINATA SUPERIORE SOPRA LO SGABUZZINO (Rampa 2)
# Parte dalla porta scorrevole (z=0.53 m), curva e sale a Nord e poi a Sud sopra il vano sottoscala
# -------------------------------------------------------------
# Gradino a ventaglio 4 nel vano di svolta
make_box("Stair_Upper_Step_4", 8.69, 9.70, -1.05, -0.68, 0.0, 4 * riser_1, mat_stairs, col_stairs)
# Gradino a ventaglio 5
make_box("Stair_Upper_Step_5", 8.69, 9.70, -0.68, -0.30, 0.0, 5 * riser_1, mat_stairs, col_stairs)

# Scalinata che sale verso Sud sopra lo sgabuzzino sottoscala (gradini 6..17)
# Larghezza vano: x da 8.69 a 9.70 (101 cm)
# Da y=-0.68 verso Sud fino al disimpegno superiore
y_upper_start = -0.68
tread_upper = 0.24

for s in range(6, 18):
    z_step_top = s * riser_1
    y_s0 = y_upper_start - (s - 6) * tread_upper
    y_s1 = y_s0 - tread_upper
    # Sotto a questi gradini c'è lo sgabuzzino (che ha aria libera fino a 1.50-1.80m)
    z_step_bot = max(0.0, z_step_top - riser_1)
    make_box(f"Stair_Upper_Step_{s}", 8.69, 9.70, y_s1, y_s0, z_step_bot, z_step_top, mat_stairs, col_stairs)

# Pianerottolo di arrivo al piano superiore (z = 3.00 m)
make_box("Stair_Upper_Top_Landing", 8.69, 9.70, -3.56, y_s1, 2.82, 3.00, mat_stairs, col_stairs)

# Aggiornamento etichette 3D per rispecchiare i nuovi vani
col_labels = bpy.data.collections.get("06_Etichette_Stanze")
if col_labels:
    for obj in list(col_labels.objects):
        if "BAGNO" in obj.name or "SCALA" in obj.name:
            bpy.data.objects.remove(obj, do_unlink=True)

def add_label(text, x, y, size=0.45):
    font_curve = bpy.data.curves.new(type="FONT", name=f"Label_{text}")
    font_curve.body = text
    font_curve.size = size
    font_curve.extrude = 0.02
    obj = bpy.data.objects.new(name=f"Label_{text}", object_data=font_curve)
    obj.location = (x, y, 0.01)
    obj.data.materials.append(bpy.data.materials.get("Mat_Etichette"))
    col_labels.objects.link(obj)

add_label("BAGNO", 6.80, -2.20, size=0.28)
add_label("ANTIBAGNO", 8.75, -3.20, size=0.14)
add_label("SGABUZZINO", 8.72, -1.80, size=0.12)
add_label("SCALA CUCINA", 9.80, -2.40, size=0.16)

print("=== Bagno, Antibagno, Sgabuzzino e Scale Updated Successfully ===")

