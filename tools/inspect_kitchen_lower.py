import bpy
from mathutils import Vector

print("=== DETAILED KITCHEN BASE CABINETS INSPECTION ===")

def get_world_bbox(obj):
    if not obj.data or not hasattr(obj.data, "vertices") or len(obj.data.vertices) == 0:
        return None
    mat = obj.matrix_world
    world_verts = [mat @ v.co for v in obj.data.vertices]
    xs = [v.x for v in world_verts]
    ys = [v.y for v in world_verts]
    zs = [v.z for v in world_verts]
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))

for obj in bpy.data.objects:
    name = obj.name
    if any(k in name.lower() for k in ["cucina", "dish", "lavastov", "casset", "lavello"]):
        bbox = get_world_bbox(obj)
        if bbox:
            min_x, max_x, min_y, max_y, min_z, max_z = bbox
            # Focus on lower cabinets (z between 0 and 1.2, y < -5.0)
            if min_z < 1.0 and max_z > 0.1 and min_y < -5.0:
                dx = max_x - min_x
                dy = max_y - min_y
                dz = max_z - min_z
                print(f"{name:35} | X: [{min_x:6.3f}..{max_x:6.3f}] (w={dx:.3f}) | Y: [{min_y:6.3f}..{max_y:6.3f}] (d={dy:.3f}) | Z: [{min_z:6.3f}..{max_z:6.3f}] (h={dz:.3f})")

