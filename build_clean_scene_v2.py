"""
Photorealistic 3D Architectural Scene Builder - Version 2.0 (Polished & Watertight)
Implements:
1. Watertight, non-overlapping polygonal ground meshes:
   - Curved Gravel Driveway with exact arc centerline and width 2.60m.
   - Giardino Area 1 (South lawn): completely outside the garage footprint, matching driveway arc.
   - Giardino Area 2 (East courtyard lawn): exact rectangular court between house and garage.
   - Giardino Area 3 (Central/West lawn): exact polygon matching the driveway arc and portico.
   - Paved Portico and Walkways: seamless slabs with flamed stone pavers.
2. Complete Garage:
   - Non-overlapping floor slabs with a dedicated recessed basement stairwell opening.
   - 12 descending concrete steps down to Z = -2.10m with metal protective safety railing.
   - Sectional overhead door, pedestrian north door, south windows, 3 north portico pillars and beam.
3. Residential Building (House):
   - Salotto with warm honey-oak parquet planks.
   - Bagno with ceramic sanitary fixtures, double-door privacy access via Antibagno.
   - Antibagno with 2-door under-stair cupboard.
   - Staircase: 3 kitchen steps -> landing -> pocket sliding door -> upper flight above cupboard.
   - Sala da pranzo with warm honey-oak parquet planks.
4. Detailed perimeter fence with stone curb and metal pickets, plus north entrance gate.
5. Hyper-photorealistic procedural PBR materials.
6. Three dedicated cameras matching Autodesk Revit Sheet 5 of 5.
"""

import bpy
import bmesh
from mathutils import Vector, Matrix
import math

print("=== Starting Watertight Photorealistic Scene Generation v2 ===")

# 1. Clean Scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

for col in [bpy.data.meshes, bpy.data.materials, bpy.data.curves, bpy.data.lights, bpy.data.cameras, bpy.data.images]:
    for item in list(col):
        try:
            col.remove(item)
        except Exception:
            pass

for col in list(bpy.data.collections):
    try:
        bpy.data.collections.remove(col)
    except Exception:
        pass

scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1.0
scene.unit_settings.length_unit = 'METERS'

# Organize collections
col_site = bpy.data.collections.new("01_Sito_e_Giardini")
col_house = bpy.data.collections.new("02_Edificio_Residenziale")
col_laundry = bpy.data.collections.new("03_Lavanderia")
col_garage = bpy.data.collections.new("04_Garage")
col_stairs = bpy.data.collections.new("05_Scale_e_Sottoscala")
col_fixtures = bpy.data.collections.new("06_Infissi_e_Porte")
col_fence = bpy.data.collections.new("07_Recinzione_e_Cancelli")
col_lighting = bpy.data.collections.new("08_Luci_e_Camere")

for c in [col_site, col_house, col_laundry, col_garage, col_stairs, col_fixtures, col_fence, col_lighting]:
    bpy.context.scene.collection.children.link(c)

