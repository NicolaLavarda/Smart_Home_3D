"""
Script to create all Home Assistant devices, 3D meshes, and Custom Properties
in Smart_Home_3D.blend based on user feedback and SSoT principles.
"""

import bpy
import bmesh
import math
from mathutils import Vector

def clear_previous_user_devices():
    """Removes previous created device objects if re-running the script to prevent duplicates."""
    to_delete = []
    for obj in bpy.data.objects:
        if obj.name.startswith(("Bollard_Garden_", "Wall_Garden_Light_", "Spot_Salotto_",
                                "Applique_Salotto_", "Portico_Wall_Light_", "Thermal_",
                                "Sensor_Puffer_", "Sensor_Caldaia_", "Switch_Caldaia_",
                                "Switch_Gate_Ped", "Switch_Gate_Carraio", "Switch_Garage_Door",
                                "Sensor_Dishwasher")):
            to_delete.append(obj)
    for obj in to_delete:
        bpy.data.objects.remove(obj, do_unlink=True)
    print(f"Cleared {len(to_delete)} previous device objects.")

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
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs['Base Color'].default_value = color
        bsdf.inputs['Roughness'].default_value = roughness
        bsdf.inputs['Metallic'].default_value = metallic
        if 'Emission Color' in bsdf.inputs:
            bsdf.inputs['Emission Color'].default_value = emission_color
            bsdf.inputs['Emission Strength'].default_value = emission_strength
    return mat

def update_wall_box(name, xmin, xmax, ymin, ymax, zmin, zmax):
    """Reshapes an 8-vertex wall prism cleanly with zero parenting offset."""
    obj = bpy.data.objects.get(name)
    if not obj:
        print(f"Object {name} not found!")
        return
    obj.parent = None
    obj.location = Vector((0, 0, 0))
    obj.rotation_euler = (0, 0, 0)
    obj.scale = Vector((1, 1, 1))

    mesh = obj.data
    coords = [
        (xmin, ymin, zmin), (xmax, ymin, zmin), (xmax, ymax, zmin), (xmin, ymax, zmin),
        (xmin, ymin, zmax), (xmax, ymin, zmax), (xmax, ymax, zmax), (xmin, ymax, zmax)
    ]
    if len(mesh.vertices) == 8:
        for i, co in enumerate(coords):
            mesh.vertices[i].co = Vector(co)
        mesh.update()
        print(f"[OK] Ridimensionato muretto {name} (spessore 8cm, box doccia compatto).")
    else:
        print(f"Warning: {name} has {len(mesh.vertices)} vertices.")

