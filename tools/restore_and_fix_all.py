import bpy
import bmesh
import math
from mathutils import Vector

print(">>> RUNNING RESTORE AND FIX ALL SCRIPT <<<")

def get_or_create_collection(name, parent_name=None):
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    coll = bpy.data.collections.new(name)
    if parent_name and parent_name in bpy.data.collections:
        bpy.data.collections[parent_name].children.link(coll)
    else:
        bpy.context.scene.collection.children.link(coll)
    return coll

def get_or_create_material(name, color=(0.8, 0.8, 0.8, 1.0), roughness=0.4, metallic=0.0, emission_color=(0,0,0,1), emission_strength=0.0):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name=name)
        mat.use_nodes = True
    if not mat.use_nodes:
        mat.use_nodes = True
    mat.blend_method = 'OPAQUE'
    nodes = mat.node_tree.nodes
    bsdf = None
    for n in nodes:
        if n.type == 'BSDF_PRINCIPLED':
            bsdf = n
            break
    if bsdf:
        if 'Base Color' in bsdf.inputs:
            bsdf.inputs['Base Color'].default_value = color
        if 'Roughness' in bsdf.inputs:
            bsdf.inputs['Roughness'].default_value = roughness
        if 'Metallic' in bsdf.inputs:
            bsdf.inputs['Metallic'].default_value = metallic
        if 'Emission Color' in bsdf.inputs:
            bsdf.inputs['Emission Color'].default_value = emission_color
        if 'Emission Strength' in bsdf.inputs:
            bsdf.inputs['Emission Strength'].default_value = emission_strength
    return mat

def ensure_in_collection(obj, target_collection):
    for c in list(obj.users_collection):
        if c != target_collection:
            c.objects.unlink(obj)
    if obj.name not in target_collection.objects:
        target_collection.objects.link(obj)

# Collections
col_site = get_or_create_collection("01_Sito_e_Giardini")
col_lav = get_or_create_collection("03_Lavanderia")
col_gar = get_or_create_collection("04_Garage")
col_scale = get_or_create_collection("05_Scale_e_Sottoscala")
col_gates = get_or_create_collection("07_Recinzione_e_Cancelli")
col_arredi = get_or_create_collection("09_Arredi_Principali")

# Materials
mat_bollard = get_or_create_material("Mat_Bollard_Dark", color=(0.12, 0.13, 0.14, 1.0), roughness=0.55, metallic=0.2)
mat_frosted = get_or_create_material("Mat_Frosted_Diffuser", color=(0.95, 0.94, 0.90, 1.0), roughness=0.25, metallic=0.0, emission_color=(1.0, 0.90, 0.75, 1.0), emission_strength=0.2)
mat_spot_metal = get_or_create_material("Mat_Spot_Metal", color=(0.90, 0.90, 0.92, 1.0), roughness=0.25, metallic=0.8)
mat_puffer = get_or_create_material("Mat_Puffer_Grey", color=(0.28, 0.30, 0.32, 1.0), roughness=0.45, metallic=0.15)
mat_puffer_cap = get_or_create_material("Mat_Puffer_Cap", color=(0.08, 0.08, 0.09, 1.0), roughness=0.6, metallic=0.05)
mat_caldaia = get_or_create_material("Mat_Caldaia_White", color=(0.94, 0.94, 0.95, 1.0), roughness=0.25, metallic=0.02)
mat_display = get_or_create_material("Mat_Caldaia_Display", color=(0.05, 0.05, 0.05, 1.0), roughness=0.1, emission_color=(0.3, 0.7, 1.0, 1.0), emission_strength=0.8)
mat_switch = get_or_create_material("Mat_Switch_Plate", color=(0.92, 0.92, 0.94, 1.0), roughness=0.3, metallic=0.1)

# =========================================================================
# 1. OUTDOOR BOLLARDS & WALL LIGHTS (light.luci_esterne & light.portico)
# =========================================================================
# 4 square bollards
bollard_coords = [
    ("Bollard_Garden_1", -4.00, -5.90, 0.00),
    ("Bollard_Garden_2", -1.00, -5.90, 0.00),
    ("Bollard_Garden_3", -3.80, -18.00, 0.00),
    ("Bollard_Garden_4",  2.20, -18.25, 0.00),
]

