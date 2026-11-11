import bpy
from mathutils import Vector

def update_wall_box(name, xmin, xmax, ymin, ymax, zmin, zmax):
    obj = bpy.data.objects.get(name)
    if not obj:
        print(f"Object {name} not found!")
        return
    # Clear animation/constraints
    obj.parent = None
    obj.location = Vector((0, 0, 0))
    obj.rotation_euler = (0, 0, 0)
    obj.scale = Vector((1, 1, 1))

    # Update vertices directly
    mesh = obj.data
    coords = [
        (xmin, ymin, zmin), (xmax, ymin, zmin), (xmax, ymax, zmin), (xmin, ymax, zmin),
        (xmin, ymin, zmax), (xmax, ymin, zmax), (xmax, ymax, zmax), (xmin, ymax, zmax)
    ]
    if len(mesh.vertices) == 8:
        for i, co in enumerate(coords):
            mesh.vertices[i].co = Vector(co)
        mesh.update()
        print(f"Updated {name} vertices directly.")
    else:
        print(f"{name} has {len(mesh.vertices)} vertices, not 8.")

update_wall_box('Wall_Lav_Part_V1', 1.65, 1.73, -15.23, -14.33, 0.0, 2.70)
update_wall_box('Wall_Lav_Part_H1', 1.65, 2.55, -14.41, -14.33, 0.0, 2.70)
update_wall_box('Wall_Lav_Part_V2', 2.55, 2.63, -15.23, -14.33, 0.0, 2.70)

