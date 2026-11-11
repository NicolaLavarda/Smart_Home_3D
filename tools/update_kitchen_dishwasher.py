import bpy
import bmesh
from mathutils import Vector

print(">>> STARTING KITCHEN DISHWASHER AND DRAWERS RESTRUCTURING <<<")

# 1. Rimuovi le vecchie paraste centrali della base sud se presenti
for name in ["Cucina_Basi_Parasta_Sud_1", "Cucina_Basi_Parasta_Sud_2"]:
    obj = bpy.data.objects.get(name)
    if obj:
        print(f"Removing obsolete parasta: {name}")
        bpy.data.objects.remove(obj, do_unlink=True)

# 2. Rimuovi il vecchio Sensor_Dishwasher provvisorio
old_sensor = bpy.data.objects.get("Sensor_Dishwasher")
if old_sensor:
    print("Removing old Sensor_Dishwasher cube")
    bpy.data.objects.remove(old_sensor, do_unlink=True)

# Recupera materiali esistenti
mat_noce = bpy.data.materials.get("Mat_Legno_Tavolo_Noce")
mat_maniglie = bpy.data.materials.get("Mat_Ottone_Maniglie")
mat_inox = bpy.data.materials.get("Mat_Inox_Satinato") or bpy.data.materials.get("Mat_Acciaio_Spazzolato")
if not mat_inox:
    mat_inox = bpy.data.materials.new(name="Mat_Inox_Satinato")
    mat_inox.use_nodes = True
    bsdf = mat_inox.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.75, 0.77, 0.80, 1.0)
        bsdf.inputs["Metallic"].default_value = 0.90
        bsdf.inputs["Roughness"].default_value = 0.25

mat_display = bpy.data.materials.get("Mat_Dishwasher_Display")
if not mat_display:
    mat_display = bpy.data.materials.new(name="Mat_Dishwasher_Display")
    mat_display.use_nodes = True
    bsdf = mat_display.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.05, 0.08, 0.12, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.10
        # Emissive per display cyan attivo
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = (0.10, 0.65, 0.95, 1.0)
            bsdf.inputs["Emission Strength"].default_value = 1.2
        elif "Emission" in bsdf.inputs:
            bsdf.inputs["Emission"].default_value = (0.10, 0.65, 0.95, 1.0)

# Coordinate esatte:
# - Lavello a sinistra (in vista camera) finisce a X = 8.765
# - Lavastoviglie 60cm: X = [8.165 .. 8.765] (larghezza = 0.600m)
# - Cassettiera a destra (in vista camera, verso angolo cottura X=7.540):
#   X = [7.555 .. 8.150] (larghezza = 0.595m)
# - Anta angolo inizia a X = 7.540 (margine minimo 1.5cm)

# 3. Aggiorna Scocca Cassetti
scocca_cassetti = bpy.data.objects.get("Cucina_Basi_Scocca_Sud_Cassetti")
if scocca_cassetti:
    # Ridimensiona e posiziona la scocca per contenere i cassetti ridimensionati
    # Bbox target: X: [7.550 .. 8.155], Y: [-7.750 .. -7.100], Z: [0.120 .. 0.860]
    mesh = scocca_cassetti.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    
    # Calcola bbox locale attuale
    min_x = min(v.co.x for v in bm.verts)
    max_x = max(v.co.x for v in bm.verts)
    span_x = (max_x - min_x) or 1.0
    
    target_min_x = 7.550
    target_max_x = 8.155
    target_span_x = target_max_x - target_min_x
    
    for v in bm.verts:
        norm_x = (v.co.x - min_x) / span_x
        v.co.x = target_min_x + norm_x * target_span_x
        
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    print("Updated Cucina_Basi_Scocca_Sud_Cassetti dimensions.")

# 4. Aggiorna i 4 cassetti (Frontale, Bugna, Maniglia)
drawer_target_min_x = 7.555
drawer_target_max_x = 8.150
drawer_span_x = drawer_target_max_x - drawer_target_min_x

bugna_target_min_x = 7.595
bugna_target_max_x = 8.110
bugna_span_x = bugna_target_max_x - bugna_target_min_x

handle_center_x = (drawer_target_min_x + drawer_target_max_x) / 2.0
handle_half_width = 0.090 # maniglia da 18cm