for name, bx, by, bz in bollard_coords:
    # Base
    base_name = f"{name}_Base"
    obj = bpy.data.objects.get(base_name)
    if not obj:
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(bx, by, bz + 0.01))
        obj = bpy.context.active_object
        obj.name = base_name
        obj.scale = Vector((0.20, 0.20, 0.02))
        obj.data.materials.append(mat_bollard)
    ensure_in_collection(obj, col_site)

    # Pillar
    pillar_name = f"{name}_Pillar"
    obj = bpy.data.objects.get(pillar_name)
    if not obj:
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(bx, by, bz + 0.02 + 0.52/2))
        obj = bpy.context.active_object
        obj.name = pillar_name
        obj.scale = Vector((0.16, 0.16, 0.52))
        obj.data.materials.append(mat_bollard)
    ensure_in_collection(obj, col_site)

    # Diffuser (interactive entity)
    obj = bpy.data.objects.get(name)
    if not obj:
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(bx, by, bz + 0.54 + 0.22/2))
        obj = bpy.context.active_object
        obj.name = name
        obj.scale = Vector((0.145, 0.145, 0.22))
        obj.data.materials.append(mat_frosted)
    obj["ha_entity"] = "light.luci_esterne"
    obj["ha_ui_type"] = "light"
    obj["ha_name"] = "Lampioncino Giardino"
    obj["ha_action"] = "toggle"
    ensure_in_collection(obj, col_site)

    # Cap
    cap_name = f"{name}_Cap"
    obj = bpy.data.objects.get(cap_name)
    if not obj:
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(bx, by, bz + 0.76 + 0.02))
        obj = bpy.context.active_object
        obj.name = cap_name
        obj.scale = Vector((0.17, 0.17, 0.04))
        obj.data.materials.append(mat_bollard)
    ensure_in_collection(obj, col_site)

# 4 Wall Lights on East Fence (Muro_Cinta_Est)
wall_lights_y = [-9.87, -11.68, -13.50, -15.31]
for idx, wy in enumerate(wall_lights_y, start=1):
    wname = f"Wall_Garden_Light_{idx}"
    body_name = f"{wname}_Body"
    obj = bpy.data.objects.get(body_name)
    if not obj:
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(13.91, wy, 0.60))
        obj = bpy.context.active_object
        obj.name = body_name
        obj.scale = Vector((0.04, 0.16, 0.12))
        obj.data.materials.append(mat_bollard)
    ensure_in_collection(obj, col_site)

    obj = bpy.data.objects.get(wname)
    if not obj:
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(13.88, wy, 0.58))
        obj = bpy.context.active_object
        obj.name = wname
        obj.scale = Vector((0.02, 0.12, 0.06))
        obj.data.materials.append(mat_frosted)
    obj["ha_entity"] = "light.luci_esterne"
    obj["ha_ui_type"] = "light"
    obj["ha_name"] = f"Luce Muro Giardino {idx}"
    obj["ha_action"] = "toggle"
    ensure_in_collection(obj, col_site)

# 2 Portico Lights (light.portico)
portico_sw = bpy.data.objects.get("Portico_Wall_Light_SW")
if not portico_sw:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.80, -12.41, 2.20))
    portico_sw = bpy.context.active_object
    portico_sw.name = "Portico_Wall_Light_SW"
    portico_sw.scale = Vector((0.14, 0.08, 0.16))
    portico_sw.data.materials.append(mat_bollard)
portico_sw["ha_entity"] = "light.portico"
portico_sw["ha_ui_type"] = "light"
portico_sw["ha_name"] = "Luce Portico Ovest"
portico_sw["ha_action"] = "toggle"
ensure_in_collection(portico_sw, col_site)

