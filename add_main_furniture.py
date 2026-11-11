"""
Script to add all main furniture, structures, and tables to Smart_Home_3D:
PERFECTED according to user specifications:
1. Tavolo e sedie della sala da pranzo/cucina RUOTATI DI 90° (asse lungo Nord-Sud).
2. Cucina ad L:
   - Fuochi a gas AD ANGOLO (a 45°) con sopra la cappa rustica angolare a camino.
   - Bancone continuo che percorre l'angolo e prosegue lungo la parete ovest fino alla porta grande scorrevole in vetro (con microonde, macchina caffè e mensole).
   - Lavandino a 2 vasche nero con miscelatore cromato posizionato VICINO AL MURETTO divisorio della zona tavolo.
   - Pensile superiore sopra il lavandino.
3. Parete Ovest della sala (x = 9.70): la vetrinetta classica bombata appoggiata alla parete dei 3 gradini.
4. Parete Est (x = 13.90): frigorifero americano a due ante, colonna forno con pensile a vetri, colonna dispensa alta, termoarredo e 1° mobile bianco a box (Kallax) vicino al camino.
5. Parete Nord della cucina (y = -3.85): 2° mobile bianco a box (Kallax, identico al primo) tra la porta scorrevole e la porta dello sgabuzzino/bagno, carrello in legno e termoarredo.
6. Salotto: tavolo conviviale con sedie, mobile TV e TV 65'' a parete, madia lungo la parete nord, trave rustica e doppie porte scorrevoli satinate.
"""

import bpy
import bmesh
from mathutils import Vector, Matrix
import math

print("=== Starting Accurate Smart_Home_3D Furniture Setup ===")

# Helpers
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

def make_poly_slab(name, poly_2d, z_min, z_max, mat=None, collection=None):
    bm = bmesh.new()
    n = len(poly_2d)
    if poly_2d[0] == poly_2d[-1]:
        poly_2d = poly_2d[:-1]
        n = len(poly_2d)
    
    bot_verts = [bm.verts.new((x, y, z_min)) for x, y in poly_2d]
    top_verts = [bm.verts.new((x, y, z_max)) for x, y in poly_2d]
    
    for i in range(n):
        nxt = (i + 1) % n
        bm.faces.new([bot_verts[i], bot_verts[nxt], top_verts[nxt], top_verts[i]])
        
    bm.faces.new(top_verts)
    bm.faces.new(list(reversed(bot_verts)))
    
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
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

def make_cylinder(name, x, y, z_min, z_max, radius, segments=16, mat=None, collection=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=segments,
        radius1=radius,
        radius2=radius,
        depth=abs(z_max - z_min)
    )
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    
    obj = bpy.data.objects.new(name, mesh)
    obj.location = (x, y, (z_min + z_max) / 2.0)
    if mat:
        obj.data.materials.append(mat)
    if collection:
        collection.objects.link(obj)
    else:
        bpy.context.scene.collection.objects.link(obj)
    return obj

# Collection
col_name = "09_Arredi_Principali"
col_furniture = bpy.data.collections.get(col_name)
if not col_furniture:
    col_furniture = bpy.data.collections.new(col_name)
    bpy.context.scene.collection.children.link(col_furniture)

# Clean previous furniture objects
for o in list(col_furniture.objects):
    bpy.data.objects.remove(o, do_unlink=True)

# -------------------------------------------------------------
# MATERIALS SETUP
# -------------------------------------------------------------
def get_or_create_mat(name, color, roughness=0.35, metallic=0.0, transmission=0.0, ior=1.45, alpha=1.0):
    mat = bpy.data.materials.get(name)
    if not mat:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()
        out = nodes.new("ShaderNodeOutputMaterial")
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        if transmission > 0:
            if "Transmission Weight" in bsdf.inputs:
                bsdf.inputs["Transmission Weight"].default_value = transmission
            elif "Transmission" in bsdf.inputs:
                bsdf.inputs["Transmission"].default_value = transmission
            bsdf.inputs["IOR"].default_value = ior
        if alpha < 1.0:
            if "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = alpha
            mat.blend_method = 'BLEND'
        links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
        mat.diffuse_color = color
    return mat

mat_wood_table = get_or_create_mat("Mat_Legno_Tavolo_Noce", (0.42, 0.26, 0.14, 1.0), roughness=0.30)
mat_dark_beam = get_or_create_mat("Mat_Legno_Caminetto", (0.20, 0.12, 0.06, 1.0), roughness=0.45)
mat_frosted_glass = get_or_create_mat("Mat_Vetro_Satinato", (0.88, 0.91, 0.94, 1.0), roughness=0.38, transmission=0.88, ior=1.52, alpha=0.45)
mat_travertine = get_or_create_mat("Mat_Marmo_Travertino", (0.86, 0.83, 0.77, 1.0), roughness=0.28)
mat_travertine_dark = get_or_create_mat("Mat_Travertino_Scuro", (0.45, 0.38, 0.30, 1.0), roughness=0.35)
mat_white_lacquer = get_or_create_mat("Mat_Laccato_Bianco", (0.92, 0.92, 0.92, 1.0), roughness=0.25)
mat_fridge_inox = get_or_create_mat("Mat_Acciaio_Inox_Frigo", (0.80, 0.82, 0.84, 1.0), roughness=0.22, metallic=0.92)
mat_black_glass = get_or_create_mat("Mat_Vetro_Nero_TV", (0.02, 0.02, 0.02, 1.0), roughness=0.08, metallic=0.2)
mat_black_sink = get_or_create_mat("Mat_Lavello_Nero", (0.07, 0.07, 0.07, 1.0), roughness=0.55)
mat_chrome = get_or_create_mat("Mat_Cromo", (0.95, 0.95, 0.95, 1.0), roughness=0.08, metallic=1.0)
mat_wall_int = get_or_create_mat("Mat_Intonaco_Interno_Light", (0.94, 0.93, 0.91, 1.0), roughness=0.65)
mat_fabric = get_or_create_mat("Mat_Tessuto_Sedie", (0.78, 0.75, 0.68, 1.0), roughness=0.80)
mat_glass = get_or_create_mat("Mat_Vetro", (0.92, 0.96, 1.0, 1.0), roughness=0.02, transmission=0.98, ior=1.52, alpha=0.25)

