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


def setup_real_security_camera():
    """
    Crea o aggiorna l'UNICA vera telecamera di sicurezza sul palo del muretto basso
    tra il cancello carrabile e il cancelletto pedonale.
    Muretto centrale: Gate_Central_Low_Wall (centro: x = -11.28, y = -6.28, top z = 1.30)
    Palo: a 218cm dallo spigolo (x = -11.29, y = -6.28), parte da z = 1.30 e sale di 38cm
    Telecamera: quota z = 1.68 (38cm sopra il muretto basso), orientata perpendicolarmente verso fuori (+Y)
    """
    col_cameras = bpy.data.collections.get("08_Luci_e_Camere")
    if not col_cameras:
        col_cameras = bpy.context.scene.collection

    # 1. Rimuovi le vecchie telecamere di test dalle entità HA
    for obj in bpy.data.objects:
        if obj.type == "CAMERA" and obj.name != "Cam_Carraio":
            if "ha_camera_entity" in obj:
                del obj["ha_camera_entity"]
            if "ha_label" in obj:
                del obj["ha_label"]

    px, py = -11.29, -6.28
    pz_top = 1.30
    pole_h = 0.38
    cam_z = pz_top + pole_h  # 1.68m

    # 2. Crea/Aggiorna Mesh del Palo e Corpo Telecamera
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
        for c in pole_obj.users_collection:
            c.objects.unlink(pole_obj)
        col_cameras.objects.link(pole_obj)
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
            scale=(0.08, 0.16, 0.08)
        )
        body_obj = bpy.context.active_object
        body_obj.name = body_name
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        mat_dark = bpy.data.materials.get("Mat_Infissi_Antracite")
        if mat_dark:
            body_obj.data.materials.append(mat_dark)
        for c in body_obj.users_collection:
            c.objects.unlink(body_obj)
        col_cameras.objects.link(body_obj)
    else:
        body_obj.location = (px, py + 0.05, cam_z)

    body_obj["ha_entity"] = "camera.carraio_scorrevole"
    body_obj["ha_action"] = "modal"
    body_obj["ha_ui_type"] = "camera"
    body_obj["ha_name"] = "Telecamera Carraio (Reolink RLC-540A)"

    # 3. Crea o Aggiorna la Camera Blender "Cam_Carraio"
    cam_name = "Cam_Carraio"
    cam_obj = bpy.data.objects.get(cam_name)
    if not cam_obj:
        cam_data = bpy.data.cameras.new(cam_name)
        cam_obj = bpy.data.objects.new(cam_name, cam_data)
        col_cameras.objects.link(cam_obj)

    cam_obj.location = (px, py, cam_z)
    # Guarda verso fuori (+Y perpendicolare al cancello) e leggermente inclinato verso il basso (pitch ~78°)
    pitch_rad = math.radians(78.0) # 78° da Z guarda in avanti (+Y) e verso il basso (strada)
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
    cam_obj["coverage_zone"] = "outdoor_gates_street"
    cam_obj["optical_model"] = "pinhole_radtan"
    cam_obj["distortion_coeffs"] = [-0.18, 0.04, 0.0, 0.0, 0.0]
    cam_obj["stream_id"] = "carraio_main"
    cam_obj["sub_stream_id"] = "carraio_sub"
    cam_obj["camera_ip"] = "192.168.86.47"

    print(f"  [OK] Telecamera reale configurata: {cam_name} a loc=({px}, {py}, {cam_z}) rot=(78°, 0°, 0°)")


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