portico_ne = bpy.data.objects.get("Portico_Wall_Light_NE")
if not portico_ne:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(4.40, -7.13, 2.20))
    portico_ne = bpy.context.active_object
    portico_ne.name = "Portico_Wall_Light_NE"
    portico_ne.scale = Vector((0.14, 0.08, 0.16))
    portico_ne.data.materials.append(mat_bollard)
portico_ne["ha_entity"] = "light.portico"
portico_ne["ha_ui_type"] = "light"
portico_ne["ha_name"] = "Luce Portico Est"
portico_ne["ha_action"] = "toggle"
ensure_in_collection(portico_ne, col_site)

print("[OK] Outdoor and Portico lights verified.")

# =========================================================================
# 2. GATES & GARAGE SWITCHES
# =========================================================================
# Cancello Carraio Switch (-6.60, -0.20, 0.85)
sw_carraio = bpy.data.objects.get("Switch_Gate_Carraio")
if not sw_carraio:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-6.60, -0.20, 0.85))
    sw_carraio = bpy.context.active_object
    sw_carraio.name = "Switch_Gate_Carraio"
    sw_carraio.scale = Vector((0.08, 0.06, 0.14))
    sw_carraio.data.materials.append(mat_bollard)
sw_carraio["ha_entity"] = "switch.switch_casa_interruttore_1"
sw_carraio["ha_ui_type"] = "switch"
sw_carraio["ha_name"] = "Cancello Carraio"
sw_carraio["ha_action"] = "toggle"
ensure_in_collection(sw_carraio, col_gates)

# Cancelletto Pedonale Switch (-4.24, -0.20, 1.05)
sw_ped = bpy.data.objects.get("Switch_Gate_Ped")
if not sw_ped:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-4.24, -0.20, 1.05))
    sw_ped = bpy.context.active_object
    sw_ped.name = "Switch_Gate_Ped"
    sw_ped.scale = Vector((0.04, 0.06, 0.12))
    sw_ped.data.materials.append(mat_bollard)
sw_ped["ha_entity"] = "switch.switch_casa_interruttore_2"
sw_ped["ha_ui_type"] = "switch"
sw_ped["ha_name"] = "Serratura Cancelletto"
sw_ped["ha_action"] = "toggle"
ensure_in_collection(sw_ped, col_gates)

# Serranda Garage Switch (6.54, -20.73, 1.15)
sw_gar = bpy.data.objects.get("Switch_Garage_Door")
if not sw_gar:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(6.54, -20.73, 1.15))
    sw_gar = bpy.context.active_object
    sw_gar.name = "Switch_Garage_Door"
    sw_gar.scale = Vector((0.03, 0.10, 0.14))
    sw_gar.data.materials.append(mat_switch)
sw_gar["ha_entity"] = "switch.switch_casa_interruttore_3"
sw_gar["ha_ui_type"] = "switch"
sw_gar["ha_name"] = "Serranda Garage"
sw_gar["ha_action"] = "toggle"
ensure_in_collection(sw_gar, col_gar)

print("[OK] Gate and Garage switches verified.")

# =========================================================================
# 3. CENTRALE TERMICA IN LAVANDERIA (PUFFER + CALDAIA + SENSORI)
# =========================================================================
# Puffer Tank
p_x, p_y = 1.25, -14.85
puffer_body = bpy.data.objects.get("Thermal_Puffer_Tank")
if not puffer_body:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.30, depth=1.52, vertices=32, location=(p_x, p_y, 0.76))
    puffer_body = bpy.context.active_object
    puffer_body.name = "Thermal_Puffer_Tank"
    puffer_body.data.materials.append(mat_puffer)
ensure_in_collection(puffer_body, col_lav)

puffer_cap = bpy.data.objects.get("Thermal_Puffer_Cap")
if not puffer_cap:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.31, depth=0.12, vertices=32, location=(p_x, p_y, 1.58))
    puffer_cap = bpy.context.active_object
    puffer_cap.name = "Thermal_Puffer_Cap"
    puffer_cap.data.materials.append(mat_puffer_cap)
ensure_in_collection(puffer_cap, col_lav)