# Helper for chair (oriented along X or Y)
def make_chair_oriented(name, cx, cy, facing='N'):
    # facing: 'N', 'S', 'E', 'W'
    w = 0.22
    for dx, dy in [(-w+0.02, -w+0.02), (w-0.02, -w+0.02), (-w+0.02, w-0.02), (w-0.02, w-0.02)]:
        make_box(f"{name}_Leg", cx + dx - 0.015, cx + dx + 0.015, cy + dy - 0.015, cy + dy + 0.015, 0.00, 0.44, mat_wood_table, col_furniture)
    make_box(f"{name}_Seat", cx - w, cx + w, cy - w, cy + w, 0.44, 0.48, mat_fabric, col_furniture)
    
    if facing == 'S': # backrest is on North side (+y)
        make_box(f"{name}_Back_L", cx - w, cx - w + 0.03, cy + w - 0.03, cy + w, 0.48, 0.96, mat_wood_table, col_furniture)
        make_box(f"{name}_Back_R", cx + w - 0.03, cx + w, cy + w - 0.03, cy + w, 0.48, 0.96, mat_wood_table, col_furniture)
        make_box(f"{name}_Back_Top", cx - w, cx + w, cy + w - 0.03, cy + w, 0.90, 0.96, mat_wood_table, col_furniture)
        for k in range(3):
            kx = cx - 0.10 + k * 0.10
            make_box(f"{name}_Slat_{k}", kx - 0.01, kx + 0.01, cy + w - 0.025, cy + w - 0.005, 0.52, 0.90, mat_wood_table, col_furniture)
    elif facing == 'N': # backrest on South side (-y)
        make_box(f"{name}_Back_L", cx - w, cx - w + 0.03, cy - w, cy - w + 0.03, 0.48, 0.96, mat_wood_table, col_furniture)
        make_box(f"{name}_Back_R", cx + w - 0.03, cx + w, cy - w, cy - w + 0.03, 0.48, 0.96, mat_wood_table, col_furniture)
        make_box(f"{name}_Back_Top", cx - w, cx + w, cy - w, cy - w + 0.03, 0.90, 0.96, mat_wood_table, col_furniture)
        for k in range(3):
            kx = cx - 0.10 + k * 0.10
            make_box(f"{name}_Slat_{k}", kx - 0.01, kx + 0.01, cy - w + 0.005, cy - w + 0.025, 0.52, 0.90, mat_wood_table, col_furniture)
    elif facing == 'E': # backrest on West side (-x)
        make_box(f"{name}_Back_L", cx - w, cx - w + 0.03, cy - w, cy - w + 0.03, 0.48, 0.96, mat_wood_table, col_furniture)
        make_box(f"{name}_Back_R", cx - w, cx - w + 0.03, cy + w - 0.03, cy + w, 0.48, 0.96, mat_wood_table, col_furniture)
        make_box(f"{name}_Back_Top", cx - w, cx - w + 0.03, cy - w, cy + w, 0.90, 0.96, mat_wood_table, col_furniture)
        for k in range(3):
            ky = cy - 0.10 + k * 0.10
            make_box(f"{name}_Slat_{k}", cx - w + 0.005, cx - w + 0.025, ky - 0.01, ky + 0.01, 0.52, 0.90, mat_wood_table, col_furniture)
    elif facing == 'W': # backrest on East side (+x)
        make_box(f"{name}_Back_L", cx + w - 0.03, cx + w, cy - w, cy - w + 0.03, 0.48, 0.96, mat_wood_table, col_furniture)
        make_box(f"{name}_Back_R", cx + w - 0.03, cx + w, cy + w - 0.03, cy + w, 0.48, 0.96, mat_wood_table, col_furniture)
        make_box(f"{name}_Back_Top", cx + w - 0.03, cx + w, cy - w, cy + w, 0.90, 0.96, mat_wood_table, col_furniture)
        for k in range(3):
            ky = cy - 0.10 + k * 0.10
            make_box(f"{name}_Slat_{k}", cx + w - 0.025, cx + w - 0.005, ky - 0.01, ky + 0.01, 0.52, 0.90, mat_wood_table, col_furniture)

# Helper for 2x4 white cube box unit (Kallax)
def make_kallax(prefix, x0, x1, y0, y1, oriented_along='X'):
    kz_h = 0.77
    if oriented_along == 'X':
        make_box(f"{prefix}_Fianco_L", x0, x0 + 0.035, y0, y1, 0.00, kz_h, mat_white_lacquer, col_furniture)
        make_box(f"{prefix}_Fianco_R", x1 - 0.035, x1, y0, y1, 0.00, kz_h, mat_white_lacquer, col_furniture)
        make_box(f"{prefix}_Base", x0, x1, y0, y1, 0.00, 0.035, mat_white_lacquer, col_furniture)
        make_box(f"{prefix}_Top", x0, x1, y0, y1, kz_h - 0.035, kz_h, mat_white_lacquer, col_furniture)
        make_box(f"{prefix}_Ripiano_Medio", x0 + 0.035, x1 - 0.035, y0, y1, kz_h/2.0 - 0.015, kz_h/2.0 + 0.015, mat_white_lacquer, col_furniture)
        w_col = (x1 - x0 - 0.07) / 4.0
        for c in range(1, 4):
            cx = x0 + 0.035 + c * w_col
            make_box(f"{prefix}_Divisorio_{c}", cx - 0.015, cx + 0.015, y0, y1, 0.035, kz_h - 0.035, mat_white_lacquer, col_furniture)
        make_box(f"{prefix}_Box_1", x0 + 0.05, x0 + 0.05 + w_col - 0.03, y0 + 0.01, y1 - 0.01, 0.05, kz_h/2.0 - 0.03, mat_white_lacquer, col_furniture)
        make_box(f"{prefix}_Box_2", x0 + 0.05 + w_col, x0 + 0.05 + 2*w_col - 0.03, y0 + 0.01, y1 - 0.01, 0.05, kz_h/2.0 - 0.03, mat_white_lacquer, col_furniture)
    else:
        make_box(f"{prefix}_Fianco_S", x0, x1, y0, y0 + 0.035, 0.00, kz_h, mat_white_lacquer, col_furniture)
        make_box(f"{prefix}_Fianco_N", x0, x1, y1 - 0.035, y1, 0.00, kz_h, mat_white_lacquer, col_furniture)
        make_box(f"{prefix}_Base", x0, x1, y0, y1, 0.00, 0.035, mat_white_lacquer, col_furniture)
        make_box(f"{prefix}_Top", x0, x1, y0, y1, kz_h - 0.035, kz_h, mat_white_lacquer, col_furniture)
        make_box(f"{prefix}_Ripiano_Medio", x0, x1, y0 + 0.035, y1 - 0.035, kz_h/2.0 - 0.015, kz_h/2.0 + 0.015, mat_white_lacquer, col_furniture)
        w_col = (y1 - y0 - 0.07) / 4.0
        for c in range(1, 4):
            cy = y0 + 0.035 + c * w_col
            make_box(f"{prefix}_Divisorio_{c}", x0, x1, cy - 0.015, cy + 0.015, 0.035, kz_h - 0.035, mat_white_lacquer, col_furniture)
        make_box(f"{prefix}_Box_1", x0 + 0.01, x1 - 0.01, y0 + 0.05, y0 + 0.05 + w_col - 0.03, 0.05, kz_h/2.0 - 0.03, mat_white_lacquer, col_furniture)
        make_box(f"{prefix}_Box_2", x0 + 0.01, x1 - 0.01, y0 + 0.05 + w_col, y0 + 0.05 + 2*w_col - 0.03, 0.05, kz_h/2.0 - 0.03, mat_white_lacquer, col_furniture)

# =============================================================
# 1. SALA DA PRANZO: TAVOLO RUOTATO DI 90°, PARETE EST, VETRINETTA
# =============================================================
print("1. Building Dining Sector (Table rotated 90 deg, East wall cabinets, Vitrine)...")

# A. TAVOLO DA PRANZO RUOTATO DI 90° (Asse lungo Nord-Sud: 1.90m su Y, 0.95m su X)
# Centrato a x = 11.55, y = -5.40
dt_x0, dt_x1 = 11.07, 12.03 # larghezza 0.96 m
dt_y0, dt_y1 = -6.35, -4.45 # lunghezza 1.90 m
# Piano in massello
make_box("Tavolo_Pranzo_Piano", dt_x0, dt_x1, dt_y0, dt_y1, 0.74, 0.78, mat_wood_table, col_furniture)
make_box("Tavolo_Pranzo_Telaio", dt_x0 + 0.05, dt_x1 - 0.05, dt_y0 + 0.06, dt_y1 - 0.06, 0.67, 0.74, mat_wood_table, col_furniture)
# 4 Gambe tornite
for lx, ly, ln in [(dt_x0 + 0.06, dt_y0 + 0.06, "SW"), (dt_x1 - 0.06, dt_y0 + 0.06, "SE"),
                   (dt_x0 + 0.06, dt_y1 - 0.06, "NW"), (dt_x1 - 0.06, dt_y1 - 0.06, "NE")]:
    make_cylinder(f"Tavolo_Pranzo_Gamba_{ln}", lx, ly, 0.00, 0.74, 0.045, segments=16, mat=mat_wood_table, collection=col_furniture)