for i in range(4):
    # Frontale
    front = bpy.data.objects.get(f"Cucina_Cassetto_Frontale_{i}")
    if front:
        bm = bmesh.new()
        bm.from_mesh(front.data)
        min_x = min(v.co.x for v in bm.verts)
        max_x = max(v.co.x for v in bm.verts)
        span = (max_x - min_x) or 1.0
        for v in bm.verts:
            norm_x = (v.co.x - min_x) / span
            v.co.x = drawer_target_min_x + norm_x * drawer_span_x
        bm.to_mesh(front.data)
        bm.free()
        front.data.update()
        
    # Bugna
    bugna = bpy.data.objects.get(f"Cucina_Cassetto_Bugna_{i}")
    if bugna:
        bm = bmesh.new()
        bm.from_mesh(bugna.data)
        min_x = min(v.co.x for v in bm.verts)
        max_x = max(v.co.x for v in bm.verts)
        span = (max_x - min_x) or 1.0
        for v in bm.verts:
            norm_x = (v.co.x - min_x) / span
            v.co.x = bugna_target_min_x + norm_x * bugna_span_x
        bm.to_mesh(bugna.data)
        bm.free()
        bugna.data.update()
        
    # Maniglia
    maniglia = bpy.data.objects.get(f"Cucina_Cassetto_Maniglia_{i}")
    if maniglia:
        bm = bmesh.new()
        bm.from_mesh(maniglia.data)
        min_x = min(v.co.x for v in bm.verts)
        max_x = max(v.co.x for v in bm.verts)
        span = (max_x - min_x) or 1.0
        for v in bm.verts:
            norm_x = (v.co.x - min_x) / span
            v.co.x = (handle_center_x - handle_half_width) + norm_x * (handle_half_width * 2)
        bm.to_mesh(maniglia.data)
        bm.free()
        maniglia.data.update()

print("Updated all 4 kitchen drawers to width 59.5cm.")

# 5. Crea la Scocca Niche Lavastoviglie 60cm
dish_scocca_name = "Cucina_Basi_Scocca_Sud_Lavastoviglie"
dish_scocca = bpy.data.objects.get(dish_scocca_name)
if not dish_scocca:
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    dish_scocca = bpy.context.active_object
    dish_scocca.name = dish_scocca_name
    dish_scocca.location = ((8.165 + 8.765) / 2.0, (-7.750 + -7.100) / 2.0, (0.120 + 0.860) / 2.0)
    dish_scocca.scale = (8.765 - 8.165, -7.100 - -7.750, 0.860 - 0.120)
    bpy.ops.object.transform_apply(location=True, scale=True, rotation=True)
    if mat_noce:
        dish_scocca.data.materials.append(mat_noce)
    # Assicura che sia nella collection Cucina
    coll_cucina = bpy.data.collections.get("Cucina") or bpy.context.scene.collection
    if dish_scocca.name not in coll_cucina.objects:
        coll_cucina.objects.link(dish_scocca)
        if dish_scocca.name in bpy.context.scene.collection.objects and coll_cucina != bpy.context.scene.collection:
            bpy.context.scene.collection.objects.unlink(dish_scocca)

# 6. Crea il pannello Lavastoviglie (Pannello Legno Noce principale)
dish_name = "Lavastoviglie"
dish_obj = bpy.data.objects.get(dish_name)
if dish_obj:
    bpy.data.objects.remove(dish_obj, do_unlink=True)

# Anta principale in legno noce coordinata con la cucina
bpy.ops.mesh.primitive_cube_add(size=1.0)
dish_obj = bpy.context.active_object
dish_obj.name = dish_name
dish_x_min = 8.170
dish_x_max = 8.760
dish_y_min = -7.100
dish_y_max = -7.080
dish_z_min = 0.130
dish_z_max = 0.770 # fino alla fascia comandi superiore

dish_obj.location = ((dish_x_min + dish_x_max) / 2.0, (dish_y_min + dish_y_max) / 2.0, (dish_z_min + dish_z_max) / 2.0)
dish_obj.scale = (dish_x_max - dish_x_min, dish_y_max - dish_y_min, dish_z_max - dish_z_min)
bpy.ops.object.transform_apply(location=True, scale=True, rotation=True)
if mat_noce:
    dish_obj.data.materials.append(mat_noce)

# Bugna decorativa coordinata per l'anta lavastoviglie
dish_bugna_name = "Lavastoviglie_Bugna"
dish_bugna = bpy.data.objects.get(dish_bugna_name)
if dish_bugna:
    bpy.data.objects.remove(dish_bugna, do_unlink=True)