p_dial = bpy.data.objects.get("Thermal_Puffer_Dial")
if not p_dial:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.045, depth=0.02, vertices=24, location=(p_x, p_y + 0.305, 1.35), rotation=(math.pi/2, 0, 0))
    p_dial = bpy.context.active_object
    p_dial.name = "Thermal_Puffer_Dial"
    p_dial.data.materials.append(mat_spot_metal)
ensure_in_collection(p_dial, col_lav)

s_p_high = bpy.data.objects.get("Sensor_Puffer_High")
if not s_p_high:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.05, depth=0.015, vertices=24, location=(p_x, p_y + 0.31, 1.18), rotation=(math.pi/2, 0, 0))
    s_p_high = bpy.context.active_object
    s_p_high.name = "Sensor_Puffer_High"
    s_p_high.data.materials.append(mat_frosted)
s_p_high["ha_entity"] = "sensor.temperatura_accumulo_alto"
s_p_high["ha_ui_type"] = "sensor"
s_p_high["ha_name"] = "Temp. Accumulo Alto"
s_p_high["ha_badge_style"] = "puffer_high"
ensure_in_collection(s_p_high, col_lav)

s_p_low = bpy.data.objects.get("Sensor_Puffer_Low")
if not s_p_low:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.05, depth=0.015, vertices=24, location=(p_x, p_y + 0.31, 0.48), rotation=(math.pi/2, 0, 0))
    s_p_low = bpy.context.active_object
    s_p_low.name = "Sensor_Puffer_Low"
    s_p_low.data.materials.append(mat_frosted)
s_p_low["ha_entity"] = "sensor.temperatura_accumulo_basso"
s_p_low["ha_ui_type"] = "sensor"
s_p_low["ha_name"] = "Temp. Accumulo Basso"
s_p_low["ha_badge_style"] = "puffer_low"
ensure_in_collection(s_p_low, col_lav)

# Caldaia Box
c_x, c_y = 0.65, -14.98
caldaia_box = bpy.data.objects.get("Thermal_Caldaia_Box")
if not caldaia_box:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(c_x, c_y, 0.70))
    caldaia_box = bpy.context.active_object
    caldaia_box.name = "Thermal_Caldaia_Box"
    caldaia_box.scale = Vector((0.44, 0.38, 1.40))
    caldaia_box.data.materials.append(mat_caldaia)
ensure_in_collection(caldaia_box, col_lav)

c_disp = bpy.data.objects.get("Thermal_Caldaia_Display")
if not c_disp:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(c_x, c_y + 0.192, 1.20))
    c_disp = bpy.context.active_object
    c_disp.name = "Thermal_Caldaia_Display"
    c_disp.scale = Vector((0.14, 0.01, 0.08))
    c_disp.data.materials.append(mat_display)
ensure_in_collection(c_disp, col_lav)

c_pipe = bpy.data.objects.get("Thermal_Caldaia_Flue")
if not c_pipe:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.055, depth=0.15, vertices=24, location=(c_x, c_y, 1.47))
    c_pipe = bpy.context.active_object
    c_pipe.name = "Thermal_Caldaia_Flue"
    c_pipe.data.materials.append(mat_spot_metal)
ensure_in_collection(c_pipe, col_lav)

s_caldaia = bpy.data.objects.get("Sensor_Caldaia_Temp")
if not s_caldaia:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.05, depth=0.015, vertices=24, location=(c_x, c_y + 0.192, 1.05), rotation=(math.pi/2, 0, 0))
    s_caldaia = bpy.context.active_object
    s_caldaia.name = "Sensor_Caldaia_Temp"
    s_caldaia.data.materials.append(mat_frosted)
s_caldaia["ha_entity"] = "sensor.temperatura_caldaia"
s_caldaia["ha_ui_type"] = "sensor"
s_caldaia["ha_name"] = "Temp. Caldaia"
s_caldaia["ha_badge_style"] = "caldaia"
ensure_in_collection(s_caldaia, col_lav)