# 6 Sedie coordinate (2 a Ovest, 2 a Est, 1 a Nord, 1 a Sud)
# 2 sedie a Ovest (rivolte a Est verso il tavolo)
make_chair_oriented("Sedia_Pranzo_W_1", dt_x0 - 0.30, -5.85, facing='E')
make_chair_oriented("Sedia_Pranzo_W_2", dt_x0 - 0.30, -4.95, facing='E')
# 2 sedie a Est (rivolte a Ovest verso il tavolo)
make_chair_oriented("Sedia_Pranzo_E_1", dt_x1 + 0.30, -5.85, facing='W')
make_chair_oriented("Sedia_Pranzo_E_2", dt_x1 + 0.30, -4.95, facing='W')
# Capotavola Nord (rivolta a Sud)
make_chair_oriented("Sedia_Pranzo_Capotavola_N", (dt_x0 + dt_x1)/2.0, dt_y1 + 0.30, facing='S')
# Capotavola Sud (rivolta a Nord)
make_chair_oriented("Sedia_Pranzo_Capotavola_S", (dt_x0 + dt_x1)/2.0, dt_y0 - 0.30, facing='N')

# Lampadario classico sospeso al centro del tavolo
ch_x = (dt_x0 + dt_x1) / 2.0
ch_y = (dt_y0 + dt_y1) / 2.0
make_cylinder("Lampadario_Pranzo_Asta", ch_x, ch_y, 2.20, 3.00, 0.01, segments=8, mat=mat_chrome, collection=col_furniture)
make_cylinder("Lampadario_Pranzo_Rosone", ch_x, ch_y, 2.10, 2.20, 0.08, segments=16, mat=mat_chrome, collection=col_furniture)
for ai, (adx, ady) in enumerate([(-0.25, 0), (0.25, 0), (0, -0.25), (0, 0.25)], start=1):
    make_cylinder(f"Lampadario_Braccio_{ai}", ch_x + adx*0.5, ch_y + ady*0.5, 2.12, 2.14, 0.008, segments=8, mat=mat_chrome, collection=col_furniture)
    make_cylinder(f"Lampadario_Coppa_{ai}", ch_x + adx, ch_y + ady, 2.05, 2.15, 0.09, segments=16, mat=mat_glass, collection=col_furniture)

# B. PARETE EST (x = 13.90)
# Termoarredo, Colonna Dispensa, Mobile Forno + Pensile, Frigo Americano, 1° Kallax
make_box("Termoarredo_Pranzo_Piastra", 13.82, 13.90, -7.50, -7.20, 0.15, 2.05, mat_white_lacquer, col_furniture)
for ti in range(8):
    typ = -7.48 + ti * 0.035
    make_cylinder(f"Termoarredo_Pranzo_Tubo_{ti}", 13.80, typ, 0.15, 2.05, 0.012, segments=12, mat=mat_white_lacquer, collection=col_furniture)

# Colonna Dispensa Alta con arco decorativo
make_box("Mobile_Dispensa_Colonna", 13.30, 13.90, -7.15, -6.50, 0.00, 2.25, mat_wood_table, col_furniture)
make_box("Mobile_Dispensa_Anta_Cornice", 13.28, 13.30, -7.13, -6.52, 0.10, 2.15, mat_wood_table, col_furniture)
make_box("Mobile_Dispensa_Arco_Top", 13.27, 13.91, -7.17, -6.48, 2.25, 2.38, mat_wood_table, col_furniture)

# Mobile Forno e Pensile Vetrina Superiore
make_box("Mobile_Forno_Base", 13.30, 13.90, -6.50, -5.55, 0.00, 0.95, mat_wood_table, col_furniture)
make_box("Forno_Incasso_Corpo", 13.27, 13.30, -6.35, -5.75, 0.32, 0.92, mat_black_glass, col_furniture)
make_box("Forno_Incasso_Maniglia", 13.24, 13.27, -6.30, -5.80, 0.86, 0.88, mat_chrome, col_furniture)
make_box("Forno_Cassettone", 13.28, 13.30, -6.45, -5.60, 0.08, 0.28, mat_wood_table, col_furniture)

make_box("Mobile_Pensile_Vetrina_Corpo", 13.52, 13.90, -6.50, -5.55, 1.55, 2.25, mat_wood_table, col_furniture)
make_box("Mobile_Pensile_Vetro_L", 13.50, 13.52, -6.45, -6.05, 1.62, 2.18, mat_glass, col_furniture)
make_box("Mobile_Pensile_Vetro_R", 13.50, 13.52, -6.00, -5.60, 1.62, 2.18, mat_glass, col_furniture)
make_box("Mobile_Pensile_Cornice", 13.48, 13.92, -6.52, -5.53, 2.25, 2.30, mat_wood_table, col_furniture)

# Frigorifero Americano Inox Side-by-Side
fr_y0, fr_y1 = -5.55, -4.63
fr_x0, fr_x1 = 13.15, 13.90
make_box("Frigo_Americano_Corpo", fr_x0, fr_x1, fr_y0, fr_y1, 0.00, 1.82, mat_fridge_inox, col_furniture)
make_box("Frigo_Porta_L", fr_x0 - 0.02, fr_x0, fr_y0 + 0.01, fr_y0 + 0.45, 0.08, 1.80, mat_fridge_inox, col_furniture)
make_box("Frigo_Porta_R", fr_x0 - 0.02, fr_x0, fr_y0 + 0.46, fr_y1 - 0.01, 0.08, 1.80, mat_fridge_inox, col_furniture)
make_box("Frigo_Dispenser", fr_x0 - 0.025, fr_x0 - 0.01, fr_y0 + 0.12, fr_y0 + 0.34, 1.05, 1.35, mat_black_glass, col_furniture)
make_box("Frigo_Maniglia_L", fr_x0 - 0.05, fr_x0 - 0.02, fr_y0 + 0.41, fr_y0 + 0.43, 0.60, 1.40, mat_chrome, col_furniture)
make_box("Frigo_Maniglia_R", fr_x0 - 0.05, fr_x0 - 0.02, fr_y0 + 0.47, fr_y0 + 0.49, 0.60, 1.40, mat_chrome, col_furniture)

# 1° Mobile Bianco a Box (tipo Kallax 2x4) vicino al camino
make_kallax("Kallax_1_Camino", 13.52, 13.90, -4.40, -2.90, oriented_along='Y')

