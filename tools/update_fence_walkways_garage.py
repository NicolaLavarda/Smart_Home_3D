"""
update_fence_walkways_garage.py
Aggiorna in Smart_Home_3D.blend:
1. Recinzione nord-ovest obliqua (da (0,0) a (-9.11, -1.50)), tratto nord-ovest-sud (-4.78m fino a Y=-6.28),
   linea cancelli/pilastri 38x38cm (h=1.50m), muretto centrale basso (h=1.30m) con palo telecamera (+38cm -> Z=1.68m),
   cancelletto pedonale (117cm), cancello carraio (318cm), recinzione ovest (X=-15.22) e recinzione sud obliqua.
2. Terrazza_All_Aperto (cemento stampato esterno + 200cm interni al cancello carraio).
3. Vialetto pedonale lungo muro ovest (100cm) + curva morbida dal cancelletto (117cm -> 150cm) al centro del portico (Y=-9.77).
4. Viale carraio in ghiaia (318cm -> curva morbida a 90° -> 240cm davanti al portone garage).
5. Colonne a est della lavanderia (Pillar_Portico_1 64x64cm a nord, Pillar_Portico_2 30x30cm a sud) e pavimentazione portico/lavanderia.
6. Correzione posizione e profondità del Garage (2.80m a sud della lavanderia, 6.30m totali N-S, porte e finestre Revit).
7. Prati watertight (Giardino Area 1, 2, 3A, 3B, 3C), lampioncini, gettini irrigazione e label.
"""

import math
import bpy
import bmesh
from mathutils import Vector, geometry


def get_or_create_collection(name):
    col = bpy.data.collections.get(name)
    if not col:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def get_mat(name):
    return bpy.data.materials.get(name)


def make_box(name, x_min, x_max, y_min, y_max, z_min, z_max, mat=None, collection=None):
    if x_min > x_max:
        x_min, x_max = x_max, x_min
    if y_min > y_max:
        y_min, y_max = y_max, y_min
    if z_min > z_max:
        z_min, z_max = z_max, z_min
    if abs(x_max - x_min) < 1e-4 or abs(y_max - y_min) < 1e-4 or abs(z_max - z_min) < 1e-4:
        return None

    mesh = bpy.data.meshes.new(name)
    verts = [
        (x_min, y_min, z_min), (x_max, y_min, z_min),
        (x_max, y_max, z_min), (x_min, y_max, z_min),
        (x_min, y_min, z_max), (x_max, y_min, z_max),
        (x_max, y_max, z_max), (x_min, y_max, z_max),
    ]
    faces = [
        (0, 3, 2, 1),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    obj = bpy.data.objects.new(name, mesh)
    if mat:
        obj.data.materials.append(mat)
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def add_prism_to_bm(bm, poly_2d, z_min, z_max):
    pts = list(poly_2d)
    if len(pts) >= 2 and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 1e-6:
        pts = pts[:-1]
    # Remove consecutive duplicate vertices
    cleaned = []
    for p in pts:
        if not cleaned or math.hypot(p[0] - cleaned[-1][0], p[1] - cleaned[-1][1]) > 1e-6:
            cleaned.append(p)
    pts = cleaned
    if len(pts) < 3:
        return

    # Ensure counter-clockwise winding in XY so normals point outward cleanly
    area2 = sum(
        pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
        for i in range(len(pts))
    )
    if area2 < 0:
        pts.reverse()

    bot_verts = [bm.verts.new((x, y, z_min)) for x, y in pts]
    top_verts = [bm.verts.new((x, y, z_max)) for x, y in pts]

    n = len(pts)
    for i in range(n):
        nxt = (i + 1) % n
        bm.faces.new([bot_verts[i], bot_verts[nxt], top_verts[nxt], top_verts[i]])

    tris = geometry.tessellate_polygon([[Vector((x, y, 0.0)) for x, y in pts]])
    for i0, i1, i2 in tris:
        try:
            bm.faces.new([top_verts[i0], top_verts[i1], top_verts[i2]])
        except ValueError:
            pass
        try:
            bm.faces.new([bot_verts[i0], bot_verts[i2], bot_verts[i1]])
        except ValueError:
            pass


def make_poly_slab(name, poly_2d, z_min, z_max, mat=None, collection=None):
    bm = bmesh.new()
    add_prism_to_bm(bm, poly_2d, z_min, z_max)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    if mat:
        obj.data.materials.append(mat)
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def make_multi_poly_slab(name, polys_2d, z_min, z_max, mat=None, collection=None):
    bm = bmesh.new()
    for poly_2d in polys_2d:
        add_prism_to_bm(bm, poly_2d, z_min, z_max)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    if mat:
        obj.data.materials.append(mat)
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def make_multi_rect_slab(name, rects, z_min, z_max, mat=None, collection=None):
    bm = bmesh.new()
    for x0, x1, y0, y1 in rects:
        add_prism_to_bm(bm, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], z_min, z_max)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    if mat:
        obj.data.materials.append(mat)
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def add_detailed_fence(name, p0, p1, col_fence, mat_curb, mat_railing,
                       h_curb=0.32, h_rail=1.10, post_spacing=2.20, picket_spacing=0.18):
    x0, y0 = p0
    x1, y1 = p1
    length = math.hypot(x1 - x0, y1 - y0)
    if length < 0.02:
        return
    dx = (x1 - x0) / length
    dy = (y1 - y0) / length
    nx, ny = -dy, dx

    w_curb = 0.22
    poly_curb = [
        (x0 + nx * w_curb / 2, y0 + ny * w_curb / 2),
        (x1 + nx * w_curb / 2, y1 + ny * w_curb / 2),
        (x1 - nx * w_curb / 2, y1 - ny * w_curb / 2),
        (x0 - nx * w_curb / 2, y0 - ny * w_curb / 2),
    ]
    make_poly_slab(f"{name}_Curb", poly_curb, 0.0, h_curb, mat_curb, col_fence)

    w_rail = 0.04
    poly_rail = [
        (x0 + nx * w_rail / 2, y0 + ny * w_rail / 2),
        (x1 + nx * w_rail / 2, y1 + ny * w_rail / 2),
        (x1 - nx * w_rail / 2, y1 - ny * w_rail / 2),
        (x0 - nx * w_rail / 2, y0 - ny * w_rail / 2),
    ]
    make_poly_slab(f"{name}_Rail_Bot", poly_rail, h_curb + 0.04, h_curb + 0.08, mat_railing, col_fence)
    make_poly_slab(f"{name}_Rail_Top", poly_rail, h_rail - 0.04, h_rail, mat_railing, col_fence)

    if length >= 0.25:
        num_posts = max(2, int(round(length / post_spacing)) + 1)
        wp = 0.07
        for i in range(num_posts):
            t = i / (num_posts - 1)
            px = x0 + t * (x1 - x0)
            py = y0 + t * (y1 - y0)
            make_box(f"{name}_Post_{i}", px - wp / 2, px + wp / 2, py - wp / 2, py + wp / 2,
                     h_curb, h_rail + 0.06, mat_railing, col_fence)

        num_pickets = int(length / picket_spacing)
        wpk = 0.02
        for j in range(1, num_pickets):
            t = j * picket_spacing / length
            px = x0 + t * (x1 - x0)
            py = y0 + t * (y1 - y0)
            make_box(f"{name}_Picket_{j}", px - wpk / 2, px + wpk / 2, py - wpk / 2, py + wpk / 2,
                     h_curb + 0.08, h_rail - 0.04, mat_railing, col_fence)