sw_caldaia = bpy.data.objects.get("Switch_Caldaia_Wall")
if not sw_caldaia:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.90, -12.60, 1.20))
    sw_caldaia = bpy.context.active_object
    sw_caldaia.name = "Switch_Caldaia_Wall"
    sw_caldaia.scale = Vector((0.10, 0.02, 0.10))
    sw_caldaia.data.materials.append(mat_switch)
sw_caldaia["ha_entity"] = "switch.smart_switch_caldaia"
sw_caldaia["ha_ui_type"] = "switch"
sw_caldaia["ha_name"] = "Interruttore Caldaia"
sw_caldaia["ha_action"] = "toggle"
ensure_in_collection(sw_caldaia, col_lav)

print("[OK] Laundry thermal equipment restored in 03_Lavanderia.")

# =========================================================================
# 4. FIX DISHWASHER Z-FIGHTING (SCOCCA, DOOR, BUGNA)
# =========================================================================
# In the kitchen:
# Scocca niche: set front face at Y = -7.110 (clear of door back face at -7.100)
scocca_dw = bpy.data.objects.get("Cucina_Basi_Scocca_Sud_Lavastoviglie")
if scocca_dw:
    bm = bmesh.new()
    bm.from_mesh(scocca_dw.data)
    for v in bm.verts:
        if v.co.y > -7.105:
            v.co.y = -7.110
    bm.to_mesh(scocca_dw.data)
    bm.free()
    scocca_dw.data.update()

# Lavastoviglie door base panel: Y in [-7.100, -7.082]
dw_door = bpy.data.objects.get("Lavastoviglie")
if dw_door:
    bm = bmesh.new()
    bm.from_mesh(dw_door.data)
    min_y = min(v.co.y for v in bm.verts)
    max_y = max(v.co.y for v in bm.verts)
    span_y = (max_y - min_y) or 1.0
    for v in bm.verts:
        norm_y = (v.co.y - min_y) / span_y
        v.co.y = -7.100 + norm_y * (-7.082 - -7.100)
    bm.to_mesh(dw_door.data)
    bm.free()
    dw_door.data.update()

# Lavastoviglie_Bugna: protruding raised decorative panel: Y in [-7.082, -7.078]
dw_bugna = bpy.data.objects.get("Lavastoviglie_Bugna")
if dw_bugna:
    bm = bmesh.new()
    bm.from_mesh(dw_bugna.data)
    min_y = min(v.co.y for v in bm.verts)
    max_y = max(v.co.y for v in bm.verts)
    span_y = (max_y - min_y) or 1.0
    for v in bm.verts:
        norm_y = (v.co.y - min_y) / span_y
        v.co.y = -7.082 + norm_y * (-7.078 - -7.082)
    bm.to_mesh(dw_bugna.data)
    bm.free()
    dw_bugna.data.update()

# Fascia comandi inox: Y in [-7.100, -7.076]
dw_panel = bpy.data.objects.get("Lavastoviglie_Pannello_Comandi")
if dw_panel:
    bm = bmesh.new()
    bm.from_mesh(dw_panel.data)
    min_y = min(v.co.y for v in bm.verts)
    max_y = max(v.co.y for v in bm.verts)
    span_y = (max_y - min_y) or 1.0
    for v in bm.verts:
        norm_y = (v.co.y - min_y) / span_y
        v.co.y = -7.100 + norm_y * (-7.076 - -7.100)
    bm.to_mesh(dw_panel.data)
    bm.free()
    dw_panel.data.update()

# Display LED: Y at -7.074
dw_disp = bpy.data.objects.get("Lavastoviglie_Display")
if dw_disp:
    dw_disp.location.y = -7.074

print("[OK] Dishwasher mesh layers cleanly separated (zero coplanarity).")

# =========================================================================
# 5. FIX MICROWAVE CABINET SIDE PANEL Z-FIGHTING
# =========================================================================
fianco_ovest = bpy.data.objects.get("Cucina_Basi_Fianco_Ovest")
if fianco_ovest:
    print("Removing overlapping duplicate Cucina_Basi_Fianco_Ovest...")
    bpy.data.objects.remove(fianco_ovest, do_unlink=True)
    print("[OK] Removed Cucina_Basi_Fianco_Ovest.")