# C. VETRINETTA BOMBATA SULLA PARETE DEI 3 GRADINI (x = 9.70)
vx0, vx1 = 9.70, 10.14
vy0, vy1 = -3.80, -2.95
make_box("Vetrina_Base_Legno", vx0, vx1, vy0, vy1, 0.00, 0.25, mat_wood_table, col_furniture)
make_box("Vetrina_Cappello_Legno", vx0 - 0.02, vx1 + 0.02, vy0 - 0.02, vy1 + 0.02, 1.85, 1.95, mat_wood_table, col_furniture)
make_box("Vetrina_Corpo_Vetro", vx0 + 0.02, vx1 - 0.02, vy0 + 0.02, vy1 - 0.02, 0.25, 1.85, mat_glass, col_furniture)
for vi, vz in enumerate([0.65, 1.05, 1.45], start=1):
    make_box(f"Vetrina_Ripiano_{vi}", vx0 + 0.04, vx1 - 0.04, vy0 + 0.04, vy1 - 0.04, vz, vz + 0.01, mat_glass, col_furniture)
for vpx, vpy in [(vx0, vy0), (vx1, vy0), (vx0, vy1), (vx1, vy1)]:
    make_cylinder("Vetrina_Montante", vpx, vpy, 0.25, 1.85, 0.02, segments=12, mat=mat_wood_table, collection=col_furniture)

# =============================================================
# 2. CUCINA VERA E PROPRIA (PERFEZIONATA FEDELMENTE ALLE FOTO REALI)
# =============================================================
print("2. Building Kitchen (Corner Cooktop & Hood, Sink near Muretto, Continuous Counter, Island, 2nd Kallax)...")

# A. ZONA AD ANGOLO: FUOCHI (GAS) A 45° CON SOPRA LA CAPPA A CAMINO
# Il raccordo angolare tra Ovest (x=6.37) e Sud (y=-7.75):
# Diagonale frontale a 45° connette (7.02, -6.57) a (7.55, -7.10) (larghezza 75 cm standard!)
poly_corner_base = [
    (6.37, -7.75),
    (7.55, -7.75),
    (7.55, -7.10),
    (7.02, -6.57),
    (6.37, -6.57)
]
make_poly_slab("Cucina_Basi_Angolo", poly_corner_base, 0.00, 0.86, mat_wood_table, col_furniture)

# Top in travertino ad angolo con bordo a 45° e sporgenza frontale di 2 cm
poly_corner_top = [
    (6.37, -7.75),
    (7.55, -7.75),
    (7.57, -7.08),
    (7.04, -6.55),
    (6.37, -6.57)
]
make_poly_slab("Cucina_Top_Angolo", poly_corner_top, 0.86, 0.90, mat_travertine, col_furniture)

# Anta / pannello frontale diagonale
make_poly_slab("Cucina_Angolo_Anta", [
    (7.03, -6.58), (7.54, -7.09), (7.52, -7.11), (7.01, -6.60)
], 0.12, 0.84, mat_wood_table, col_furniture)

# PIANO COTTURA A GAS AD ANGOLO (Tipo Franke/Foster angolare pentagonale)
cx_cook, cy_cook = 7.15, -6.97
rad45 = math.radians(45.0)
cos45, sin45 = math.cos(rad45), math.sin(rad45)
def rot45(lx, ly):
    return (cx_cook + lx*cos45 - ly*sin45, cy_cook + lx*sin45 + ly*cos45)

bm_hob = bmesh.new()
hw_front = 0.35
hw_back = 0.40
d_front = -0.22
d_back = 0.24
hob_2d = [
    rot45(-hw_front, d_front),
    rot45(hw_front, d_front),
    rot45(hw_back, 0.05),
    rot45(0.0, d_back),
    rot45(-hw_back, 0.05)
]
v_hob_top = [bm_hob.verts.new((x, y, 0.908)) for x, y in hob_2d]
v_hob_bot = [bm_hob.verts.new((x, y, 0.900)) for x, y in hob_2d]
for i in range(5):
    nxt = (i + 1) % 5
    bm_hob.faces.new([v_hob_bot[i], v_hob_bot[nxt], v_hob_top[nxt], v_hob_top[i]])
bm_hob.faces.new(v_hob_top)
bm_hob.faces.new(list(reversed(v_hob_bot)))

# Vaschetta ribassata
tray_2d = [
    rot45(-hw_front + 0.04, d_front + 0.07),
    rot45(hw_front - 0.04, d_front + 0.07),
    rot45(hw_back - 0.05, 0.05),
    rot45(0.0, d_back - 0.05),
    rot45(-hw_back + 0.05, 0.05)
]
v_tray_bot = [bm_hob.verts.new((x, y, 0.898)) for x, y in tray_2d]
v_tray_top = [bm_hob.verts.new((x, y, 0.908)) for x, y in tray_2d]
for i in range(5):
    nxt = (i + 1) % 5
    bm_hob.faces.new([v_tray_bot[i], v_tray_top[i], v_tray_top[nxt], v_tray_bot[nxt]])
bm_hob.faces.new(v_tray_bot)

bmesh.ops.recalc_face_normals(bm_hob, faces=bm_hob.faces)
mesh_hob = bpy.data.meshes.new("Cucina_Piano_Cottura_Angolare")
bm_hob.to_mesh(mesh_hob)
bm_hob.free()
obj_hob = bpy.data.objects.new("Cucina_Piano_Cottura_Angolare", mesh_hob)
obj_hob.data.materials.append(mat_fridge_inox)
col_furniture.objects.link(obj_hob)

# 5 Fuochi e Griglie in ghisa
burners_data = [
    ("Centrale_Wok", 0.0, 0.0, 0.055, 0.016, True),
    ("Sinistra_Front", -0.18, -0.06, 0.035, 0.012, False),
    ("Sinistra_Rear", -0.16, 0.12, 0.042, 0.012, False),
    ("Destra_Front", 0.18, -0.06, 0.038, 0.012, False),
    ("Destra_Rear", 0.16, 0.12, 0.045, 0.012, False),
]

for bname, lx, ly, brad, bh, is_wok in burners_data:
    bx, by = rot45(lx, ly)
    make_cylinder(f"Cucina_Bruciatore_{bname}_Base", bx, by, 0.908, 0.908 + bh, brad, segments=16, mat=mat_black_sink, collection=col_furniture)
    make_cylinder(f"Cucina_Bruciatore_{bname}_Cap", bx, by, 0.908 + bh, 0.908 + bh + 0.004, brad * 0.95, segments=16, mat=mat_black_sink, collection=col_furniture)
    if is_wok:
        make_cylinder(f"Cucina_Bruciatore_{bname}_InnerRing", bx, by, 0.908 + bh, 0.908 + bh + 0.005, brad * 0.45, segments=12, mat=mat_black_sink, collection=col_furniture)
    g_arm = brad + 0.035
    for rot_arm in [0, 45, 90, 135]:
        r_rad = math.radians(rot_arm) + rad45
        dx_arm = math.cos(r_rad) * g_arm
        dy_arm = math.sin(r_rad) * g_arm
        make_box(f"Cucina_Griglia_{bname}_{rot_arm}",
                 bx - dx_arm*0.9, bx + dx_arm*0.9,
                 by - dy_arm*0.9, by + dy_arm*0.9,
                 0.912, 0.928, mat_black_sink, col_furniture)

for ki, k_offset in enumerate([-0.20, -0.10, 0.0, 0.10, 0.20]):
    kx, ky = rot45(k_offset, d_front + 0.035)
    make_cylinder(f"Cucina_Manopola_{ki}", kx, ky, 0.908, 0.922, 0.014, segments=12, mat=mat_chrome, collection=col_furniture)
    make_cylinder(f"Cucina_Manopola_Top_{ki}", kx, ky, 0.922, 0.924, 0.012, segments=12, mat=mat_black_sink, collection=col_furniture)

