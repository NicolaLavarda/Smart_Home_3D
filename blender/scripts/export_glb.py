"""
export_glb.py
Script Python per export headless da Blender a GLB e generazione di scene_manifest.json.
Converte automaticamente gli shader procedurali Blender in colori glTF PBR per evitare mesh bianche.
"""

import sys
import os
import json
import math
import bpy
import mathutils

MATERIAL_COLOR_OVERRIDES = {
    "Mat_Prato_Fotorealistico": (0.42, 0.71, 0.28, 1.0),       # Verde prato vivo identico a Blender
    "Mat_Ghiaia_Fotorealistica": (0.62, 0.64, 0.66, 1.0),      # Ghiaia chiara
    "Mat_Lastricato_Pietra": (0.70, 0.72, 0.74, 1.0),          # Lastricato pietra chiaro
    "Mat_Parquet_Rovere_PBR": (0.73, 0.52, 0.31, 1.0),         # Rovere caldo parquet
    "Mat_Cemento_Garage": (0.54, 0.56, 0.58, 1.0),             # Cemento garage
    "Mat_Intonaco_Esterno_Dark": (0.43, 0.48, 0.53, 1.0),      # Intonaco ardesia moderno (come in viewport)
    "Mat_Intonaco_Interno_Light": (0.92, 0.90, 0.87, 1.0),     # Intonaco chiaro caldo
    "Mat_Marmo_Travertino": (0.82, 0.78, 0.70, 1.0),           # Travertino chiaro
    "Mat_Legno_Tavolo_Noce": (0.35, 0.20, 0.10, 1.0),          # Noce scuro arredi
    "Mat_Porta_Legno": (0.45, 0.30, 0.18, 1.0),                # Legno porte
    "Mat_Ringhiera_Metallo": (0.12, 0.12, 0.14, 1.0),          # Metallo recinzione
    "Mat_Infissi_Antracite": (0.14, 0.14, 0.16, 1.0),          # Antracite infissi
    "Mat_Gres_Bagno": (0.65, 0.70, 0.75, 1.0),                 # Gres bagno
    "Mat_Gres_Lavanderia": (0.55, 0.54, 0.51, 1.0),            # Gres lavanderia
    "Mat_Portone_Garage": (0.60, 0.62, 0.65, 1.0),             # Portone garage
    "Mat_Cordolo_Pietra": (0.85, 0.86, 0.87, 1.0),             # Cordolo pietra chiaro
    "Mat_Bollard_Dark": (0.13, 0.14, 0.15, 1.0),               # Alluminio scuro lampioncini
    "Mat_Frosted_Diffuser": (0.95, 0.94, 0.90, 1.0),           # Diffusore satinato bianco
    "Mat_Spot_Metal": (0.90, 0.90, 0.92, 1.0),                 # Metallo faretti incassati
    "Mat_Spot_Glass": (0.98, 0.97, 0.95, 1.0),                 # Vetro satinato faretti
    "Mat_Puffer_Grey": (0.28, 0.30, 0.32, 1.0),                # Grigio antracite puffer
    "Mat_Puffer_Cap": (0.08, 0.08, 0.09, 1.0),                 # Calotta nera puffer
    "Mat_Caldaia_White": (0.94, 0.94, 0.95, 1.0),              # Bianco lucido caldaia
    "Mat_Caldaia_Display": (0.05, 0.05, 0.05, 1.0),            # Display caldaia
    "Mat_Switch_Plate": (0.92, 0.92, 0.94, 1.0),               # Placca interruttori
    "Mat_Laccato_Bianco": (0.82, 0.81, 0.79, 1.0),             # Bianco caldo opaco satinato mobili/termoarredo
    "Mat_Lampada_Isola": (0.95, 0.94, 0.90, 1.0),              # Diffusore sospensione isola
    "Mat_Macchina_Caffe_Corpo": (0.14, 0.14, 0.16, 1.0),       # Antracite scuro opaco macchina caffe
    "Mat_Vetro_Nero_TV": (0.02, 0.02, 0.02, 1.0),              # Nero lucido display/TV/schermi
    "Mat_Deebot_White": (0.92, 0.92, 0.94, 1.0),               # Bianco robottino Ecovacs Deebot
    "Mat_Deebot_Dark": (0.12, 0.13, 0.14, 1.0),                # Antracite scuro dock / bumper Deebot
    "Mat_Deebot_Chrome": (0.85, 0.85, 0.87, 1.0),              # Ghiera metallica sensore LDS
    "Mat_Deebot_Glow": (0.15, 0.70, 1.0, 1.0),                 # LED cyan pulsante e dock
    "Mat_Security_Cam_White": (0.92, 0.93, 0.95, 1.0),         # Corpo bianco opaco telecamera Reolink bullet
}