def make_offset_curb(name, path_pts, width, outward_left, z_min, z_max, mat, col):
    """Build a continuous mitered curb ribbon along path_pts offset by `width` to left/right."""
    pts = []
    for p in path_pts:
        if not pts or math.hypot(p[0] - pts[-1][0], p[1] - pts[-1][1]) > 1e-5:
            pts.append(p)
    if len(pts) < 2:
        return None
    seg_normals = []
    for i in range(len(pts) - 1):
        dx = pts[i + 1][0] - pts[i][0]
        dy = pts[i + 1][1] - pts[i][1]
        L = math.hypot(dx, dy) or 1.0
        nx, ny = (-dy / L, dx / L) if outward_left else (dy / L, -dx / L)
        seg_normals.append((nx, ny))

    outer_pts = []
    for i, (px, py) in enumerate(pts):
        if i == 0:
            mx, my = seg_normals[0]
        elif i == len(pts) - 1:
            mx, my = seg_normals[-1]
        else:
            n0, n1 = seg_normals[i - 1], seg_normals[i]
            denom = max(0.25, 1.0 + n0[0] * n1[0] + n0[1] * n1[1])
            mx, my = (n0[0] + n1[0]) / denom, (n0[1] + n1[1]) / denom
        outer_pts.append((px + mx * width, py + my * width))

    bm = bmesh.new()
    for i in range(len(pts) - 1):
        quad = [pts[i], pts[i + 1], outer_pts[i + 1], outer_pts[i]]
        add_prism_to_bm(bm, quad, z_min, z_max)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    if mat:
        obj.data.materials.append(mat)
    col.objects.link(obj)
    return obj


def add_picket_gate_leaf(name, hinge_x, hinge_y, span_x, num_pickets=11, z_bot=0.12, z_top=1.45, mat=None, col=None):
    """Build a single metal picket gate leaf whose object origin sits at the side hinge (hinge_x, hinge_y, 0)."""
    sign = 1.0 if span_x >= 0 else -1.0
    x_start = 0.015 * sign
    x_end = span_x - 0.01 * sign
    x_min, x_max = min(x_start, x_end), max(x_start, x_end)

    t_frame = 0.04
    half_y = 0.015
    half_pk = 0.010

    bm = bmesh.new()

    def add_local_box(bx0, bx1, by0, by1, bz0, bz1):
        verts = bmesh.ops.create_cube(bm, size=1.0)["verts"]
        cx, cy, cz = (bx0 + bx1) * 0.5, (by0 + by1) * 0.5, (bz0 + bz1) * 0.5
        sx, sy, sz = abs(bx1 - bx0), abs(by1 - by0), abs(bz1 - bz0)
        for v in verts:
            v.co.x = cx + v.co.x * sx
            v.co.y = cy + v.co.y * sy
            v.co.z = cz + v.co.z * sz

    # Perimeter frame
    add_local_box(x_min, x_max, -half_y, half_y, z_bot, z_bot + t_frame)
    add_local_box(x_min, x_max, -half_y, half_y, z_top - t_frame, z_top)
    add_local_box(x_min, x_min + t_frame, -half_y, half_y, z_bot + t_frame, z_top - t_frame)
    add_local_box(x_max - t_frame, x_max, -half_y, half_y, z_bot + t_frame, z_top - t_frame)

    # Equally spaced vertical metal pickets
    inner_x0 = x_min + t_frame
    inner_x1 = x_max - t_frame
    for k in range(1, num_pickets + 1):
        px = inner_x0 + k * (inner_x1 - inner_x0) / (num_pickets + 1)
        add_local_box(px - half_pk, px + half_pk, -half_pk, half_pk, z_bot + t_frame, z_top - t_frame)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    obj.location = Vector((hinge_x, hinge_y, 0.0))
    if mat:
        obj.data.materials.append(mat)
    (col or bpy.context.scene.collection).objects.link(obj)
    return obj


