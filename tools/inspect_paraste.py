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
    "Cucina_Anta_Sud_1_Bugna",
    "Cucina_Anta_Sud_1_Maniglia",
    "Cucina_Basi_Parasta_Sud_1",
    "Cucina_Basi_Scocca_Sud_Cassetti",
    "Cucina_Basi_Parasta_Sud_2",
    "Cucina_Anta_Lavello_L_Telaio",
    "Cucina_Cassetto_Frontale_0",
    "Cucina_Cassetto_Bugna_0",
    "Cucina_Cassetto_Maniglia_0",
    "Sensor_Dishwasher",
    "Cucina_Top_Sud_Centrale"
]

print("=== SELECTED KITCHEN OBJECTS ===")
for n in names:
    obj = bpy.data.objects.get(n)
    if obj:
        bbox = get_world_bbox(obj)
        mats = [m.name for m in obj.data.materials if m] if obj.data else []
        print(f"{n:32} | bbox: {bbox} | mats: {mats}")
    else:
        print(f"{n:32} | NOT FOUND")