def prepare_materials_for_gltf():
    """
    Risolve il problema delle mesh bianche:
    Scollega i nodi procedurali interni di Blender (Rampa Colore, Texture Mattoni) che glTF
    non supporta, impostando il corretto colore PBR baseColorFactor sul Principled BSDF.
    """
    print("\n--- PREPARAZIONE COLORI MATERIALI PER EXPORT GLTF ---")
    fixed_count = 0

    for mat in bpy.data.materials:
        if not mat.node_tree:
            continue

        bsdf = None
        for node in mat.node_tree.nodes:
            if node.type == "BSDF_PRINCIPLED":
                bsdf = node
                break

        if not bsdf:
            continue

        target_color = MATERIAL_COLOR_OVERRIDES.get(mat.name)
        if not target_color and mat.diffuse_color:
            target_color = tuple(mat.diffuse_color)

        base_color_input = bsdf.inputs.get("Base Color")
        if base_color_input:
            # Se è collegato a nodi procedurali o è un materiale con override, imposta il colore fisso
            if base_color_input.is_linked or mat.name in MATERIAL_COLOR_OVERRIDES:
                for link in list(base_color_input.links):
                    if link.from_node.type != "TEX_IMAGE":
                        mat.node_tree.links.remove(link)
                
                if target_color:
                    base_color_input.default_value = target_color
                    mat.diffuse_color = target_color
                    fixed_count += 1
                    print(f"  [FIX] {mat.name:30} -> BaseColor = {[round(c, 3) for c in target_color]}")

        # Calibra la roughness per evitare speculari bianchi bruciati
        roughness_input = bsdf.inputs.get("Roughness")
        if roughness_input:
            for link in list(roughness_input.links):
                if link.from_node.type != "TEX_IMAGE":
                    mat.node_tree.links.remove(link)
            if mat.name == "Mat_Prato_Fotorealistico":
                roughness_input.default_value = 0.90
            elif mat.name == "Mat_Parquet_Rovere_PBR":
                roughness_input.default_value = 0.40
            elif mat.name == "Mat_Laccato_Bianco":
                roughness_input.default_value = 0.65
            elif "Dark" in mat.name:
                roughness_input.default_value = 0.85
            elif "Light" in mat.name:
                roughness_input.default_value = 0.90

        # Calibra emissione per evitare auto-illuminazione su arredi e mobili bianchi
        emission_input = bsdf.inputs.get("Emission Color")
        if emission_input:
            if mat.name == "Mat_Laccato_Bianco":
                for link in list(emission_input.links):
                    mat.node_tree.links.remove(link)
                emission_input.default_value = (0.0, 0.0, 0.0, 1.0)
                if "Emission Strength" in bsdf.inputs:
                    bsdf.inputs["Emission Strength"].default_value = 0.0

    print(f"Materiali calibrati per glTF: {fixed_count}\n")


def get_world_centroid(obj):
    if obj.type == "MESH" and obj.data and len(obj.data.vertices) > 0:
        local_bbox_center = 0.125 * sum(
            (mathutils.Vector(b) for b in obj.bound_box), mathutils.Vector((0, 0, 0))
        )
        world_center = obj.matrix_world @ local_bbox_center
        return [round(world_center.x, 4), round(world_center.y, 4), round(world_center.z, 4)]
    loc = obj.matrix_world.translation
    return [round(loc.x, 4), round(loc.y, 4), round(loc.z, 4)]


def blender_to_gltf_coords(v):
    return [round(v[0], 4), round(v[2], 4), round(-v[1], 4)]


def matrix_to_list(mat):
    return [round(val, 6) for row in mat for val in row]


