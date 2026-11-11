# update_kitchen_refined.py
# Perfezionamento fotorealistico dell'angolo cucina di Smart_Home_3D conforme alle foto reali:
# 1. Basi cucina ad angolo retto concavo a L (90° reale con paraste in tozzetti di travertino)
# 2. Top in marmo travertino con becco di civetta e smusso a 45° sul raccordo interno
# 3. Piano cottura a gas angolare a L (Foster/Franke angolare) con piastra inox, 4 fuochi, griglie in ghisa a ragno,
#    barra curva frontale di protezione e 5 manopole di regolazione
# 4. Paraschizzi ad arco in travertino sagomato a 90° contro le pareti con tozzetti superiori e barra mestoli
# 5. Cappa angolare a 45° con trave in noce, greca a rombi in ceramica e mensola superiore con oggetti
# 6. Mensola superiore a soffitto a L (z: 2.48-2.58) con faretti incassati e parete bianca a vista sopra
# 7. Mensola inferiore Ovest RIALZATA a z=1.96-2.00 con libro blu 'Il nuovo Cucchiaio Azzurro', teiera inox e barattoli
# 8. Accessori: portarotolo scottex, portaspezie, ceppo coltelli, microonde e macchina caffè Gaggia

import bpy
import bmesh
import mathutils
import math

print("=== Inizio Perfezionamento Angolo Cucina Smart_Home_3D ===")

col_furniture = bpy.data.collections.get("09_Arredi_Principali")
if not col_furniture:
    col_furniture = bpy.data.collections.new("09_Arredi_Principali")
    bpy.context.scene.collection.children.link(col_furniture)