# =========================================================================
# 6. FIX COFFEE MACHINE MATERIAL (NO TRANSPARENT GLASS)
# =========================================================================
mat_caffe_corpo = get_or_create_material(
    "Mat_Macchina_Caffe_Corpo",
    color=(0.14, 0.14, 0.16, 1.0),
    roughness=0.35,
    metallic=0.15
)
caffe_corpo = bpy.data.objects.get("Cucina_Macchina_Caffe_Corpo")
if caffe_corpo:
    caffe_corpo.data.materials.clear()
    caffe_corpo.data.materials.append(mat_caffe_corpo)
    print("[OK] Cucina_Macchina_Caffe_Corpo assigned Mat_Macchina_Caffe_Corpo (opaque dark charcoal).")

# =========================================================================
# 7. FIX STAIRS COMPENETRATION & STEP NOSING
# =========================================================================
# 7a. Top Arrival Lintel: Wall_Antibagno_South_Lintel must stop at Z = 2.820
lintel = bpy.data.objects.get("Wall_Antibagno_South_Lintel")
if lintel:
    bm = bmesh.new()
    bm.from_mesh(lintel.data)
    for v in bm.verts:
        if v.co.z > 2.820:
            v.co.z = 2.820
    bm.to_mesh(lintel.data)
    bm.free()
    lintel.data.update()
    print("[OK] Wall_Antibagno_South_Lintel top adjusted to Z=2.820 (below Stair_Top_Arrival).")

# 7b. Risers top Z: must stop at bottom of treads (s_zmin)
for i in range(6, 18):
    step = bpy.data.objects.get(f"Stair_Upper_Step_{i}")
    riser = bpy.data.objects.get(f"Stair_Upper_Riser_{i}")
    if step and riser:
        s_zmin = min((step.matrix_world @ Vector(c)).z for c in step.bound_box)
        bm = bmesh.new()
        bm.from_mesh(riser.data)
        for v in bm.verts:
            if v.co.z > s_zmin:
                v.co.z = s_zmin
        bm.to_mesh(riser.data)
        bm.free()
        riser.data.update()

print("[OK] Stair risers adjusted beneath wooden treads (zero nosing z-fighting).")

# =========================================================================
# 8. FIX LAUNDRY FLOOR Z-FIGHTING (PORTICO OVERLAP & ELEVATION)
# =========================================================================
# 8a. Elevate Floor_Lavanderia by 2mm (Z = 0.002)
fl = bpy.data.objects.get("Floor_Lavanderia")
if fl:
    bm = bmesh.new()
    bm.from_mesh(fl.data)
    for v in bm.verts:
        if v.co.z >= -0.001:
            v.co.z = 0.002
    bm.to_mesh(fl.data)
    bm.free()
    fl.data.update()
    print("[OK] Floor_Lavanderia top elevated to Z=0.002m.")

# 8b. Adjust Portico_Pavement_Unified so it doesn't overlap the laundry area
portico = bpy.data.objects.get("Portico_Pavement_Unified")
if portico:
    bm = bmesh.new()
    bm.from_mesh(portico.data)
    # The laundry room spans X in [0.300, 4.450], Y in [-15.430, -12.430]
    # Portico pavement vertices inside this laundry box should be pulled out or trimmed
    # Let's inspect vertices that lie inside the laundry box
    for v in bm.verts:
        if 0.25 <= v.co.x <= 4.55 and -15.45 <= v.co.y <= -12.40:
            # If at top surface, pull down to -0.010 or adjust
            if v.co.z >= -0.001:
                v.co.z = -0.005 # below laundry floor slab
    bm.to_mesh(portico.data)
    bm.free()
    portico.data.update()
    print("[OK] Portico_Pavement_Unified laundry overlap trimmed below slab.")

# Save Blender File
bpy.ops.wm.save_mainfile()
print("\n>>> ALL RESTORATIONS AND FIXES SAVED TO Smart_Home_3D.blend! <<<\n")

