"""
add_ecovacs_deebot.py
Aggiunge il robot aspirapolvere Ecovacs Deebot con stazione di ricarica
nella sala da pranzo: parete Est (x = 13.90), a fianco del caminetto ad angolo (nord-est).
"""

import bpy
import bmesh
import math
from mathutils import Vector, Euler

print(">>> AGGIUNTA ROBOT ASPIRAPOLVERE ECOVACS DEEBOT IN SALA DA PRANZO <<<")

# 1. Pulizia oggetti esistenti
for obj in list(bpy.data.objects):
    if obj.name.startswith("Ecovacs_Deebot_"):
        print(f"Rimuovo oggetto precedente: {obj.name}")
        bpy.data.objects.remove(obj, do_unlink=True)

# 2. Materiali dedicati
def get_or_create_material(name, base_color, metallic=0.0, roughness=0.3, emission=None, emission_strength=1.0):
    mat = bpy.data.materials.get(name)
    if not mat:
        mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = None
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            bsdf = n
            break
    if bsdf:
        bsdf.inputs["Base Color"].default_value = base_color
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
        if emission:
            if "Emission Color" in bsdf.inputs:
                bsdf.inputs["Emission Color"].default_value = emission
                bsdf.inputs["Emission Strength"].default_value = emission_strength
            elif "Emission" in bsdf.inputs:
                bsdf.inputs["Emission"].default_value = emission
    return mat

mat_white = get_or_create_material("Mat_Deebot_White", (0.92, 0.92, 0.94, 1.0), metallic=0.05, roughness=0.18)
mat_dark = get_or_create_material("Mat_Deebot_Dark", (0.12, 0.13, 0.14, 1.0), metallic=0.1, roughness=0.45)
mat_chrome = get_or_create_material("Mat_Deebot_Chrome", (0.85, 0.85, 0.87, 1.0), metallic=0.92, roughness=0.15)
mat_led = get_or_create_material("Mat_Deebot_Glow", (0.10, 0.65, 0.95, 1.0), metallic=0.0, roughness=0.2, emission=(0.15, 0.70, 1.0, 1.0), emission_strength=2.5)

# Coordinate di posizionamento:
# Muro Est interno: x = 13.90 (orientato verso -X, verso l'interno della stanza)
# Caminetto finisce a y = -1.15
# Mobile Kallax inizia a y = -2.90
# Posizionamento centrale robottino + dock: y = -1.65 (a 50cm dal caminetto, perfetto)
# Pavimento: z = 0.00
wall_x = 13.90
center_y = -1.65
floor_z = 0.00

col_arredi = bpy.data.collections.get("09_Arredi_Principali") or bpy.context.scene.collection

def link_to_col(obj):
    if obj.name not in col_arredi.objects:
        col_arredi.objects.link(obj)
    if obj.name in bpy.context.scene.collection.objects and col_arredi != bpy.context.scene.collection:
        bpy.context.scene.collection.objects.unlink(obj)

# -------------------------------------------------------------------------
# A. STAZIONE DI RICARICA (DOCK)
# -------------------------------------------------------------------------
# 1. Piastra di base / Rampa a terra
# Spessore 1.2 cm, larghezza lungo Y = 38 cm (da -1.84 a -1.46)
# Profondità lungo X = da wall_x - 0.38 (13.52) a wall_x (13.90)
dock_ramp_w = 0.38
dock_ramp_d = 0.36
dock_x_min = wall_x - dock_ramp_d
dock_x_max = wall_x
dock_y_min = center_y - dock_ramp_w / 2.0
dock_y_max = center_y + dock_ramp_w / 2.0
dock_z_max = floor_z + 0.014

bpy.ops.mesh.primitive_cube_add(size=1.0)
dock_base = bpy.context.active_object
dock_base.name = "Ecovacs_Deebot_Dock_Base"
dock_base.location = ((dock_x_min + dock_x_max) / 2.0, center_y, (floor_z + dock_z_max) / 2.0)
dock_base.scale = (dock_ramp_d, dock_ramp_w, dock_z_max - floor_z)
bpy.ops.object.transform_apply(location=True, scale=True, rotation=True)
dock_base.data.materials.append(mat_dark)
link_to_col(dock_base)

# 2. Torretta verticale di ricarica contro il muro
# Altezza: 36 cm (z: 0.014 a 0.38)
# Profondità lungo X: 16 cm (da wall_x - 0.16 = 13.74 a 13.90)
# Larghezza lungo Y: 32 cm (da center_y - 0.16 a center_y + 0.16)
tower_d = 0.16
tower_w = 0.32
tower_h = 0.36
tower_x_min = wall_x - tower_d
tower_x_max = wall_x
tower_z_min = floor_z + 0.014
tower_z_max = tower_z_min + tower_h

bpy.ops.mesh.primitive_cube_add(size=1.0)
dock_tower = bpy.context.active_object
dock_tower.name = "Ecovacs_Deebot_Dock_Tower"
dock_tower.location = ((tower_x_min + tower_x_max) / 2.0, center_y, (tower_z_min + tower_z_max) / 2.0)
dock_tower.scale = (tower_d, tower_w, tower_h)
bpy.ops.object.transform_apply(location=True, scale=True, rotation=True)
dock_tower.data.materials.append(mat_white)
link_to_col(dock_tower)