# --- 1. MATERIALI PBR E COLORI DIFFUSE VIEWPORT ---
def get_or_create_material(name, base_color, metallic=0.0, roughness=0.5):
    mat = bpy.data.materials.get(name)
    if not mat:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
    mat.diffuse_color = base_color
    if mat.use_nodes:
        bsdf = [n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED']
        if bsdf:
            b = bsdf[0]
            if "Base Color" in b.inputs:
                b.inputs["Base Color"].default_value = base_color
            elif "Colore di base" in b.inputs:
                b.inputs["Colore di base"].default_value = base_color
            if "Metallic" in b.inputs:
                b.inputs["Metallic"].default_value = metallic
            elif "Metallico" in b.inputs:
                b.inputs["Metallico"].default_value = metallic
            if "Roughness" in b.inputs:
                b.inputs["Roughness"].default_value = roughness
            elif "Rugosità" in b.inputs:
                b.inputs["Rugosità"].default_value = roughness
    return mat

mat_travertine = get_or_create_material("Mat_Marmo_Travertino", (0.86, 0.81, 0.72, 1.0), 0.0, 0.35)
mat_travertine_mosaic = get_or_create_material("Mat_Travertino_Tozzetti", (0.80, 0.74, 0.65, 1.0), 0.0, 0.65)
mat_wood = get_or_create_material("Mat_Legno_Tavolo_Noce", (0.35, 0.20, 0.10, 1.0), 0.0, 0.45)
mat_dark_beam = get_or_create_material("Mat_Legno_Caminetto", (0.20, 0.11, 0.06, 1.0), 0.0, 0.65)
mat_black_sink = get_or_create_material("Mat_Lavello_Nero", (0.05, 0.05, 0.05, 1.0), 0.0, 0.3)
mat_chrome = get_or_create_material("Mat_Cromo", (0.95, 0.95, 0.95, 1.0), 0.95, 0.1)
mat_inox = get_or_create_material("Mat_Acciaio_Inox_Frigo", (0.82, 0.82, 0.84, 1.0), 0.9, 0.25)
mat_cast_iron = get_or_create_material("Mat_Focolare_Ghisa", (0.06, 0.06, 0.06, 1.0), 0.15, 0.8)
mat_black_glass = get_or_create_material("Mat_Vetro_Nero_TV", (0.02, 0.02, 0.02, 1.0), 0.1, 0.05)
mat_wall = get_or_create_material("Mat_Intonaco_Interno_Light", (0.92, 0.91, 0.89, 1.0), 0.0, 0.8)
mat_ceramic = get_or_create_material("Mat_Ceramica", (0.90, 0.88, 0.85, 1.0), 0.0, 0.2)
mat_brass = get_or_create_material("Mat_Ottone_Maniglie", (0.85, 0.65, 0.22, 1.0), 0.85, 0.3)
mat_blue_book = get_or_create_material("Mat_Libro_Blu", (0.06, 0.28, 0.70, 1.0), 0.0, 0.5)
mat_white_paper = get_or_create_material("Mat_Carta_Rotolo", (0.96, 0.96, 0.95, 1.0), 0.0, 0.9)

# Assicura diffuse_color per il viewport workbench/solid
mat_cast_iron.diffuse_color = (0.08, 0.08, 0.08, 1.0)
mat_dark_beam.diffuse_color = (0.22, 0.13, 0.07, 1.0)
mat_wood.diffuse_color = (0.38, 0.22, 0.12, 1.0)
mat_travertine.diffuse_color = (0.86, 0.81, 0.72, 1.0)
mat_travertine_mosaic.diffuse_color = (0.78, 0.72, 0.63, 1.0)
mat_blue_book.diffuse_color = (0.06, 0.28, 0.70, 1.0)
mat_brass.diffuse_color = (0.82, 0.65, 0.22, 1.0)
mat_inox.diffuse_color = (0.78, 0.78, 0.80, 1.0)

# --- 2. FUNZIONI HELPER MESH ---
def remove_existing(prefixes):
    to_delete = []
    for o in col_furniture.objects:
        for p in prefixes:
            if o.name.startswith(p):
                to_delete.append(o)
                break
    for o in bpy.data.objects:
        if o.name.startswith("Test_"):
            to_delete.append(o)
    for o in set(to_delete):
        bpy.data.objects.remove(o, do_unlink=True)

def make_box(name, x0, x1, y0, y1, z0, z1, mat, collection=col_furniture):
    x_min, x_max = min(x0, x1), max(x0, x1)
    y_min, y_max = min(y0, y1), max(y0, y1)
    z_min, z_max = min(z0, z1), max(z0, z1)
    bm = bmesh.new()
    verts = [
        bm.verts.new((x_min, y_min, z_min)),
        bm.verts.new((x_max, y_min, z_min)),
        bm.verts.new((x_max, y_max, z_min)),
        bm.verts.new((x_min, y_max, z_min)),
        bm.verts.new((x_min, y_min, z_max)),
        bm.verts.new((x_max, y_min, z_max)),
        bm.verts.new((x_max, y_max, z_max)),
        bm.verts.new((x_min, y_max, z_max)),
    ]
    bm.faces.new([verts[0], verts[3], verts[2], verts[1]])
    bm.faces.new([verts[4], verts[5], verts[6], verts[7]])
    bm.faces.new([verts[0], verts[1], verts[5], verts[4]])
    bm.faces.new([verts[2], verts[3], verts[7], verts[6]])
    bm.faces.new([verts[0], verts[4], verts[7], verts[3]])
    bm.faces.new([verts[1], verts[2], verts[6], verts[5]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    if mat:
        obj.data.materials.append(mat)
    collection.objects.link(obj)
    return obj

def make_cylinder(name, x, y, z0, z1, radius, segments=16, mat=None, collection=col_furniture):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments,
                          radius1=radius, radius2=radius, depth=(z1 - z0))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = (x, y, (z0 + z1)/2.0)
    if mat:
        obj.data.materials.append(mat)
    collection.objects.link(obj)
    return obj

def make_poly_prism(name, poly_2d, z0, z1, mat, collection=col_furniture):
    bm = bmesh.new()
    v_bot = [bm.verts.new((x, y, z0)) for x, y in poly_2d]
    v_top = [bm.verts.new((x, y, z1)) for x, y in poly_2d]
    n = len(poly_2d)
    for i in range(n):
        nxt = (i + 1) % n
        bm.faces.new([v_bot[i], v_bot[nxt], v_top[nxt], v_top[i]])
    bm.faces.new(list(reversed(v_bot)))
    bm.faces.new(v_top)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    if mat:
        obj.data.materials.append(mat)
    collection.objects.link(obj)
    return obj

# --- 3. RIMOZIONE ELEMENTI CUCINA ESISTENTI ---
remove_prefixes = [
    "Cucina_Basi", "Cucina_Top", "Cucina_Paraschizzi", "Cucina_Microonde",
    "Cucina_Macchina_Caffe", "Cucina_Coltelli", "Cucina_Mensola", "Cucina_Piano_Cottura",
    "Cucina_Bruciatore", "Cucina_Griglia", "Cucina_Manopola", "Cucina_Cappa",
    "Cucina_Lavello", "Cucina_Miscelatore", "Cucina_Pensile", "Cucina_Angolo",
    "Cucina_Cassetto", "Cucina_Anta", "Cucina_Asta", "Cucina_Gancio", "Cucina_Ceppo",
    "Cucina_Parasta", "Cucina_Libro", "Cucina_Teiera", "Cucina_Scottex", "Cucina_Barattolo",
    "Cucina_Portamestoli", "Cucina_Faretto", "Cucina_Mestolo", "Cucina_Spezie", "Test_"
]
remove_existing(remove_prefixes)
print("Rimossi vecchi elementi cucina.")

# --- 4. BASI CUCINA AD ANGOLO CONCAVO A 90° CON PARASTE IN TOZZETTI ---
# Parete Sud: y=-7.75, da x=6.37 a 9.71 (profondità 65 cm, fronte basi a y=-7.10)
# Parete Ovest: x=6.37, da y=-7.75 a -5.85 (profondità 65 cm, fronte basi a x=7.02)
# Zoccolatura continua in noce z: 0.00 a 0.12, arretrata di 4 cm
make_box("Cucina_Basi_Zoccolo_Sud", 6.37, 9.71, -7.75, -7.14, 0.00, 0.12, mat_wood)
make_box("Cucina_Basi_Zoccolo_Ovest", 6.37, 6.98, -7.75, -5.85, 0.00, 0.12, mat_wood)

# A. Parete Sud:
# 1. Modulo ad angolo cieco (6.37 a 7.02)
make_box("Cucina_Basi_Scocca_Angolo_Sud", 6.37, 7.02, -7.75, -7.10, 0.12, 0.86, mat_wood)
make_box("Cucina_Basi_Angolo_Spalla", 6.98, 7.02, -7.10, -7.06, 0.12, 0.86, mat_wood)

# 2. Anta singola Sud sotto i fuochi a sinistra (7.02 a 7.55)
make_box("Cucina_Basi_Scocca_Sud_Anta1", 7.02, 7.55, -7.75, -7.10, 0.12, 0.86, mat_wood)
make_box("Cucina_Anta_Sud_1_Telaio", 7.03, 7.54, -7.10, -7.08, 0.13, 0.85, mat_wood)
make_box("Cucina_Anta_Sud_1_Bugna", 7.08, 7.49, -7.09, -7.08, 0.18, 0.80, mat_wood)
make_box("Cucina_Anta_Sud_1_Maniglia", 7.46, 7.48, -7.08, -7.06, 0.70, 0.80, mat_brass)

# 3. Parasta piastrellata 1 Sud (7.55 a 7.67) - tozzetti di travertino
make_box("Cucina_Basi_Parasta_Sud_1", 7.55, 7.67, -7.75, -7.08, 0.00, 0.86, mat_travertine_mosaic)

# 4. Modulo cassettiera sotto finestra (7.67 a 8.65) - 4 cassetti
make_box("Cucina_Basi_Scocca_Sud_Cassetti", 7.67, 8.65, -7.75, -7.10, 0.12, 0.86, mat_wood)
for ci in range(4):
    cz0 = 0.13 + ci * 0.178
    make_box(f"Cucina_Cassetto_Frontale_{ci}", 7.69, 8.63, -7.10, -7.08, cz0, cz0 + 0.165, mat_wood)
    make_box(f"Cucina_Cassetto_Bugna_{ci}", 7.74, 8.58, -7.09, -7.08, cz0 + 0.02, cz0 + 0.145, mat_wood)
    make_box(f"Cucina_Cassetto_Maniglia_{ci}", 8.04, 8.28, -7.08, -7.06, cz0 + 0.07, cz0 + 0.09, mat_brass)

# 5. Parasta piastrellata 2 Sud (8.65 a 8.77)
make_box("Cucina_Basi_Parasta_Sud_2", 8.65, 8.77, -7.75, -7.08, 0.00, 0.86, mat_travertine_mosaic)

# 6. Modulo sottolavello a 2 ante (8.77 a 9.59)
make_box("Cucina_Basi_Scocca_Sud_Sottolavello", 8.77, 9.59, -7.75, -7.10, 0.12, 0.86, mat_wood)
make_box("Cucina_Anta_Lavello_L_Telaio", 8.79, 9.17, -7.10, -7.08, 0.13, 0.85, mat_wood)
make_box("Cucina_Anta_Lavello_L_Bugna", 8.84, 9.12, -7.09, -7.08, 0.18, 0.80, mat_wood)
make_box("Cucina_Anta_Lavello_R_Telaio", 9.19, 9.57, -7.10, -7.08, 0.13, 0.85, mat_wood)
make_box("Cucina_Anta_Lavello_R_Bugna", 9.24, 9.52, -7.09, -7.08, 0.18, 0.80, mat_wood)
make_box("Cucina_Anta_Lavello_Maniglia_L", 9.07, 9.15, -7.08, -7.06, 0.70, 0.80, mat_brass)
make_box("Cucina_Anta_Lavello_Maniglia_R", 9.21, 9.29, -7.08, -7.06, 0.70, 0.80, mat_brass)

# 7. Parasta piastrellata 3 Sud (9.59 a 9.71) contro divisorio
make_box("Cucina_Basi_Parasta_Sud_3", 9.59, 9.71, -7.75, -7.08, 0.00, 0.86, mat_travertine_mosaic)

# B. Parete Ovest:
# 1. Anta Ovest sotto i fuochi a destra (y: -7.10 a -6.55) facing +X
make_box("Cucina_Basi_Scocca_Ovest_Anta1", 6.37, 7.02, -7.10, -6.55, 0.12, 0.86, mat_wood)
make_box("Cucina_Anta_Ovest_1_Telaio", 7.02, 7.04, -7.08, -6.57, 0.13, 0.85, mat_wood)
make_box("Cucina_Anta_Ovest_1_Bugna", 7.02, 7.03, -7.03, -6.62, 0.18, 0.80, mat_wood)
make_box("Cucina_Anta_Ovest_1_Maniglia", 7.04, 7.06, -6.90, -6.75, 0.78, 0.80, mat_brass)

# 2. Parasta piastrellata 1 Ovest (-6.55 a -6.43)
make_box("Cucina_Basi_Parasta_Ovest_1", 6.37, 7.04, -6.55, -6.43, 0.00, 0.86, mat_travertine_mosaic)

# 3. Modulo sotto microonde (-6.43 a -5.97)
make_box("Cucina_Basi_Scocca_Ovest_Anta2", 6.37, 7.02, -6.43, -5.97, 0.12, 0.86, mat_wood)
make_box("Cucina_Anta_Ovest_2_Telaio", 7.02, 7.04, -6.41, -5.99, 0.13, 0.85, mat_wood)
make_box("Cucina_Anta_Ovest_2_Bugna", 7.02, 7.03, -6.36, -6.04, 0.18, 0.80, mat_wood)
make_box("Cucina_Anta_Ovest_2_Maniglia", 7.04, 7.06, -6.28, -6.13, 0.78, 0.80, mat_brass)

# 4. Parasta terminale Ovest (-5.97 a -5.85) e fianco
make_box("Cucina_Basi_Parasta_Ovest_2", 6.37, 7.04, -5.97, -5.85, 0.00, 0.86, mat_travertine_mosaic)
make_box("Cucina_Basi_Fianco_Ovest", 6.37, 7.02, -5.86, -5.85, 0.00, 0.86, mat_wood)


# --- 5. TOP IN TRAVERTINO SAGOMATO A L CON SMUSSO INTERNO ---
make_box("Cucina_Top_Sud_Centrale", 7.17, 8.78, -7.75, -7.08, 0.86, 0.90, mat_travertine)
make_box("Cucina_Top_Sud_DietroLavello", 8.78, 9.58, -7.75, -7.67, 0.86, 0.90, mat_travertine)
make_box("Cucina_Top_Sud_FronteLavello", 8.78, 9.58, -7.11, -7.08, 0.86, 0.90, mat_travertine)
make_box("Cucina_Top_Sud_Terminale", 9.58, 9.71, -7.75, -7.08, 0.86, 0.90, mat_travertine)
make_box("Cucina_Top_Ovest_Rettilineo", 6.37, 7.04, -6.95, -5.85, 0.86, 0.90, mat_travertine)

poly_top_corner = [
    (6.37, -7.75),
    (7.17, -7.75),
    (7.17, -7.08),
    (7.04, -6.95),
    (6.37, -6.95)
]
make_poly_prism("Cucina_Top_Angolo_L", poly_top_corner, 0.86, 0.90, mat_travertine)


# --- 6. PIANO COTTURA A GAS ANGOLARE A L CON BRUCIATORI E GRIGLIE ---
# Flangia sagomata inox satinato adiacente all'angolo pareti
poly_hob_flange = [
    (6.38, -7.74), # angolo muro interno
    (7.42, -7.74), # ala Sud lungo muro
    (7.42, -7.12), # bordo frontale ala Sud
    (7.15, -7.12), # inizio smusso manopole angolo interno
    (7.02, -6.99), # fine smusso manopole angolo interno
    (7.02, -6.70), # bordo frontale ala Ovest
    (6.38, -6.70), # ala Ovest lungo muro
]
make_poly_prism("Cucina_Piano_Cottura_Piastra_Inox", poly_hob_flange, 0.900, 0.908, mat_inox)

# Vaschette ribassate inox
make_box("Cucina_Piano_Cottura_Vaschetta_Sud", 6.78, 7.38, -7.66, -7.16, 0.898, 0.908, mat_inox)
make_box("Cucina_Piano_Cottura_Vaschetta_Ovest", 6.44, 6.98, -7.38, -6.76, 0.898, 0.908, mat_inox)

# I 4 BRUCIATORI A GAS CON GRIGLIE IN GHISA A RAGNO MARCATE:
burners_info = [
    ("Sud_Wok", 7.22, -7.41, 0.056, 0.016, 0.095, True),
    ("Sud_Rear", 6.92, -7.46, 0.042, 0.012, 0.075, False),
    ("Ovest_Front", 6.66, -6.94, 0.042, 0.012, 0.075, False),
    ("Ovest_Rear", 6.70, -7.26, 0.046, 0.013, 0.080, False)
]

for bname, bx, by, brad, bh, g_arm, is_wok in burners_info:
    # Base bruciatore ghisa
    make_cylinder(f"Cucina_Bruciatore_{bname}_Base", bx, by, 0.908, 0.908 + bh, brad, segments=16, mat=mat_cast_iron)
    # Spartifiamma
    make_cylinder(f"Cucina_Bruciatore_{bname}_Cap", bx, by, 0.908 + bh, 0.908 + bh + 0.005, brad * 0.95, segments=16, mat=mat_cast_iron)
    if is_wok:
        make_cylinder(f"Cucina_Bruciatore_{bname}_InnerRing", bx, by, 0.908 + bh, 0.908 + bh + 0.006, brad * 0.45, segments=12, mat=mat_brass)
    
    # Anello centrale griglia in ghisa
    make_cylinder(f"Cucina_Griglia_Ring_{bname}", bx, by, 0.910, 0.928, brad + 0.012, segments=16, mat=mat_cast_iron)
    # Bracci a croce e diagonali (4 razze principali a ragno)
    for rot_arm in [0, 90, 45, 135]:
        r_rad = math.radians(rot_arm)
        dx_arm = math.cos(r_rad) * g_arm
        dy_arm = math.sin(r_rad) * g_arm
        make_box(f"Cucina_Griglia_{bname}_{rot_arm}",
                 bx - dx_arm, bx + dx_arm,
                 by - dy_arm, by + dy_arm,
                 0.912, 0.934, mat_cast_iron)

# BARRA CURVA FRONTALE IN GHISA DI PROTEZIONE / APPOGGIO (crop_knobs.jpg)
rail_points = [
    (7.38, -7.14),
    (7.14, -7.14),
    (7.03, -7.03),
    (7.03, -6.72)
]
for i in range(len(rail_points) - 1):
    p0, p1 = rail_points[i], rail_points[i+1]
    make_box(f"Cucina_Griglia_Barra_Frontale_{i}",
             min(p0[0], p1[0]) - 0.012, max(p0[0], p1[0]) + 0.012,
             min(p0[1], p1[1]) - 0.012, max(p0[1], p1[1]) + 0.012,
             0.912, 0.932, mat_cast_iron)

# 5 MANOPOLE CILINDRICHE LUNGO LO SMUSSO A 45°
for ki in range(5):
    t = ki / 4.0
    kx = 7.13 * (1.0 - t) + 7.04 * t
    ky = -7.11 * (1.0 - t) + -7.02 * t
    make_cylinder(f"Cucina_Manopola_Base_{ki}", kx, ky, 0.908, 0.922, 0.014, segments=12, mat=mat_black_glass)
    make_cylinder(f"Cucina_Manopola_Puntatore_{ki}", kx, ky, 0.922, 0.926, 0.011, segments=12, mat=mat_chrome)


# --- 7. PARASCHIZZI AD ARCO IN TRAVERTINO CONTRO LE DUE PARETI ---
# Conforme a Image 1: il paraschizzi aderisce alle due pareti ad angolo di 90°
# Parete Sud: x da 6.37 a 7.35, y da -7.75 a -7.73 (arco da 1.22 a 1.38 nell'angolo)
make_box("Cucina_Paraschizzi_Sud_Arco", 6.37, 7.35, -7.75, -7.73, 0.90, 1.38, mat_travertine)
# Parete Ovest: x da 6.37 a 6.39, y da -7.75 a -6.75 (arco da 1.22 a 1.38 nell'angolo)
make_box("Cucina_Paraschizzi_Ovest_Arco", 6.37, 6.39, -7.75, -6.75, 0.90, 1.38, mat_travertine)

# Tozzetti di travertino burattato sopra l'arco fino alla base della cappa (z=1.62)
make_box("Cucina_Paraschizzi_Mosaico_Sud", 6.37, 7.35, -7.75, -7.73, 1.38, 1.62, mat_travertine_mosaic)
make_box("Cucina_Paraschizzi_Mosaico_Ovest", 6.37, 6.39, -7.75, -6.75, 1.38, 1.62, mat_travertine_mosaic)

# Barra cromata porta-mestoli a parete Sud (sotto la cappa, Image 1)
make_box("Cucina_Asta_Mestoli_Sud", 6.65, 7.25, -7.72, -7.70, 1.30, 1.32, mat_chrome)
for mi, mx in enumerate([6.72, 6.85, 6.98, 7.11]):
    make_box(f"Cucina_Mestolo_Gancio_{mi}", mx - 0.005, mx + 0.005, -7.71, -7.69, 1.25, 1.30, mat_chrome)
    make_box(f"Cucina_Mestolo_Manico_{mi}", mx - 0.006, mx + 0.006, -7.71, -7.69, 1.05, 1.25, mat_chrome)
    make_cylinder(f"Cucina_Mestolo_Coppa_{mi}", mx, -7.69, 1.01, 1.05, 0.024, segments=12, mat=mat_chrome)

# Portamestoli in legno noce con mestoli nell'angolo (Image 1)
make_cylinder("Cucina_Portamestoli_Legno", 6.55, -7.60, 0.90, 1.08, 0.055, segments=16, mat=mat_wood)


# --- 8. CAPPA ANGOLARE RUSTICA A CAMINO ---
# Trave modanata da z=1.62 a 1.76 con greca a rombi in ceramica
# Spazio mensola in legno sopra la trave a z=1.76
# Camino rastremato da z=1.76 a 2.48
x_c, y_c = 6.37, -7.75
d_hood = 0.95
rad45 = math.radians(45.0)

poly_hood_beam = [
    (x_c, y_c),
    (x_c + d_hood, y_c),
    (x_c, y_c + d_hood)
]
make_poly_prism("Cucina_Cappa_Trave_Legno", poly_hood_beam, 1.62, 1.76, mat_dark_beam)

# Fascia ceramica a rombi sulla faccia a 45°
p_d0 = (x_c, y_c + d_hood)
p_d1 = (x_c + d_hood, y_c)
nx_diag, ny_diag = math.cos(rad45) * 0.02, math.sin(rad45) * 0.02

bm_tile = bmesh.new()
v_tb = [
    bm_tile.verts.new((p_d0[0] + nx_diag, p_d0[1] + ny_diag, 1.65)),
    bm_tile.verts.new((p_d1[0] + nx_diag, p_d1[1] + ny_diag, 1.65)),
    bm_tile.verts.new((p_d1[0], p_d1[1], 1.65)),
    bm_tile.verts.new((p_d0[0], p_d0[1], 1.65)),
]
v_tt = [
    bm_tile.verts.new((p_d0[0] + nx_diag, p_d0[1] + ny_diag, 1.73)),
    bm_tile.verts.new((p_d1[0] + nx_diag, p_d1[1] + ny_diag, 1.73)),
    bm_tile.verts.new((p_d1[0], p_d1[1], 1.73)),
    bm_tile.verts.new((p_d0[0], p_d0[1], 1.73)),
]
for i in range(4):
    nxt = (i + 1) % 4
    bm_tile.faces.new([v_tb[i], v_tb[nxt], v_tt[nxt], v_tt[i]])
bm_tile.faces.new(v_tt)
bm_tile.faces.new(list(reversed(v_tb)))
bmesh.ops.recalc_face_normals(bm_tile, faces=bm_tile.faces)
mesh_tile = bpy.data.meshes.new("Cucina_Cappa_Fascia_Decorata")
bm_tile.to_mesh(mesh_tile)
bm_tile.free()
obj_tile = bpy.data.objects.new("Cucina_Cappa_Fascia_Decorata", mesh_tile)
obj_tile.data.materials.append(mat_ceramic)
col_furniture.objects.link(obj_tile)

# Camino rastremato in muratura (z: 1.76 a 2.48)
# Base leggermente arretrata di 6 cm rispetto alla trave per creare il bordo/mensolina
d_b = 0.89
d_t = 0.44
z_hb = 1.76
z_ht = 2.48

bm_hood = bmesh.new()
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
obj_hood.data.materials.append(mat_wall)
col_furniture.objects.link(obj_hood)


# --- 9. MENSOLA SUPERIORE A L A SOFFITTO (z: 2.48 a 2.58) ---
make_box("Cucina_Cappa_Trave_Soffitto_Ovest", 6.37, 6.70, -7.75, -5.85, 2.48, 2.58, mat_dark_beam)
make_box("Cucina_Cappa_Trave_Soffitto_Sud", 6.70, 7.57, -7.75, -7.42, 2.48, 2.58, mat_dark_beam)

# Faretti incassati sotto la mensola superiore
make_cylinder("Cucina_Faretto_Incassato_Ovest", 6.54, -6.35, 2.475, 2.482, 0.040, segments=16, mat=mat_chrome)
make_cylinder("Cucina_Faretto_Incassato_Sud", 7.15, -7.58, 2.475, 2.482, 0.040, segments=16, mat=mat_chrome)


# --- 10. MENSOLA INFERIORE OVEST RIALZATA (z: 1.96 a 2.00) CON ACCESSORI REALI ---
# RIALZATA esattamente come richiesto ("la mensola inferiore che deve stare più alta")
make_box("Cucina_Mensola_Ovest", 6.38, 6.64, -6.80, -5.88, 1.96, 2.00, mat_dark_beam)

# 1. Libro blu 'Il nuovo Cucchiaio Azzurro' in piedi appoggiato sulla mensola (Image 1, 2, 3)
make_box("Cucina_Libro_Cucchiaio_Azzurro", 6.40, 6.60, -6.64, -6.44, 2.00, 2.27, mat_blue_book)
make_box("Cucina_Libro_Dorso", 6.595, 6.602, -6.64, -6.44, 2.00, 2.27, mat_ceramic)

# 2. Teiera in acciaio inox
f_t_x, f_t_y = 6.51, -6.24
make_cylinder("Cucina_Teiera_Corpo", f_t_x, f_t_y, 2.00, 2.12, 0.065, segments=16, mat=mat_inox)
make_cylinder("Cucina_Teiera_Coperchio", f_t_x, f_t_y, 2.12, 2.145, 0.045, segments=16, mat=mat_inox)
make_cylinder("Cucina_Teiera_Pomolo", f_t_x, f_t_y, 2.145, 2.165, 0.012, segments=12, mat=mat_wood)
make_box("Cucina_Teiera_Beccuccio", f_t_x + 0.05, f_t_x + 0.09, f_t_y - 0.015, f_t_y + 0.015, 2.05, 2.11, mat_inox)
make_box("Cucina_Teiera_Manico", f_t_x - 0.09, f_t_x - 0.05, f_t_y - 0.012, f_t_y + 0.012, 2.03, 2.13, mat_inox)

# 3. Barattolo e pera in ceramica
make_cylinder("Cucina_Barattolo_Ceramica_1", 6.51, -6.04, 2.00, 2.08, 0.035, segments=14, mat=mat_ceramic)
make_cylinder("Cucina_Barattolo_Ceramica_2", 6.51, -5.94, 2.00, 2.11, 0.030, segments=14, mat=mat_ceramic)


# --- 11. ACCESSORI A PARETE SOTTO LA MENSOLA ---
# Paraschizzi continuo a tozzetti sopra il bancone Ovest (z: 0.90 a 1.35)
make_box("Cucina_Paraschizzi_Ovest", 6.37, 6.39, -6.75, -5.85, 0.90, 1.35, mat_travertine_mosaic)

# Portarotolo Scottex da parete (z: 1.35 sopra il microonde, Image 1 & 2)
make_box("Cucina_Scottex_Supporto_L", 6.38, 6.48, -6.50, -6.48, 1.32, 1.40, mat_chrome)
make_box("Cucina_Scottex_Supporto_R", 6.38, 6.48, -6.22, -6.20, 1.32, 1.40, mat_chrome)
make_cylinder("Cucina_Scottex_Rotolo_Carta", 6.43, -6.35, 1.33, 1.39, 0.048, segments=16, mat=mat_white_paper)

# Mensolina portaspezie con vasetti sotto lo scottex (Image 2)
make_box("Cucina_Portaspezie_Base", 6.38, 6.44, -6.18, -5.96, 1.32, 1.33, mat_wood)
for si, sy in enumerate([-6.14, -6.08, -6.02]):
    make_cylinder(f"Cucina_Spezie_Vasetto_{si}", 6.41, sy, 1.33, 1.38, 0.018, segments=12, mat=mat_ceramic)


# --- 12. ELETTRODOMESTICI BANCONE OVEST ---
# Microonde Inox e Vetro Nero
mw_x0, mw_x1 = 6.42, 6.78
mw_y0, mw_y1 = -6.60, -6.18
mw_z0, mw_z1 = 0.90, 1.18
make_box("Cucina_Microonde_Corpo", mw_x0, mw_x1, mw_y0, mw_y1, mw_z0, mw_z1, mat_inox)
make_box("Cucina_Microonde_Sportello_Vetro", mw_x1, mw_x1 + 0.01, mw_y0 + 0.02, mw_y1 - 0.10, mw_z0 + 0.03, mw_z1 - 0.03, mat_black_glass)
make_box("Cucina_Microonde_Maniglia", mw_x1 + 0.015, mw_x1 + 0.025, mw_y0 + 0.03, mw_y0 + 0.05, mw_z0 + 0.05, mw_z1 - 0.05, mat_inox)
make_box("Cucina_Microonde_Display", mw_x1, mw_x1 + 0.005, mw_y1 - 0.09, mw_y1 - 0.02, mw_z1 - 0.09, mw_z1 - 0.04, mat_black_glass)
make_cylinder("Cucina_Microonde_Manopola_1", mw_x1 + 0.008, mw_y1 - 0.055, 0.98, 1.02, 0.015, segments=12, mat=mat_chrome)
make_cylinder("Cucina_Microonde_Manopola_2", mw_x1 + 0.008, mw_y1 - 0.055, 0.93, 0.97, 0.015, segments=12, mat=mat_chrome)

# Ceppo Coltelli in legno noce
make_box("Cucina_Ceppo_Coltelli", 6.45, 6.57, -6.16, -6.07, 0.90, 1.08, mat_wood)

# Macchina Espresso Gaggia (Silver/Inox e Nero)
cm_x0, cm_x1 = 6.42, 6.80
cm_y0, cm_y1 = -6.05, -5.87
cm_z0, cm_z1 = 0.90, 1.25
make_box("Cucina_Macchina_Caffe_Corpo", cm_x0, cm_x1, cm_y0, cm_y1, cm_z0, cm_z1, mat_black_glass)
make_box("Cucina_Macchina_Caffe_Frontale_Silver", cm_x1 - 0.03, cm_x1 + 0.01, cm_y0, cm_y1, cm_z0 + 0.05, cm_z1 - 0.02, mat_inox)
make_box("Cucina_Macchina_Caffe_Erogatore", cm_x1 + 0.01, cm_x1 + 0.04, cm_y0 + 0.06, cm_y1 - 0.06, 1.02, 1.08, mat_chrome)
make_box("Cucina_Macchina_Caffe_DripTray", cm_x1 - 0.08, cm_x1 + 0.04, cm_y0, cm_y1, 0.90, 0.94, mat_chrome)


# --- 13. LAVELLO A DUE VASCHE IN COMPOSITO NERO E MISCELATORE COLLO D'OCA ---
bm_sink = bmesh.new()
xl0, xl1 = 8.84, 9.15
xr0, xr1 = 9.21, 9.52
yb0, yb1 = -7.58, -7.17
z_f = 0.710
z_t = 0.895
z_rim = 0.906

v_l_bot = [bm_sink.verts.new((xl0, yb0, z_f)), bm_sink.verts.new((xl1, yb0, z_f)), bm_sink.verts.new((xl1, yb1, z_f)), bm_sink.verts.new((xl0, yb1, z_f))]
v_l_top = [bm_sink.verts.new((xl0, yb0, z_t)), bm_sink.verts.new((xl1, yb0, z_t)), bm_sink.verts.new((xl1, yb1, z_t)), bm_sink.verts.new((xl0, yb1, z_t))]
bm_sink.faces.new(v_l_bot)
for i in range(4):
    nxt = (i + 1) % 4
    bm_sink.faces.new([v_l_bot[i], v_l_top[i], v_l_top[nxt], v_l_bot[nxt]])

v_r_bot = [bm_sink.verts.new((xr0, yb0, z_f)), bm_sink.verts.new((xr1, yb0, z_f)), bm_sink.verts.new((xr1, yb1, z_f)), bm_sink.verts.new((xr0, yb1, z_f))]
v_r_top = [bm_sink.verts.new((xr0, yb0, z_t)), bm_sink.verts.new((xr1, yb0, z_t)), bm_sink.verts.new((xr1, yb1, z_t)), bm_sink.verts.new((xr0, yb1, z_t))]
bm_sink.faces.new(v_r_bot)
for i in range(4):
    nxt = (i + 1) % 4
    bm_sink.faces.new([v_r_bot[i], v_r_top[i], v_r_top[nxt], v_r_bot[nxt]])

xo0, xo1 = 8.78, 9.58
yo0, yo1 = -7.67, -7.11
v_ro = [bm_sink.verts.new((xo0, yo0, z_rim)), bm_sink.verts.new((xo1, yo0, z_rim)), bm_sink.verts.new((xo1, yo1, z_rim)), bm_sink.verts.new((xo0, yo1, z_rim))]
v_ra = [bm_sink.verts.new((xo0, yo0, 0.900)), bm_sink.verts.new((xo1, yo0, 0.900)), bm_sink.verts.new((xo1, yo1, 0.900)), bm_sink.verts.new((xo0, yo1, 0.900))]
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

make_cylinder("Cucina_Lavello_Piletta_L", (xl0 + xl1)/2.0, (yb0 + yb1)/2.0, 0.710, 0.715, 0.045, segments=16, mat=mat_chrome)
make_cylinder("Cucina_Lavello_Tappo_L", (xl0 + xl1)/2.0, (yb0 + yb1)/2.0, 0.715, 0.722, 0.015, segments=12, mat=mat_black_glass)
make_cylinder("Cucina_Lavello_Piletta_R", (xr0 + xr1)/2.0, (yb0 + yb1)/2.0, 0.710, 0.715, 0.045, segments=16, mat=mat_chrome)
make_cylinder("Cucina_Lavello_Tappo_R", (xr0 + xr1)/2.0, (yb0 + yb1)/2.0, 0.715, 0.722, 0.015, segments=12, mat=mat_black_glass)

f_x, f_y = 9.18, -7.63
make_cylinder("Cucina_Miscelatore_Base", f_x, f_y, 0.906, 0.940, 0.024, segments=16, mat=mat_chrome)
make_box("Cucina_Miscelatore_Leva", f_x + 0.02, f_x + 0.09, f_y - 0.012, f_y + 0.012, 0.965, 0.985, mat_chrome)
make_cylinder("Cucina_Miscelatore_Fusto", f_x, f_y, 0.940, 1.140, 0.015, segments=16, mat=mat_chrome)

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
make_cylinder("Cucina_Miscelatore_Beccuccio", f_x, f_y + 0.17, 1.115, 1.140, 0.014, segments=16, mat=mat_chrome)

make_box("Cucina_Pensile_Sopra_Lavello_Corpo", 8.66, 9.66, -7.75, -7.40, 1.45, 2.22, mat_wood)
make_box("Cucina_Pensile_Lavello_Cornice", 8.64, 9.68, -7.76, -7.38, 2.22, 2.28, mat_dark_beam)
make_box("Cucina_Pensile_Anta_L", 8.68, 9.14, -7.40, -7.38, 1.47, 2.20, mat_wood)
make_box("Cucina_Pensile_Anta_R", 9.18, 9.64, -7.40, -7.38, 1.47, 2.20, mat_wood)
make_cylinder("Cucina_Pensile_Pomolo_L", 9.10, -7.37, 1.55, 1.57, 0.012, segments=12, mat=mat_brass)
make_cylinder("Cucina_Pensile_Pomolo_R", 9.22, -7.37, 1.55, 1.57, 0.012, segments=12, mat=mat_brass)
make_box("Cucina_Paraschizzi_Sud_Lavello", 8.65, 9.71, -7.75, -7.73, 0.90, 1.45, mat_travertine_mosaic)

# Salva il file blend per rendere le modifiche permanenti
bpy.ops.wm.save_mainfile()
print("=== Perfezionamento Angolo Cucina Completato e File Blend Salvato! ===")