def add_window(name, x_min, x_max, y_min, y_max, sill_h, lintel_h, col_fixtures, mat_frame, mat_glass):
    t_frame = 0.05
    d_frame = 0.08
    w = abs(x_max - x_min)
    y_c = (y_min + y_max) / 2.0
    make_box(f"{name}_Frame_Bottom", x_min, x_max, y_c - d_frame / 2, y_c + d_frame / 2, sill_h, sill_h + t_frame, mat_frame, col_fixtures)
    make_box(f"{name}_Frame_Top", x_min, x_max, y_c - d_frame / 2, y_c + d_frame / 2, lintel_h - t_frame, lintel_h, mat_frame, col_fixtures)
    make_box(f"{name}_Frame_Left", x_min, x_min + t_frame, y_c - d_frame / 2, y_c + d_frame / 2, sill_h + t_frame, lintel_h - t_frame, mat_frame, col_fixtures)
    make_box(f"{name}_Frame_Right", x_max - t_frame, x_max, y_c - d_frame / 2, y_c + d_frame / 2, sill_h + t_frame, lintel_h - t_frame, mat_frame, col_fixtures)
    if w > 0.70:
        x_m = (x_min + x_max) / 2.0
        make_box(f"{name}_Mullion", x_m - t_frame / 2, x_m + t_frame / 2, y_c - d_frame / 2, y_c + d_frame / 2, sill_h + t_frame, lintel_h - t_frame, mat_frame, col_fixtures)
    make_box(f"{name}_Glass", x_min + t_frame, x_max - t_frame, y_c - 0.01, y_c + 0.01, sill_h + t_frame, lintel_h - t_frame, mat_glass, col_fixtures)


def add_door(name, x_min, x_max, y_min, y_max, col_fixtures, mat_door_wood, mat_chrome, lintel_h=2.13, open_deg=40.0):
    t_frame = 0.05
    d_frame = 0.10
    rad = math.radians(open_deg)
    w = abs(x_max - x_min)
    y_c = (y_min + y_max) / 2.0
    make_box(f"{name}_Frame_Top", x_min, x_max, y_c - d_frame / 2, y_c + d_frame / 2, lintel_h - t_frame, lintel_h, mat_door_wood, col_fixtures)
    make_box(f"{name}_Frame_Left", x_min, x_min + t_frame, y_c - d_frame / 2, y_c + d_frame / 2, 0.0, lintel_h - t_frame, mat_door_wood, col_fixtures)
    make_box(f"{name}_Frame_Right", x_max - t_frame, x_max, y_c - d_frame / 2, y_c + d_frame / 2, 0.0, lintel_h - t_frame, mat_door_wood, col_fixtures)

    p_w = w - 2 * t_frame
    p_t = 0.04
    p_h = lintel_h - t_frame
    hx = x_min + t_frame
    hy = y_c
    c_loc = [(0, -p_t / 2), (p_w, -p_t / 2), (p_w, p_t / 2), (0, p_t / 2)]
    c_rot = [(hx + x * math.cos(rad) - y * math.sin(rad), hy + x * math.sin(rad) + y * math.cos(rad)) for x, y in c_loc]

    mesh = bpy.data.meshes.new(f"{name}_Panel")
    verts = [
        (c_rot[0][0], c_rot[0][1], 0.0), (c_rot[1][0], c_rot[1][1], 0.0),
        (c_rot[2][0], c_rot[2][1], 0.0), (c_rot[3][0], c_rot[3][1], 0.0),
        (c_rot[0][0], c_rot[0][1], p_h), (c_rot[1][0], c_rot[1][1], p_h),
        (c_rot[2][0], c_rot[2][1], p_h), (c_rot[3][0], c_rot[3][1], p_h),
    ]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(f"{name}_Panel", mesh)
    obj.data.materials.append(mat_door_wood)
    col_fixtures.objects.link(obj)

    hand_dist = p_w - 0.08
    han_x = hx + hand_dist * math.cos(rad)
    han_y = hy + hand_dist * math.sin(rad)
    make_box(f"{name}_Handle", han_x - 0.06, han_x + 0.06, han_y - 0.02, han_y + 0.02, 0.98, 1.02, mat_chrome, col_fixtures)


def move_group_xy(prefixes, new_x, new_y):
    """Translate a group of parts (e.g. Bollard_Garden_2* or Sprinkler_Area1_2*) so primary object sits at (new_x, new_y)."""
    primary = bpy.data.objects.get(prefixes[0])
    if not primary:
        return
    vs = [primary.matrix_world @ v.co for v in primary.data.vertices]
    cx = 0.5 * (min(v.x for v in vs) + max(v.x for v in vs))
    cy = 0.5 * (min(v.y for v in vs) + max(v.y for v in vs))
    dx = new_x - cx
    dy = new_y - cy
    for name in prefixes:
        obj = bpy.data.objects.get(name)
        if obj:
            obj.location.x += dx
            obj.location.y += dy


