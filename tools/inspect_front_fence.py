import bpy

print('=== ALL OBJECTS NEAR Y=0 (Front fence and gates) ===')
for obj in bpy.data.objects:
    if hasattr(obj.data, 'vertices') and len(obj.data.vertices) > 0:
        bb = [obj.matrix_world @ v.co for v in obj.data.vertices]
        xs = [v.x for v in bb]
        ys = [v.y for v in bb]
        zs = [v.z for v in bb]
        cy = (min(ys) + max(ys)) / 2
        if -1.5 <= cy <= 1.5:
            print(f'{obj.name:32} | X=[{min(xs):6.2f}, {max(xs):6.2f}], Y=[{min(ys):6.2f}, {max(ys):6.2f}], Z=[{min(zs):6.2f}, {max(zs):6.2f}] | parent={obj.parent.name if obj.parent else None}')