# CAPPA RUSTICA ANGOLARE A CAMINO (Trave modanata a 45° + cappa piramidale rastremata)
x_c, y_c = 6.37, -7.75
d_hood_base = 0.95
poly_hood_beam = [
    (x_c, y_c),
    (x_c + d_hood_base, y_c),
    (x_c, y_c + d_hood_base)
]
make_poly_slab("Cucina_Cappa_Trave_Legno", poly_hood_beam, 1.62, 1.76, mat_dark_beam, col_furniture)

# Fascia decorativa a rombi in ceramica
bm_tile = bmesh.new()
p_diag_0 = (x_c, y_c + d_hood_base)
p_diag_1 = (x_c + d_hood_base, y_c)
nx_diag, ny_diag = math.cos(rad45) * 0.02, math.sin(rad45) * 0.02
v_tile_bot = [
    bm_tile.verts.new((p_diag_0[0] + nx_diag, p_diag_0[1] + ny_diag, 1.65)),
    bm_tile.verts.new((p_diag_1[0] + nx_diag, p_diag_1[1] + ny_diag, 1.65)),
    bm_tile.verts.new((p_diag_1[0], p_diag_1[1], 1.65)),
    bm_tile.verts.new((p_diag_0[0], p_diag_0[1], 1.65)),
]
v_tile_top = [
    bm_tile.verts.new((p_diag_0[0] + nx_diag, p_diag_0[1] + ny_diag, 1.73)),
    bm_tile.verts.new((p_diag_1[0] + nx_diag, p_diag_1[1] + ny_diag, 1.73)),
    bm_tile.verts.new((p_diag_1[0], p_diag_1[1], 1.73)),
    bm_tile.verts.new((p_diag_0[0], p_diag_0[1], 1.73)),
]
for i in range(4):
    nxt = (i + 1) % 4
    bm_tile.faces.new([v_tile_bot[i], v_tile_bot[nxt], v_tile_top[nxt], v_tile_top[i]])
bm_tile.faces.new(v_tile_top)
bm_tile.faces.new(list(reversed(v_tile_bot)))
bmesh.ops.recalc_face_normals(bm_tile, faces=bm_tile.faces)
mesh_tile = bpy.data.meshes.new("Cucina_Cappa_Fascia_Decorata")
bm_tile.to_mesh(mesh_tile)
bm_tile.free()
obj_tile = bpy.data.objects.new("Cucina_Cappa_Fascia_Decorata", mesh_tile)
obj_tile.data.materials.append(mat_travertine)
col_furniture.objects.link(obj_tile)

# Cappa rastremata a tronco di piramide (da z=1.76 a z=2.50)
bm_hood = bmesh.new()
d_b = 0.93
d_t = 0.48
z_hb = 1.76
z_ht = 2.50
v_hb = [
    bm_hood.verts.new((x_c, y_c, z_hb)),
    bm_hood.verts.new((x_c + d_b, y_c, z_hb)),
    bm_hood.verts.new((x_c, y_c + d_b, z_hb))
]
v_ht = [
    bm_hood.verts.new((x_c, y_c, z_ht)),
    bm_hood.verts.new((x_c + d_t, y_c, z_ht)),
    bm_hood.verts.new((x_c, y_c + d_t, z_ht))
]
bm_hood.faces.new([v_hb[0], v_hb[1], v_ht[1], v_ht[0]])
bm_hood.faces.new([v_hb[2], v_hb[0], v_ht[0], v_ht[2]])
bm_hood.faces.new([v_hb[1], v_hb[2], v_ht[2], v_ht[1]])
bm_hood.faces.new(list(reversed(v_hb)))
bm_hood.faces.new(v_ht)
bmesh.ops.recalc_face_normals(bm_hood, faces=bm_hood.faces)
mesh_hood = bpy.data.meshes.new("Cucina_Cappa_Muratura_Rastremata")
bm_hood.to_mesh(mesh_hood)
bm_hood.free()
obj_hood = bpy.data.objects.new("Cucina_Cappa_Muratura_Rastremata", mesh_hood)
obj_hood.data.materials.append(mat_wall_int)
col_furniture.objects.link(obj_hood)

# Collare superiore dritto con cornice (z: 2.50 a 2.70)
poly_hood_collar = [
    (x_c, y_c),
    (x_c + d_t, y_c),
    (x_c, y_c + d_t)
]
make_poly_slab("Cucina_Cappa_Collare_Top", poly_hood_collar, 2.50, 2.70, mat_wall_int, col_furniture)

# Travi in legno a soffitto a chiusura sopra la cappa (z: 2.70 a 2.82)
make_box("Cucina_Cappa_Trave_Soffitto_Ovest", 6.37, 6.70, -7.75, -5.85, 2.70, 2.82, mat_dark_beam, col_furniture)
make_box("Cucina_Cappa_Trave_Soffitto_Sud", 6.70, 7.57, -7.75, -7.45, 2.70, 2.82, mat_dark_beam, col_furniture)

# B. TRATTO OVEST: DALL'ANGOLO COTTURA ALLA PORTA SCORREVOLE (y: -6.57 a -5.85)
make_box("Cucina_Basi_Ovest", 6.37, 7.02, -6.57, -5.85, 0.00, 0.86, mat_wood_table, col_furniture)
make_box("Cucina_Top_Ovest", 6.37, 7.04, -6.57, -5.85, 0.86, 0.90, mat_travertine, col_furniture)
make_box("Cucina_Basi_Ovest_Fianco", 6.37, 7.02, -5.86, -5.85, 0.00, 0.86, mat_wood_table, col_furniture)
make_box("Cucina_Basi_Ovest_Anta_1", 7.02, 7.04, -6.55, -6.22, 0.12, 0.84, mat_wood_table, col_furniture)
make_box("Cucina_Basi_Ovest_Anta_2", 7.02, 7.04, -6.20, -5.88, 0.12, 0.84, mat_wood_table, col_furniture)
make_box("Cucina_Basi_Ovest_Maniglia_1", 7.04, 7.06, -6.40, -6.36, 0.76, 0.78, mat_chrome, col_furniture)
make_box("Cucina_Basi_Ovest_Maniglia_2", 7.04, 7.06, -6.04, -6.00, 0.76, 0.78, mat_chrome, col_furniture)
make_box("Cucina_Paraschizzi_Ovest", 6.37, 6.39, -6.57, -5.85, 0.90, 1.35, mat_travertine, col_furniture)

# MICROONDE INOX E VETRO NERO (Perfettamente poggiato sul top da y=-6.57 a y=-6.15)
make_box("Cucina_Microonde_Corpo", 6.42, 6.76, -6.57, -6.15, 0.90, 1.18, mat_fridge_inox, col_furniture)
make_box("Cucina_Microonde_Sportello_Vetro", 6.76, 6.77, -6.55, -6.25, 0.93, 1.15, mat_black_glass, col_furniture)
make_box("Cucina_Microonde_Maniglia", 6.775, 6.785, -6.54, -6.52, 0.95, 1.13, mat_fridge_inox, col_furniture)
make_box("Cucina_Microonde_Display", 6.76, 6.765, -6.24, -6.17, 1.09, 1.14, mat_black_glass, col_furniture)
make_cylinder("Cucina_Microonde_Manopola_1", 6.768, -6.205, 0.98, 1.02, 0.015, segments=12, mat=mat_chrome, collection=col_furniture)
make_cylinder("Cucina_Microonde_Manopola_2", 6.768, -6.205, 0.93, 0.97, 0.015, segments=12, mat=mat_chrome, collection=col_furniture)

