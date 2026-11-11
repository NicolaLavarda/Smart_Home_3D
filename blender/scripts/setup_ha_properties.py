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
}


def setup_real_security_camera():
    """
    Crea o aggiorna l'UNICA vera telecamera di sicurezza sul palo del pilastrino
    tra il cancello carrabile e il cancelletto pedonale.
    Pillar: Gate_Pillar_R (centro: x = -5.3, y = -0.2, top z = 1.8)
    Palo: parte dal centro del pilastrino e sale di 35cm
    Telecamera: quota z = 2.1 (30cm sopra il pilastrino), orientata perpendicolarmente verso fuori (+Y)
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

    pillar = bpy.data.objects.get("Gate_Pillar_R")
    px, py = -5.3, -0.2
    pz_top = 1.8
    cam_z = pz_top + 0.30 # 30cm più in alto del pilastrino = 2.10m

    # 2. Crea/Aggiorna Mesh del Palo e Corpo Telecamera se non esistono
    pole_name = "Security_Cam_Pole_Pillar"
    pole_obj = bpy.data.objects.get(pole_name)
    if not pole_obj:
        bpy.ops.mesh.primitive_cylinder_add(
            radius=0.025,
            depth=0.35,
            location=(px, py, pz_top + 0.175),
        )
        pole_obj = bpy.context.active_object
        pole_obj.name = pole_name
        # Assegna materiale metallo scuro
        mat_metal = bpy.data.materials.get("Mat_Ringhiera_Metallo")
        if mat_metal:
            pole_obj.data.materials.append(mat_metal)
        for c in pole_obj.users_collection:
            c.objects.unlink(pole_obj)
        col_cameras.objects.link(pole_obj)

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
        # Applica scala
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        mat_dark = bpy.data.materials.get("Mat_Infissi_Antracite")
        if mat_dark:
            body_obj.data.materials.append(mat_dark)
        for c in body_obj.users_collection:
            c.objects.unlink(body_obj)
        col_cameras.objects.link(body_obj)

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

    # Parametri ottici della telecamera di sicurezza
    cam_obj.data.lens = 24.0 # Grandangolare di sicurezza (~84° FOV orizzontale)
    cam_obj.data.sensor_width = 36.0
    cam_obj.data.clip_start = 0.1
    cam_obj.data.clip_end = 250.0

    # Custom Properties SSoT
    cam_obj["ha_camera_entity"] = "camera.carraio_scorrevole"
    cam_obj["ha_label"] = "Telecamera Carraio (Cancelli)"
    cam_obj["coverage_zone"] = "outdoor_gates_street"

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