def build_all():
    clear_previous_user_devices()

    # -------------------------------------------------------------
    # 0. RIDIMENSIONA I MURETTI INTERNI DEL BOX DOCCIA IN LAVANDERIA
    # Muretti molto meno spessi (8cm invece di 22cm), box doccia più compatto
    # -------------------------------------------------------------
    # Parete ovest doccia: X=[1.76, 1.87] (11cm spessore, ridotta all'80% in X)
    update_wall_box('Wall_Lav_Part_V1', 1.760, 1.870, -15.230, -14.350, 0.0, 2.70)
    # Parete nord doccia: Y=[-14.46, -14.35] (11cm spessore), apertura 47cm
    update_wall_box('Wall_Lav_Part_H1', 1.760, 2.500, -14.460, -14.350, 0.0, 2.70)
    # Parete est doccia: X=[2.97, 3.08] (11cm spessore)
    update_wall_box('Wall_Lav_Part_V2', 2.970, 3.080, -15.230, -14.350, 0.0, 2.70)

    coll_devices = get_or_create_collection("HA_SSoT_Devices")

    # --- MATERIALS ---
    mat_bollard = get_or_create_material("Mat_Bollard_Dark", color=(0.12, 0.13, 0.14, 1.0), roughness=0.55, metallic=0.2)
    mat_frosted = get_or_create_material("Mat_Frosted_Diffuser", color=(0.95, 0.94, 0.90, 1.0), roughness=0.25, metallic=0.0, emission_color=(1.0, 0.90, 0.75, 1.0), emission_strength=0.2)
    mat_spot_glass = get_or_create_material("Mat_Spot_Glass", color=(0.98, 0.97, 0.95, 1.0), roughness=0.15, emission_color=(1.0, 0.95, 0.85, 1.0), emission_strength=0.5)

    mat_puffer = get_or_create_material("Mat_Puffer_Grey", color=(0.28, 0.30, 0.32, 1.0), roughness=0.45, metallic=0.15)
    mat_puffer_cap = get_or_create_material("Mat_Puffer_Cap", color=(0.08, 0.08, 0.09, 1.0), roughness=0.6, metallic=0.05)
    mat_caldaia = get_or_create_material("Mat_Caldaia_White", color=(0.94, 0.94, 0.95, 1.0), roughness=0.25, metallic=0.02)
    mat_display = get_or_create_material("Mat_Caldaia_Display", color=(0.05, 0.05, 0.05, 1.0), roughness=0.1, emission_color=(0.3, 0.7, 1.0, 1.0), emission_strength=0.8)
    mat_switch = get_or_create_material("Mat_Switch_Plate", color=(0.92, 0.92, 0.94, 1.0), roughness=0.3, metallic=0.1)
    mat_spot_metal = get_or_create_material("Mat_Spot_Metal", color=(0.90, 0.90, 0.92, 1.0), roughness=0.25, metallic=0.8)

    # -------------------------------------------------------------
    # 1. SALOTTO CEILING SPOTLIGHTS (light.smart_plug_in_unit_switch_3)
    # ESATTAMENTE 6 faretti incassati singoli (NO parenting, NO duplicati in quota)
    # -------------------------------------------------------------
    spot_positions = [
        ("Spot_Salotto_1", 2.00, -1.60, 2.98),
        ("Spot_Salotto_2", 4.40, -1.60, 2.98),
        ("Spot_Salotto_3", 2.00, -3.55, 2.98),
        ("Spot_Salotto_4", 4.40, -3.55, 2.98),
        ("Spot_Salotto_5", 2.00, -5.40, 2.98),
        ("Spot_Salotto_6", 4.40, -5.40, 2.98),
    ]

    for name, sx, sy, sz in spot_positions:
        bpy.ops.mesh.primitive_cylinder_add(radius=0.08, depth=0.02, vertices=24, location=(sx, sy, sz))
        spot = bpy.context.active_object
        spot.name = name
        spot.data.materials.append(mat_spot_glass)
        spot["ha_entity"] = "light.smart_plug_in_unit_switch_3"
        spot["ha_ui_type"] = "light"
        spot["ha_name"] = "Faretto Salotto"
        spot["ha_action"] = "toggle"
        coll_devices.objects.link(spot)
        bpy.context.scene.collection.objects.unlink(spot)

    # -------------------------------------------------------------
    # 2. SALOTTO WALL SCONCES (light.1 and light.2)
    # -------------------------------------------------------------
    # light.1: Applique on East wall between sliding door and NE corner
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(6.05, -2.07, 1.95))
    sconce_e = bpy.context.active_object
    sconce_e.name = "Applique_Salotto_Est"
    sconce_e.scale = Vector((0.08, 0.16, 0.18))
    sconce_e.data.materials.append(mat_bollard)
    sconce_e["ha_entity"] = "light.1"
    sconce_e["ha_ui_type"] = "light"
    sconce_e["ha_name"] = "Applique Salotto Est"
    sconce_e["ha_action"] = "toggle"
    coll_devices.objects.link(sconce_e)
    bpy.context.scene.collection.objects.unlink(sconce_e)

    # light.2: Applique on North wall center
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(3.14, -0.32, 1.95))
    sconce_n = bpy.context.active_object
    sconce_n.name = "Applique_Salotto_Nord"
    sconce_n.scale = Vector((0.16, 0.08, 0.18))
    sconce_n.data.materials.append(mat_bollard)
    sconce_n["ha_entity"] = "light.2"
    sconce_n["ha_ui_type"] = "light"
    sconce_n["ha_name"] = "Applique Salotto Nord"
    sconce_n["ha_action"] = "toggle"
    coll_devices.objects.link(sconce_n)
    bpy.context.scene.collection.objects.unlink(sconce_n)

    # -------------------------------------------------------------
    # 3. PORTICO LIGHTS (light.portico)
    # 2 wall sconces: SW corner and NE corner
    # -------------------------------------------------------------
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.80, -12.41, 2.20))
    portico_sw = bpy.context.active_object
    portico_sw.name = "Portico_Wall_Light_SW"
    portico_sw.scale = Vector((0.14, 0.08, 0.16))
    portico_sw.data.materials.append(mat_bollard)
    portico_sw["ha_entity"] = "light.portico"
    portico_sw["ha_ui_type"] = "light"
    portico_sw["ha_name"] = "Luce Portico Ovest"
    portico_sw["ha_action"] = "toggle"
    coll_devices.objects.link(portico_sw)
    bpy.context.scene.collection.objects.unlink(portico_sw)

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(4.40, -7.13, 2.20))
    portico_ne = bpy.context.active_object
    portico_ne.name = "Portico_Wall_Light_NE"
    portico_ne.scale = Vector((0.14, 0.08, 0.16))
    portico_ne.data.materials.append(mat_bollard)
    portico_ne["ha_entity"] = "light.portico"
    portico_ne["ha_ui_type"] = "light"
    portico_ne["ha_name"] = "Luce Portico Est"
    portico_ne["ha_action"] = "toggle"
    coll_devices.objects.link(portico_ne)
    bpy.context.scene.collection.objects.unlink(portico_ne)

    # -------------------------------------------------------------
    # 4. GARDEN LIGHTS (light.luci_esterne)
    # 4 square bollards matching media_1794393742557_21d29c1a.jpg
    # + 4 wall sconces along Muro_Cinta_Est
    # -------------------------------------------------------------
    bollard_coords = [
        ("Bollard_Garden_1", -4.00, -5.90, 0.00),
        ("Bollard_Garden_2", -1.00, -5.90, 0.00),
        ("Bollard_Garden_3", -3.80, -18.00, 0.00),
        ("Bollard_Garden_4",  2.20, -18.25, 0.00),
    ]

    for name, bx, by, bz in bollard_coords:
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(bx, by, bz + 0.01))
        b_base = bpy.context.active_object
        b_base.name = f"{name}_Base"
        b_base.scale = Vector((0.20, 0.20, 0.02))
        b_base.data.materials.append(mat_bollard)
        coll_devices.objects.link(b_base)
        bpy.context.scene.collection.objects.unlink(b_base)

        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(bx, by, bz + 0.02 + 0.52/2))
        b_col = bpy.context.active_object
        b_col.name = f"{name}_Pillar"
        b_col.scale = Vector((0.16, 0.16, 0.52))
        b_col.data.materials.append(mat_bollard)
        coll_devices.objects.link(b_col)
        bpy.context.scene.collection.objects.unlink(b_col)

        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(bx, by, bz + 0.54 + 0.22/2))
        b_diff = bpy.context.active_object
        b_diff.name = name
        b_diff.scale = Vector((0.145, 0.145, 0.22))
        b_diff.data.materials.append(mat_frosted)
        b_diff["ha_entity"] = "light.luci_esterne"
        b_diff["ha_ui_type"] = "light"
        b_diff["ha_name"] = "Lampioncino Giardino"
        b_diff["ha_action"] = "toggle"
        coll_devices.objects.link(b_diff)
        bpy.context.scene.collection.objects.unlink(b_diff)

        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(bx, by, bz + 0.76 + 0.02))
        b_cap = bpy.context.active_object
        b_cap.name = f"{name}_Cap"
        b_cap.scale = Vector((0.17, 0.17, 0.04))
        b_cap.data.materials.append(mat_bollard)
        coll_devices.objects.link(b_cap)
        bpy.context.scene.collection.objects.unlink(b_cap)

    # 4 wall sconces along Muro_Cinta_Est bordering Giardino Area 2
    # Spanning between house south wall (Y = -8.05) and garage north pillar (Y = -17.13)
    # Height = 0.60m from ground (60cm da terra)
    wall_lights_y = [-9.87, -11.68, -13.50, -15.31]
    for idx, wy in enumerate(wall_lights_y, start=1):
        wname = f"Wall_Garden_Light_{idx}"
        
        # 1. Dark metal fixture housing on the east wall
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(13.91, wy, 0.60))
        wl_body = bpy.context.active_object
        wl_body.name = f"{wname}_Body"
        wl_body.scale = Vector((0.04, 0.16, 0.12))
        wl_body.data.materials.append(mat_bollard)
        coll_devices.objects.link(wl_body)
        bpy.context.scene.collection.objects.unlink(wl_body)

        # 2. Recessed frosted lens facing west (-X into Giardino Area 2)
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(13.88, wy, 0.58))
        wl = bpy.context.active_object
        wl.name = wname
        wl.scale = Vector((0.02, 0.12, 0.06))
        wl.data.materials.append(mat_frosted)
        wl["ha_entity"] = "light.luci_esterne"
        wl["ha_ui_type"] = "light"
        wl["ha_name"] = f"Luce Muro Giardino {idx}"
        wl["ha_action"] = "toggle"
        coll_devices.objects.link(wl)
        bpy.context.scene.collection.objects.unlink(wl)

    # 4b. Disaccoppia i diffusori lampade Isola Bancone da Mat_Laccato_Bianco
    mat_isola_lamp = get_or_create_material("Mat_Lampada_Isola", color=(0.95, 0.94, 0.90, 1.0), roughness=0.35, metallic=0.0, emission_color=(1.0, 0.95, 0.85, 1.0), emission_strength=0.0)
    for obj_name in ["Isola_Lampada_Cono_1", "Isola_Lampada_Cono_2"]:
        lamp_obj = bpy.data.objects.get(obj_name)
        if lamp_obj and lamp_obj.data.materials:
            lamp_obj.data.materials[0] = mat_isola_lamp

    # Calibra Mat_Laccato_Bianco per non essere abbagliante o auto-illuminante
    mat_laccato = bpy.data.materials.get("Mat_Laccato_Bianco")
    if mat_laccato and mat_laccato.node_tree:
        bsdf = mat_laccato.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            if "Base Color" in bsdf.inputs:
                bsdf.inputs["Base Color"].default_value = (0.82, 0.81, 0.79, 1.0)
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = 0.65
            if "Emission Color" in bsdf.inputs:
                bsdf.inputs["Emission Color"].default_value = (0.0, 0.0, 0.0, 1.0)
            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = 0.0

    # -------------------------------------------------------------
    # 5. CENTRALE TERMICA IN LAVANDERIA SULLA PARETE A SUD
    # "nella parete a sud tra il muro ovest della lavanderia e il muretto del box doccia"
    # Spazio tra Muro Ovest (X=0.30) e Muretto Doccia (X=1.65): larghezza 1.35m
    # Inversione richiesta dall'utente: Accumulo (Puffer) a SINISTRA e Caldaia a DESTRA
    # Nella vista verso la parete Sud (+Z Three.js / -Y Blender):
    # Sinistra vista = X maggiore (X=1.25), Destra vista = X minore (X=0.65)
    # Entrambi affiancati con retro contro la parete Sud (Y=-15.23) e fronte verso Nord (+Y)
    # -------------------------------------------------------------
    # 1) Accumulatore / Puffer (cilindro grigio scuro con cupola nera) a SINISTRA
    p_x, p_y = 1.25, -14.85
    bpy.ops.mesh.primitive_cylinder_add(radius=0.30, depth=1.52, vertices=32, location=(p_x, p_y, 0.76))
    puffer_body = bpy.context.active_object
    puffer_body.name = "Thermal_Puffer_Tank"
    puffer_body.data.materials.append(mat_puffer)
    coll_devices.objects.link(puffer_body)
    bpy.context.scene.collection.objects.unlink(puffer_body)

    # Calotta nera superiore
    bpy.ops.mesh.primitive_cylinder_add(radius=0.31, depth=0.12, vertices=32, location=(p_x, p_y, 1.58))
    puffer_cap = bpy.context.active_object
    puffer_cap.name = "Thermal_Puffer_Cap"
    puffer_cap.data.materials.append(mat_puffer_cap)
    coll_devices.objects.link(puffer_cap)
    bpy.context.scene.collection.objects.unlink(puffer_cap)

    # Manometro frontale a quadrante
    bpy.ops.mesh.primitive_cylinder_add(radius=0.045, depth=0.02, vertices=24, location=(p_x, p_y + 0.305, 1.35), rotation=(math.pi/2, 0, 0))
    p_dial = bpy.context.active_object
    p_dial.name = "Thermal_Puffer_Dial"
    p_dial.data.materials.append(mat_spot_metal)
    coll_devices.objects.link(p_dial)
    bpy.context.scene.collection.objects.unlink(p_dial)

    # SENSOR 1: sensor.temperatura_accumulo_alto (Cerchio rosso alto sul fronte del puffer, orientato verso Nord +Y)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.05, depth=0.015, vertices=24, location=(p_x, p_y + 0.31, 1.18), rotation=(math.pi/2, 0, 0))
    s_p_high = bpy.context.active_object
    s_p_high.name = "Sensor_Puffer_High"
    s_p_high.data.materials.append(mat_frosted)
    s_p_high["ha_entity"] = "sensor.temperatura_accumulo_alto"
    s_p_high["ha_ui_type"] = "sensor"
    s_p_high["ha_name"] = "Temp. Accumulo Alto"
    s_p_high["ha_badge_style"] = "puffer_high"
    coll_devices.objects.link(s_p_high)
    bpy.context.scene.collection.objects.unlink(s_p_high)

    # SENSOR 2: sensor.temperatura_accumulo_basso (Cerchio blu basso sul fronte del puffer)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.05, depth=0.015, vertices=24, location=(p_x, p_y + 0.31, 0.48), rotation=(math.pi/2, 0, 0))
    s_p_low = bpy.context.active_object
    s_p_low.name = "Sensor_Puffer_Low"
    s_p_low.data.materials.append(mat_frosted)
    s_p_low["ha_entity"] = "sensor.temperatura_accumulo_basso"
    s_p_low["ha_ui_type"] = "sensor"
    s_p_low["ha_name"] = "Temp. Accumulo Basso"
    s_p_low["ha_badge_style"] = "puffer_low"
    coll_devices.objects.link(s_p_low)
    bpy.context.scene.collection.objects.unlink(s_p_low)

    # 2) Caldaia a DESTRA del puffer, sempre contro la parete Sud
    c_x, c_y = 0.65, -14.98
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(c_x, c_y, 0.70))
    caldaia_box = bpy.context.active_object
    caldaia_box.name = "Thermal_Caldaia_Box"
    caldaia_box.scale = Vector((0.44, 0.38, 1.40))
    caldaia_box.data.materials.append(mat_caldaia)
    coll_devices.objects.link(caldaia_box)
    bpy.context.scene.collection.objects.unlink(caldaia_box)

    # Display digitale frontale
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(c_x, c_y + 0.192, 1.20))
    c_disp = bpy.context.active_object
    c_disp.name = "Thermal_Caldaia_Display"
    c_disp.scale = Vector((0.14, 0.01, 0.08))
    c_disp.data.materials.append(mat_display)
    coll_devices.objects.link(c_disp)
    bpy.context.scene.collection.objects.unlink(c_disp)

    # Tubo scarico fumi superiore
    bpy.ops.mesh.primitive_cylinder_add(radius=0.055, depth=0.15, vertices=24, location=(c_x, c_y, 1.47))
    c_pipe = bpy.context.active_object
    c_pipe.name = "Thermal_Caldaia_Flue"
    c_pipe.data.materials.append(mat_spot_metal)
    coll_devices.objects.link(c_pipe)
    bpy.context.scene.collection.objects.unlink(c_pipe)

    # SENSOR 3: sensor.temperatura_caldaia (Cerchio rosso al centro ad altezza circa 3/4 caldaia)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.05, depth=0.015, vertices=24, location=(c_x, c_y + 0.192, 1.05), rotation=(math.pi/2, 0, 0))
    s_caldaia = bpy.context.active_object
    s_caldaia.name = "Sensor_Caldaia_Temp"
    s_caldaia.data.materials.append(mat_frosted)
    s_caldaia["ha_entity"] = "sensor.temperatura_caldaia"
    s_caldaia["ha_ui_type"] = "sensor"
    s_caldaia["ha_name"] = "Temp. Caldaia"
    s_caldaia["ha_badge_style"] = "caldaia"
    coll_devices.objects.link(s_caldaia)
    bpy.context.scene.collection.objects.unlink(s_caldaia)

    # Interruttore on/off caldaia a muro sulla parete di fronte (Wall_Lav_North_01)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.90, -12.60, 1.20))
    sw_caldaia = bpy.context.active_object
    sw_caldaia.name = "Switch_Caldaia_Wall"
    sw_caldaia.scale = Vector((0.10, 0.02, 0.10))
    sw_caldaia.data.materials.append(mat_switch)
    sw_caldaia["ha_entity"] = "switch.smart_switch_caldaia"
    sw_caldaia["ha_ui_type"] = "switch"
    sw_caldaia["ha_name"] = "Interruttore Caldaia"
    sw_caldaia["ha_action"] = "toggle"
    coll_devices.objects.link(sw_caldaia)
    bpy.context.scene.collection.objects.unlink(sw_caldaia)

    # -------------------------------------------------------------
    # 6. GATES AND ACCESS SWITCHES
    # - Cancello Carraio al CENTRO del cancello nero a sinistra del cancelletto (-6.60, -0.20, 0.85)
    # - Cancelletto Pedonale sul montante del cancelletto (-4.24, -0.20, 1.05)
    # - Serranda Garage al centro del portone (6.54, -20.73, 1.15)
    # -------------------------------------------------------------
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-6.60, -0.20, 0.85))
    sw_carraio = bpy.context.active_object
    sw_carraio.name = "Switch_Gate_Carraio"
    sw_carraio.scale = Vector((0.08, 0.06, 0.14))
    sw_carraio.data.materials.append(mat_bollard)
    sw_carraio["ha_entity"] = "switch.switch_casa_interruttore_1"
    sw_carraio["ha_ui_type"] = "switch"
    sw_carraio["ha_name"] = "Cancello Carraio"
    sw_carraio["ha_action"] = "toggle"
    coll_devices.objects.link(sw_carraio)
    bpy.context.scene.collection.objects.unlink(sw_carraio)

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-4.24, -0.20, 1.05))
    sw_gate = bpy.context.active_object
    sw_gate.name = "Switch_Gate_Ped"
    sw_gate.scale = Vector((0.04, 0.06, 0.12))
    sw_gate.data.materials.append(mat_bollard)
    sw_gate["ha_entity"] = "switch.switch_casa_interruttore_2"
    sw_gate["ha_ui_type"] = "switch"
    sw_gate["ha_name"] = "Serratura Cancelletto"
    sw_gate["ha_action"] = "toggle"
    coll_devices.objects.link(sw_gate)
    bpy.context.scene.collection.objects.unlink(sw_gate)

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(6.54, -20.73, 1.15))
    sw_gar = bpy.context.active_object
    sw_gar.name = "Switch_Garage_Door"
    sw_gar.scale = Vector((0.03, 0.10, 0.14))
    sw_gar.data.materials.append(mat_switch)
    sw_gar["ha_entity"] = "switch.switch_casa_interruttore_3"
    sw_gar["ha_ui_type"] = "switch"
    sw_gar["ha_name"] = "Serranda Garage"
    sw_gar["ha_action"] = "toggle"
    coll_devices.objects.link(sw_gar)
    bpy.context.scene.collection.objects.unlink(sw_gar)

    # -------------------------------------------------------------
    # 7. KITCHEN DISHWASHER (LAVASTOVIGLIE)
    # -------------------------------------------------------------
    dish_obj = bpy.data.objects.get("Lavastoviglie")
    if dish_obj:
        dish_obj["ha_entity"] = "sensor.lavastoviglie_stato_di_funzionamento"
        dish_obj["ha_ui_type"] = "dishwasher"
        dish_obj["ha_name"] = "Lavastoviglie"
        dish_obj["ha_action"] = "modal"
        if dish_obj.name not in coll_devices.objects:
            coll_devices.objects.link(dish_obj)

    # -------------------------------------------------------------
    # 8. TELECAMERA DI SICUREZZA
    # -------------------------------------------------------------
    cam_carraio = bpy.data.objects.get("Cam_Carraio")
    if cam_carraio:
        cam_carraio["ha_entity"] = "camera.carraio_scorrevole"
        cam_carraio["ha_alt_entity"] = "camera.carraio_trasparente"
        cam_carraio["ha_ui_type"] = "camera"
        cam_carraio["ha_name"] = "Telecamera Carraio"
        cam_carraio["ha_action"] = "stream"

    # Salva il file .blend
    bpy.ops.wm.save_mainfile()
    print("SUCCESS: Smart_Home_3D.blend updated with all user adjustments!")

if __name__ == "__main__":
    build_all()