# CEPPO COLTELLI
make_box("Cucina_Ceppo_Coltelli", 6.45, 6.57, -6.14, -6.06, 0.90, 1.08, mat_wood_table, col_furniture)

# MACCHINA DEL CAFFÈ ESPRESSO GAGGIA (Perfettamente sul top da y=-6.05 a y=-5.87)
make_box("Cucina_Macchina_Caffe_Corpo", 6.42, 6.80, -6.05, -5.87, 0.90, 1.24, mat_black_glass, col_furniture)
make_box("Cucina_Macchina_Caffe_Frontale_Silver", 6.77, 6.81, -6.05, -5.87, 0.95, 1.22, mat_fridge_inox, col_furniture)
make_box("Cucina_Macchina_Caffe_Erogatore", 6.81, 6.84, -5.99, -5.93, 1.02, 1.08, mat_chrome, col_furniture)
make_box("Cucina_Macchina_Caffe_DripTray", 6.72, 6.84, -6.05, -5.87, 0.90, 0.94, mat_chrome, col_furniture)

# MENSOLA SUPERIORE IN LEGNO LUNGO LA PARETE OVEST
make_box("Cucina_Mensola_Ovest", 6.38, 6.66, -6.80, -5.88, 1.55, 1.58, mat_dark_beam, col_furniture)

# C. TRATTO SUD: DALL'ANGOLO COTTURA AL MURETTO DIVISORIO (x: 7.55 a 9.71)
make_box("Cucina_Basi_Sud_Cassetti", 7.55, 8.65, -7.75, -7.10, 0.00, 0.86, mat_wood_table, col_furniture)
for ci in range(4):
    cz0 = 0.12 + ci * 0.175
    make_box(f"Cucina_Cassetto_{ci}", 7.57, 8.63, -7.10, -7.08, cz0, cz0 + 0.155, mat_wood_table, col_furniture)
    make_box(f"Cucina_Cassetto_Maniglia_{ci}", 8.00, 8.20, -7.08, -7.06, cz0 + 0.07, cz0 + 0.09, mat_chrome, col_furniture)

make_box("Cucina_Basi_Sud_SottoLavello", 8.65, 9.56, -7.75, -7.10, 0.00, 0.86, mat_wood_table, col_furniture)
make_box("Cucina_Anta_Lavello_L", 8.67, 9.09, -7.10, -7.08, 0.12, 0.84, mat_wood_table, col_furniture)
make_box("Cucina_Anta_Lavello_R", 9.11, 9.54, -7.10, -7.08, 0.12, 0.84, mat_wood_table, col_furniture)
make_box("Cucina_Anta_Lavello_Maniglia_L", 8.95, 9.05, -7.08, -7.06, 0.76, 0.78, mat_chrome, col_furniture)
make_box("Cucina_Anta_Lavello_Maniglia_R", 9.15, 9.25, -7.08, -7.06, 0.76, 0.78, mat_chrome, col_furniture)
make_box("Cucina_Basi_Sud_Parasta", 9.56, 9.71, -7.75, -7.10, 0.00, 0.86, mat_travertine_dark, col_furniture)

# TOP IN TRAVERTINO SUD CON FORO PASSANTE PER IL LAVELLO!
make_box("Cucina_Top_Sud_Sinistra", 7.55, 8.66, -7.75, -7.08, 0.86, 0.90, mat_travertine, col_furniture)
make_box("Cucina_Top_Sud_Posteriore", 8.66, 9.56, -7.75, -7.67, 0.86, 0.90, mat_travertine, col_furniture)
make_box("Cucina_Top_Sud_Frontale", 8.66, 9.56, -7.11, -7.08, 0.86, 0.90, mat_travertine, col_furniture)
make_box("Cucina_Top_Sud_Destra", 9.56, 9.71, -7.75, -7.08, 0.86, 0.90, mat_travertine, col_furniture)
make_box("Cucina_Paraschizzi_Sud", 8.60, 9.71, -7.75, -7.73, 0.90, 1.45, mat_travertine, col_furniture)

# LAVELLO A DUE VASCHE IN COMPOSITO NERO SCAVATO E IPER-REALISTICO
bm_sink = bmesh.new()
xl0, xl1 = 8.72, 9.08
xr0, xr1 = 9.14, 9.50
yb0, yb1 = -7.58, -7.17
z_f = 0.710
z_t = 0.895
z_rim = 0.906

v_l_bot = [
    bm_sink.verts.new((xl0, yb0, z_f)),
    bm_sink.verts.new((xl1, yb0, z_f)),
    bm_sink.verts.new((xl1, yb1, z_f)),
    bm_sink.verts.new((xl0, yb1, z_f))
]
v_l_top = [
    bm_sink.verts.new((xl0, yb0, z_t)),
    bm_sink.verts.new((xl1, yb0, z_t)),
    bm_sink.verts.new((xl1, yb1, z_t)),
    bm_sink.verts.new((xl0, yb1, z_t))
]
bm_sink.faces.new(v_l_bot)
for i in range(4):
    nxt = (i + 1) % 4
    bm_sink.faces.new([v_l_bot[i], v_l_top[i], v_l_top[nxt], v_l_bot[nxt]])

v_r_bot = [
    bm_sink.verts.new((xr0, yb0, z_f)),
    bm_sink.verts.new((xr1, yb0, z_f)),
    bm_sink.verts.new((xr1, yb1, z_f)),
    bm_sink.verts.new((xr0, yb1, z_f))
]
v_r_top = [
    bm_sink.verts.new((xr0, yb0, z_t)),
    bm_sink.verts.new((xr1, yb0, z_t)),
    bm_sink.verts.new((xr1, yb1, z_t)),
    bm_sink.verts.new((xr0, yb1, z_t))
]
bm_sink.faces.new(v_r_bot)
for i in range(4):
    nxt = (i + 1) % 4
    bm_sink.faces.new([v_r_bot[i], v_r_top[i], v_r_top[nxt], v_r_bot[nxt]])

xo0, xo1 = 8.66, 9.56
yo0, yo1 = -7.67, -7.11
v_ro = [
    bm_sink.verts.new((xo0, yo0, z_rim)),
    bm_sink.verts.new((xo1, yo0, z_rim)),
    bm_sink.verts.new((xo1, yo1, z_rim)),
    bm_sink.verts.new((xo0, yo1, z_rim))
]
v_ra = [
    bm_sink.verts.new((xo0, yo0, 0.900)),
    bm_sink.verts.new((xo1, yo0, 0.900)),
    bm_sink.verts.new((xo1, yo1, 0.900)),
    bm_sink.verts.new((xo0, yo1, 0.900))
]
for i in range(4):
    nxt = (i + 1) % 4
    bm_sink.faces.new([v_ra[i], v_ra[nxt], v_ro[nxt], v_ro[i]])

bm_sink.faces.new([v_ro[0], bm_sink.verts.new((xl0, yo0, z_rim)), bm_sink.verts.new((xl0, yo1, z_rim)), v_ro[3]])
bm_sink.faces.new([bm_sink.verts.new((xr1, yo0, z_rim)), v_ro[1], v_ro[2], bm_sink.verts.new((xr1, yo1, z_rim))])
bm_sink.faces.new([v_ro[3], bm_sink.verts.new((xl0, yo1, z_rim)), bm_sink.verts.new((xr1, yo1, z_rim)), v_ro[2]])
bm_sink.faces.new([v_ro[0], v_ro[1], bm_sink.verts.new((xr1, yo0, z_rim)), bm_sink.verts.new((xl0, yo0, z_rim))])

