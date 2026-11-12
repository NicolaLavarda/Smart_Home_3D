"""
add_irrigation_sprinklers.py
Aggiunge gli 11 gettini/irrigatori pop-up del giardino in Smart_Home_3D.blend
suddivisi nelle 3 aree Home Assistant (switch.smart_switch_area1, area2, area3).
"""

import bpy
import bmesh
from mathutils import Vector

print(">>> AGGIUNTA GETTINI IRRIGAZIONE GIARDINO IN SMART_HOME_3D.BLEND <<<")

# 1. Rimuovi eventuali gettini precedenti per evitare duplicati
for obj in list(bpy.data.objects):
    if obj.name.startswith("Sprinkler_"):
        print(f"Rimuovo oggetto precedente: {obj.name}")
        bpy.data.objects.remove(obj, do_unlink=True)

# 2. Materiali dedicati
def get_or_create_material(name, base_color, roughness=0.4, metallic=0.2):
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
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
    return mat

mat_collar = get_or_create_material("Mat_Sprinkler_Collar", (0.11, 0.12, 0.13, 1.0), roughness=0.6, metallic=0.1)
mat_riser = get_or_create_material("Mat_Sprinkler_Riser", (0.20, 0.24, 0.28, 1.0), roughness=0.35, metallic=0.4)

col_target = bpy.data.collections.get("01_Sito_e_Giardini") or bpy.context.scene.collection

def link_to_col(obj):
    if obj.name not in col_target.objects:
        col_target.objects.link(obj)
    if obj.name in bpy.context.scene.collection.objects and col_target != bpy.context.scene.collection:
        bpy.context.scene.collection.objects.unlink(obj)

sprinklers_data = [
    # Area 1: Giardino Area 1 (Prato Sud) - 4 gettini
    ("Sprinkler_Area1_1", -7.39, -26.45, 0.00, "switch.smart_switch_area1", "Irrigatore Area 1 - 1 (Sud-Ovest)", "Area 1"),
    ("Sprinkler_Area1_2", -0.16, -21.50, 0.00, "switch.smart_switch_area1", "Irrigatore Area 1 - 2 (Nord Viale)", "Area 1"),
    ("Sprinkler_Area1_3",  5.00, -24.69, 0.00, "switch.smart_switch_area1", "Irrigatore Area 1 - 3 (Centro Sud)", "Area 1"),
    ("Sprinkler_Area1_4", 12.30, -24.82, 0.00, "switch.smart_switch_area1", "Irrigatore Area 1 - 4 (Est Garage)", "Area 1"),

    # Area 2: Giardino Area 2 (Corte Est) - 2 gettini
    ("Sprinkler_Area2_1",  6.89,  -8.57, 0.00, "switch.smart_switch_area2", "Irrigatore Area 2 - 1 (Nord-Ovest Portico)", "Area 2"),
    ("Sprinkler_Area2_2", 13.28, -16.58, 0.00, "switch.smart_switch_area2", "Irrigatore Area 2 - 2 (Sud-Est Garage)", "Area 2"),

    # Area 3: Giardino Area 3 (Prato Nord e Viale Ovest) - 5 gettini
    ("Sprinkler_Area3_1", -3.52,  -0.58, 0.00, "switch.smart_switch_area3", "Irrigatore Area 3 - 1 (Nord Cancello)", "Area 3"),
    ("Sprinkler_Area3_2", -0.67,  -5.40, 0.00, "switch.smart_switch_area3", "Irrigatore Area 3 - 2 (Nord-Est Casa)", "Area 3"),
    ("Sprinkler_Area3_3", -5.09,  -7.96, 0.00, "switch.smart_switch_area3", "Irrigatore Area 3 - 3 (Ovest Viale)", "Area 3"),
    ("Sprinkler_Area3_4", -0.85, -14.95, 0.00, "switch.smart_switch_area3", "Irrigatore Area 3 - 4 (Lavanderia Ovest)", "Area 3"),
    ("Sprinkler_Area3_5",  4.15, -16.02, 0.00, "switch.smart_switch_area3", "Irrigatore Area 3 - 5 (Lavanderia Sud)", "Area 3"),
]

for name, sx, sy, sz, ent_id, friendly_name, area_name in sprinklers_data:
    # 1. Ghiera circolare a terra (collar flush con il prato)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.045, depth=0.025, vertices=24, location=(sx, sy, sz + 0.012))
    collar = bpy.context.active_object
    collar.name = f"{name}_Base"
    collar.data.materials.append(mat_collar)
    collar["ha_entity"] = ent_id
    collar["ha_action"] = "modal"
    collar["ha_ui_type"] = "irrigation"
    collar["ha_name"] = f"{friendly_name} (Base)"
    link_to_col(collar)

    # 2. Torretta pop-up alta 25cm (stelo cilindrico)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.016, depth=0.25, vertices=24, location=(sx, sy, sz + 0.125))
    riser = bpy.context.active_object
    riser.name = name
    riser.data.materials.append(mat_riser)
    riser["ha_entity"] = ent_id
    riser["ha_action"] = "modal"
    riser["ha_ui_type"] = "irrigation"
    riser["ha_name"] = friendly_name
    riser["ha_area"] = area_name
    riser["ha_riser_height"] = 0.25
    link_to_col(riser)

    # 3. Ugello superiore orientabile (nozzle)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.022, depth=0.03, vertices=24, location=(sx, sy, sz + 0.25 - 0.015))
    nozzle = bpy.context.active_object
    nozzle.name = f"{name}_Nozzle"
    nozzle.data.materials.append(mat_collar)
    nozzle["ha_entity"] = ent_id
    nozzle["ha_action"] = "modal"
    nozzle["ha_ui_type"] = "irrigation"
    nozzle["ha_name"] = f"{friendly_name} (Ugello)"
    link_to_col(nozzle)

print(f"Creati {len(sprinklers_data)} irrigatori (33 mesh: Base, Riser, Nozzle) in Smart_Home_3D.blend.")

bpy.ops.wm.save_mainfile()
print(">>> SUCCESSO: Gettini irrigazione salvati in Smart_Home_3D.blend! <<<")

