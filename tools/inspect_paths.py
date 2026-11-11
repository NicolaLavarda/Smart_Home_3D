import bpy

print('--- WALKWAYS AND ROADS ---')
for obj in bpy.data.objects:
    name = obj.name.lower()
    if any(k in name for k in ['walk', 'pave', 'road', 'strada', 'vialett', 'carrab', 'driveway', 'asfalt']):
        if hasattr(obj.data, 'vertices') and len(obj.data.vertices) > 0:
            bb = [obj.matrix_world @ v.co for v in obj.data.vertices]
            xs = [v.x for v in bb]
            ys = [v.y for v in bb]
            zs = [v.z for v in bb]
            print(f'{obj.name:35} | X=[{min(xs):5.2f}, {max(xs):5.2f}], Y=[{min(ys):5.2f}, {max(ys):5.2f}], Z=[{min(zs):5.2f}, {max(zs):5.2f}]')