v_ls = [bm_sink.verts.new((xl0, yb0, z_rim)), bm_sink.verts.new((xl1, yb0, z_rim)), bm_sink.verts.new((xl1, yb1, z_rim)), bm_sink.verts.new((xl0, yb1, z_rim))]
for i in range(4):
    nxt = (i + 1) % 4
    bm_sink.faces.new([v_ls[i], v_ls[nxt], v_l_top[nxt], v_l_top[i]])

v_rs = [bm_sink.verts.new((xr0, yb0, z_rim)), bm_sink.verts.new((xr1, yb0, z_rim)), bm_sink.verts.new((xr1, yb1, z_rim)), bm_sink.verts.new((xr0, yb1, z_rim))]
for i in range(4):
    nxt = (i + 1) % 4
    bm_sink.faces.new([v_rs[i], v_rs[nxt], v_r_top[nxt], v_r_top[i]])

bm_sink.faces.new([v_l_top[1], v_r_top[0], v_r_top[3], v_l_top[2]])
bmesh.ops.recalc_face_normals(bm_sink, faces=bm_sink.faces)
mesh_sink = bpy.data.meshes.new("Cucina_Lavello_Due_Vasche")
bm_sink.to_mesh(mesh_sink)
bm_sink.free()
obj_sink = bpy.data.objects.new("Cucina_Lavello_Due_Vasche", mesh_sink)
obj_sink.data.materials.append(mat_black_sink)
col_furniture.objects.link(obj_sink)

# Pilette
make_cylinder("Cucina_Lavello_Piletta_L", (xl0 + xl1)/2.0, (yb0 + yb1)/2.0, 0.710, 0.715, 0.045, segments=16, mat=mat_chrome, collection=col_furniture)
make_cylinder("Cucina_Lavello_Tappo_L", (xl0 + xl1)/2.0, (yb0 + yb1)/2.0, 0.715, 0.722, 0.015, segments=12, mat=mat_black_sink, collection=col_furniture)
make_cylinder("Cucina_Lavello_Piletta_R", (xr0 + xr1)/2.0, (yb0 + yb1)/2.0, 0.710, 0.715, 0.045, segments=16, mat=mat_chrome, collection=col_furniture)
make_cylinder("Cucina_Lavello_Tappo_R", (xr0 + xr1)/2.0, (yb0 + yb1)/2.0, 0.715, 0.722, 0.015, segments=12, mat=mat_black_sink, collection=col_furniture)

# Miscelatore a collo d'oca
f_x, f_y = 9.11, -7.63
make_cylinder("Cucina_Miscelatore_Base", f_x, f_y, 0.906, 0.940, 0.024, segments=16, mat=mat_chrome, collection=col_furniture)
make_box("Cucina_Miscelatore_Leva", f_x + 0.02, f_x + 0.09, f_y - 0.012, f_y + 0.012, 0.965, 0.985, mat_chrome, col_furniture)
make_cylinder("Cucina_Miscelatore_Fusto", f_x, f_y, 0.940, 1.140, 0.015, segments=16, mat=mat_chrome, collection=col_furniture)

bm_faucet = bmesh.new()
n_pts = 14
arc_pts = []
for i in range(n_pts):
    t = i / (n_pts - 1)
    ang = t * math.pi
    p_z = 1.14 + 0.14 * math.sin(ang)
    p_y = f_y + 0.17 * (1.0 - math.cos(ang))/2.0
    arc_pts.append((f_x, p_y, p_z))

r_pipe = 0.012
rings = []
for p in arc_pts:
    ring = []
    for s in range(12):
        s_ang = s * (2 * math.pi / 12)
        rx = p[0] + r_pipe * math.cos(s_ang)
        rz = p[2] + r_pipe * math.sin(s_ang)
        ring.append(bm_faucet.verts.new((rx, p[1], rz)))
    rings.append(ring)

for i in range(len(rings) - 1):
    for s in range(12):
        nxt = (s + 1) % 12
        bm_faucet.faces.new([rings[i][s], rings[i][nxt], rings[i+1][nxt], rings[i+1][s]])

bmesh.ops.recalc_face_normals(bm_faucet, faces=bm_faucet.faces)
mesh_faucet = bpy.data.meshes.new("Cucina_Miscelatore_Collo_Oca")
bm_faucet.to_mesh(mesh_faucet)
bm_faucet.free()
obj_faucet = bpy.data.objects.new("Cucina_Miscelatore_Collo_Oca", mesh_faucet)
obj_faucet.data.materials.append(mat_chrome)
col_furniture.objects.link(obj_faucet)

make_cylinder("Cucina_Miscelatore_Beccuccio", f_x, f_y + 0.17, 1.115, 1.140, 0.014, segments=16, mat=mat_chrome, collection=col_furniture)

# Pensile a due ante sopra il lavello
make_box("Cucina_Pensile_Sopra_Lavello_Corpo", 8.66, 9.66, -7.75, -7.40, 1.45, 2.22, mat_wood_table, col_furniture)
make_box("Cucina_Pensile_Lavello_Cornice", 8.64, 9.68, -7.76, -7.38, 2.22, 2.28, mat_dark_beam, col_furniture)
make_box("Cucina_Pensile_Anta_L", 8.68, 9.14, -7.40, -7.38, 1.47, 2.20, mat_wood_table, col_furniture)
make_box("Cucina_Pensile_Anta_R", 9.18, 9.64, -7.40, -7.38, 1.47, 2.20, mat_wood_table, col_furniture)
make_cylinder("Cucina_Pensile_Pomolo_L", 9.10, -7.37, 1.55, 1.57, 0.012, segments=12, mat=mat_chrome, collection=col_furniture)
make_cylinder("Cucina_Pensile_Pomolo_R", 9.22, -7.37, 1.55, 1.57, 0.012, segments=12, mat=mat_chrome, collection=col_furniture)
make_box("Cucina_Asta_Utensili", 8.75, 9.55, -7.72, -7.70, 1.38, 1.39, mat_chrome, col_furniture)
for gi, gx in enumerate([8.85, 9.00, 9.15, 9.30, 9.45]):
    make_box(f"Cucina_Gancio_Utensile_{gi}", gx - 0.005, gx + 0.005, -7.71, -7.69, 1.33, 1.38, mat_chrome, col_furniture)

# D. ISOLA CENTRALE DELLA CUCINA
ix0, ix1 = 7.30, 8.60
iy0, iy1 = -6.00, -5.15
iz_top = 0.90
make_box("Isola_Fianco_W", ix0, ix0 + 0.06, iy0, iy1, 0.00, iz_top - 0.04, mat_travertine, col_furniture)
make_box("Isola_Fianco_E", ix1 - 0.06, ix1, iy0, iy1, 0.00, iz_top - 0.04, mat_travertine, col_furniture)
make_box("Isola_Base_Mobile", ix0 + 0.06, ix1 - 0.06, iy0 + 0.04, iy1 - 0.04, 0.08, iz_top - 0.04, mat_wood_table, col_furniture)
make_box("Isola_Piano_Travertino", ix0 - 0.02, ix1 + 0.02, iy0 - 0.02, iy1 + 0.02, iz_top - 0.04, iz_top, mat_travertine, col_furniture)
make_box("Isola_Inserto_Centrale", ix0 + 0.15, ix1 - 0.15, iy0 + 0.12, iy1 - 0.12, iz_top - 0.038, iz_top + 0.002, mat_travertine_dark, col_furniture)
make_box("Isola_Maniglia_1", ix0 + 0.40, ix0 + 0.55, iy0 - 0.03, iy0 - 0.01, 0.75, 0.77, mat_chrome, col_furniture)
make_box("Isola_Maniglia_2", ix0 + 0.75, ix0 + 0.90, iy0 - 0.03, iy0 - 0.01, 0.75, 0.77, mat_chrome, col_furniture)

