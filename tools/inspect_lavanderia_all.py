import bpy

print('--- ALL OBJECTS BY VERTICES IN LAVANDERIA ---')
for obj in bpy.data.objects:
    if not hasattr(obj.data, 'vertices') or len(obj.data.vertices) == 0:
        continue
    bb = [obj.matrix_world @ v.co for v in obj.data.vertices]
    xs = [v.x for v in bb]
    ys = [v.y for v in bb]
    zs = [v.z for v in bb]
    cx = (min(xs) + max(xs)) / 2
    cy = (min(ys) + max(ys)) / 2
    if 0.0 <= cx <= 5.0 and -16.0 <= cy <= -12.0:
        print(f'{obj.name:35} | X=[{min(xs):5.2f}, {max(xs):5.2f}], Y=[{min(ys):5.2f}, {max(ys):5.2f}], Z=[{min(zs):5.2f}, {max(zs):5.2f}]')
