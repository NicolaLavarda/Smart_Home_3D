import bpy

obj = bpy.data.objects.get('Driveway_Gravel')
if obj:
    verts = [obj.matrix_world @ v.co for v in obj.data.vertices]
    # sort by Y descending
    sorted_verts = sorted(verts, key=lambda v: -v.y)
    print(f'Driveway vertex count: {len(verts)}')
    for v in sorted_verts[::max(1, len(verts)//20)]:
        print(f'  X={v.x:6.2f}, Y={v.y:6.2f}, Z={v.z:6.2f}')