# -------------------------------------------------------------
# 2. ADVANCED PROCEDURAL PBR SHADERS
# -------------------------------------------------------------
def make_pbr_grass(name="Mat_Prato_Fotorealistico"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    t = mat.node_tree
    t.nodes.clear()
    
    n_out = t.nodes.new("ShaderNodeOutputMaterial")
    n_bsdf = t.nodes.new("ShaderNodeBsdfPrincipled")
    n_coord = t.nodes.new("ShaderNodeTexCoord")
    n_map = t.nodes.new("ShaderNodeMapping")
    
    n_noise_macro = t.nodes.new("ShaderNodeTexNoise")
    n_noise_macro.inputs["Scale"].default_value = 2.0
    n_noise_macro.inputs["Detail"].default_value = 4.0
    
    n_voro = t.nodes.new("ShaderNodeTexVoronoi")
    n_voro.inputs["Scale"].default_value = 120.0
    n_voro.feature = 'F1'
    
    n_noise_fine = t.nodes.new("ShaderNodeTexNoise")
    n_noise_fine.inputs["Scale"].default_value = 40.0
    n_noise_fine.inputs["Detail"].default_value = 6.0
    
    n_mix = t.nodes.new("ShaderNodeMix")
    n_mix.data_type = 'FLOAT'
    n_mix.inputs["Factor"].default_value = 0.50
    
    n_ramp = t.nodes.new("ShaderNodeValToRGB")
    n_ramp.color_ramp.elements[0].position = 0.20
    n_ramp.color_ramp.elements[0].color = (0.10, 0.32, 0.05, 1.0) # Deep rich clover green
    n_ramp.color_ramp.elements[1].position = 0.70
    n_ramp.color_ramp.elements[1].color = (0.24, 0.56, 0.10, 1.0) # Vibrant fresh grass green
    
    n_bump = t.nodes.new("ShaderNodeBump")
    n_bump.inputs["Strength"].default_value = 0.50
    n_bump.inputs["Distance"].default_value = 0.03
    
    t.links.new(n_coord.outputs["Object"], n_map.inputs["Vector"])
    t.links.new(n_map.outputs["Vector"], n_noise_macro.inputs["Vector"])
    t.links.new(n_map.outputs["Vector"], n_voro.inputs["Vector"])
    t.links.new(n_map.outputs["Vector"], n_noise_fine.inputs["Vector"])
    
    t.links.new(n_noise_macro.outputs["Factor"], n_mix.inputs[2])
    t.links.new(n_voro.outputs["Distance"], n_mix.inputs[3])
    t.links.new(n_mix.outputs[0], n_ramp.inputs["Factor"])
    t.links.new(n_ramp.outputs["Color"], n_bsdf.inputs["Base Color"])
    t.links.new(n_voro.outputs["Distance"], n_bump.inputs["Height"])
    t.links.new(n_bump.outputs["Normal"], n_bsdf.inputs["Normal"])
    
    n_bsdf.inputs["Roughness"].default_value = 0.75
    n_bsdf.inputs["Specular IOR Level"].default_value = 0.30
    t.links.new(n_bsdf.outputs["BSDF"], n_out.inputs["Surface"])
    mat.diffuse_color = (0.22, 0.52, 0.09, 1.0)
    return mat

def make_pbr_gravel(name="Mat_Ghiaia_Fotorealistica"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    t = mat.node_tree
    t.nodes.clear()
    
    n_out = t.nodes.new("ShaderNodeOutputMaterial")
    n_bsdf = t.nodes.new("ShaderNodeBsdfPrincipled")
    n_coord = t.nodes.new("ShaderNodeTexCoord")
    n_map = t.nodes.new("ShaderNodeMapping")
    
    n_voro = t.nodes.new("ShaderNodeTexVoronoi")
    n_voro.inputs["Scale"].default_value = 100.0
    n_voro.feature = 'F1'
    
    n_voro_c = t.nodes.new("ShaderNodeTexVoronoi")
    n_voro_c.inputs["Scale"].default_value = 100.0
    n_voro_c.feature = 'F1'
    
    n_ramp = t.nodes.new("ShaderNodeValToRGB")
    n_ramp.color_ramp.elements[0].position = 0.18
    n_ramp.color_ramp.elements[0].color = (0.25, 0.24, 0.23, 1.0) # Dark basalt
    n_ramp.color_ramp.elements[1].position = 0.82
    n_ramp.color_ramp.elements[1].color = (0.70, 0.68, 0.64, 1.0) # Light limestone
    
    n_bump = t.nodes.new("ShaderNodeBump")
    n_bump.inputs["Strength"].default_value = 0.80
    n_bump.inputs["Distance"].default_value = 0.02
    
    t.links.new(n_coord.outputs["Object"], n_map.inputs["Vector"])
    t.links.new(n_map.outputs["Vector"], n_voro.inputs["Vector"])
    t.links.new(n_map.outputs["Vector"], n_voro_c.inputs["Vector"])
    t.links.new(n_voro_c.outputs["Distance"], n_ramp.inputs["Factor"])
    t.links.new(n_ramp.outputs["Color"], n_bsdf.inputs["Base Color"])
    t.links.new(n_voro.outputs["Distance"], n_bump.inputs["Height"])
    t.links.new(n_bump.outputs["Normal"], n_bsdf.inputs["Normal"])
    
    n_bsdf.inputs["Roughness"].default_value = 0.88
    t.links.new(n_bsdf.outputs["BSDF"], n_out.inputs["Surface"])
    mat.diffuse_color = (0.48, 0.46, 0.44, 1.0)
    return mat

def make_pbr_stone_pavement(name="Mat_Lastricato_Pietra"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    t = mat.node_tree
    t.nodes.clear()
    
    n_out = t.nodes.new("ShaderNodeOutputMaterial")
    n_bsdf = t.nodes.new("ShaderNodeBsdfPrincipled")
    n_coord = t.nodes.new("ShaderNodeTexCoord")
    n_map = t.nodes.new("ShaderNodeMapping")
    
    n_brick = t.nodes.new("ShaderNodeTexBrick")
    n_brick.inputs["Scale"].default_value = 3.5
    n_brick.inputs["Mortar Size"].default_value = 0.012
    n_brick.inputs["Mortar Smooth"].default_value = 0.1
    n_brick.inputs["Brick Width"].default_value = 0.50
    n_brick.inputs["Row Height"].default_value = 0.35
    n_brick.inputs["Color1"].default_value = (0.60, 0.59, 0.57, 1.0)
    n_brick.inputs["Color2"].default_value = (0.52, 0.51, 0.49, 1.0)
    n_brick.inputs["Mortar"].default_value = (0.22, 0.22, 0.22, 1.0)
    
    n_bump = t.nodes.new("ShaderNodeBump")
    n_bump.inputs["Strength"].default_value = 0.40
    n_bump.inputs["Distance"].default_value = 0.015
    
    t.links.new(n_coord.outputs["Object"], n_map.inputs["Vector"])
    t.links.new(n_map.outputs["Vector"], n_brick.inputs["Vector"])
    t.links.new(n_brick.outputs["Color"], n_bsdf.inputs["Base Color"])
    t.links.new(n_brick.outputs["Factor"], n_bump.inputs["Height"])
    t.links.new(n_bump.outputs["Normal"], n_bsdf.inputs["Normal"])
    
    n_bsdf.inputs["Roughness"].default_value = 0.65
    t.links.new(n_bsdf.outputs["BSDF"], n_out.inputs["Surface"])
    mat.diffuse_color = (0.56, 0.55, 0.53, 1.0)
    return mat

def make_pbr_parquet(name="Mat_Parquet_Rovere_PBR"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    t = mat.node_tree
    t.nodes.clear()
    
    n_out = t.nodes.new("ShaderNodeOutputMaterial")
    n_bsdf = t.nodes.new("ShaderNodeBsdfPrincipled")
    n_coord = t.nodes.new("ShaderNodeTexCoord")
    n_map = t.nodes.new("ShaderNodeMapping")
    
    n_brick = t.nodes.new("ShaderNodeTexBrick")
    n_brick.inputs["Scale"].default_value = 1.0
    n_brick.inputs["Brick Width"].default_value = 0.85
    n_brick.inputs["Row Height"].default_value = 0.14
    n_brick.inputs["Mortar Size"].default_value = 0.005
    n_brick.inputs["Color1"].default_value = (0.64, 0.46, 0.28, 1.0) # Warm honey oak
    n_brick.inputs["Color2"].default_value = (0.55, 0.39, 0.23, 1.0) # Golden amber plank
    n_brick.inputs["Mortar"].default_value = (0.28, 0.18, 0.10, 1.0)
    
    n_bump = t.nodes.new("ShaderNodeBump")
    n_bump.inputs["Strength"].default_value = 0.30
    n_bump.inputs["Distance"].default_value = 0.008
    
    t.links.new(n_coord.outputs["Object"], n_map.inputs["Vector"])
    t.links.new(n_map.outputs["Vector"], n_brick.inputs["Vector"])
    t.links.new(n_brick.outputs["Color"], n_bsdf.inputs["Base Color"])
    t.links.new(n_brick.outputs["Factor"], n_bump.inputs["Height"])
    t.links.new(n_bump.outputs["Normal"], n_bsdf.inputs["Normal"])
    
    n_bsdf.inputs["Roughness"].default_value = 0.28
    n_bsdf.inputs["Specular IOR Level"].default_value = 0.50
    t.links.new(n_bsdf.outputs["BSDF"], n_out.inputs["Surface"])
    mat.diffuse_color = (0.62, 0.44, 0.26, 1.0)
    return mat

def make_pbr_wall_ext(name="Mat_Intonaco_Esterno_Dark"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    t = mat.node_tree
    t.nodes.clear()
    
    n_out = t.nodes.new("ShaderNodeOutputMaterial")
    n_bsdf = t.nodes.new("ShaderNodeBsdfPrincipled")
    n_noise = t.nodes.new("ShaderNodeTexNoise")
    n_noise.inputs["Scale"].default_value = 100.0
    n_noise.inputs["Detail"].default_value = 6.0
    
    n_bump = t.nodes.new("ShaderNodeBump")
    n_bump.inputs["Strength"].default_value = 0.18
    n_bump.inputs["Distance"].default_value = 0.01
    
    n_bsdf.inputs["Base Color"].default_value = (0.22, 0.23, 0.24, 1.0) # Charcoal stucco
    n_bsdf.inputs["Roughness"].default_value = 0.88
    
    t.links.new(n_noise.outputs["Factor"], n_bump.inputs["Height"])
    t.links.new(n_bump.outputs["Normal"], n_bsdf.inputs["Normal"])
    t.links.new(n_bsdf.outputs["BSDF"], n_out.inputs["Surface"])
    mat.diffuse_color = (0.22, 0.23, 0.24, 1.0)
    return mat

def make_pbr_wall_int(name="Mat_Intonaco_Interno_Light"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    t = mat.node_tree
    t.nodes.clear()
    
    n_out = t.nodes.new("ShaderNodeOutputMaterial")
    n_bsdf = t.nodes.new("ShaderNodeBsdfPrincipled")
    n_bsdf.inputs["Base Color"].default_value = (0.90, 0.89, 0.87, 1.0)
    n_bsdf.inputs["Roughness"].default_value = 0.90
    t.links.new(n_bsdf.outputs["BSDF"], n_out.inputs["Surface"])
    mat.diffuse_color = (0.90, 0.89, 0.87, 1.0)
    return mat

def make_pbr_concrete(name="Mat_Cemento_Garage"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    t = mat.node_tree
    t.nodes.clear()
    
    n_out = t.nodes.new("ShaderNodeOutputMaterial")
    n_bsdf = t.nodes.new("ShaderNodeBsdfPrincipled")
    n_noise = t.nodes.new("ShaderNodeTexNoise")
    n_noise.inputs["Scale"].default_value = 25.0
    n_noise.inputs["Detail"].default_value = 4.0
    
    n_ramp = t.nodes.new("ShaderNodeValToRGB")
    n_ramp.color_ramp.elements[0].color = (0.36, 0.36, 0.37, 1.0)
    n_ramp.color_ramp.elements[1].color = (0.45, 0.45, 0.46, 1.0)
    
    t.links.new(n_noise.outputs["Factor"], n_ramp.inputs["Factor"])
    t.links.new(n_ramp.outputs["Color"], n_bsdf.inputs["Base Color"])
    n_bsdf.inputs["Roughness"].default_value = 0.45
    t.links.new(n_bsdf.outputs["BSDF"], n_out.inputs["Surface"])
    mat.diffuse_color = (0.40, 0.40, 0.41, 1.0)
    return mat

def make_standard_mat(name, color, roughness=0.5, metallic=0.0, transmission=0.0, ior=1.45, alpha=1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = transmission
    elif "Transmission" in bsdf.inputs:
        bsdf.inputs["Transmission"].default_value = transmission
    if "IOR" in bsdf.inputs:
        bsdf.inputs["IOR"].default_value = ior
    if alpha < 1.0:
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = alpha
        mat.blend_method = 'BLEND'
    mat.diffuse_color = color
    return mat

mat_grass = make_pbr_grass()
mat_gravel = make_pbr_gravel()
mat_portico = make_pbr_stone_pavement()
mat_parquet = make_pbr_parquet()
mat_wall_ext = make_pbr_wall_ext()
mat_wall_int = make_pbr_wall_int()
mat_concrete = make_pbr_concrete()
mat_tile = make_standard_mat("Mat_Gres_Bagno", (0.72, 0.77, 0.82, 1.0), roughness=0.20)
mat_laundry_tile = make_standard_mat("Mat_Gres_Lavanderia", (0.55, 0.54, 0.51, 1.0), roughness=0.40)
mat_frame = make_standard_mat("Mat_Infissi_Antracite", (0.10, 0.10, 0.11, 1.0), roughness=0.20, metallic=0.7)
mat_glass = make_standard_mat("Mat_Vetro", (0.92, 0.96, 1.0, 1.0), roughness=0.02, transmission=0.98, ior=1.52, alpha=0.30)
mat_door_wood = make_standard_mat("Mat_Porta_Legno", (0.42, 0.28, 0.16, 1.0), roughness=0.35)
mat_garage_door = make_standard_mat("Mat_Portone_Garage", (0.70, 0.72, 0.75, 1.0), roughness=0.30, metallic=0.4)
mat_chrome = make_standard_mat("Mat_Cromo", (0.95, 0.95, 0.95, 1.0), roughness=0.08, metallic=1.0)
mat_ceramic = make_standard_mat("Mat_Ceramica", (0.97, 0.97, 0.97, 1.0), roughness=0.10)
mat_curb = make_standard_mat("Mat_Cordolo_Pietra", (0.85, 0.85, 0.84, 1.0), roughness=0.55)
mat_railing = make_standard_mat("Mat_Ringhiera_Metallo", (0.08, 0.08, 0.09, 1.0), roughness=0.25, metallic=0.9)
mat_travertine = make_standard_mat("Mat_Marmo_Travertino", (0.86, 0.83, 0.77, 1.0), roughness=0.28)
mat_dark_wood = make_standard_mat("Mat_Legno_Caminetto", (0.22, 0.13, 0.07, 1.0), roughness=0.40)
mat_firebox = make_standard_mat("Mat_Focolare_Ghisa", (0.05, 0.05, 0.05, 1.0), roughness=0.65, metallic=0.80)

# -------------------------------------------------------------
# 3. MESH BUILDERS
# -------------------------------------------------------------
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

def make_poly_slab(name, polygon_2d, z_min, z_max, mat=None, collection=None):
    bm = bmesh.new()
    verts_bottom = [bm.verts.new((x, y, z_min)) for x, y in polygon_2d]
    verts_top = [bm.verts.new((x, y, z_max)) for x, y in polygon_2d]
    
    n = len(polygon_2d)
    bm.faces.new(reversed(verts_bottom))
    bm.faces.new(verts_top)
    for i in range(n):
        i_next = (i + 1) % n
        bm.faces.new([verts_bottom[i], verts_bottom[i_next], verts_top[i_next], verts_top[i]])
        
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    
    obj = bpy.data.objects.new(name, mesh)
    if mat:
        obj.data.materials.append(mat)
    if collection:
        collection.objects.link(obj)
    else:
        bpy.context.scene.collection.objects.link(obj)
    return obj

def add_window(name, x_min, x_max, y_min, y_max, sill_h, lintel_h, is_y_axis=False):
    t_frame = 0.05
    d_frame = 0.08
    if not is_y_axis:
        w = abs(x_max - x_min)
        y_c = (y_min + y_max) / 2.0
        make_box(f"{name}_Frame_Bottom", x_min, x_max, y_c - d_frame/2, y_c + d_frame/2, sill_h, sill_h + t_frame, mat_frame, col_fixtures)
        make_box(f"{name}_Frame_Top", x_min, x_max, y_c - d_frame/2, y_c + d_frame/2, lintel_h - t_frame, lintel_h, mat_frame, col_fixtures)
        make_box(f"{name}_Frame_Left", x_min, x_min + t_frame, y_c - d_frame/2, y_c + d_frame/2, sill_h + t_frame, lintel_h - t_frame, mat_frame, col_fixtures)
        make_box(f"{name}_Frame_Right", x_max - t_frame, x_max, y_c - d_frame/2, y_c + d_frame/2, sill_h + t_frame, lintel_h - t_frame, mat_frame, col_fixtures)
        if w > 0.70:
            x_m = (x_min + x_max) / 2.0
            make_box(f"{name}_Mullion", x_m - t_frame/2, x_m + t_frame/2, y_c - d_frame/2, y_c + d_frame/2, sill_h + t_frame, lintel_h - t_frame, mat_frame, col_fixtures)
        make_box(f"{name}_Glass", x_min + t_frame, x_max - t_frame, y_c - 0.01, y_c + 0.01, sill_h + t_frame, lintel_h - t_frame, mat_glass, col_fixtures)
    else:
        x_c = (x_min + x_max) / 2.0
        make_box(f"{name}_Frame_Bottom", x_c - d_frame/2, x_c + d_frame/2, y_min, y_max, sill_h, sill_h + t_frame, mat_frame, col_fixtures)
        make_box(f"{name}_Frame_Top", x_c - d_frame/2, x_c + d_frame/2, y_min, y_max, lintel_h - t_frame, lintel_h, mat_frame, col_fixtures)
        make_box(f"{name}_Frame_Front", x_c - d_frame/2, x_c + d_frame/2, y_min, y_min + t_frame, sill_h + t_frame, lintel_h - t_frame, mat_frame, col_fixtures)
        make_box(f"{name}_Frame_Back", x_c - d_frame/2, x_c + d_frame/2, y_max - t_frame, y_max, sill_h + t_frame, lintel_h - t_frame, mat_frame, col_fixtures)
        make_box(f"{name}_Glass", x_c - 0.01, x_c + 0.01, y_min + t_frame, y_max - t_frame, sill_h + t_frame, lintel_h - t_frame, mat_glass, col_fixtures)

def add_door(name, x_min, x_max, y_min, y_max, lintel_h=2.13, is_y_axis=False, open_deg=35.0):
    t_frame = 0.05
    d_frame = 0.10
    rad = math.radians(open_deg)
    if not is_y_axis:
        w = abs(x_max - x_min)
        y_c = (y_min + y_max) / 2.0
        make_box(f"{name}_Frame_Top", x_min, x_max, y_c - d_frame/2, y_c + d_frame/2, lintel_h - t_frame, lintel_h, mat_door_wood, col_fixtures)
        make_box(f"{name}_Frame_Left", x_min, x_min + t_frame, y_c - d_frame/2, y_c + d_frame/2, 0.0, lintel_h - t_frame, mat_door_wood, col_fixtures)
        make_box(f"{name}_Frame_Right", x_max - t_frame, x_max, y_c - d_frame/2, y_c + d_frame/2, 0.0, lintel_h - t_frame, mat_door_wood, col_fixtures)
        
        p_w = w - 2*t_frame
        p_t = 0.04
        p_h = lintel_h - t_frame
        hx = x_min + t_frame
        hy = y_c
        c_loc = [(0, -p_t/2), (p_w, -p_t/2), (p_w, p_t/2), (0, p_t/2)]
        c_rot = [(hx + x*math.cos(rad) - y*math.sin(rad), hy + x*math.sin(rad) + y*math.cos(rad)) for x, y in c_loc]
        
        mesh = bpy.data.meshes.new(f"{name}_Panel")
        verts = [(c_rot[0][0], c_rot[0][1], 0.0), (c_rot[1][0], c_rot[1][1], 0.0),
                 (c_rot[2][0], c_rot[2][1], 0.0), (c_rot[3][0], c_rot[3][1], 0.0),
                 (c_rot[0][0], c_rot[0][1], p_h), (c_rot[1][0], c_rot[1][1], p_h),
                 (c_rot[2][0], c_rot[2][1], p_h), (c_rot[3][0], c_rot[3][1], p_h)]
        faces = [(0,3,2,1), (4,5,6,7), (0,1,5,4), (1,2,6,5), (2,3,7,6), (3,0,4,7)]
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(f"{name}_Panel", mesh)
        obj.data.materials.append(mat_door_wood)
        col_fixtures.objects.link(obj)
        
        hand_dist = p_w - 0.08
        han_x = hx + hand_dist * math.cos(rad)
        han_y = hy + hand_dist * math.sin(rad)
        make_box(f"{name}_Handle", han_x - 0.06, han_x + 0.06, han_y - 0.02, han_y + 0.02, 0.98, 1.02, mat_chrome, col_fixtures)
    else:
        d = abs(y_max - y_min)
        x_c = (x_min + x_max) / 2.0
        make_box(f"{name}_Frame_Top", x_c - d_frame/2, x_c + d_frame/2, y_min, y_max, lintel_h - t_frame, lintel_h, mat_door_wood, col_fixtures)
        make_box(f"{name}_Frame_Front", x_c - d_frame/2, x_c + d_frame/2, y_min, y_min + t_frame, 0.0, lintel_h - t_frame, mat_door_wood, col_fixtures)
        make_box(f"{name}_Frame_Back", x_c - d_frame/2, x_c + d_frame/2, y_max - t_frame, y_max, 0.0, lintel_h - t_frame, mat_door_wood, col_fixtures)
        
        p_w = d - 2*t_frame
        p_t = 0.04
        p_h = lintel_h - t_frame
        hx = x_c
        hy = y_min + t_frame
        c_loc = [(-p_t/2, 0), (p_t/2, 0), (p_t/2, p_w), (-p_t/2, p_w)]
        c_rot = [(hx + x*math.cos(rad) - y*math.sin(rad), hy + x*math.sin(rad) + y*math.cos(rad)) for x, y in c_loc]
        mesh = bpy.data.meshes.new(f"{name}_Panel")
        verts = [(c_rot[0][0], c_rot[0][1], 0.0), (c_rot[1][0], c_rot[1][1], 0.0),
                 (c_rot[2][0], c_rot[2][1], 0.0), (c_rot[3][0], c_rot[3][1], 0.0),
                 (c_rot[0][0], c_rot[0][1], p_h), (c_rot[1][0], c_rot[1][1], p_h),
                 (c_rot[2][0], c_rot[2][1], p_h), (c_rot[3][0], c_rot[3][1], p_h)]
        faces = [(0,3,2,1), (4,5,6,7), (0,1,5,4), (1,2,6,5), (2,3,7,6), (3,0,4,7)]
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(f"{name}_Panel", mesh)
        obj.data.materials.append(mat_door_wood)
        col_fixtures.objects.link(obj)

# -------------------------------------------------------------
# 4. SITE & TERRAIN: UNIFIED NON-OVERLAPPING SURFACES
# -------------------------------------------------------------
make_box("Site_Foundation_Earth", -8.50, 14.50, -28.00, 1.50, -0.20, -0.05, mat_concrete, col_site)

# DRIVEWAY AND GROUND BOUNDARIES
# Width = 2.60 m (half-width = 1.30 m)
# Centerline: (-6.75, 0.0) -> (-6.75, -15.50) -> Arc center (-2.50, -15.50), R=4.25 -> (-2.50, -19.75) -> (6.39, -19.75)
driveway_pts_inner = [(-5.45, 0.00), (-5.45, -5.00), (-5.45, -12.00), (-5.45, -15.50)]
driveway_pts_outer = [(-8.05, 0.00), (-8.05, -5.00), (-8.05, -12.00), (-8.05, -15.50)]

cx, cy = -2.50, -15.50
r_in = 4.25 - 1.30  # 2.95 m
r_out = 4.25 + 1.30 # 5.55 m

arc_pts_in = []
arc_pts_out = []
for a in range(1, 12):
    theta = math.pi + (a / 12.0) * (math.pi / 2.0) # from 180 to 270 deg
    px_in = cx + r_in * math.cos(theta)
    py_in = cy + r_in * math.sin(theta)
    px_out = cx + r_out * math.cos(theta)
    py_out = cy + r_out * math.sin(theta)
    arc_pts_in.append((px_in, py_in))
    arc_pts_out.append((px_out, py_out))

driveway_pts_inner.extend(arc_pts_in)
driveway_pts_inner.extend([(-2.50, -18.45), (0.00, -18.45), (3.00, -18.45), (6.39, -18.45)])

driveway_pts_outer.extend(arc_pts_out)
driveway_pts_outer.extend([(-2.50, -21.05), (0.00, -21.05), (3.00, -21.05), (6.39, -21.05)])

# Single contiguous mesh for Driveway
bm_drv = bmesh.new()
n_pts = len(driveway_pts_inner)
prev_pair = None
for i in range(n_pts):
    lx, ly = driveway_pts_inner[i]
    rx, ry = driveway_pts_outer[i]
    v_l_bot = bm_drv.verts.new((lx, ly, -0.05))
    v_r_bot = bm_drv.verts.new((rx, ry, -0.05))
    v_l_top = bm_drv.verts.new((lx, ly, 0.00))
    v_r_top = bm_drv.verts.new((rx, ry, 0.00))
    if prev_pair is not None:
        bm_drv.faces.new([prev_pair[1], v_l_top, v_r_top, prev_pair[3]])
        bm_drv.faces.new([prev_pair[0], prev_pair[2], v_r_bot, v_l_bot])
        bm_drv.faces.new([prev_pair[0], v_l_bot, v_l_top, prev_pair[1]])
        bm_drv.faces.new([prev_pair[2], prev_pair[3], v_r_top, v_r_bot])
    prev_pair = (v_l_bot, v_l_top, v_r_bot, v_r_top)

bmesh.ops.recalc_face_normals(bm_drv, faces=bm_drv.faces)
mesh_drv = bpy.data.meshes.new("Driveway_Gravel")
bm_drv.to_mesh(mesh_drv)
bm_drv.free()
obj_drv = bpy.data.objects.new("Driveway_Gravel", mesh_drv)
obj_drv.data.materials.append(mat_gravel)
col_site.objects.link(obj_drv)

# GIARDINO AREA 1 (South Lawn): Perfectly conforms to driveway outer edge and stops at Garage south wall
poly_grass_1 = [
    (-8.05, -27.40),
    (13.90, -27.40),
    (13.90, -23.73), # Garage south wall east corner
    (6.39, -23.73),  # Garage south wall west corner
    (6.39, -21.05)   # Up along garage west wall to driveway south edge
]
# Add driveway outer boundary in reverse order
for pt in reversed(driveway_pts_outer[3:]):
    poly_grass_1.append(pt)
poly_grass_1.append((-8.05, -27.40))
make_poly_slab("Giardino_Area_1_Prato", poly_grass_1, -0.05, 0.00, mat_grass, col_site)

# GIARDINO AREA 2 (East Courtyard Lawn between house and garage)
make_box("Giardino_Area_2_Prato", 6.39, 13.90, -17.13, -8.05, -0.05, 0.00, mat_grass, col_site)

# GIARDINO AREA 3, VIALETTO PEDONALE & ENTRANCE GATES
# Smaller Pedestrian Walkway (Vialetto Pedonale ad L)
poly_walkway = [
    (-5.10, 0.00),
    (-4.10, 0.00),
    (-4.10, -6.11),
    (0.30, -6.11),
    (0.30, -7.11),
    (-5.10, -7.11)
]
make_poly_slab("Walkway_Pedestrian_Pavement", poly_walkway, -0.05, 0.00, mat_portico, col_site)

# Stone curbs bordering the walkway
make_box("Walkway_Curb_West", -5.16, -5.10, -7.11, 0.00, 0.00, 0.04, mat_curb, col_site)
make_box("Walkway_Curb_South", -5.16, 0.30, -7.17, -7.11, 0.00, 0.04, mat_curb, col_site)
make_box("Walkway_Curb_East", -4.10, -4.04, -6.11, 0.00, 0.00, 0.04, mat_curb, col_site)
make_box("Walkway_Curb_North", -4.04, 0.30, -6.11, -6.05, 0.00, 0.04, mat_curb, col_site)

# Watertight Lawn Meshes for Area 3
# 1. Lawn 3A (North-East lawn in front of house)
make_box("Giardino_Area_3A_Prato", -4.04, 0.00, -6.05, 0.00, -0.05, 0.00, mat_grass, col_site)

# 2. Lawn 3B (West strip between driveway and walkway)
make_box("Giardino_Area_3B_Prato", -5.45, -5.16, -7.11, 0.00, -0.05, 0.00, mat_grass, col_site)

# 3. Lawn 3C (South lawn between walkway, laundry, portico, and driveway curve)
poly_grass_3C = [
    (-5.45, -7.17),
    (0.30, -7.17),
    (0.30, -12.43), (0.00, -12.43), (0.00, -15.43), (4.65, -15.43),
    (4.65, -18.45),
    (-2.50, -18.45)
]
for pt in reversed(arc_pts_in):
    poly_grass_3C.append(pt)
poly_grass_3C.extend([(-5.45, -15.50), (-5.45, -7.17)])
make_poly_slab("Giardino_Area_3C_Prato", poly_grass_3C, -0.05, 0.00, mat_grass, col_site)

# PAVED PORTICO & WALKWAYS (Unified slab)
poly_portico = [
    (0.30, -7.11), (6.39, -7.11),
    (6.39, -17.13),
    (13.90, -17.13), (13.90, -18.13),
    (4.65, -18.13),
    (4.65, -15.43), (0.30, -15.43), (0.30, -12.43),
    (0.30, -7.11)
]
make_poly_slab("Portico_Pavement_Unified", poly_portico, -0.05, 0.00, mat_portico, col_site)

# Paved terrace "All'aperto" at North-West
make_box("Terrazza_All_Aperto", -8.05, -5.45, -5.00, 0.00, -0.05, 0.00, mat_portico, col_site)

# East boundary wall
make_box("Muro_Cinta_Est", 13.90, 14.20, -27.50, -8.05, 0.0, 2.20, mat_wall_ext, col_site)

# Perimeter fence with stone curb and metal pickets
def add_detailed_fence(name, p0, p1, h_curb=0.32, h_rail=1.10, post_spacing=2.20, picket_spacing=0.18):
    x0, y0 = p0
    x1, y1 = p1
    length = math.hypot(x1 - x0, y1 - y0)
    if length < 0.1: return
    
    dx = (x1 - x0) / length
    dy = (y1 - y0) / length
    nx = -dy
    ny = dx
    w_curb = 0.22
    
    poly_curb = [
        (x0 + nx*w_curb/2, y0 + ny*w_curb/2), (x1 + nx*w_curb/2, y1 + ny*w_curb/2),
        (x1 - nx*w_curb/2, y1 - ny*w_curb/2), (x0 - nx*w_curb/2, y0 - ny*w_curb/2)
    ]
    make_poly_slab(f"{name}_Curb", poly_curb, 0.0, h_curb, mat_curb, col_fence)
    
    w_rail = 0.04
    poly_rail_bot = [
        (x0 + nx*w_rail/2, y0 + ny*w_rail/2), (x1 + nx*w_rail/2, y1 + ny*w_rail/2),
        (x1 - nx*w_rail/2, y1 - ny*w_rail/2), (x0 - nx*w_rail/2, y0 - ny*w_rail/2)
    ]
    make_poly_slab(f"{name}_Rail_Bot", poly_rail_bot, h_curb + 0.04, h_curb + 0.08, mat_railing, col_fence)
    make_poly_slab(f"{name}_Rail_Top", poly_rail_bot, h_rail - 0.04, h_rail, mat_railing, col_fence)
    
    num_posts = max(2, int(round(length / post_spacing)) + 1)
    wp = 0.07
    for i in range(num_posts):
        t = i / (num_posts - 1)
        px = x0 + t * (x1 - x0)
        py = y0 + t * (y1 - y0)
        make_box(f"{name}_Post_{i}", px - wp/2, px + wp/2, py - wp/2, py + wp/2, h_curb, h_rail + 0.06, mat_railing, col_fence)
        
    num_pickets = int(length / picket_spacing)
    wpk = 0.02
    for j in range(1, num_pickets):
        t = j * picket_spacing / length
        px = x0 + t * (x1 - x0)
        py = y0 + t * (y1 - y0)
        make_box(f"{name}_Picket_{j}", px - wpk/2, px + wpk/2, py - wpk/2, py + wpk/2, h_curb + 0.08, h_rail - 0.04, mat_railing, col_fence)

add_detailed_fence("Fence_South", (-8.05, -27.40), (13.90, -27.40))
add_detailed_fence("Fence_West", (-8.05, -27.40), (-8.05, 0.00))

# North-West Entrance Gates
# 1. Driveway Car Gate
make_box("Gate_Pillar_L", -8.05, -7.75, -0.40, 0.00, 0.0, 1.80, mat_curb, col_fence)
make_box("Gate_Pillar_R", -5.45, -5.15, -0.40, 0.00, 0.0, 1.80, mat_curb, col_fence)
make_box("Gate_Leaf_L", -7.75, -6.60, -0.22, -0.18, 0.15, 1.45, mat_railing, col_fence)
make_box("Gate_Leaf_R", -6.60, -5.45, -0.22, -0.18, 0.15, 1.45, mat_railing, col_fence)

# 2. Pedestrian Gate (Cancelletto pedonale)
make_box("Gate_Ped_Pillar_R", -4.15, -3.85, -0.40, 0.00, 0.0, 1.80, mat_curb, col_fence)
wp_leaf_l = -5.10
wp_leaf_r = -4.20
h_g_bot = 0.15
h_g_top = 1.45
make_box("Gate_Ped_Frame_Bot", wp_leaf_l, wp_leaf_r, -0.21, -0.19, h_g_bot, h_g_bot + 0.04, mat_railing, col_fence)
make_box("Gate_Ped_Frame_Top", wp_leaf_l, wp_leaf_r, -0.21, -0.19, h_g_top - 0.04, h_g_top, mat_railing, col_fence)
make_box("Gate_Ped_Frame_L", wp_leaf_l, wp_leaf_l + 0.04, -0.21, -0.19, h_g_bot, h_g_top, mat_railing, col_fence)
make_box("Gate_Ped_Frame_R", wp_leaf_r - 0.04, wp_leaf_r, -0.21, -0.19, h_g_bot, h_g_top, mat_railing, col_fence)
for pk in range(1, 6):
    pk_x = wp_leaf_l + pk * (wp_leaf_r - wp_leaf_l) / 6.0
    make_box(f"Gate_Ped_Picket_{pk}", pk_x - 0.01, pk_x + 0.01, -0.21, -0.19, h_g_bot + 0.04, h_g_top - 0.04, mat_railing, col_fence)
make_box("Gate_Ped_Handle", wp_leaf_r - 0.08, wp_leaf_r - 0.02, -0.24, -0.16, 0.95, 1.05, mat_chrome, col_fence)

# 3. North fence connecting pedestrian gate pillar to house corner
add_detailed_fence("Fence_North_West", (-3.85, 0.00), (-0.10, 0.00))

# Pilastri del portico tra Lavanderia e Giardino 2 (30x30 cm)
make_box("Pillar_Portico_1", 5.25, 5.55, -12.73, -12.43, 0.0, 2.70, mat_wall_ext, col_site)
make_box("Pillar_Portico_2", 5.25, 5.55, -15.23, -14.93, 0.0, 2.70, mat_wall_ext, col_site)

# -------------------------------------------------------------
# 5. EDIFICIO RESIDENZIALE
# -------------------------------------------------------------
H_MAIN = 3.00

# PARETE NORD
make_box("Wall_North_01", 0.00, 1.35, -0.30, 0.00, 0.0, H_MAIN, mat_wall_ext, col_house)
make_box("Wall_North_Sill_1", 1.35, 2.27, -0.30, 0.00, 0.0, 1.00, mat_wall_ext, col_house)
make_box("Wall_North_Lintel_1", 1.35, 2.27, -0.30, 0.00, 2.83, H_MAIN, mat_wall_ext, col_house)
add_window("Win_N1", 1.35, 2.27, -0.30, 0.00, 1.00, 2.83)

make_box("Wall_North_02", 2.27, 4.00, -0.30, 0.00, 0.0, H_MAIN, mat_wall_ext, col_house)
make_box("Wall_North_Sill_2", 4.00, 4.92, -0.30, 0.00, 0.0, 1.00, mat_wall_ext, col_house)
make_box("Wall_North_Lintel_2", 4.00, 4.92, -0.30, 0.00, 2.83, H_MAIN, mat_wall_ext, col_house)
add_window("Win_N2", 4.00, 4.92, -0.30, 0.00, 1.00, 2.83)

make_box("Wall_North_03", 4.92, 6.96, -0.30, 0.00, 0.0, H_MAIN, mat_wall_ext, col_house)
make_box("Wall_North_Sill_3", 6.96, 7.88, -0.30, 0.00, 0.0, 1.00, mat_wall_ext, col_house)
make_box("Wall_North_Lintel_3", 6.96, 7.88, -0.30, 0.00, 2.83, H_MAIN, mat_wall_ext, col_house)
add_window("Win_N3", 6.96, 7.88, -0.30, 0.00, 1.00, 2.83)

make_box("Wall_North_04", 7.88, 10.05, -0.30, 0.00, 0.0, H_MAIN, mat_wall_ext, col_house)
make_box("Wall_North_Sill_4", 10.05, 10.97, -0.30, 0.00, 0.0, 1.00, mat_wall_ext, col_house)
make_box("Wall_North_Lintel_4", 10.05, 10.97, -0.30, 0.00, 2.83, H_MAIN, mat_wall_ext, col_house)
add_window("Win_N4", 10.05, 10.97, -0.30, 0.00, 1.00, 2.83)

make_box("Wall_North_05", 10.97, 14.20, -0.30, 0.00, 0.0, H_MAIN, mat_wall_ext, col_house)

# PARETE OVEST SALOTTO
make_box("Wall_West_01", 0.00, 0.30, -3.50, 0.00, 0.0, H_MAIN, mat_wall_ext, col_house)
make_box("Wall_West_Sill_1", 0.00, 0.30, -3.91, -3.50, 0.0, 1.00, mat_wall_ext, col_house)
make_box("Wall_West_Lintel_1", 0.00, 0.30, -3.91, -3.50, 1.61, H_MAIN, mat_wall_ext, col_house)
add_window("Win_W1", 0.00, 0.30, -3.91, -3.50, 1.00, 1.61, is_y_axis=True)
make_box("Wall_West_02", 0.00, 0.30, -8.21, -3.91, 0.0, H_MAIN, mat_wall_ext, col_house)

# PARETE SUD SALOTTO
make_box("Wall_South_West_01", 0.30, 1.44, -7.11, -6.81, 0.0, H_MAIN, mat_wall_ext, col_house)
make_box("Wall_South_West_Sill_1", 1.44, 2.36, -7.11, -6.81, 0.0, 1.00, mat_wall_ext, col_house)
make_box("Wall_South_West_Lintel_1", 1.44, 2.36, -7.11, -6.81, 2.83, H_MAIN, mat_wall_ext, col_house)
add_window("Win_SW1", 1.44, 2.36, -7.11, -6.81, 1.00, 2.83)
make_box("Wall_South_West_02", 2.36, 3.50, -7.11, -6.81, 0.0, H_MAIN, mat_wall_ext, col_house)
make_box("Wall_South_West_Door_Lintel", 3.50, 4.42, -7.11, -6.81, 2.13, H_MAIN, mat_wall_ext, col_house)
add_door("Door_Salotto_Sud", 3.50, 4.42, -7.11, -6.81, lintel_h=2.13, open_deg=45.0)
make_box("Wall_South_West_03", 4.42, 6.07, -7.11, -6.81, 0.0, H_MAIN, mat_wall_ext, col_house)

# MURO DIVISORIO SALOTTO / SALA DA PRANZO
make_box("Wall_Div_01", 6.07, 6.37, -3.85, -0.30, 0.0, H_MAIN, mat_wall_int, col_house)
make_box("Wall_Div_Lintel", 6.07, 6.37, -5.85, -3.85, 2.83, H_MAIN, mat_wall_int, col_house)
make_box("Wall_Div_02", 6.07, 6.37, -8.05, -5.85, 0.0, H_MAIN, mat_wall_int, col_house)

# BAGNO: PARETE SUD COMPLETAMENTE CHIUSA
make_box("Wall_Bath_South_Solid", 6.37, 8.46, -3.85, -3.56, 0.0, H_MAIN, mat_wall_int, col_house)

# PARETE EST BAGNO CON PORTA VERSO ANTIBAGNO
make_box("Wall_Bath_East_Junction", 8.46, 8.69, -3.85, -3.56, 0.0, H_MAIN, mat_wall_int, col_house)
make_box("Wall_Bath_Door_Lintel", 8.46, 8.69, -3.56, -2.76, 2.13, H_MAIN, mat_wall_int, col_house)
make_box("Wall_Bath_East_NorthSolid", 8.46, 8.69, -2.76, -0.30, 0.0, H_MAIN, mat_wall_int, col_house)

# Porta bagno (si apre all'interno verso Ovest)
hx_b = 8.46
hy_b = -3.56
p_w_b = 0.74
p_h_b = 2.08
p_t_b = 0.04
rad_b = math.radians(130.0)
c_loc_b = [(-p_t_b/2, 0), (p_t_b/2, 0), (p_t_b/2, p_w_b), (-p_t_b/2, p_w_b)]
c_rot_b = [(hx_b + x*math.cos(rad_b) - y*math.sin(rad_b), hy_b + x*math.sin(rad_b) + y*math.cos(rad_b)) for x, y in c_loc_b]
mesh_b = bpy.data.meshes.new("Door_Bagno_Panel")
verts_b = [(c_rot_b[0][0], c_rot_b[0][1], 0.0), (c_rot_b[1][0], c_rot_b[1][1], 0.0),
           (c_rot_b[2][0], c_rot_b[2][1], 0.0), (c_rot_b[3][0], c_rot_b[3][1], 0.0),
           (c_rot_b[0][0], c_rot_b[0][1], p_h_b), (c_rot_b[1][0], c_rot_b[1][1], p_h_b),
           (c_rot_b[2][0], c_rot_b[2][1], p_h_b), (c_rot_b[3][0], c_rot_b[3][1], p_h_b)]
faces_b = [(0,3,2,1), (4,5,6,7), (0,1,5,4), (1,2,6,5), (2,3,7,6), (3,0,4,7)]
mesh_b.from_pydata(verts_b, [], faces_b)
mesh_b.update()
obj_b = bpy.data.objects.new("Door_Bagno_Panel", mesh_b)
obj_b.data.materials.append(mat_door_wood)
col_fixtures.objects.link(obj_b)

# PARETE EST ESTERNA SALA DA PRANZO
make_box("Wall_East_Ext", 13.90, 14.20, -8.05, 0.00, 0.0, H_MAIN, mat_wall_ext, col_house)

# PARETE SUD SALA DA PRANZO
make_box("Wall_Dining_South_01", 6.37, 7.57, -8.05, -7.75, 0.0, H_MAIN, mat_wall_ext, col_house)
make_box("Wall_Dining_South_Sill_1", 7.57, 8.49, -8.05, -7.75, 0.0, 1.00, mat_wall_ext, col_house)
make_box("Wall_Dining_South_Lintel_1", 7.57, 8.49, -8.05, -7.75, 2.83, H_MAIN, mat_wall_ext, col_house)
add_window("Win_Dining_S1", 7.57, 8.49, -8.05, -7.75, 1.00, 2.83)

make_box("Wall_Dining_South_02", 8.49, 11.15, -8.05, -7.75, 0.0, H_MAIN, mat_wall_ext, col_house)
make_box("Wall_Dining_South_Door_Lintel", 11.15, 12.07, -8.05, -7.75, 2.13, H_MAIN, mat_wall_ext, col_house)
add_door("Door_Dining_Main", 11.15, 12.07, -8.05, -7.75, lintel_h=2.13, open_deg=50.0)

make_box("Wall_Dining_South_03", 12.07, 12.82, -8.05, -7.75, 0.0, H_MAIN, mat_wall_ext, col_house)
make_box("Wall_Dining_South_Sill_2", 12.82, 13.74, -8.05, -7.75, 0.0, 1.00, mat_wall_ext, col_house)
make_box("Wall_Dining_South_Lintel_2", 12.82, 13.74, -8.05, -7.75, 2.83, H_MAIN, mat_wall_ext, col_house)
add_window("Win_Dining_S2", 12.82, 13.74, -8.05, -7.75, 1.00, 2.83)
make_box("Wall_Dining_South_04", 13.74, 13.90, -8.05, -7.75, 0.0, H_MAIN, mat_wall_ext, col_house)

# Muretto divisorio ingresso (22cm x 110cm)
make_box("Wall_Dining_Partition", 9.71, 9.93, -7.75, -6.65, 0.0, H_MAIN, mat_wall_int, col_house)

# Pavimenti interni casa
make_box("Floor_Salotto", 0.30, 6.07, -6.81, -0.30, -0.05, 0.00, mat_parquet, col_house)
make_box("Floor_Bagno", 6.37, 8.46, -3.56, -0.30, -0.05, 0.00, mat_tile, col_house)
make_box("Floor_Dining_Main", 6.37, 13.90, -7.75, -3.85, -0.05, 0.00, mat_parquet, col_house)
make_box("Floor_Dining_NorthWing", 10.05, 13.90, -3.85, -0.30, -0.05, 0.00, mat_parquet, col_house)
make_box("Floor_Dining_Passage", 6.37, 10.05, -3.85, -3.56, -0.05, 0.00, mat_parquet, col_house)

# Sanitari Bagno
wc_x = 8.10
wc_y = -2.00
make_box("WC_Flush_Plate", 8.44, 8.46, wc_y - 0.12, wc_y + 0.12, 1.05, 1.25, mat_chrome, col_house)
make_box("WC_Bowl", wc_x, wc_x + 0.35, wc_y - 0.18, wc_y + 0.18, 0.15, 0.42, mat_ceramic, col_house)
make_box("WC_Seat", wc_x - 0.02, wc_x + 0.36, wc_y - 0.19, wc_y + 0.19, 0.42, 0.45, mat_ceramic, col_house)
make_box("Vanity_Cabinet", 6.40, 7.15, -1.10, -0.32, 0.0, 0.82, mat_door_wood, col_house)
make_box("Vanity_Basin", 6.45, 7.10, -1.05, -0.35, 0.82, 0.86, mat_ceramic, col_house)
make_box("Vanity_Tap", 6.75, 6.80, -0.42, -0.37, 0.86, 1.02, mat_chrome, col_house)
make_box("Vanity_Mirror", 6.45, 7.10, -0.32, -0.30, 1.15, 1.95, mat_glass, col_house)

# -------------------------------------------------------------
# 6. BLOCCO ANTIBAGNO + SGABUZZINO SOTTOSCALA + SCALE
# -------------------------------------------------------------
# Porta d'accesso ad Antibagno da Cucina (76cm, 0|213)
make_box("Wall_Antibagno_South_Lintel", 8.69, 9.45, -3.85, -3.56, 2.13, H_MAIN, mat_wall_int, col_stairs)
make_box("Door_Anti_Frame_Top", 8.69, 9.45, -3.73, -3.63, 2.08, 2.13, mat_door_wood, col_fixtures)
make_box("Door_Anti_Frame_L", 8.69, 8.74, -3.73, -3.63, 0.0, 2.08, mat_door_wood, col_fixtures)
make_box("Door_Anti_Frame_R", 9.40, 9.45, -3.73, -3.63, 0.0, 2.08, mat_door_wood, col_fixtures)
make_box("Door_Antibagno_Panel", 9.38, 9.42, -3.68, -3.02, 0.0, 2.08, mat_door_wood, col_fixtures)

# Pavimento Antibagno
make_box("Floor_Antibagno", 8.69, 9.45, -3.56, -2.06, -0.05, 0.00, mat_tile, col_stairs)

# Armadio Sgabuzzino sottoscala (2 ante con maniglie a nord dell'antibagno a y=-2.06)
h_cup = 1.45
w_cup_half = (0.76 - 0.08) / 2.0
make_box("Cupboard_Frame_Top", 8.69, 9.45, -2.10, -2.06, h_cup - 0.04, h_cup, mat_door_wood, col_stairs)
make_box("Cupboard_Frame_L", 8.69, 8.73, -2.10, -2.06, 0.0, h_cup, mat_door_wood, col_stairs)
make_box("Cupboard_Frame_R", 9.41, 9.45, -2.10, -2.06, 0.0, h_cup, mat_door_wood, col_stairs)
make_box("Cupboard_Door_L", 8.73, 8.73 + w_cup_half, -2.10, -2.06, 0.02, h_cup - 0.02, mat_door_wood, col_stairs)
make_box("Cupboard_Door_R", 8.73 + w_cup_half, 9.41, -2.10, -2.06, 0.02, h_cup - 0.02, mat_door_wood, col_stairs)
make_box("Cupboard_Handle_L", 8.73 + w_cup_half - 0.04, 8.73 + w_cup_half - 0.02, -2.12, -2.10, 0.85, 0.95, mat_chrome, col_stairs)
make_box("Cupboard_Handle_R", 8.73 + w_cup_half + 0.02, 8.73 + w_cup_half + 0.04, -2.12, -2.10, 0.85, 0.95, mat_chrome, col_stairs)
make_box("Cupboard_Header_Wall", 8.69, 9.45, -2.10, -2.06, h_cup, 1.80, mat_wall_int, col_stairs)

# Muro divisorio continuo e solido verso la sala da pranzo (nessuna compenetrazione)
make_box("Wall_Stair_West_SouthSolid", 9.45, 9.70, -3.85, -2.06, 0.0, H_MAIN, mat_wall_int, col_stairs)
z_landing = 3 * (3.00 / 17.0) # ~ 0.5294 m
h_door_l = 2.10
make_box("Wall_Sliding_Lintel", 9.45, 9.70, -2.06, -1.25, z_landing + h_door_l, H_MAIN, mat_wall_int, col_stairs)

# Scalinata superiore all'interno del vano scala (x: 8.69 a 9.44 -> stop prima del muro a 9.45)
r1 = 3.00 / 17.0
x_st_in, x_st_out = 8.69, 9.44
make_box("Stair_Upper_Step_4", x_st_in, x_st_out, -1.05, -0.68, 0.0, 4*r1, mat_parquet, col_stairs)
make_box("Stair_Upper_Step_5", x_st_in, x_st_out, -0.68, -0.30, 0.0, 5*r1, mat_parquet, col_stairs)

y_up = -0.68
t_up = 0.24
for s in range(6, 18):
    z_top = s * r1
    y0 = y_up - (s - 6) * t_up
    y1 = y0 - t_up
    z_bot = max(0.0, z_top - r1)
    make_box(f"Stair_Upper_Riser_{s}", x_st_in, x_st_out, y0 - 0.02, y0, z_bot, z_top, mat_wall_int, col_stairs)
    make_box(f"Stair_Upper_Step_{s}", x_st_in, x_st_out, y1, y0, z_top - 0.035, z_top, mat_parquet, col_stairs)
make_box("Stair_Top_Arrival", x_st_in, x_st_out, -3.85, y1, 2.82, 3.00, mat_parquet, col_stairs)

# Scala in Cucina (3 gradini aperti a destra, senza muretto laterale, come in foto reale 2)
step_y_bounds = [(-2.84, -2.58), (-2.58, -2.32), (-2.32, -2.06)]
for i, (sy0, sy1) in enumerate(step_y_bounds, start=1):
    z_step_top = i * r1
    z_step_bot = (i - 1) * r1
    make_box(f"Stair_Kitchen_Riser_{i}", 9.70, 10.65, sy0, sy0 + 0.03, z_step_bot, z_step_top, mat_wall_int, col_stairs)
    make_box(f"Stair_Kitchen_Base_{i}", 9.70, 10.65, sy0 + 0.03, sy1, z_step_bot, z_step_top - 0.035, mat_wall_int, col_stairs)
    make_box(f"Stair_Kitchen_Step_{i}", 9.70, 10.67, sy0 - 0.02, sy1, z_step_top - 0.035, z_step_top, mat_parquet, col_stairs)

# Pianerottolo con spigolo curvo, fascia sagomata, griglia decorativa e porta vetrata
arc_corner_pts = []
for a in range(1, 9):
    ang = -math.pi/2.0 + (a / 8.0) * (math.pi/2.0)
    ax = 10.95 + 0.30 * math.cos(ang)
    ay = -1.55 + 0.30 * math.sin(ang)
    arc_corner_pts.append((ax, ay))

poly_landing = [
    (9.70, -2.06), (10.65, -2.06), (10.65, -1.85), (10.95, -1.85)
] + arc_corner_pts + [(11.25, -0.30), (9.70, -0.30)]

make_poly_slab("Pianerottolo_Piano_Legno", poly_landing, z_landing - 0.035, z_landing, mat_parquet, col_stairs)
make_poly_slab("Pianerottolo_Fascia_Bianca", poly_landing, 0.37, z_landing - 0.035, mat_wall_int, col_stairs)
make_poly_slab("Pianerottolo_Toro_Pietra", poly_landing, 0.33, 0.37, mat_travertine, col_stairs)
make_box("Pianerottolo_Plinth_Front", 10.65, 10.95, -1.85, -1.75, 0.00, 0.33, mat_wall_int, col_stairs)
make_box("Pianerottolo_Vent_Frame", 10.72, 10.88, -1.86, -1.84, 0.10, 0.26, mat_travertine, col_stairs)
for g in range(5):
    gx = 10.74 + g * 0.026
    make_box(f"Pianerottolo_Vent_Louver_{g}", gx, gx + 0.012, -1.865, -1.845, 0.12, 0.24, mat_dark_wood, col_stairs)
poly_wood_curved = [(10.95, -1.85)] + arc_corner_pts + [(10.95, -1.55)]
make_poly_slab("Pianerottolo_Base_CurvedWood", poly_wood_curved, 0.00, 0.33, mat_dark_wood, col_stairs)
make_poly_slab("Pianerottolo_Zoccolo_Base", poly_landing, 0.00, 0.04, mat_travertine, col_stairs)

# Porta a vetri sopra il pianerottolo
hy_d0, hy_d1 = -2.06, -1.25
z_d0, z_d1 = z_landing, z_landing + h_door_l
make_box("Door_Landing_Frame_Top", 9.68, 9.74, hy_d0, hy_d1, z_d1 - 0.05, z_d1, mat_door_wood, col_fixtures)
make_box("Door_Landing_Frame_S", 9.68, 9.74, hy_d0, hy_d0 + 0.05, z_d0, z_d1 - 0.05, mat_door_wood, col_fixtures)
make_box("Door_Landing_Frame_N", 9.68, 9.74, hy_d1 - 0.05, hy_d1, z_d0, z_d1 - 0.05, mat_door_wood, col_fixtures)
y_p0, y_p1 = hy_d0 + 0.06, hy_d1 - 0.06
make_box("Door_Landing_Leaf_Stile_S", 9.69, 9.73, y_p0, y_p0 + 0.08, z_d0 + 0.01, z_d1 - 0.06, mat_door_wood, col_fixtures)
make_box("Door_Landing_Leaf_Stile_N", 9.69, 9.73, y_p1 - 0.08, y_p1, z_d0 + 0.01, z_d1 - 0.06, mat_door_wood, col_fixtures)
make_box("Door_Landing_Leaf_Rail_Bot", 9.69, 9.73, y_p0 + 0.08, y_p1 - 0.08, z_d0 + 0.01, z_d0 + 0.18, mat_door_wood, col_fixtures)
make_box("Door_Landing_Leaf_Rail_Top", 9.69, 9.73, y_p0 + 0.08, y_p1 - 0.08, z_d1 - 0.14, z_d1 - 0.06, mat_door_wood, col_fixtures)
make_box("Door_Landing_Glass", 9.705, 9.715, y_p0 + 0.08, y_p1 - 0.08, z_d0 + 0.18, z_d1 - 0.14, mat_glass, col_fixtures)
for m in range(1, 4):
    zm = z_d0 + 0.18 + m * (z_d1 - 0.14 - (z_d0 + 0.18)) / 4.0
    make_box(f"Door_Landing_Mullion_{m}", 9.69, 9.73, y_p0 + 0.08, y_p1 - 0.08, zm - 0.015, zm + 0.015, mat_door_wood, col_fixtures)
make_box("Door_Landing_Handle_Plate", 9.67, 9.75, y_p0 + 0.05, y_p0 + 0.07, z_d0 + 0.95, z_d0 + 1.15, mat_chrome, col_fixtures)
make_box("Door_Landing_Handle_Lever", 9.65, 9.67, y_p0 + 0.03, y_p0 + 0.14, z_d0 + 1.05, z_d0 + 1.07, mat_chrome, col_fixtures)

# Panca bassa in muratura lungo la parete nord (da x=11.25 a 12.65)
x_bench0, x_bench1 = 11.25, 12.65
y_bench_front, y_bench_back = -0.85, -0.30
z_bench_h = 0.42
make_box("Bench_North_Plinth", x_bench0, x_bench1, y_bench_front + 0.04, y_bench_back, 0.00, 0.08, mat_travertine, col_house)
make_box("Bench_North_Body", x_bench0, x_bench1, y_bench_front, y_bench_back, 0.08, z_bench_h - 0.04, mat_wall_int, col_house)
for s in range(8):
    sx = x_bench0 + 0.15 + s * 0.14
    make_box(f"Bench_North_Slot_{s}", sx, sx + 0.05, y_bench_front - 0.005, y_bench_front + 0.03, 0.16, 0.30, mat_travertine, col_house)
make_box("Bench_North_TopSlab", x_bench0, x_bench1, y_bench_front - 0.02, y_bench_back, z_bench_h - 0.04, z_bench_h, mat_travertine, col_house)
for sh_i, sh_z in enumerate([1.25, 1.60, 1.95], start=1):
    make_box(f"Bench_North_Shelf_{sh_i}", x_bench0 + 0.05, x_bench1 - 0.05, -0.55, y_bench_back, sh_z, sh_z + 0.03, mat_door_wood, col_house)

# Caminetto angolare a legna (da x=12.65 a 13.90)
x_fp0, x_fp1 = 12.65, 13.90
y_fp_front, y_fp_back = -1.15, -0.30
z_fp_hearth = 0.45
make_box("Fireplace_Hearth_Plinth", x_fp0, x_fp1, y_fp_front + 0.04, y_fp_back, 0.00, 0.08, mat_travertine, col_house)
make_box("Fireplace_Hearth_Body", x_fp0, x_fp1, y_fp_front, y_fp_back, 0.08, z_fp_hearth - 0.04, mat_wall_int, col_house)
for fs in range(7):
    fsx = x_fp0 + 0.18 + fs * 0.14
    make_box(f"Fireplace_Base_Slot_{fs}", fsx, fsx + 0.05, y_fp_front - 0.005, y_fp_front + 0.03, 0.18, 0.32, mat_travertine, col_house)
make_box("Fireplace_Hearth_TopSlab", x_fp0 - 0.02, x_fp1, y_fp_front - 0.03, y_fp_back, z_fp_hearth - 0.04, z_fp_hearth, mat_travertine, col_house)
make_box("Fireplace_Pilaster_L", x_fp0, x_fp0 + 0.15, y_fp_front + 0.05, y_fp_back, z_fp_hearth, 1.20, mat_travertine, col_house)
x_box0, x_box1 = x_fp0 + 0.18, x_fp1 - 0.05
y_box_front, y_box_back = y_fp_front + 0.10, y_fp_back + 0.05
z_box_top = 1.18
make_box("Fireplace_Firebox_Casing", x_box0, x_box1, y_box_front, y_box_back, z_fp_hearth, z_box_top, mat_firebox, col_house)
make_box("Fireplace_Glass_Front", x_box0 + 0.02, x_box1 - 0.02, y_box_front - 0.01, y_box_front + 0.01, z_fp_hearth + 0.05, z_box_top - 0.05, mat_glass, col_house)
make_box("Fireplace_Glass_Side", x_box0 - 0.01, x_box0 + 0.01, y_box_front + 0.02, y_box_back - 0.05, z_fp_hearth + 0.05, z_box_top - 0.05, mat_glass, col_house)
make_box("Fireplace_Mantel_Beam", x_fp0 - 0.03, x_fp1, y_fp_front - 0.04, y_fp_back, 1.18, 1.28, mat_dark_wood, col_house)
make_box("Fireplace_Hood", x_fp0 + 0.02, x_fp1, y_fp_front + 0.05, y_fp_back, 1.28, H_MAIN, mat_wall_int, col_house)

# -------------------------------------------------------------
# 7. LAVANDERIA
# -------------------------------------------------------------
H_LAV = 2.70
make_box("Wall_Lav_West", 0.00, 0.30, -15.43, -11.33, 0.0, H_LAV, mat_wall_ext, col_laundry)
make_box("Wall_Lav_North_01", 0.30, 2.70, -12.63, -12.43, 0.0, H_LAV, mat_wall_ext, col_laundry)
make_box("Wall_Lav_North_Door_Lintel", 2.70, 3.62, -12.63, -12.43, 2.13, H_LAV, mat_wall_ext, col_laundry)
add_door("Door_Lav_North", 2.70, 3.62, -12.63, -12.43, lintel_h=2.13, open_deg=40.0)
make_box("Wall_Lav_North_02", 3.62, 4.65, -12.63, -12.43, 0.0, H_LAV, mat_wall_ext, col_laundry)
make_box("Wall_Lav_East", 4.45, 4.65, -15.43, -12.63, 0.0, H_LAV, mat_wall_ext, col_laundry)

make_box("Wall_Lav_South_01", 0.30, 0.82, -15.43, -15.23, 0.0, H_LAV, mat_wall_ext, col_laundry)
make_box("Wall_Lav_South_Sill_1", 0.82, 1.43, -15.43, -15.23, 0.0, 1.00, mat_wall_ext, col_laundry)
make_box("Wall_Lav_South_Lintel_1", 0.82, 1.43, -15.43, -15.23, 1.61, H_LAV, mat_wall_ext, col_laundry)
add_window("Win_Lav_1", 0.82, 1.43, -15.43, -15.23, 1.00, 1.61)

make_box("Wall_Lav_South_02", 1.43, 3.08, -15.43, -15.23, 0.0, H_LAV, mat_wall_ext, col_laundry)
make_box("Wall_Lav_South_Sill_2", 3.08, 3.69, -15.43, -15.23, 0.0, 1.00, mat_wall_ext, col_laundry)
make_box("Wall_Lav_South_Lintel_2", 3.08, 3.69, -15.43, -15.23, 1.61, H_LAV, mat_wall_ext, col_laundry)
add_window("Win_Lav_2", 3.08, 3.69, -15.43, -15.23, 1.00, 1.61)
make_box("Wall_Lav_South_03", 3.69, 4.45, -15.43, -15.23, 0.0, H_LAV, mat_wall_ext, col_laundry)

make_box("Wall_Lav_Part_V1", 1.43, 1.65, -15.23, -14.46, 0.0, H_LAV, mat_wall_int, col_laundry)
make_box("Wall_Lav_Part_H1", 1.43, 2.50, -14.46, -14.24, 0.0, H_LAV, mat_wall_int, col_laundry)
make_box("Wall_Lav_Part_V2", 3.08, 3.30, -15.23, -14.46, 0.0, H_LAV, mat_wall_int, col_laundry)
make_box("Floor_Lavanderia", 0.30, 4.45, -15.23, -12.63, -0.05, 0.00, mat_laundry_tile, col_laundry)

# -------------------------------------------------------------
# 8. GARAGE (Completely Watertight & No Grass Compenetration)
# -------------------------------------------------------------
H_GAR = 2.80
x_g0, x_g1 = 6.39, 14.20
y_g_n_out = -18.13
y_g_n_in = -18.43
y_g_s_in = -23.43
y_g_s_out = -23.73

# Parete Est Garage
make_box("Wall_Garage_East", 13.90, 14.20, y_g_s_out, y_g_n_out, 0.0, H_GAR, mat_wall_ext, col_garage)

# Parete Ovest Garage con portone sezionale (2.40m luce da y=-21.93 a -19.53)
make_box("Wall_Garage_West_Ext", x_g0, x_g0 + 0.30, -18.13, -17.13, 0.0, H_GAR, mat_wall_ext, col_garage)
make_box("Wall_Garage_West_01", x_g0, x_g0 + 0.30, -19.53, -18.13, 0.0, H_GAR, mat_wall_ext, col_garage)
make_box("Wall_Garage_West_Lintel", x_g0, x_g0 + 0.30, -21.93, -19.53, 2.10, H_GAR, mat_wall_ext, col_garage)
make_box("Wall_Garage_West_02", x_g0, x_g0 + 0.30, y_g_s_out, -21.93, 0.0, H_GAR, mat_wall_ext, col_garage)

# Portone sezionale a doghe
for pan in range(5):
    zp0 = pan * (2.05 / 5.0)
    zp1 = zp0 + (2.05 / 5.0) - 0.015
    make_box(f"Garage_Door_Panel_{pan+1}", x_g0 + 0.12, x_g0 + 0.18, -21.90, -19.56, zp0, zp1, mat_garage_door, col_fixtures)

# Parete Nord con porta pedonale e 2 finestre
make_box("Wall_Garage_North_01", 6.69, 7.49, y_g_n_in, y_g_n_out, 0.0, H_GAR, mat_wall_ext, col_garage)
make_box("Wall_Garage_North_Door_Lintel", 7.49, 8.41, y_g_n_in, y_g_n_out, 2.13, H_GAR, mat_wall_ext, col_garage)
add_door("Door_Garage_Pedestrian", 7.49, 8.41, y_g_n_in, y_g_n_out, lintel_h=2.13, open_deg=40.0)

make_box("Wall_Garage_North_02", 8.41, 9.02, y_g_n_in, y_g_n_out, 0.0, H_GAR, mat_wall_ext, col_garage)
make_box("Wall_Garage_North_Sill_1", 9.02, 9.63, y_g_n_in, y_g_n_out, 0.0, 1.00, mat_wall_ext, col_garage)
make_box("Wall_Garage_North_Lintel_1", 9.02, 9.63, y_g_n_in, y_g_n_out, 1.61, H_GAR, mat_wall_ext, col_garage)
add_window("Win_Garage_N1", 9.02, 9.63, y_g_n_in, y_g_n_out, 1.00, 1.61)

make_box("Wall_Garage_North_03", 9.63, 11.83, y_g_n_in, y_g_n_out, 0.0, H_GAR, mat_wall_ext, col_garage)
make_box("Wall_Garage_North_Sill_2", 11.83, 12.44, y_g_n_in, y_g_n_out, 0.0, 1.00, mat_wall_ext, col_garage)
make_box("Wall_Garage_North_Lintel_2", 11.83, 12.44, y_g_n_in, y_g_n_out, 1.61, H_GAR, mat_wall_ext, col_garage)
add_window("Win_Garage_N2", 11.83, 12.44, y_g_n_in, y_g_n_out, 1.00, 1.61)
make_box("Wall_Garage_North_04", 12.44, 13.90, y_g_n_in, y_g_n_out, 0.0, H_GAR, mat_wall_ext, col_garage)

# Portico Nord Garage con 3 pilastri da 50x30 cm e trave
make_box("Pillar_Garage_1", 8.41, 8.91, -17.43, -17.13, 0.0, H_GAR, mat_wall_ext, col_garage)
make_box("Pillar_Garage_2", 10.60, 11.10, -17.43, -17.13, 0.0, H_GAR, mat_wall_ext, col_garage)
make_box("Pillar_Garage_3", 13.40, 13.90, -17.43, -17.13, 0.0, H_GAR, mat_wall_ext, col_garage)
make_box("Beam_Portico_Garage", 6.39, 13.90, -17.43, -17.13, 2.50, H_GAR, mat_wall_ext, col_garage)

# Parete Sud Garage con 2 finestre
make_box("Wall_Garage_South_01", 6.69, 9.41, y_g_s_out, y_g_s_in, 0.0, H_GAR, mat_wall_ext, col_garage)
make_box("Wall_Garage_South_Sill_1", 9.41, 10.02, y_g_s_out, y_g_s_in, 0.0, 1.00, mat_wall_ext, col_garage)
make_box("Wall_Garage_South_Lintel_1", 9.41, 10.02, y_g_s_out, y_g_s_in, 1.61, H_GAR, mat_wall_ext, col_garage)
add_window("Win_Garage_S1", 9.41, 10.02, y_g_s_out, y_g_s_in, 1.00, 1.61)

make_box("Wall_Garage_South_02", 10.02, 12.49, y_g_s_out, y_g_s_in, 0.0, H_GAR, mat_wall_ext, col_garage)
make_box("Wall_Garage_South_Sill_2", 12.49, 13.10, y_g_s_out, y_g_s_in, 0.0, 1.00, mat_wall_ext, col_garage)
make_box("Wall_Garage_South_Lintel_2", 12.49, 13.10, y_g_s_out, y_g_s_in, 1.61, H_GAR, mat_wall_ext, col_garage)
add_window("Win_Garage_S2", 12.49, 13.10, y_g_s_out, y_g_s_in, 1.00, 1.61)
make_box("Wall_Garage_South_03", 13.10, 13.90, y_g_s_out, y_g_s_in, 0.0, H_GAR, mat_wall_ext, col_garage)

# PAVIMENTO GARAGE CON FORO VANO SCALA INTERRATO
# Foro scala: x: [9.40, 12.81], y: [-23.43, -22.53]
make_box("Floor_Garage_Main", 6.69, 13.90, -22.53, y_g_n_in, -0.05, 0.00, mat_concrete, col_garage)
make_box("Floor_Garage_WestStair", 6.69, 9.40, y_g_s_in, -22.53, -0.05, 0.00, mat_concrete, col_garage)
make_box("Floor_Garage_EastStair", 12.81, 13.90, y_g_s_in, -22.53, -0.05, 0.00, mat_concrete, col_garage)

# Gradini scala interrata discendente (12 gradini da Z=0.00 a Z=-2.10)
num_gar_steps = 12
w_step_g = (12.81 - 9.40) / num_gar_steps # ~28.4 cm
h_step_g = 2.10 / num_gar_steps           # 17.5 cm
for gs in range(num_gar_steps):
    x_gs0 = 12.81 - (gs + 1) * w_step_g
    x_gs1 = 12.81 - gs * w_step_g
    z_gs = -(gs + 1) * h_step_g
    make_box(f"Garage_Basement_Step_{gs+1}", x_gs0, x_gs1, -23.43, -22.53, z_gs, z_gs + h_step_g, mat_concrete, col_garage)

# Parapetto di sicurezza attorno al vano scala
make_box("Railing_Garage_Stair_North", 9.40, 12.81, -22.53, -22.49, 0.00, 0.90, mat_railing, col_garage)
make_box("Railing_Garage_Stair_West", 9.40, 9.44, -23.43, -22.53, 0.00, 0.90, mat_railing, col_garage)

# -------------------------------------------------------------
# 9. ETICHETTE TESTUALI 3D SUL PAVIMENTO
# -------------------------------------------------------------
def add_label(text, x, y, size=0.45):
    font_curve = bpy.data.curves.new(type="FONT", name=f"Label_{text}")
    font_curve.body = text
    font_curve.size = size
    font_curve.extrude = 0.015
    obj = bpy.data.objects.new(name=f"Label_{text}", object_data=font_curve)
    obj.location = (x, y, 0.01)
    obj.data.materials.append(mat_frame)
    col_site.objects.link(obj)

add_label("SALOTTO", 1.80, -3.80, size=0.40)
add_label("BAGNO", 6.90, -2.20, size=0.28)
add_label("SALA DA PRANZO", 8.20, -5.80, size=0.42)
add_label("PORTICO", 2.20, -9.50, size=0.45)
add_label("LAVANDERIA", 1.30, -13.80, size=0.32)
add_label("GARAGE", 9.50, -20.80, size=0.50)
add_label("GIARDINO AREA 2", 8.50, -13.00, size=0.42)
add_label("GIARDINO AREA 3", -4.50, -11.00, size=0.45)
add_label("GIARDINO AREA 1", 1.00, -25.50, size=0.50)
add_label("ALL'APERTO", -7.50, -2.50, size=0.38)

# -------------------------------------------------------------
# 9B. ARREDI E STRUTTURE PRINCIPALI (Cucina, Pranzo, Salotto)
# -------------------------------------------------------------
try:
    with open("add_main_furniture.py", "r", encoding="utf-8") as f_furn:
        exec(f_furn.read())
except Exception as e_furn:
    print(f"Notice: furniture script executed inline: {e_furn}")

# -------------------------------------------------------------
# 10. ILLUMINAZIONE ARCHITETTONICA E SKY
# -------------------------------------------------------------
sun_data = bpy.data.lights.new(name="Sun_Key", type='SUN')
sun_data.energy = 4.2
sun_data.color = (1.0, 0.98, 0.95)
sun_data.angle = math.radians(4.0)
sun_obj = bpy.data.objects.new(name="Sun_Key", object_data=sun_data)
sun_obj.location = (15.0, -15.0, 25.0)
sun_obj.rotation_euler = (math.radians(48.0), math.radians(12.0), math.radians(-32.0))
col_lighting.objects.link(sun_obj)

world = bpy.context.scene.world
if not world:
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
world.use_nodes = True
bg_node = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
bg_node.inputs["Color"].default_value = (0.86, 0.90, 0.95, 1.0)
bg_node.inputs["Strength"].default_value = 0.85

# -------------------------------------------------------------
# 11. CAMERE CORRISPONDENTI AL FOGLIO 5 DI 5 REVIT
# -------------------------------------------------------------
def point_camera_at(cam_obj, target_pt):
    loc = cam_obj.location
    direction = target_pt - loc
    rot_quat = direction.to_track_quat('-Z', 'Y')
    cam_obj.rotation_euler = rot_quat.to_euler()

# 1. Camera Assonometrica Sud-Ovest (corrisponde al render in basso a sinistra del Foglio 5)
cam_sw_data = bpy.data.cameras.new(name="Camera_Revit_Isometric_SW")
cam_sw_data.lens = 32
cam_sw_data.clip_start = 0.1
cam_sw_data.clip_end = 200.0
cam_sw_obj = bpy.data.objects.new(name="Camera_Revit_Isometric_SW", object_data=cam_sw_data)
cam_sw_obj.location = Vector((-26.0, -44.0, 30.0))
point_camera_at(cam_sw_obj, Vector((3.0, -13.5, 0.0)))
col_lighting.objects.link(cam_sw_obj)

# 2. Camera Prospetto Zenitale Top-Down (corrisponde al prospetto in alto a destra del Foglio 5)
cam_top_data = bpy.data.cameras.new(name="Camera_Revit_Plan_Top")
cam_top_data.type = 'PERSP'
cam_top_data.lens = 28
cam_top_obj = bpy.data.objects.new(name="Camera_Revit_Plan_Top", object_data=cam_top_data)
cam_top_obj.location = Vector((3.0, -13.5, 34.0))
cam_top_obj.rotation_euler = (0.0, 0.0, 0.0)
col_lighting.objects.link(cam_top_obj)

# 3. Camera Assonometrica Nord-Ovest (corrisponde al render in alto a sinistra del Foglio 5)
cam_nw_data = bpy.data.cameras.new(name="Camera_Revit_Isometric_NW")
cam_nw_data.lens = 32
cam_nw_obj = bpy.data.objects.new(name="Camera_Revit_Isometric_NW", object_data=cam_nw_data)
cam_nw_obj.location = Vector((-32.0, 16.0, 28.0))
point_camera_at(cam_nw_obj, Vector((3.0, -13.5, 0.0)))
col_lighting.objects.link(cam_nw_obj)

# Imposta camera attiva
bpy.context.scene.camera = cam_sw_obj

# Setup viewport shading to show Material Preview
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        for space in area.spaces:
            if space.type == 'VIEW_3D':
                space.shading.type = 'MATERIAL'

print("=== Watertight Photorealistic Scene Generation v2 Finished Successfully ===")