# 3. Fascia frontale / Vano contatti dock
bpy.ops.mesh.primitive_cube_add(size=1.0)
dock_slot = bpy.context.active_object
dock_slot.name = "Ecovacs_Deebot_Dock_Slot"
slot_w = 0.22
slot_h = 0.10
dock_slot.location = (tower_x_min + 0.005, center_y, tower_z_min + 0.07)
dock_slot.scale = (0.015, slot_w, slot_h)
bpy.ops.object.transform_apply(location=True, scale=True, rotation=True)
dock_slot.data.materials.append(mat_dark)
link_to_col(dock_slot)

# 4. LED di stato dock (piccolo segmento orizzontale in alto)
bpy.ops.mesh.primitive_cube_add(size=1.0)
dock_led = bpy.context.active_object
dock_led.name = "Ecovacs_Deebot_Dock_LED"
dock_led.location = (tower_x_min - 0.002, center_y, tower_z_max - 0.035)
dock_led.scale = (0.005, 0.05, 0.006)
bpy.ops.object.transform_apply(location=True, scale=True, rotation=True)
dock_led.data.materials.append(mat_led)
link_to_col(dock_led)

# -------------------------------------------------------------------------
# B. ROBOT ASPIRAPOLVERE (ECOVACS DEEBOT)
# -------------------------------------------------------------------------
# Posizione del robot quando è alla base (docked):
# Il retro entra leggermente nel vano della base, il muso guarda verso ovest (-X)
# Centro robot: x = 13.63, y = center_y = -1.65
robot_x = 13.63
robot_y = center_y
robot_radius = 0.170 # diametro 34 cm
robot_h = 0.078     # altezza scocca principale ~7.8 cm
robot_z_min = floor_z + 0.012
robot_z_max = robot_z_min + robot_h

# 1. Scocca circolare principale (Cylinder 32 segmenti)
bpy.ops.mesh.primitive_cylinder_add(vertices=36, radius=robot_radius, depth=robot_h)
robot_body = bpy.context.active_object
robot_body.name = "Ecovacs_Deebot_Body"
robot_body.location = (robot_x, robot_y, (robot_z_min + robot_z_max) / 2.0)
bpy.ops.object.transform_apply(location=True, scale=True, rotation=True)
robot_body.data.materials.append(mat_white)
link_to_col(robot_body)

# 2. Bumper anteriore (arco semicircolare / paracolpi scuro a ovest -X)
# Realizzato come cilindro sottile concentrico con offset
bpy.ops.mesh.primitive_cylinder_add(vertices=36, radius=robot_radius + 0.004, depth=robot_h * 0.70)
bumper = bpy.context.active_object
bumper.name = "Ecovacs_Deebot_Bumper"
bumper.location = (robot_x - 0.005, robot_y, robot_z_min + (robot_h * 0.70) / 2.0)
bpy.ops.object.transform_apply(location=True, scale=True, rotation=True)
bumper.data.materials.append(mat_dark)
link_to_col(bumper)

# 3. Torretta laser LiDAR (LDS) superiore (tonda centrata leggermente verso il centro/posteriore)
lidar_r = 0.042
lidar_h = 0.022
lidar_x = robot_x + 0.015
lidar_y = robot_y
lidar_z_min = robot_z_max
lidar_z_max = lidar_z_min + lidar_h

bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=lidar_r, depth=lidar_h)
lidar = bpy.context.active_object
lidar.name = "Ecovacs_Deebot_Lidar"
lidar.location = (lidar_x, lidar_y, (lidar_z_min + lidar_z_max) / 2.0)
bpy.ops.object.transform_apply(location=True, scale=True, rotation=True)
lidar.data.materials.append(mat_white)
link_to_col(lidar)

# 4. Anello metallico / fessura sensore LiDAR
bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=lidar_r + 0.003, depth=lidar_h * 0.35)
lidar_ring = bpy.context.active_object
lidar_ring.name = "Ecovacs_Deebot_Lidar_Ring"
lidar_ring.location = (lidar_x, lidar_y, lidar_z_min + lidar_h * 0.50)
bpy.ops.object.transform_apply(location=True, scale=True, rotation=True)
lidar_ring.data.materials.append(mat_chrome)
link_to_col(lidar_ring)

# 5. Pulsante di accensione / Auto Clean con anello luminoso cyan
btn_r = 0.016
btn_h = 0.004
btn_x = robot_x - 0.085
btn_y = robot_y
btn_z = robot_z_max + 0.002

bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=btn_r, depth=btn_h)
btn = bpy.context.active_object
btn.name = "Ecovacs_Deebot_Power_Button"
btn.location = (btn_x, btn_y, btn_z)
bpy.ops.object.transform_apply(location=True, scale=True, rotation=True)
btn.data.materials.append(mat_led)
link_to_col(btn)

# -------------------------------------------------------------------------
# C. PROPRIETÀ SSoT HOME ASSISTANT
# -------------------------------------------------------------------------
interactive_objects = [
    robot_body,
    bumper,
    lidar,
    lidar_ring,
    btn,
    dock_base,
    dock_tower,
    dock_slot,
    dock_led,
]

for obj in interactive_objects:
    obj["ha_entity"] = "vacuum.deebot"
    obj["ha_action"] = "modal"
    obj["ha_ui_type"] = "vacuum"
    obj["ha_name"] = "Ecovacs Deebot"

# Salva il file Blend
bpy.ops.wm.save_mainfile()
print(">>> SUCCESSO: Robot aspirapolvere Ecovacs Deebot e Stazione salvati in Smart_Home_3D.blend! <<<")