def extract_camera_data(cam_obj):
    cam = cam_obj.data
    scene = bpy.context.scene

    render_w = scene.render.resolution_x
    render_h = scene.render.resolution_y
    aspect = render_w / render_h if render_h != 0 else 1.7778
    custom_aspect = cam_obj.get("aspect_ratio")
    if custom_aspect is not None:
        try:
            custom_aspect_val = float(custom_aspect)
            if custom_aspect_val > 0.2:
                aspect = custom_aspect_val
        except (TypeError, ValueError):
            pass

    sensor_w = cam.sensor_width
    if cam_obj.get("optical_model") and cam.sensor_height > 0:
        sensor_h = cam.sensor_height
    else:
        sensor_h = cam.sensor_height if cam.sensor_fit == "VERTICAL" else sensor_w / aspect
    lens = cam.lens

    fov_h_rad = 2.0 * math.atan((sensor_w / 2.0) / lens)
    fov_v_rad = 2.0 * math.atan((sensor_h / 2.0) / lens)
    fov_deg = math.degrees(fov_v_rad)

    mat_world = cam_obj.matrix_world
    quat_world = mat_world.to_quaternion()
    loc = mat_world.translation
    rot_euler = mat_world.to_euler()

    # Cambio base Blender World (+Z Up, +Y North) -> Three.js/glTF World (+Y Up, +Z South)
    c_w_b = mathutils.Matrix((
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, -1.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    ))
    # Cambio base locale OpenCV (+X right, +Y down, +Z forward) -> OpenGL/Blender (+X right, +Y up, -Z forward)
    s_gl_cv = mathutils.Matrix((
        (1.0, 0.0, 0.0, 0.0),
        (0.0, -1.0, 0.0, 0.0),
        (0.0, 0.0, -1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    ))
    mat_threejs_gl = c_w_b @ mat_world
    mat_threejs_cv = c_w_b @ mat_world @ s_gl_cv

    raw_dist = cam_obj.get("distortion_coeffs")
    dist_coeffs = [round(float(x), 6) for x in raw_dist] if raw_dist is not None else [0.0, 0.0, 0.0, 0.0, 0.0]

    result = {
        "name": cam_obj.name,
        "ha_camera_entity": cam_obj.get("ha_camera_entity", ""),
        "ha_label": cam_obj.get("ha_label", cam_obj.name),
        "coverage_zone": cam_obj.get("coverage_zone", "general"),
        "is_real_security_camera": bool(cam_obj.get("ha_camera_entity")),
        "optical_model": cam_obj.get("optical_model", "pinhole_radtan"),
        "distortion_coeffs": dist_coeffs,
        "stream_id": cam_obj.get("stream_id", ""),
        "sub_stream_id": cam_obj.get("sub_stream_id", ""),
        "camera_ip": cam_obj.get("camera_ip", ""),
        "lens_mm": round(lens, 2),
        "sensor_width_mm": round(sensor_w, 4),
        "sensor_height_mm": round(sensor_h, 4),
        "fov_v_deg": round(fov_deg, 2),
        "fov_h_deg": round(math.degrees(fov_h_rad), 2),
        "aspect_ratio": round(aspect, 4),
        "clip_near": round(cam.clip_start, 3),
        "clip_far": round(cam.clip_end, 3),
        "blender_transform": {
            "position": [round(loc.x, 4), round(loc.y, 4), round(loc.z, 4)],
            "quaternion": [round(quat_world.x, 5), round(quat_world.y, 5), round(quat_world.z, 5), round(quat_world.w, 5)],
            "rotation_euler_deg": [round(math.degrees(rot_euler.x), 2), round(math.degrees(rot_euler.y), 2), round(math.degrees(rot_euler.z), 2)],
            "matrix_world": matrix_to_list(mat_world),
        },
        "gltf_transform": {
            "position": blender_to_gltf_coords([loc.x, loc.y, loc.z]),
            "matrix_world_gl": matrix_to_list(mat_threejs_gl),
            "extrinsic_cv_to_world": matrix_to_list(mat_threejs_cv),
        }
    }
    if cam_obj.get("camera_model"):
        result["camera_model"] = str(cam_obj.get("camera_model"))
    if cam_obj.get("main_stream_label"):
        result["main_stream_label"] = str(cam_obj.get("main_stream_label"))
    if cam_obj.get("sub_stream_label"):
        result["sub_stream_label"] = str(cam_obj.get("sub_stream_label"))
    if cam_obj.get("is_panoramic_180") is not None:
        result["is_panoramic_180"] = bool(cam_obj.get("is_panoramic_180"))
    return result


def generate_manifest(manifest_path):
    manifest = {
        "generator": "export_glb.py (Blender SSoT Pipeline)",
        "blender_version": bpy.app.version_string,
        "scene_name": bpy.context.scene.name,
        "unit_system": bpy.context.scene.unit_settings.system,
        "ha_entities": {},
        "cameras": {},
        "ground_colliders": [],
    }

    # 1. Raggruppa entità HA
    for obj in bpy.data.objects:
        entities = []
        if obj.get("ha_entity"):
            entities.append(obj.get("ha_entity"))
        if obj.get("ha_alt_entity"):
            entities.append(obj.get("ha_alt_entity"))

        for ent in entities:
            domain = ent.split(".")[0] if "." in ent else "unknown"
            centroid = get_world_centroid(obj)
            dims = [round(obj.dimensions.x, 3), round(obj.dimensions.y, 3), round(obj.dimensions.z, 3)]
            
            if ent not in manifest["ha_entities"]:
                manifest["ha_entities"][ent] = {
                    "entity_id": ent,
                    "domain": domain,
                    "name": obj.get("ha_name", ent),
                    "action": obj.get("ha_action", "toggle"),
                    "ui_type": obj.get("ha_ui_type", "default"),
                    "badge_style": obj.get("ha_badge_style", ""),
                    "objects": [],
                    "centroid_blender": centroid,
                    "centroid_gltf": blender_to_gltf_coords(centroid),
                }

            manifest["ha_entities"][ent]["objects"].append({
                "object_name": obj.name,
                "type": obj.type,
                "centroid": centroid,
                "dimensions": dims,
                "badge_style": obj.get("ha_badge_style", ""),
            })

    # 2. Raccogli telecamere
    for obj in bpy.data.objects:
        if obj.type == "CAMERA":
            cam_data = extract_camera_data(obj)
            manifest["cameras"][obj.name] = cam_data

    # 3. Raccogli ground colliders
    for obj in bpy.data.objects:
        if obj.get("collider_role") == "ground":
            manifest["ground_colliders"].append({
                "object_name": obj.name,
                "centroid": get_world_centroid(obj),
                "dimensions": [round(obj.dimensions.x, 3), round(obj.dimensions.y, 3), round(obj.dimensions.z, 3)],
            })

    os.makedirs(os.path.dirname(os.path.abspath(manifest_path)), exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    real_cams = [k for k, v in manifest["cameras"].items() if v.get("is_real_security_camera")]
    print(f"[Manifest Generato]: {manifest_path}")
    print(f"  - Entità HA: {len(manifest['ha_entities'])}")
    print(f"  - Telecamere: {len(manifest['cameras'])} (Reali: {', '.join(real_cams) or 'nessuna'})")
    print(f"  - Ground Colliders: {len(manifest['ground_colliders'])}")


def export_glb(output_glb_path):
    os.makedirs(os.path.dirname(os.path.abspath(output_glb_path)), exist_ok=True)
    print(f"\n[Avvio Export GLTF]: {output_glb_path}")
    bpy.ops.export_scene.gltf(
        filepath=output_glb_path,
        export_format="GLB",
        export_extras=True,
        export_cameras=True,
        export_lights=False,  # Disabilitato per non importare il sole fisico (2868 lux) che brucia i colori Three.js
        export_apply=True,
        export_yup=True,
    )
    size_mb = os.path.getsize(output_glb_path) / (1024 * 1024)
    print(f"[Export GLB Completato! Dimensione: {size_mb:.2f} MB]")


def main():
    argv = sys.argv
    args = argv[argv.index("--") + 1 :] if "--" in argv else []
    output_glb = args[0] if len(args) > 0 else "public/models/house_raw.glb"
    manifest_path = args[1] if len(args) > 1 else "public/models/scene_manifest.json"

    prepare_materials_for_gltf()
    generate_manifest(manifest_path)
    export_glb(output_glb)


if __name__ == "__main__":
    main()