def run_update():
    print("=== Updating Fence, Gates, Camera, Curved Walkways, Pillars & Garage ===")

    col_site = get_or_create_collection("01_Sito_e_Giardini")
    col_garage = get_or_create_collection("04_Garage")
    col_fixtures = get_or_create_collection("06_Infissi_e_Porte")
    col_fence = get_or_create_collection("07_Recinzione_e_Cancelli")
    col_cameras = get_or_create_collection("08_Luci_e_Camere")

    mat_grass = get_mat("Mat_Prato_Fotorealistico")
    mat_gravel = get_mat("Mat_Ghiaia_Fotorealistica")
    mat_portico = get_mat("Mat_Lastricato_Pietra")
    mat_concrete = get_mat("Mat_Cemento_Garage")
    mat_wall_ext = get_mat("Mat_Intonaco_Esterno_Dark")
    mat_curb = get_mat("Mat_Cordolo_Pietra")
    mat_railing = get_mat("Mat_Ringhiera_Metallo")
    mat_frame = get_mat("Mat_Infissi_Antracite")
    mat_glass = get_mat("Mat_Vetro")
    mat_door_wood = get_mat("Mat_Porta_Legno")
    mat_garage_door = get_mat("Mat_Portone_Garage")
    mat_chrome = get_mat("Mat_Cromo")

    # ---------------------------------------------------------
    # 1. CLEANUP OLD OBJECTS TO BE REBUILT
    # ---------------------------------------------------------
    prefixes_to_remove = (
        "Fence_", "Gate_Pillar_", "Gate_Ped_", "Gate_Leaf_", "Gate_Central_",
        "Walkway_", "Giardino_Area_", "Driveway_Gravel", "Portico_Pavement_Unified",
        "Terrazza_All_Aperto", "Site_Foundation_Earth", "Muro_Cinta_Est",
        "Pillar_Portico_",
        "Wall_Garage_", "Floor_Garage_", "Garage_Basement_Step_",
        "Railing_Garage_Stair_", "Pillar_Garage_", "Beam_Portico_Garage",
        "Door_Garage_Pedestrian_", "Win_Garage_", "Garage_Door_Panel_",
    )
    for obj in list(bpy.data.objects):
        if obj.name.startswith("Switch_"):
            continue
        if obj.name.startswith(prefixes_to_remove):
            bpy.data.objects.remove(obj, do_unlink=True)

    # ---------------------------------------------------------
    # 2. PERIMETER FENCES, GATES, PILLARS & CENTRAL LOW WALL
    # ---------------------------------------------------------
    # North-West oblique fence: from house NW corner (0.00, 0.00) -> (-9.11, -1.50)
    add_detailed_fence("Fence_North_West", (0.00, 0.00), (-9.11, -1.50), col_fence, mat_curb, mat_railing)
    # North-West vertical fence: from (-9.11, -1.50) -> (-9.11, -6.28)
    add_detailed_fence("Fence_North_West_Vert", (-9.11, -1.50), (-9.11, -6.28), col_fence, mat_curb, mat_railing)

    # 5cm stub from (-9.11, -6.28) to (-9.16, -6.28)
    make_box("Fence_Gate_Stub_East_Curb", -9.16, -9.11, -6.39, -6.17, 0.00, 0.32, mat_curb, col_fence)
    make_box("Fence_Gate_Stub_East_Rail_Bot", -9.16, -9.11, -6.30, -6.26, 0.36, 0.40, mat_railing, col_fence)
    make_box("Fence_Gate_Stub_East_Rail_Top", -9.16, -9.11, -6.30, -6.26, 1.06, 1.10, mat_railing, col_fence)

    # 1st Pillar (East of pedestrian gate): 38x38cm, h=1.50m
    make_box("Gate_Ped_Pillar_R", -9.54, -9.16, -6.47, -6.09, 0.00, 1.50, mat_curb, col_fence)

    # Pedestrian Gate (117cm opening: X in [-10.71, -9.54])
    wp_l, wp_r = -10.68, -9.57
    h_g_bot, h_g_top = 0.12, 1.45
    make_box("Gate_Ped_Frame_Bot", wp_l, wp_r, -6.29, -6.27, h_g_bot, h_g_bot + 0.04, mat_railing, col_fence)
    make_box("Gate_Ped_Frame_Top", wp_l, wp_r, -6.29, -6.27, h_g_top - 0.04, h_g_top, mat_railing, col_fence)
    make_box("Gate_Ped_Frame_L", wp_l, wp_l + 0.04, -6.29, -6.27, h_g_bot, h_g_top, mat_railing, col_fence)
    make_box("Gate_Ped_Frame_R", wp_r - 0.04, wp_r, -6.29, -6.27, h_g_bot, h_g_top, mat_railing, col_fence)
    for pk in range(1, 7):
        pk_x = wp_l + pk * (wp_r - wp_l) / 7.0
        make_box(f"Gate_Ped_Picket_{pk}", pk_x - 0.01, pk_x + 0.01, -6.29, -6.27, h_g_bot + 0.04, h_g_top - 0.04, mat_railing, col_fence)
    make_box("Gate_Ped_Handle", wp_r - 0.10, wp_r - 0.03, -6.32, -6.24, 0.95, 1.05, mat_chrome, col_fence)

    # 38 + 38 + 38 cm block between pedestrian gate and driveway gate (X in [-11.85, -10.71])
    make_box("Gate_Ped_Pillar_L", -11.09, -10.71, -6.47, -6.09, 0.00, 1.50, mat_curb, col_fence)
    make_box("Gate_Central_Low_Wall", -11.47, -11.09, -6.47, -6.09, 0.00, 1.30, mat_curb, col_fence)
    make_box("Gate_Pillar_R", -11.85, -11.47, -6.47, -6.09, 0.00, 1.50, mat_curb, col_fence)

    # Driveway Gate (318cm opening: X in [-15.03, -11.85], metal picket style with side hinge pivots)
    leaf_l = add_picket_gate_leaf("Gate_Leaf_L", -15.03, -6.28, +1.59, num_pickets=11, z_bot=0.12, z_top=1.45, mat=mat_railing, col=col_fence)
    leaf_r = add_picket_gate_leaf("Gate_Leaf_R", -11.85, -6.28, -1.59, num_pickets=11, z_bot=0.12, z_top=1.45, mat=mat_railing, col=col_fence)
    for leaf in (leaf_l, leaf_r):
        if leaf:
            leaf["ha_entity"] = "switch.switch_casa_interruttore_1"
            leaf["ha_action"] = "toggle"
            leaf["ha_ui_type"] = "sliding_gate"
            leaf["ha_name"] = "Cancello Carraio"

    # 4th Pillar (West of driveway gate): 38x38cm, h=1.50m
    make_box("Gate_Pillar_L", -15.41, -15.03, -6.47, -6.09, 0.00, 1.50, mat_curb, col_fence)

    # Move Gate Switches
    sw_car = bpy.data.objects.get("Switch_Gate_Carraio")
    if sw_car:
        sw_car.location = Vector((-13.44, -6.28, 0.85))
    sw_ped = bpy.data.objects.get("Switch_Gate_Ped")
    if sw_ped:
        sw_ped.location = Vector((-9.60, -6.28, 1.05))

    # West Fence & Oblique South Fence
    add_detailed_fence("Fence_West", (-15.22, -6.47), (-15.22, -33.61), col_fence, mat_curb, mat_railing)
    add_detailed_fence("Fence_South", (-15.22, -33.61), (13.90, -31.20), col_fence, mat_curb, mat_railing)

    # ---------------------------------------------------------
    # 3. TELECAMERA CARRAIO ON CENTRAL LOW WALL (218cm from -9.11)
    # ---------------------------------------------------------
    cam_x, cam_y, low_wall_z, pole_h = -11.29, -6.28, 1.30, 0.38
    cam_z = low_wall_z + pole_h  # 1.68 m

    for old_cam_mesh in ("Security_Cam_Pole_Pillar", "Security_Cam_Body"):
        obj = bpy.data.objects.get(old_cam_mesh)
        if obj:
            bpy.data.objects.remove(obj, do_unlink=True)

    bpy.ops.mesh.primitive_cylinder_add(radius=0.025, depth=pole_h, location=(cam_x, cam_y, low_wall_z + pole_h * 0.5))
    pole_obj = bpy.context.active_object
    pole_obj.name = "Security_Cam_Pole_Pillar"
    if mat_railing:
        pole_obj.data.materials.append(mat_railing)
    for c in list(pole_obj.users_collection):
        c.objects.unlink(pole_obj)
    col_cameras.objects.link(pole_obj)

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cam_x, cam_y + 0.05, cam_z), scale=(0.08, 0.16, 0.08))
    body_obj = bpy.context.active_object
    body_obj.name = "Security_Cam_Body"
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if mat_frame:
        body_obj.data.materials.append(mat_frame)
    for c in list(body_obj.users_collection):
        c.objects.unlink(body_obj)
    col_cameras.objects.link(body_obj)

    cam_obj = bpy.data.objects.get("Cam_Carraio")
    if cam_obj:
        cam_obj.location = Vector((cam_x, cam_y, cam_z))

    # ---------------------------------------------------------
    # 4. LAUNDRY PORTICO PILLARS & EAST BOUNDARY WALL
    # ---------------------------------------------------------
    # North column (64x64cm): aligned north with laundry (-12.43), 60cm gap from laundry east (4.65 -> 5.25), east face at 124cm (5.89)
    make_box("Pillar_Portico_1", 5.25, 5.89, -13.07, -12.43, 0.00, 2.70, mat_wall_ext, col_site)
    # South column (30x30cm): aligned south with laundry (-15.43), east face at 124cm (5.89)
    make_box("Pillar_Portico_2", 5.59, 5.89, -15.43, -15.13, 0.00, 2.70, mat_wall_ext, col_site)

    # East boundary wall split cleanly around Garage East Wall (-24.53..-19.23) so there is zero Z-fighting
    make_box("Muro_Cinta_Est", 13.90, 14.20, -19.23, -8.05, 0.00, 2.20, mat_wall_ext, col_site)
    make_box("Muro_Cinta_Est_Sud", 13.90, 14.20, -31.30, -24.53, 0.00, 2.20, mat_wall_ext, col_site)

    # ---------------------------------------------------------
    # 5. GARAGE (2.80m south of Lavanderia -> North edge Y = -18.23)
    # ---------------------------------------------------------
    H_GAR = 2.80
    x_g0, x_g1 = 6.39, 14.20
    y_porch_n = -18.23
    y_g_n_out = -19.23
    y_g_n_in = -19.53
    y_g_s_in = -24.23
    y_g_s_out = -24.53

    # East wall
    make_box("Wall_Garage_East", 13.90, 14.20, y_g_s_out, y_g_n_out, 0.00, H_GAR, mat_wall_ext, col_garage)

    # West wall with 240cm overhead door (Y in [-23.03, -20.63])
    make_box("Wall_Garage_West_Ext", x_g0, x_g0 + 0.30, y_g_n_out, y_porch_n, 0.00, H_GAR, mat_wall_ext, col_garage)
    make_box("Wall_Garage_West_01", x_g0, x_g0 + 0.30, -20.63, y_g_n_out, 0.00, H_GAR, mat_wall_ext, col_garage)
    make_box("Wall_Garage_West_Lintel", x_g0, x_g0 + 0.30, -23.03, -20.63, 2.10, H_GAR, mat_wall_ext, col_garage)
    make_box("Wall_Garage_West_02", x_g0, x_g0 + 0.30, y_g_s_out, -23.03, 0.00, H_GAR, mat_wall_ext, col_garage)

    for pan in range(5):
        zp0 = pan * (2.05 / 5.0)
        zp1 = zp0 + (2.05 / 5.0) - 0.015
        make_box(f"Garage_Door_Panel_{pan + 1}", x_g0 + 0.12, x_g0 + 0.18, -23.00, -20.66, zp0, zp1, mat_garage_door, col_fixtures)

    sw_gar = bpy.data.objects.get("Switch_Garage_Door")
    if sw_gar:
        sw_gar.location = Vector((6.54, -21.83, 1.15))

    # North wall (Revit chain: 80 + 92 + 80 + 61 + 247 + 61 + 100 = 721cm)
    make_box("Wall_Garage_North_01", 6.69, 7.49, y_g_n_in, y_g_n_out, 0.00, H_GAR, mat_wall_ext, col_garage)
    make_box("Wall_Garage_North_Door_Lintel", 7.49, 8.41, y_g_n_in, y_g_n_out, 2.13, H_GAR, mat_wall_ext, col_garage)
    add_door("Door_Garage_Pedestrian", 7.49, 8.41, y_g_n_in, y_g_n_out, col_fixtures, mat_door_wood, mat_chrome, lintel_h=2.13, open_deg=40.0)

    make_box("Wall_Garage_North_02", 8.41, 9.21, y_g_n_in, y_g_n_out, 0.00, H_GAR, mat_wall_ext, col_garage)
    make_box("Wall_Garage_North_Sill_1", 9.21, 9.82, y_g_n_in, y_g_n_out, 0.00, 1.00, mat_wall_ext, col_garage)
    make_box("Wall_Garage_North_Lintel_1", 9.21, 9.82, y_g_n_in, y_g_n_out, 1.61, H_GAR, mat_wall_ext, col_garage)
    add_window("Win_Garage_N1", 9.21, 9.82, y_g_n_in, y_g_n_out, 1.00, 1.61, col_fixtures, mat_frame, mat_glass)

    make_box("Wall_Garage_North_03", 9.82, 12.29, y_g_n_in, y_g_n_out, 0.00, H_GAR, mat_wall_ext, col_garage)
    make_box("Wall_Garage_North_Sill_2", 12.29, 12.90, y_g_n_in, y_g_n_out, 0.00, 1.00, mat_wall_ext, col_garage)
    make_box("Wall_Garage_North_Lintel_2", 12.29, 12.90, y_g_n_in, y_g_n_out, 1.61, H_GAR, mat_wall_ext, col_garage)
    add_window("Win_Garage_N2", 12.29, 12.90, y_g_n_in, y_g_n_out, 1.00, 1.61, col_fixtures, mat_frame, mat_glass)
    make_box("Wall_Garage_North_04", 12.90, 13.90, y_g_n_in, y_g_n_out, 0.00, H_GAR, mat_wall_ext, col_garage)

    # Garage North Portico Pillars & Beam (Y in [-18.53, -18.23])
    make_box("Pillar_Garage_1", 8.41, 8.91, -18.53, y_porch_n, 0.00, H_GAR, mat_wall_ext, col_garage)
    make_box("Pillar_Garage_2", 11.02, 11.52, -18.53, y_porch_n, 0.00, H_GAR, mat_wall_ext, col_garage)
    make_box("Pillar_Garage_3", 13.40, 13.90, -18.53, y_porch_n, 0.00, H_GAR, mat_wall_ext, col_garage)
    make_box("Beam_Portico_Garage", 6.39, 13.90, -18.53, y_porch_n, 2.50, H_GAR, mat_wall_ext, col_garage)

    # Garage South wall
    make_box("Wall_Garage_South_01", 6.69, 9.41, y_g_s_out, y_g_s_in, 0.00, H_GAR, mat_wall_ext, col_garage)
    make_box("Wall_Garage_South_Sill_1", 9.41, 10.02, y_g_s_out, y_g_s_in, 0.00, 1.00, mat_wall_ext, col_garage)
    make_box("Wall_Garage_South_Lintel_1", 9.41, 10.02, y_g_s_out, y_g_s_in, 1.61, H_GAR, mat_wall_ext, col_garage)
    add_window("Win_Garage_S1", 9.41, 10.02, y_g_s_out, y_g_s_in, 1.00, 1.61, col_fixtures, mat_frame, mat_glass)

    make_box("Wall_Garage_South_02", 10.02, 12.49, y_g_s_out, y_g_s_in, 0.00, H_GAR, mat_wall_ext, col_garage)
    make_box("Wall_Garage_South_Sill_2", 12.49, 13.10, y_g_s_out, y_g_s_in, 0.00, 1.00, mat_wall_ext, col_garage)
    make_box("Wall_Garage_South_Lintel_2", 12.49, 13.10, y_g_s_out, y_g_s_in, 1.61, H_GAR, mat_wall_ext, col_garage)
    add_window("Win_Garage_S2", 12.49, 13.10, y_g_s_out, y_g_s_in, 1.00, 1.61, col_fixtures, mat_frame, mat_glass)
    make_box("Wall_Garage_South_03", 13.10, 13.90, y_g_s_out, y_g_s_in, 0.00, H_GAR, mat_wall_ext, col_garage)

    # Garage Floor Slabs & Basement Stairwell (Y shifted to [-24.23, -19.53])
    make_box("Floor_Garage_Main", 6.69, 13.90, -23.33, y_g_n_in, -0.05, 0.00, mat_concrete, col_garage)
    make_box("Floor_Garage_WestStair", 6.69, 9.40, y_g_s_in, -23.33, -0.05, 0.00, mat_concrete, col_garage)
    make_box("Floor_Garage_EastStair", 12.81, 13.90, y_g_s_in, -23.33, -0.05, 0.00, mat_concrete, col_garage)

    num_gar_steps = 12
    w_step_g = (12.81 - 9.40) / num_gar_steps
    h_step_g = 2.10 / num_gar_steps
    for gs in range(num_gar_steps):
        x_gs0 = 12.81 - (gs + 1) * w_step_g
        x_gs1 = 12.81 - gs * w_step_g
        z_gs = -(gs + 1) * h_step_g
        make_box(f"Garage_Basement_Step_{gs + 1}", x_gs0, x_gs1, y_g_s_in, -23.33, z_gs, z_gs + h_step_g, mat_concrete, col_garage)

    make_box("Railing_Garage_Stair_North", 9.40, 12.81, -23.33, -23.29, 0.00, 0.90, mat_railing, col_garage)
    make_box("Railing_Garage_Stair_West", 9.40, 9.44, y_g_s_in, -23.33, 0.00, 0.90, mat_railing, col_garage)

    # ---------------------------------------------------------
    # 6. SITE GROUND SLABS: TERRAZZA, CURVED WALKWAY, PORTICO, CURVED DRIVEWAY, LAWNS
    # ---------------------------------------------------------
    make_box("Site_Foundation_Earth", -16.00, 14.50, -35.00, 1.50, -0.20, -0.05, mat_concrete, col_site)

    # A. Terrazza_All_Aperto (Stamped concrete outside gates + 200cm inside driveway gate)
    poly_terrazza = [
        (-15.41, -1.50),
        (-15.41, -6.28),
        (-15.03, -6.28),
        (-15.03, -8.28),
        (-11.85, -8.28),
        (-11.85, -6.28),
        (-9.11, -6.28),
        (-9.11, -1.50),
    ]
    make_poly_slab("Terrazza_All_Aperto", poly_terrazza, -0.05, 0.00, mat_portico, col_site)

    # B. Curved Pedestrian Walkway (117cm at gate -> tight r_in=40cm curve -> 150cm at portico midpoint Y=-9.77) + 100cm West-wall path down to Y=-16.43
    n_walk_seg = 24
    cx_w, cy_w = -9.14, -8.62
    r_w_in = 0.40  # 40cm inner curve radius
    walk_outer_arc = []
    walk_inner_arc = []
    for k in range(n_walk_seg + 1):
        t = k / n_walk_seg
        ang = math.pi + t * (math.pi * 0.5)
        r_out_w = 1.57 + 0.33 * (0.5 - 0.5 * math.cos(math.pi * t))
        walk_outer_arc.append((cx_w + r_out_w * math.cos(ang), cy_w + r_out_w * math.sin(ang)))
        walk_inner_arc.append((cx_w + r_w_in * math.cos(ang), cy_w + r_w_in * math.sin(ang)))

    poly_walkway_west = [
        (-1.00, -16.43),
        (0.00, -16.43),
        (0.00, 0.00),
        (-1.00, -0.165),
    ]
    poly_walkway_curve = (
        [(-10.71, -6.28), (-10.71, -8.62)]
        + walk_outer_arc
        + [(-1.00, -10.52), (-1.00, -9.02)]
        + list(reversed(walk_inner_arc))
        + [(-9.54, -8.62), (-9.54, -6.28)]
    )
    make_multi_poly_slab("Walkway_Pedestrian_Pavement", [poly_walkway_west, poly_walkway_curve], -0.05, 0.00, mat_portico, col_site)

    # Stone curbs bordering the pedestrian walkway
    curb_outer_path = [(-10.71, -6.47), (-10.71, -8.62)] + walk_outer_arc + [(-1.00, -10.52), (-1.00, -16.43), (4.65, -16.43)]
    make_offset_curb("Walkway_Curb_Outer", curb_outer_path, 0.06, outward_left=False, z_min=0.00, z_max=0.04, mat=mat_curb, col=col_site)

    curb_inner_path = [(-9.54, -6.47), (-9.54, -8.62)] + walk_inner_arc + [(-1.00, -9.02), (-1.00, -0.28)]
    make_offset_curb("Walkway_Curb_Inner", curb_inner_path, 0.06, outward_left=True, z_min=0.00, z_max=0.04, mat=mat_curb, col=col_site)

    # C. Portico_Pavement_Unified (Courtyard + perimeter sidewalks + 40cm/diagonal transition + garage porch/apron)
    portico_polys = [
        [(0.30, -12.43), (5.89, -12.43), (5.89, -8.05), (6.07, -8.05), (6.07, -7.11), (0.30, -7.11)],
        [(0.00, -11.33), (0.30, -11.33), (0.30, -8.21), (0.00, -8.21)],
        [(2.70, -12.63), (3.62, -12.63), (3.62, -12.43), (2.70, -12.43)],
        [(5.89, -9.05), (13.90, -9.05), (13.90, -8.05), (5.89, -8.05)],
        [(4.65, -16.83), (5.89, -16.83), (5.89, -12.43), (4.65, -12.43)],
        [(0.00, -16.43), (4.65, -16.43), (4.65, -15.43), (0.00, -15.43)],
        [(4.65, -16.83), (5.89, -16.83), (6.39, -18.23), (5.59, -18.23)],
        [(5.59, -25.03), (6.39, -25.03), (6.39, -18.23), (5.59, -18.23)],
        [(6.39, -19.23), (13.90, -19.23), (13.90, -18.23), (6.39, -18.23)],
        [(6.39, -25.03), (13.90, -25.03), (13.90, -24.53), (6.39, -24.53)],
    ]
    make_multi_poly_slab("Portico_Pavement_Unified", portico_polys, -0.05, 0.00, mat_portico, col_site)

    # D. Curved Gravel Driveway (318cm from Y=-8.28 -> smooth 90 deg curve -> 240cm meeting 80cm garage sidewalk at X=5.59)
    n_drv_seg = 24
    cx_d, cy_d = -8.85, -17.63
    r_d_in = 3.00  # 11.85 - 8.85 = 3.00 and 20.63 - 17.63 = 3.00
    drv_outer_arc = []
    drv_inner_arc = []
    for k in range(n_drv_seg + 1):
        t = k / n_drv_seg
        ang = math.pi + t * (math.pi * 0.5)
        r_d_out = 6.18 + (5.40 - 6.18) * (0.5 - 0.5 * math.cos(math.pi * t))
        drv_outer_arc.append((cx_d + r_d_out * math.cos(ang), cy_d + r_d_out * math.sin(ang)))
        drv_inner_arc.append((cx_d + r_d_in * math.cos(ang), cy_d + r_d_in * math.sin(ang)))

    poly_driveway = (
        [(-15.03, -8.28)]
        + drv_outer_arc
        + [(5.59, -23.03), (5.59, -20.63)]
        + list(reversed(drv_inner_arc))
        + [(-11.85, -8.28)]
    )
    make_poly_slab("Driveway_Gravel", poly_driveway, -0.05, 0.00, mat_gravel, col_site)

    # E. Watertight Lawns (Giardino Area 1, 2, 3A, 3B, 3C)
    # Area 1 (South lawn)
    poly_grass_1 = (
        [
            (-15.22, -33.61),
            (13.90, -31.20),
            (13.90, -25.03),
            (5.59, -25.03),
            (5.59, -23.03),
        ]
        + list(reversed(drv_outer_arc))
        + [(-15.22, -17.63)]
    )
    make_poly_slab("Giardino_Area_1_Prato", poly_grass_1, -0.05, 0.00, mat_grass, col_site)

    # Area 2 (East courtyard lawn between kitchen south sidewalk Y=-9.05, diagonal transition and garage north porch Y=-18.23)
    poly_grass_2 = [
        (5.89, -9.05),
        (13.90, -9.05),
        (13.90, -18.23),
        (6.39, -18.23),
        (5.89, -16.83),
    ]
    make_poly_slab("Giardino_Area_2_Prato", poly_grass_2, -0.05, 0.00, mat_grass, col_site)

    # Area 3A (North lawn enclosed by NW fences and tight-curve walkway)
    poly_grass_3a = (
        [
            (-9.11, -1.50),
            (-1.00, -0.165),
            (-1.00, -9.02),
        ]
        + list(reversed(walk_inner_arc))
        + [(-9.54, -8.62), (-9.54, -6.28), (-9.11, -6.28)]
    )
    make_poly_slab("Giardino_Area_3A_Prato", poly_grass_3a, -0.05, 0.00, mat_grass, col_site)

    # Area 3B (West border strip along Fence_West from Y=-6.28 to Y=-17.63)
    make_box("Giardino_Area_3B_Prato", -15.22, -15.03, -17.63, -6.28, -0.05, 0.00, mat_grass, col_site)

    # Area 3C (Central lawn between Driveway, Curved Walkway, Lavanderia south sidewalk, diagonal transition & Garage west sidewalk)
    poly_grass_3c = (
        [(-11.85, -6.28), (-10.71, -6.28), (-10.71, -8.62)]
        + walk_outer_arc
        + [
            (-1.00, -10.52),
            (-1.00, -16.43),
            (4.65, -16.43),
            (4.65, -16.83),
            (5.59, -18.23),
            (5.59, -20.63),
        ]
        + list(reversed(drv_inner_arc))
    )
    make_poly_slab("Giardino_Area_3C_Prato", poly_grass_3c, -0.05, 0.00, mat_grass, col_site)

    # ---------------------------------------------------------
    # 7. REPOSITION BOLLARDS, SPRINKLERS & LABELS INTO NEW LAWNS
    # ---------------------------------------------------------
    bollard_updates = [
        ("Bollard_Garden_1", -8.90, -8.40),
        ("Bollard_Garden_2", -5.90, -8.40),
        ("Bollard_Garden_3", -10.20, -19.20),
        ("Bollard_Garden_4", -4.20, -19.20),
    ]
    for b_name, bx, by in bollard_updates:
        move_group_xy([b_name, f"{b_name}_Base", f"{b_name}_Cap", f"{b_name}_Pillar"], bx, by)

    sprinkler_updates = [
        ("Sprinkler_Area1_1", -13.50, -31.50),
        ("Sprinkler_Area1_2", -1.50, -24.20),
        ("Sprinkler_Area1_3", 4.50, -26.80),
        ("Sprinkler_Area1_4", 12.30, -25.80),
        ("Sprinkler_Area2_1", 6.89, -9.60),
        ("Sprinkler_Area3_1", -7.80, -2.50),
        ("Sprinkler_Area3_2", -1.60, -5.40),
        ("Sprinkler_Area3_4", -1.60, -14.95),
        ("Sprinkler_Area3_5", 3.80, -17.00),
    ]
    for s_name, sx, sy in sprinkler_updates:
        move_group_xy([s_name, f"{s_name}_Base", f"{s_name}_Nozzle"], sx, sy)

    label_updates = {
        "Label_ALL'APERTO": (-14.20, -4.00),
        "Label_GARAGE": (9.20, -21.50),
        "Label_GIARDINO AREA 1": (1.00, -27.50),
        "Label_GIARDINO AREA 3": (-6.00, -13.50),
    }
    for lname, (lx, ly) in label_updates.items():
        lobj = bpy.data.objects.get(lname)
        if lobj:
            lobj.location.x = lx
            lobj.location.y = ly

    bpy.ops.wm.save_mainfile()
    print("=== Saved Smart_Home_3D.blend successfully! ===")


if __name__ == "__main__":
    run_update()
