import bpy

for name in ['Wall_Lav_Part_H1', 'Wall_Lav_Part_V1', 'Wall_Lav_Part_V2', 'Floor_Lavanderia']:
    obj = bpy.data.objects.get(name)
    if obj:
        bb = [obj.matrix_world @ v.co for v in obj.data.vertices]
        xs = [v.x for v in bb]
        ys = [v.y for v in bb]
        zs = [v.z for v in bb]
        print(f'{name}: X=[{min(xs):.2f}, {max(xs):.2f}], Y=[{min(ys):.2f}, {max(ys):.2f}], Z=[{min(zs):.2f}, {max(zs):.2f}]')

