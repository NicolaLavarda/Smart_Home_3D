"""
setup_ha_properties.py
Configura le Custom Properties SSoT e la vera telecamera di sicurezza su Smart_Home_3D.blend.
"""

import sys
import math
import bpy
import mathutils

GROUND_COLLIDERS = [
    # Aree esterne
    "Driveway_Gravel",
    "Giardino_Area_1_Prato",
    "Giardino_Area_2_Prato",
    "Giardino_Area_3A_Prato",
    "Giardino_Area_3B_Prato",
    "Giardino_Area_3C_Prato",
    "Portico_Pavement_Unified",
    "Terrazza_All_Aperto",
    "Walkway_Pedestrian_Pavement",
    "Site_Foundation_Earth",
    # Pavimenti interni
    "Floor_Salotto",
    "Floor_Dining_Main",
    "Floor_Dining_NorthWing",
    "Floor_Dining_Passage",
    "Floor_Bagno",
    "Floor_Antibagno",
    "Floor_Lavanderia",
    "Floor_Garage_Main",
    "Floor_Garage_EastStair",
    "Floor_Garage_WestStair",
]

# Nuovi mapping specificati dall'utente in base a Home Assistant reale
ENTITY_MAPPINGS = {
    # 1. Lampadario sopra al tavolo in cucina -> entità "light.forno"
    "Lampadario_Coppa_1": {
        "ha_entity": "light.forno",
        "ha_action": "toggle",
        "ha_ui_type": "light_emissive",
        "ha_name": "Lampadario Tavolo (HA: Forno)",
    },
    "Lampadario_Coppa_2": {
        "ha_entity": "light.forno",
        "ha_action": "toggle",
        "ha_ui_type": "light_emissive",
        "ha_name": "Lampadario Tavolo (HA: Forno)",
    },
    "Lampadario_Coppa_3": {
        "ha_entity": "light.forno",
        "ha_action": "toggle",
        "ha_ui_type": "light_emissive",
        "ha_name": "Lampadario Tavolo (HA: Forno)",
    },
    "Lampadario_Coppa_4": {
        "ha_entity": "light.forno",
        "ha_action": "toggle",
        "ha_ui_type": "light_emissive",
        "ha_name": "Lampadario Tavolo (HA: Forno)",
    },
    "Lampadario_Pranzo_Asta": {
        "ha_entity": "light.forno",
        "ha_action": "toggle",
        "ha_ui_type": "light_emissive",
        "ha_name": "Lampadario Tavolo (Asta)",
    },
    # 2. Luci sopra al bancone -> entità "light.bancone"
    "Isola_Lampada_Cono_1": {
        "ha_entity": "light.bancone",
        "ha_action": "toggle",
        "ha_ui_type": "light_emissive",
        "ha_name": "Luce Bancone Ovest (HA: Bancone)",
    },
    "Isola_Lampada_Cono_2": {
        "ha_entity": "light.bancone",
        "ha_action": "toggle",
        "ha_ui_type": "light_emissive",
        "ha_name": "Luce Bancone Est (HA: Bancone)",
    },
    # 3. Cancello -> switch reale su HA: switch.switch_casa_interruttore_1
    "Gate_Leaf_L": {
        "ha_entity": "switch.switch_casa_interruttore_1",
        "ha_action": "toggle",
        "ha_ui_type": "sliding_gate",
        "ha_name": "Cancello Carraio",
    },
    "Gate_Leaf_R": {
        "ha_entity": "switch.switch_casa_interruttore_1",
        "ha_action": "toggle",
        "ha_ui_type": "sliding_gate",
        "ha_name": "Cancello Carraio",
    },
    # 4. Lavastoviglie -> sensor reale su HA: sensor.lavastoviglie_stato_di_funzionamento
    "Lavastoviglie": {
        "ha_entity": "sensor.lavastoviglie_stato_di_funzionamento",
        "ha_action": "modal",
        "ha_ui_type": "dishwasher",
        "ha_name": "Lavastoviglie",
    },
    "Lavastoviglie_Pannello_Comandi": {
        "ha_entity": "sensor.lavastoviglie_stato_di_funzionamento",
        "ha_action": "modal",
        "ha_ui_type": "dishwasher",
        "ha_name": "Lavastoviglie Comandi",
    },
    "Lavastoviglie_Display": {
        "ha_entity": "sensor.lavastoviglie_stato_di_funzionamento",
        "ha_action": "modal",
        "ha_ui_type": "dishwasher",
        "ha_name": "Lavastoviglie Display",
    },
    # 5. Smart TV -> media_player reale su HA: media_player.smart_tv_lg_oled_2
    "TV_Salotto_Screen": {
        "ha_entity": "media_player.smart_tv_lg_oled_2",
        "ha_action": "modal",
        "ha_ui_type": "tv_display",
        "ha_name": "Smart TV LG OLED",
    },
    "TV_Salotto_Bezel": {
        "ha_entity": "media_player.smart_tv_lg_oled_2",
        "ha_action": "modal",
        "ha_ui_type": "tv_frame",
        "ha_name": "Smart TV Frame",
    },
    # 6. Salotto - Applique Parete Est -> light.1
    "Applique_Salotto_Est": {
        "ha_entity": "light.1",
        "ha_action": "toggle",
        "ha_ui_type": "light_emissive",
        "ha_name": "Applique Salotto Est",
    },
    # 7. Salotto - Applique Parete Nord -> light.2
    "Applique_Salotto_Nord": {
        "ha_entity": "light.2",
        "ha_action": "toggle",
        "ha_ui_type": "light_emissive",
        "ha_name": "Applique Salotto Nord",
    },
    # 8. Salotto - Faretti a Soffitto 2x3 -> light.smart_plug_in_unit_switch_3
    "Salotto_Faretto_1": {
        "ha_entity": "light.smart_plug_in_unit_switch_3",
        "ha_action": "toggle",
        "ha_ui_type": "light_emissive",
        "ha_name": "Faretto Soffitto Salotto 1",
    },
    "Salotto_Faretto_2": {
        "ha_entity": "light.smart_plug_in_unit_switch_3",
        "ha_action": "toggle",
        "ha_ui_type": "light_emissive",
        "ha_name": "Faretto Soffitto Salotto 2",
    },
    "Salotto_Faretto_3": {
        "ha_entity": "light.smart_plug_in_unit_switch_3",
        "ha_action": "toggle",
        "ha_ui_type": "light_emissive",
        "ha_name": "Faretto Soffitto Salotto 3",
    },
    "Salotto_Faretto_4": {
        "ha_entity": "light.smart_plug_in_unit_switch_3",
        "ha_action": "toggle",
        "ha_ui_type": "light_emissive",
        "ha_name": "Faretto Soffitto Salotto 4",
    },
    "Salotto_Faretto_5": {
        "ha_entity": "light.smart_plug_in_unit_switch_3",
        "ha_action": "toggle",
        "ha_ui_type": "light_emissive",
        "ha_name": "Faretto Soffitto Salotto 5",
    },
    "Salotto_Faretto_6": {
        "ha_entity": "light.smart_plug_in_unit_switch_3",
        "ha_action": "toggle",
        "ha_ui_type": "light_emissive",
        "ha_name": "Faretto Soffitto Salotto 6",
    },
    # 9. Giardino e Portico (Luci esterne)
    "Bollard_Garden_1": {
        "ha_entity": "light.luci_esterne",
        "ha_action": "toggle",
        "ha_ui_type": "light",
        "ha_name": "Lampioncino Giardino 1",
    },
    "Bollard_Garden_2": {
        "ha_entity": "light.luci_esterne",
        "ha_action": "toggle",
        "ha_ui_type": "light",
        "ha_name": "Lampioncino Giardino 2",
    },
    "Bollard_Garden_3": {
        "ha_entity": "light.luci_esterne",
        "ha_action": "toggle",
        "ha_ui_type": "light",
        "ha_name": "Lampioncino Giardino 3",
    },
    "Bollard_Garden_4": {
        "ha_entity": "light.luci_esterne",
        "ha_action": "toggle",
        "ha_ui_type": "light",
        "ha_name": "Lampioncino Giardino 4",
    },
    "Wall_Garden_Light_1": {
        "ha_entity": "light.luci_esterne",
        "ha_action": "toggle",
        "ha_ui_type": "light",
        "ha_name": "Luce Muro Giardino 1",
    },
    "Wall_Garden_Light_2": {
        "ha_entity": "light.luci_esterne",
        "ha_action": "toggle",
        "ha_ui_type": "light",
        "ha_name": "Luce Muro Giardino 2",
    },
    "Wall_Garden_Light_3": {
        "ha_entity": "light.luci_esterne",
        "ha_action": "toggle",
        "ha_ui_type": "light",
        "ha_name": "Luce Muro Giardino 3",
    },
    "Wall_Garden_Light_4": {
        "ha_entity": "light.luci_esterne",
        "ha_action": "toggle",
        "ha_ui_type": "light",
        "ha_name": "Luce Muro Giardino 4",
    },
    "Portico_Wall_Light_SW": {
        "ha_entity": "light.portico",
        "ha_action": "toggle",
        "ha_ui_type": "light",
        "ha_name": "Luce Portico Ovest",
    },
    "Portico_Wall_Light_NE": {
        "ha_entity": "light.portico",
        "ha_action": "toggle",
        "ha_ui_type": "light",
        "ha_name": "Luce Portico Est",
    },
    # 10. Interruttori Cancelli e Garage
    "Switch_Gate_Carraio": {
        "ha_entity": "switch.switch_casa_interruttore_1",
        "ha_action": "toggle",
        "ha_ui_type": "switch",
        "ha_name": "Cancello Carraio",
    },
    "Switch_Gate_Ped": {
        "ha_entity": "switch.switch_casa_interruttore_2",
        "ha_action": "toggle",
        "ha_ui_type": "switch",
        "ha_name": "Serratura Cancelletto",
    },
    "Switch_Garage_Door": {
        "ha_entity": "switch.switch_casa_interruttore_3",
        "ha_action": "toggle",
        "ha_ui_type": "switch",
        "ha_name": "Serranda Garage",
    },
    # 11. Centrale Termica Lavanderia
    "Sensor_Puffer_High": {
        "ha_entity": "sensor.temperatura_accumulo_alto",
        "ha_ui_type": "sensor",
        "ha_name": "Temp. Accumulo Alto",
        "ha_badge_style": "puffer_high",
    },
    "Sensor_Puffer_Low": {
        "ha_entity": "sensor.temperatura_accumulo_basso",
        "ha_ui_type": "sensor",
        "ha_name": "Temp. Accumulo Basso",
        "ha_badge_style": "puffer_low",
    },
    "Sensor_Caldaia_Temp": {
        "ha_entity": "sensor.temperatura_caldaia",
        "ha_ui_type": "sensor",
        "ha_name": "Temp. Caldaia",
        "ha_badge_style": "caldaia",
    },
    "Switch_Caldaia_Wall": {
        "ha_entity": "switch.smart_switch_caldaia",
        "ha_action": "toggle",
        "ha_ui_type": "switch",
        "ha_name": "Interruttore Caldaia",
    },
    # 12. Robot Aspirapolvere Ecovacs Deebot (Sala da pranzo muro Est vicino al camino)
    "Ecovacs_Deebot_Body": {
        "ha_entity": "vacuum.deebot",
        "ha_action": "modal",
        "ha_ui_type": "vacuum",
        "ha_name": "Ecovacs Deebot",
    },
    "Ecovacs_Deebot_Bumper": {
        "ha_entity": "vacuum.deebot",
        "ha_action": "modal",
        "ha_ui_type": "vacuum",
        "ha_name": "Ecovacs Deebot",
    },
    "Ecovacs_Deebot_Lidar": {
        "ha_entity": "vacuum.deebot",
        "ha_action": "modal",
        "ha_ui_type": "vacuum",
        "ha_name": "Ecovacs Deebot",
    },
    "Ecovacs_Deebot_Lidar_Ring": {
        "ha_entity": "vacuum.deebot",
        "ha_action": "modal",
        "ha_ui_type": "vacuum",
        "ha_name": "Ecovacs Deebot",
    },
    "Ecovacs_Deebot_Power_Button": {
        "ha_entity": "vacuum.deebot",
        "ha_action": "modal",
        "ha_ui_type": "vacuum",
        "ha_name": "Ecovacs Deebot",
    },
    "Ecovacs_Deebot_Dock_Base": {
        "ha_entity": "vacuum.deebot",
        "ha_action": "modal",
        "ha_ui_type": "vacuum",
        "ha_name": "Ecovacs Deebot Stazione",
    },
    "Ecovacs_Deebot_Dock_Tower": {
        "ha_entity": "vacuum.deebot",
        "ha_action": "modal",
        "ha_ui_type": "vacuum",
        "ha_name": "Ecovacs Deebot Stazione",
    },
    "Ecovacs_Deebot_Dock_Slot": {
        "ha_entity": "vacuum.deebot",
        "ha_action": "modal",
        "ha_ui_type": "vacuum",
        "ha_name": "Ecovacs Deebot Stazione",
    },
    "Ecovacs_Deebot_Dock_LED": {
        "ha_entity": "vacuum.deebot",
        "ha_action": "modal",
        "ha_ui_type": "vacuum",
        "ha_name": "Ecovacs Deebot Stazione",
    },
    # 13. Gettini Irrigazione Giardino (Area 1, Area 2, Area 3)
    # Area 1: Prato Sud (4 gettini)
    "Sprinkler_Area1_1": { "ha_entity": "switch.smart_switch_area1", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 1 - 1" },
    "Sprinkler_Area1_1_Base": { "ha_entity": "switch.smart_switch_area1", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 1 - 1 (Base)" },
    "Sprinkler_Area1_1_Nozzle": { "ha_entity": "switch.smart_switch_area1", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 1 - 1 (Ugello)" },
    "Sprinkler_Area1_2": { "ha_entity": "switch.smart_switch_area1", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 1 - 2" },
    "Sprinkler_Area1_2_Base": { "ha_entity": "switch.smart_switch_area1", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 1 - 2 (Base)" },
    "Sprinkler_Area1_2_Nozzle": { "ha_entity": "switch.smart_switch_area1", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 1 - 2 (Ugello)" },
    "Sprinkler_Area1_3": { "ha_entity": "switch.smart_switch_area1", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 1 - 3" },
    "Sprinkler_Area1_3_Base": { "ha_entity": "switch.smart_switch_area1", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 1 - 3 (Base)" },
    "Sprinkler_Area1_3_Nozzle": { "ha_entity": "switch.smart_switch_area1", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 1 - 3 (Ugello)" },
    "Sprinkler_Area1_4": { "ha_entity": "switch.smart_switch_area1", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 1 - 4" },
    "Sprinkler_Area1_4_Base": { "ha_entity": "switch.smart_switch_area1", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 1 - 4 (Base)" },
    "Sprinkler_Area1_4_Nozzle": { "ha_entity": "switch.smart_switch_area1", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 1 - 4 (Ugello)" },
    # Area 2: Corte Est (2 gettini)
    "Sprinkler_Area2_1": { "ha_entity": "switch.smart_switch_area2", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 2 - 1" },
    "Sprinkler_Area2_1_Base": { "ha_entity": "switch.smart_switch_area2", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 2 - 1 (Base)" },
    "Sprinkler_Area2_1_Nozzle": { "ha_entity": "switch.smart_switch_area2", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 2 - 1 (Ugello)" },
    "Sprinkler_Area2_2": { "ha_entity": "switch.smart_switch_area2", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 2 - 2" },
    "Sprinkler_Area2_2_Base": { "ha_entity": "switch.smart_switch_area2", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 2 - 2 (Base)" },
    "Sprinkler_Area2_2_Nozzle": { "ha_entity": "switch.smart_switch_area2", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 2 - 2 (Ugello)" },
    # Area 3: Prato Nord & Viale Ovest (5 gettini)
    "Sprinkler_Area3_1": { "ha_entity": "switch.smart_switch_area3", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 3 - 1" },
    "Sprinkler_Area3_1_Base": { "ha_entity": "switch.smart_switch_area3", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 3 - 1 (Base)" },
    "Sprinkler_Area3_1_Nozzle": { "ha_entity": "switch.smart_switch_area3", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 3 - 1 (Ugello)" },
    "Sprinkler_Area3_2": { "ha_entity": "switch.smart_switch_area3", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 3 - 2" },
    "Sprinkler_Area3_2_Base": { "ha_entity": "switch.smart_switch_area3", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 3 - 2 (Base)" },
    "Sprinkler_Area3_2_Nozzle": { "ha_entity": "switch.smart_switch_area3", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 3 - 2 (Ugello)" },
    "Sprinkler_Area3_3": { "ha_entity": "switch.smart_switch_area3", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 3 - 3" },
    "Sprinkler_Area3_3_Base": { "ha_entity": "switch.smart_switch_area3", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 3 - 3 (Base)" },
    "Sprinkler_Area3_3_Nozzle": { "ha_entity": "switch.smart_switch_area3", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 3 - 3 (Ugello)" },
    "Sprinkler_Area3_4": { "ha_entity": "switch.smart_switch_area3", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 3 - 4" },
    "Sprinkler_Area3_4_Base": { "ha_entity": "switch.smart_switch_area3", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 3 - 4 (Base)" },
    "Sprinkler_Area3_4_Nozzle": { "ha_entity": "switch.smart_switch_area3", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 3 - 4 (Ugello)" },
    "Sprinkler_Area3_5": { "ha_entity": "switch.smart_switch_area3", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 3 - 5" },
    "Sprinkler_Area3_5_Base": { "ha_entity": "switch.smart_switch_area3", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 3 - 5 (Base)" },
    "Sprinkler_Area3_5_Nozzle": { "ha_entity": "switch.smart_switch_area3", "ha_action": "modal", "ha_ui_type": "irrigation", "ha_name": "Irrigatore Area 3 - 5 (Ugello)" },
}


SECURITY_CAMERA_NAMES = {"Cam_Carraio", "Cam_Portico", "Cam_Ingresso"}


def _get_or_create_camera_material(name, color=(0.92, 0.93, 0.95, 1.0), roughness=0.35, metallic=0.05):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name=name)
        mat.use_nodes = True
    if mat.node_tree:
        bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf:
            if "Base Color" in bsdf.inputs:
                bsdf.inputs["Base Color"].default_value = color
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = roughness
            if "Metallic" in bsdf.inputs:
                bsdf.inputs["Metallic"].default_value = metallic
    mat.diffuse_color = color
    return mat


def _link_object_exclusively(obj, target_collection):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    target_collection.objects.link(obj)


def _remove_object_if_exists(name):
    obj = bpy.data.objects.get(name)
    if obj is not None:
        bpy.data.objects.remove(obj, do_unlink=True)


def _setup_cam_carraio(col_cameras):
    """
    Crea o aggiorna la telecamera di sicurezza Cam_Carraio (Reolink RLC-540A)
    sul palo del muretto basso tra cancello carrabile e cancelletto pedonale.
    Muretto centrale: Gate_Central_Low_Wall (centro: x = -11.28, y = -6.28, top z = 1.30)
    Palo: x = -11.29, y = -6.28, parte da z = 1.30 e sale di 38cm -> quota z = 1.68m
    """
    px, py = -11.29, -6.28
    pz_top = 1.30
    pole_h = 0.38
    cam_z = pz_top + pole_h  # 1.68m

    pole_name = "Security_Cam_Pole_Pillar"
    pole_obj = bpy.data.objects.get(pole_name)
    if not pole_obj:
        bpy.ops.mesh.primitive_cylinder_add(
            radius=0.025,
            depth=pole_h,
            location=(px, py, pz_top + pole_h * 0.5),
        )
        pole_obj = bpy.context.active_object
        pole_obj.name = pole_name
        mat_metal = bpy.data.materials.get("Mat_Ringhiera_Metallo")
        if mat_metal:
            pole_obj.data.materials.append(mat_metal)
        _link_object_exclusively(pole_obj, col_cameras)
    else:
        pole_obj.location = (px, py, pz_top + pole_h * 0.5)

    pole_obj["ha_entity"] = "camera.carraio_scorrevole"
    pole_obj["ha_action"] = "modal"
    pole_obj["ha_ui_type"] = "camera"
    pole_obj["ha_name"] = "Telecamera Carraio (Reolink RLC-540A)"

    body_name = "Security_Cam_Body"
    body_obj = bpy.data.objects.get(body_name)
    if not body_obj:
        bpy.ops.mesh.primitive_cube_add(
            size=1.0,
            location=(px, py + 0.05, cam_z),
            scale=(0.08, 0.16, 0.08),
        )
        body_obj = bpy.context.active_object
        body_obj.name = body_name
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        mat_dark = bpy.data.materials.get("Mat_Infissi_Antracite")
        if mat_dark:
            body_obj.data.materials.append(mat_dark)
        _link_object_exclusively(body_obj, col_cameras)
    else:
        body_obj.location = (px, py + 0.05, cam_z)

    body_obj["ha_entity"] = "camera.carraio_scorrevole"
    body_obj["ha_action"] = "modal"
    body_obj["ha_ui_type"] = "camera"
    body_obj["ha_name"] = "Telecamera Carraio (Reolink RLC-540A)"

    cam_name = "Cam_Carraio"
    cam_obj = bpy.data.objects.get(cam_name)
    if not cam_obj:
        cam_data = bpy.data.cameras.new(cam_name)
        cam_obj = bpy.data.objects.new(cam_name, cam_data)
        col_cameras.objects.link(cam_obj)

    cam_obj.location = (px, py, cam_z)
    # Guarda verso fuori (+Y perpendicolare al cancello) e leggermente inclinato verso il basso (pitch ~78°)
    pitch_rad = math.radians(78.0)
    cam_obj.rotation_mode = "XYZ"
    cam_obj.rotation_euler = (pitch_rad, 0.0, 0.0)

    # Parametri ottici reali Reolink RLC-540A (4.0mm @ FOV_H=80°, FOV_V=42°)
    cam_obj.data.sensor_fit = "HORIZONTAL"
    cam_obj.data.lens = 4.0
    cam_obj.data.sensor_width = round(2.0 * 4.0 * math.tan(math.radians(80.0 / 2.0)), 4)
    cam_obj.data.sensor_height = round(2.0 * 4.0 * math.tan(math.radians(42.0 / 2.0)), 4)
    cam_obj.data.clip_start = 0.1
    cam_obj.data.clip_end = 250.0

    # Custom Properties SSoT
    cam_obj["ha_camera_entity"] = "camera.carraio_scorrevole"
    cam_obj["ha_entity"] = "camera.carraio_scorrevole"
    cam_obj["ha_label"] = "Telecamera Carraio (Reolink RLC-540A)"
    cam_obj["camera_model"] = "Reolink RLC-540A"
    cam_obj["coverage_zone"] = "outdoor_gates_street"
    cam_obj["optical_model"] = "pinhole_radtan"
    cam_obj["distortion_coeffs"] = [-0.18, 0.04, 0.0, 0.0, 0.0]
    cam_obj["stream_id"] = "carraio_main"
    cam_obj["sub_stream_id"] = "carraio_sub"
    cam_obj["main_stream_label"] = "Main 5MP"
    cam_obj["sub_stream_label"] = "Sub 640×360"
    cam_obj["camera_ip"] = "192.168.86.47"

    print(f"  [OK] Telecamera reale configurata: {cam_name} a loc=({px}, {py}, {cam_z}) rot=(78°, 0°, 0°)")


def _setup_cam_portico(col_cameras):
    """
    Crea o aggiorna la telecamera di sicurezza Cam_Portico (Reolink RLC-810A, 4.0mm 1x).
    Misure fisiche fornite dall'utente rispetto alla casa:
    - Quota obiettivo da terra: Z = 2.15 m (215 cm)
    - 66 cm più a ovest dalla parete più a est della sala da pranzo (X = 13.90 -> X = 13.24 m)
    - Sporge 17 cm verso sud dal muro sud della sala da pranzo (Y = -8.05 -> Y = -8.22 m)
    - Inquadratura (FOV 87° H x 44° V, 1x): guarda verso il portico prendendo in orizzontale
      dal muro sud della sala da pranzo (bordo destro ~179°) fino a buona parte del garage (bordo sinistro ~266°).
    """
    import bmesh

    cam_pos = mathutils.Vector((13.24, -8.22, 2.15))
    azimuth_deg = 222.5     # Centro tra muro sud sala da pranzo (179°) e garage (266°), span HFOV=87°
    pitch_down_deg = 16.0   # Inclinazione verso il basso: +6° headroom sopra, -38° suolo da 2.75m

    az_rad = math.radians(azimuth_deg)
    pd_rad = math.radians(pitch_down_deg)
    direction = mathutils.Vector((
        math.cos(pd_rad) * math.cos(az_rad),
        math.cos(pd_rad) * math.sin(az_rad),
        -math.sin(pd_rad),
    )).normalized()
    rot_quat = direction.to_track_quat("-Z", "Y")
    rot_euler = rot_quat.to_euler("XYZ")

    mat_white = _get_or_create_camera_material(
        "Mat_Security_Cam_White",
        color=(0.92, 0.93, 0.95, 1.0),
        roughness=0.35,
        metallic=0.05,
    )
    mat_dark = bpy.data.materials.get("Mat_Infissi_Antracite") or _get_or_create_camera_material(
        "Mat_Infissi_Antracite",
        color=(0.14, 0.14, 0.16, 1.0),
        roughness=0.45,
        metallic=0.3,
    )

    # 1. Mesh corpo bullet Reolink RLC-810A (Ø 66 mm, corpo 115 mm arretrato dietro l'obiettivo -> zero occlusione POV)
    body_name = "Security_Cam_Portico_Body"
    _remove_object_if_exists(body_name)
    body_len = 0.115
    body_radius = 0.033
    body_center = cam_pos - direction * (0.015 + body_len * 0.5)

    bpy.ops.mesh.primitive_cylinder_add(
        vertices=24,
        radius=body_radius,
        depth=body_len,
        location=body_center,
        rotation=rot_euler,
    )
    body_obj = bpy.context.active_object
    body_obj.name = body_name
    body_obj.data.materials.append(mat_white)
    _link_object_exclusively(body_obj, col_cameras)

    body_obj["ha_entity"] = "camera.portico"
    body_obj["ha_action"] = "modal"
    body_obj["ha_ui_type"] = "camera"
    body_obj["ha_name"] = "Portico"

    # 2. Mesh staffa e basetta a muro (collega il retro del corpo bullet al piano facciata Y = -8.05)
    mount_name = "Security_Cam_Portico_Mount"
    _remove_object_if_exists(mount_name)
    rear_pt = cam_pos - direction * (0.015 + body_len)
    wall_pt = mathutils.Vector((rear_pt.x + 0.02, -8.055, rear_pt.z + 0.01))
    arm_vec = wall_pt - rear_pt
    arm_len = max(arm_vec.length, 0.04)
    arm_mid = (rear_pt + wall_pt) * 0.5
    arm_quat = arm_vec.normalized().to_track_quat("Z", "Y")

    mount_mesh = bpy.data.meshes.new(mount_name)
    bm = bmesh.new()
    # Stelo cilindrico staffa
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=16,
        radius1=0.012,
        radius2=0.012,
        depth=arm_len,
        matrix=mathutils.Matrix.Translation(arm_mid) @ arm_quat.to_matrix().to_4x4(),
    )
    # Flangia circolare a parete (normale -Y)
    flange_quat = mathutils.Vector((0.0, -1.0, 0.0)).to_track_quat("Z", "Y")
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=20,
        radius1=0.035,
        radius2=0.032,
        depth=0.014,
        matrix=mathutils.Matrix.Translation(wall_pt) @ flange_quat.to_matrix().to_4x4(),
    )
    bm.to_mesh(mount_mesh)
    bm.free()

    mount_obj = bpy.data.objects.new(mount_name, mount_mesh)
    mount_obj.data.materials.append(mat_dark)
    col_cameras.objects.link(mount_obj)

    mount_obj["ha_entity"] = "camera.portico"
    mount_obj["ha_action"] = "modal"
    mount_obj["ha_ui_type"] = "camera"
    mount_obj["ha_name"] = "Portico"

    # 3. Oggetto Camera ottica SSoT "Cam_Portico"
    cam_name = "Cam_Portico"
    cam_obj = bpy.data.objects.get(cam_name)
    if not cam_obj:
        cam_data = bpy.data.cameras.new(cam_name)
        cam_obj = bpy.data.objects.new(cam_name, cam_data)
        col_cameras.objects.link(cam_obj)

    cam_obj.location = cam_pos
    cam_obj.rotation_mode = "XYZ"
    cam_obj.rotation_euler = rot_euler

    # Parametri ottici ufficiali Reolink RLC-810A (4.0mm fisso 1x: FOV_H=87°, FOV_V=44°, 16:9 4K)
    cam_obj.data.sensor_fit = "HORIZONTAL"
    cam_obj.data.lens = 4.0
    cam_obj.data.sensor_width = round(2.0 * 4.0 * math.tan(math.radians(87.0 / 2.0)), 4)
    cam_obj.data.sensor_height = round(2.0 * 4.0 * math.tan(math.radians(44.0 / 2.0)), 4)
    cam_obj.data.clip_start = 0.1
    cam_obj.data.clip_end = 250.0

    # Custom Properties SSoT
    cam_obj["ha_camera_entity"] = "camera.portico"
    cam_obj["ha_entity"] = "camera.portico"
    cam_obj["ha_name"] = "Portico"
    cam_obj["ha_action"] = "modal"
    cam_obj["ha_ui_type"] = "camera"
    cam_obj["ha_label"] = "Portico (Reolink RLC-810A)"
    cam_obj["camera_model"] = "Reolink RLC-810A"
    cam_obj["coverage_zone"] = "Portico"
    cam_obj["optical_model"] = "pinhole_radtan"
    cam_obj["distortion_coeffs"] = [0.0, 0.0, 0.0, 0.0, 0.0]
    cam_obj["stream_id"] = "portico_main"
    cam_obj["sub_stream_id"] = "portico_sub"
    cam_obj["main_stream_label"] = "Main 4K"
    cam_obj["sub_stream_label"] = "Sub 640×360"
    cam_obj["aspect_ratio"] = round(16.0 / 9.0, 4)
    cam_obj["camera_ip"] = "192.168.86.51"

    euler_deg = [round(math.degrees(a), 2) for a in rot_euler]
    print(f"  [OK] Telecamera reale configurata: {cam_name} a loc={tuple(round(c, 3) for c in cam_pos)} rot={euler_deg}")


def _setup_cam_ingresso(col_cameras):
    """
    Crea o aggiorna la telecamera panoramica 180° Cam_Ingresso (Reolink Duo 3 PoE, dual-lens 2.8mm).
    Misure fisiche confermate dall'utente rispetto alla casa:
    - Quota obiettivo da terra: Z = 3.50 m (350 cm)
    - Distanza dallo spigolo nord-ovest della casa (Y = 0.00): 593.6 cm verso sud -> Y = -5.936 m
    - Sporgenza dalla facciata ovest (X = 0.00): ~10 cm (specifiche staffa + corpo 195x103x56mm Reolink Duo 3 PoE) -> X = -0.10 m
    - Direzione: guarda verso ovest (-X, perpendicolare al muro) inclinata di 25° verso il basso.
    - Ottica ufficiale Reolink Duo 3 PoE: dual-lens f=2.8mm F1.6, equirectangular 180° H x 55° V,
      Main 7680x2160 (16MP, 32:9 = 3.5556), Sub 1536x576 (H.264).
    """
    import bmesh

    cam_pos = mathutils.Vector((-0.10, -5.936, 3.50))
    pitch_down_deg = 25.0
    pd_rad = math.radians(pitch_down_deg)
    direction = mathutils.Vector((-math.cos(pd_rad), 0.0, -math.sin(pd_rad))).normalized()
    rot_quat = direction.to_track_quat("-Z", "Y")
    rot_euler = rot_quat.to_euler("XYZ")

    mat_white = _get_or_create_camera_material(
        "Mat_Security_Cam_White",
        color=(0.92, 0.93, 0.95, 1.0),
        roughness=0.35,
        metallic=0.05,
    )
    mat_dark = bpy.data.materials.get("Mat_Infissi_Antracite") or _get_or_create_camera_material(
        "Mat_Infissi_Antracite",
        color=(0.14, 0.14, 0.16, 1.0),
        roughness=0.45,
        metallic=0.3,
    )

    # 1. Mesh corpo dual-lens Reolink Duo 3 PoE (195mm larghezza x 103mm altezza x 56mm profondita)
    # Posizionato strettamente dietro al punto ottico (-direction) per zero auto-occlusione POV.
    body_name = "Security_Cam_Ingresso_Body"
    _remove_object_if_exists(body_name)
    body_w = 0.195
    body_h = 0.103
    body_d = 0.056
    body_center = cam_pos - direction * (0.012 + body_d * 0.5)

    body_mesh = bpy.data.meshes.new(body_name)
    bm = bmesh.new()
    # Scocca principale nel frame locale camera (+X=larghezza 195mm, +Y=altezza 103mm, +Z=spessore 56mm dietro lente)
    cam_rot_mat = rot_quat.to_matrix().to_4x4()
    bmesh.ops.create_cube(
        bm,
        size=1.0,
        matrix=(
            mathutils.Matrix.Translation(body_center)
            @ cam_rot_mat
            @ mathutils.Matrix.Diagonal((body_w, body_h, body_d, 1.0))
        ),
    )
    bm.to_mesh(body_mesh)
    bm.free()

    body_obj = bpy.data.objects.new(body_name, body_mesh)
    body_obj.data.materials.append(mat_white)
    col_cameras.objects.link(body_obj)

    body_obj["ha_entity"] = "camera.ingresso"
    body_obj["ha_action"] = "modal"
    body_obj["ha_ui_type"] = "camera"
    body_obj["ha_name"] = "Ingresso"

    # 2. Mesh staffa integrata a snodo + piastra a muro (dal retro corpo alla facciata ovest X = 0.00)
    mount_name = "Security_Cam_Ingresso_Mount"
    _remove_object_if_exists(mount_name)
    rear_pt = cam_pos - direction * (0.012 + body_d)
    wall_pt = mathutils.Vector((-0.005, rear_pt.y, rear_pt.z + 0.01))
    arm_vec = wall_pt - rear_pt
    arm_len = max(arm_vec.length, 0.035)
    arm_mid = (rear_pt + wall_pt) * 0.5
    arm_quat = arm_vec.normalized().to_track_quat("Z", "Y")

    mount_mesh = bpy.data.meshes.new(mount_name)
    bm = bmesh.new()
    # Stelo snodo staffa
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=16,
        radius1=0.016,
        radius2=0.016,
        depth=arm_len,
        matrix=mathutils.Matrix.Translation(arm_mid) @ arm_quat.to_matrix().to_4x4(),
    )
    # Piastra a parete (normale -X)
    plate_quat = mathutils.Vector((-1.0, 0.0, 0.0)).to_track_quat("Z", "Y")
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=20,
        radius1=0.042,
        radius2=0.038,
        depth=0.014,
        matrix=mathutils.Matrix.Translation(wall_pt) @ plate_quat.to_matrix().to_4x4(),
    )
    bm.to_mesh(mount_mesh)
    bm.free()

    mount_obj = bpy.data.objects.new(mount_name, mount_mesh)
    mount_obj.data.materials.append(mat_dark)
    col_cameras.objects.link(mount_obj)

    mount_obj["ha_entity"] = "camera.ingresso"
    mount_obj["ha_action"] = "modal"
    mount_obj["ha_ui_type"] = "camera"
    mount_obj["ha_name"] = "Ingresso"

    # 3. Oggetto Camera ottica SSoT "Cam_Ingresso"
    cam_name = "Cam_Ingresso"
    cam_obj = bpy.data.objects.get(cam_name)
    if not cam_obj:
        cam_data = bpy.data.cameras.new(cam_name)
        cam_obj = bpy.data.objects.new(cam_name, cam_data)
        col_cameras.objects.link(cam_obj)

    cam_obj.location = cam_pos
    cam_obj.rotation_mode = "XYZ"
    cam_obj.rotation_euler = rot_euler

    # Proxy grandangolare per preview Blender (ottica reale 180°x55° equirettangolare esportata via custom properties SSoT)
    cam_obj.data.sensor_fit = "HORIZONTAL"
    cam_obj.data.lens = 2.8
    cam_obj.data.sensor_width = 16.0
    cam_obj.data.sensor_height = round(2.0 * 2.8 * math.tan(math.radians(55.0 / 2.0)), 4)
    cam_obj.data.clip_start = 0.1
    cam_obj.data.clip_end = 250.0

    # Custom Properties SSoT (Reolink Duo 3 PoE 180° panoramica)
    cam_obj["ha_camera_entity"] = "camera.ingresso"
    cam_obj["ha_entity"] = "camera.ingresso"
    cam_obj["ha_name"] = "Ingresso"
    cam_obj["ha_action"] = "modal"
    cam_obj["ha_ui_type"] = "camera"
    cam_obj["ha_label"] = "Ingresso (Reolink Duo 3 PoE)"
    cam_obj["camera_model"] = "Reolink Duo 3 PoE"
    cam_obj["coverage_zone"] = "zona ovest della casa"
    cam_obj["optical_model"] = "equirectangular_180"
    cam_obj["is_panoramic_180"] = True
    cam_obj["fov_h_deg"] = 180.0
    cam_obj["fov_v_deg"] = 55.0
    cam_obj["aspect_ratio"] = round(7680.0 / 2160.0, 4)
    cam_obj["distortion_coeffs"] = [0.0, 0.0, 0.0, 0.0, 0.0]
    cam_obj["stream_id"] = "ingresso_main"
    cam_obj["sub_stream_id"] = "ingresso_sub"
    cam_obj["main_stream_label"] = "Main 16MP 180°"
    cam_obj["sub_stream_label"] = "Sub 1536×576"
    cam_obj["camera_ip"] = "192.168.86.53"

    euler_deg = [round(math.degrees(a), 2) for a in rot_euler]
    print(f"  [OK] Telecamera reale configurata: {cam_name} a loc={tuple(round(c, 3) for c in cam_pos)} rot={euler_deg}")


def setup_real_security_cameras():
    """
    Configura in modo idempotente tutte le telecamere di sicurezza reali censite
    (Cam_Carraio, Cam_Portico, Cam_Ingresso) preservando tutte le proprietà SSoT.
    """
    col_cameras = bpy.data.collections.get("08_Luci_e_Camere")
    if not col_cameras:
        col_cameras = bpy.context.scene.collection

    # 1. Rimuovi solo eventuali vecchie telecamere di test/preview non censite dalle entità HA
    for obj in bpy.data.objects:
        if obj.type == "CAMERA" and obj.name not in SECURITY_CAMERA_NAMES:
            if "ha_camera_entity" in obj:
                del obj["ha_camera_entity"]
            if "ha_label" in obj:
                del obj["ha_label"]

    # 2. Setup idempotente di ogni telecamera reale
    _setup_cam_carraio(col_cameras)
    _setup_cam_portico(col_cameras)
    _setup_cam_ingresso(col_cameras)
    bpy.context.view_layer.update()


def setup_real_security_camera():
    """Alias retrocompatibile per setup_real_security_cameras()."""
    setup_real_security_cameras()


def apply_all():
    print("\n" + "=" * 65)
    print("AGGIORNAMENTO PROPRIETÀ REALI HOME ASSISTANT & VERA TELECAMERA")
    print("=" * 65)

    # 1. Ground Colliders
    for name in GROUND_COLLIDERS:
        obj = bpy.data.objects.get(name)
        if obj:
            obj["collider_role"] = "ground"

    # 2. Entità HA aggiornate
    for name, props in ENTITY_MAPPINGS.items():
        obj = bpy.data.objects.get(name)
        if obj:
            for k, v in props.items():
                obj[k] = v
            print(f"  [OK] HA: {props['ha_entity']:32} -> {name}")

    # 3. Setup Telecamera reale
    setup_real_security_camera()

    # Salva il file
    bpy.ops.wm.save_mainfile()
    print("\nFile Blender salvato con successo!")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    apply_all()
