import bpy

print('--- OBJECTS ON EAST SIDE OF SALOTTO (X around 5.5 to 6.5, Y between -7 and 0) ---')
for obj in bpy.data.objects:
    if hasattr(obj.data, 'vertices') and len(obj.data.vertices) > 0:
        bb = [obj.matrix_world @ v.co for v in obj.data.vertices]
        xs = [v.x for v in bb]
        ys = [v.y for v in bb]
        zs = [v.z for v in bb]
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2
        if 5.0 <= cx <= 7.0 and -7.0 <= cy <= 0.0:
            print(f'{obj.name:35} | X=[{min(xs):5.2f}, {max(xs):5.2f}], Y=[{min(ys):5.2f}, {max(ys):5.2f}], Z=[{min(zs):5.2f}, {max(zs):5.2f}]')

