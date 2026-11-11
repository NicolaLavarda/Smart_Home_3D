import bpy

def get_world_bbox(obj):
    if not obj.data or not hasattr(obj.data, "vertices") or len(obj.data.vertices) == 0:
        return None
    mat = obj.matrix_world
    world_verts = [mat @ v.co for v in obj.data.vertices]
    xs = [v.x for v in world_verts]
    ys = [v.y for v in world_verts]
    zs = [v.z for v in world_verts]
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))

names = [
    "Cucina_Anta_Sud_1_Telaio",
    "Cucina_Basi_Scocca_Sud_Cassetti",
    "Cucina_Cassetto_Frontale_0",
    "Cucina_Cassetto_Bugna_0",
    "Cucina_Cassetto_Maniglia_0",
    "Cucina_Basi_Scocca_Sud_Lavastoviglie",
    "Lavastoviglie",
    "Lavastoviglie_Bugna",
    "Lavastoviglie_Pannello_Comandi",
    "Lavastoviglie_Display",
    "Lavastoviglie_Maniglia",
    "Cucina_Anta_Lavello_L_Telaio",
    "Cucina_Top_Sud_Centrale"
]

print("=== VERIFY UPDATED KITCHEN OBJECTS ===")
for n in names:
    obj = bpy.data.objects.get(n)
    if obj:
        bbox = get_world_bbox(obj)
        dx = bbox[1] - bbox[0]
        dy = bbox[3] - bbox[2]
        dz = bbox[5] - bbox[4]
        ha = {k: obj[k] for k in obj.keys() if k.startswith("ha_")}
        print(f"{n:35} | X: [{bbox[0]:.3f}..{bbox[1]:.3f}] (w={dx:.3f}) | Z: [{bbox[4]:.3f}..{bbox[5]:.3f}] | HA: {ha}")
    else:
        print(f"{n:35} | NOT FOUND")