# Due lampade a sospensione coniche sopra l'isola
for li, lx in enumerate([7.65, 8.25], start=1):
    make_cylinder(f"Isola_Cavo_Lampada_{li}", lx, -5.58, 2.30, 3.00, 0.005, segments=8, mat=mat_chrome, collection=col_furniture)
    bm_cone = bmesh.new()
    bmesh.ops.create_cone(bm_cone, cap_ends=True, segments=16, radius1=0.14, radius2=0.03, depth=0.18)
    mesh_cone = bpy.data.meshes.new(f"Isola_Lampada_Cono_{li}")
    bm_cone.to_mesh(mesh_cone)
    bm_cone.free()
    obj_cone = bpy.data.objects.new(f"Isola_Lampada_Cono_{li}", mesh_cone)
    obj_cone.location = (lx, -5.58, 2.20)
    obj_cone.data.materials.append(mat_white_lacquer)
    col_furniture.objects.link(obj_cone)

# E. PARETE NORD CUCINA (TRA PORTA SCORREVOLE E PORTA SGABUZZINO/BAGNO)
# Parete y = -3.85 (x da 6.37 a 8.69):
# 2° Mobile Bianco a Box (Kallax 2x4, identico a quello vicino al camino!)
make_kallax("Kallax_2_Cucina", 6.45, 7.95, -4.23, -3.85, oriented_along='X')

# Carrello da Cucina in Legno con ripiani
carr_x0, carr_x1 = 8.05, 8.55
carr_y0, carr_y1 = -4.30, -3.85
make_box("Carrello_Top", carr_x0, carr_x1, carr_y0, carr_y1, 0.81, 0.85, mat_wood_table, col_furniture)
make_box("Carrello_Ripiano_1", carr_x0 + 0.04, carr_x1 - 0.04, carr_y0 + 0.04, carr_y1 - 0.04, 0.45, 0.47, mat_wood_table, col_furniture)
make_box("Carrello_Ripiano_2", carr_x0 + 0.04, carr_x1 - 0.04, carr_y0 + 0.04, carr_y1 - 0.04, 0.12, 0.14, mat_wood_table, col_furniture)
for cx, cy in [(carr_x0+0.02, carr_y0+0.02), (carr_x1-0.02, carr_y0+0.02), (carr_x0+0.02, carr_y1-0.02), (carr_x1-0.02, carr_y1-0.02)]:
    make_cylinder("Carrello_Gamba", cx, cy, 0.04, 0.81, 0.015, segments=8, mat=mat_wood_table, collection=col_furniture)

# Termoarredo Verticale Cucina (a lato della porta antibagno a x = 9.48..9.68)
make_box("Termoarredo_Cucina_Piastra", 9.48, 9.68, -3.75, -3.67, 0.15, 2.05, mat_white_lacquer, col_furniture)
for ti in range(5):
    txp = 9.50 + ti * 0.035
    make_cylinder(f"Termoarredo_Cucina_Tubo_{ti}", txp, -3.78, 0.15, 2.05, 0.012, segments=12, mat=mat_white_lacquer, collection=col_furniture)

# =============================================================
# 3. APERTURA SALOTTO-CUCINA E SALOTTO
# =============================================================
print("3. Building Salotto-Cucina Beam, Sliding Doors, and Salotto Furniture...")

# Trave rustica maestra in legno antico sopra il varco salotto-cucina (y: -5.85 a -3.85)
make_box("Trave_Rustica_Salotto_Cucina", 6.00, 6.44, -5.95, -3.75, 2.25, 2.55, mat_dark_beam, col_furniture)
make_box("Wall_Salotto_Cucina_Header", 6.07, 6.37, -5.85, -3.85, 2.55, 2.83, mat_wall_int, col_furniture)

# Due ante scorrevoli a tutta altezza in vetro satinato/screziato
make_box("Porta_Scorrevole_Vetro_L", 6.04, 6.06, -5.85, -4.80, 0.02, 2.24, mat_frosted_glass, col_furniture)
make_box("Porta_Scorrevole_Vetro_R", 6.01, 6.03, -4.90, -3.85, 0.02, 2.24, mat_frosted_glass, col_furniture)
make_box("Maniglia_Porta_Scorrevole_L", 6.06, 6.09, -4.88, -4.84, 1.00, 1.25, mat_wood_table, col_furniture)
make_box("Maniglia_Porta_Scorrevole_R", 5.98, 6.01, -4.86, -4.82, 1.00, 1.25, mat_wood_table, col_furniture)

# SALOTTO:
# Tavolo conviviale del salotto con gambe tornite
st_x0, st_x1 = 2.40, 4.60
st_y0, st_y1 = -4.50, -3.50
make_box("Tavolo_Salotto_Piano", st_x0, st_x1, st_y0, st_y1, 0.74, 0.78, mat_wood_table, col_furniture)
make_box("Tavolo_Salotto_Telaio", st_x0 + 0.06, st_x1 - 0.06, st_y0 + 0.05, st_y1 - 0.05, 0.67, 0.74, mat_wood_table, col_furniture)
for lx, ly, ln in [(st_x0 + 0.05, st_y0 + 0.05, "SW"), (st_x1 - 0.05, st_y0 + 0.05, "SE"),
                   (st_x0 + 0.05, st_y1 - 0.05, "NW"), (st_x1 - 0.05, st_y1 - 0.05, "NE")]:
    make_cylinder(f"Tavolo_Salotto_Gamba_{ln}", lx, ly, 0.00, 0.74, 0.045, segments=16, mat=mat_wood_table, collection=col_furniture)

# 6 Sedie del salotto
for i, xpos in enumerate([2.80, 3.50, 4.20], start=1):
    make_chair_oriented(f"Sedia_Salotto_S_{i}", xpos, st_y0 - 0.28, facing='N')
    make_chair_oriented(f"Sedia_Salotto_N_{i}", xpos, st_y1 + 0.28, facing='S')

# Mobile TV e TV 65'' a parete sulla parete Ovest
make_box("Mobile_TV_Salotto_Base", 0.32, 0.80, -4.80, -3.20, 0.00, 0.50, mat_wood_table, col_furniture)
make_box("TV_Salotto_Screen", 0.33, 0.36, -4.70, -3.30, 0.85, 1.65, mat_black_glass, col_furniture)
make_box("TV_Salotto_Bezel", 0.32, 0.33, -4.72, -3.28, 0.83, 1.67, mat_fridge_inox, col_furniture)

# Madia credenza del salotto lungo la parete Nord
make_box("Madia_Salotto_Corpo", 1.50, 3.50, -0.75, -0.32, 0.00, 0.95, mat_wood_table, col_furniture)
make_box("Madia_Salotto_Top", 1.48, 3.52, -0.77, -0.31, 0.93, 0.96, mat_wood_table, col_furniture)

print("=== Perfectly Corrected Kitchen & Rotated Dining Setup Finished Successfully! ===")