bpy.ops.mesh.primitive_cube_add(size=1.0)
dish_bugna = bpy.context.active_object
dish_bugna.name = dish_bugna_name
b_x_min = dish_x_min + 0.040
b_x_max = dish_x_max - 0.040
b_y_min = -7.090
b_y_max = -7.080
b_z_min = dish_z_min + 0.040
b_z_max = dish_z_max - 0.040

dish_bugna.location = ((b_x_min + b_x_max) / 2.0, (b_y_min + b_y_max) / 2.0, (b_z_min + b_z_max) / 2.0)
dish_bugna.scale = (b_x_max - b_x_min, b_y_max - b_y_min, b_z_max - b_z_min)
bpy.ops.object.transform_apply(location=True, scale=True, rotation=True)
if mat_noce:
    dish_bugna.data.materials.append(mat_noce)

# 7. Fascia Comandi Inox superiore con display
dish_panel_name = "Lavastoviglie_Pannello_Comandi"
dish_panel = bpy.data.objects.get(dish_panel_name)
if dish_panel:
    bpy.data.objects.remove(dish_panel, do_unlink=True)

bpy.ops.mesh.primitive_cube_add(size=1.0)
dish_panel = bpy.context.active_object
dish_panel.name = dish_panel_name
p_x_min = dish_x_min
p_x_max = dish_x_max
p_y_min = -7.100
p_y_max = -7.078
p_z_min = 0.770
p_z_max = 0.850

dish_panel.location = ((p_x_min + p_x_max) / 2.0, (p_y_min + p_y_max) / 2.0, (p_z_min + p_z_max) / 2.0)
dish_panel.scale = (p_x_max - p_x_min, p_y_max - p_y_min, p_z_max - p_z_min)
bpy.ops.object.transform_apply(location=True, scale=True, rotation=True)
dish_panel.data.materials.append(mat_inox)

# Display / Indicatore LED centrale
dish_disp_name = "Lavastoviglie_Display"
dish_disp = bpy.data.objects.get(dish_disp_name)
if dish_disp:
    bpy.data.objects.remove(dish_disp, do_unlink=True)

bpy.ops.mesh.primitive_cube_add(size=1.0)
dish_disp = bpy.context.active_object
dish_disp.name = dish_disp_name
d_center_x = (dish_x_min + dish_x_max) / 2.0
d_width = 0.160
d_height = 0.030
dish_disp.location = (d_center_x, -7.076, (p_z_min + p_z_max) / 2.0)
dish_disp.scale = (d_width, 0.005, d_height)
bpy.ops.object.transform_apply(location=True, scale=True, rotation=True)
dish_disp.data.materials.append(mat_display)

# Maniglia orizzontale in ottone/inox coordinata
dish_handle_name = "Lavastoviglie_Maniglia"
dish_handle = bpy.data.objects.get(dish_handle_name)
if dish_handle:
    bpy.data.objects.remove(dish_handle, do_unlink=True)

bpy.ops.mesh.primitive_cube_add(size=1.0)
dish_handle = bpy.context.active_object
dish_handle.name = dish_handle_name
h_width = 0.280
dish_handle.location = (d_center_x, -7.060, 0.740)
dish_handle.scale = (h_width, 0.020, 0.020)
bpy.ops.object.transform_apply(location=True, scale=True, rotation=True)
if mat_maniglie:
    dish_handle.data.materials.append(mat_maniglie)

# Assegna custom properties per Home Assistant su Lavastoviglie
for o in [dish_obj, dish_panel, dish_disp]:
    o["ha_entity"] = "sensor.lavastoviglie_stato_di_funzionamento"
    o["ha_ui_type"] = "dishwasher"
    o["ha_name"] = "Lavastoviglie"
    o["ha_action"] = "modal"

# Assicura che gli oggetti siano nella collection corretta
coll_dev = bpy.data.collections.get("Devices") or bpy.data.collections.get("Cucina") or bpy.context.scene.collection
for o in [dish_obj, dish_bugna, dish_panel, dish_disp, dish_handle]:
    if o.name not in coll_dev.objects:
        coll_dev.objects.link(o)
    if o.name in bpy.context.scene.collection.objects and coll_dev != bpy.context.scene.collection:
        bpy.context.scene.collection.objects.unlink(o)

# Salva il file .blend
bpy.ops.wm.save_mainfile()
print(">>> SUCCESS: Smart_Home_3D.blend updated with accurate dishwasher and drawers layout! <<<")

