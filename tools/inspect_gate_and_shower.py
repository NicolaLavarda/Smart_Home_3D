import bpy

print('=== INSPECT GATES ===')
for obj in bpy.data.objects:
    if 'gate' in obj.name.lower() or 'cancello' in obj.name.lower():
        bb = [obj.matrix_world @ v.co for v in obj.data.vertices] if hasattr(obj.data, 'vertices') and len(obj.data.vertices) > 0 else []
        if bb:
            xs = [v.x for v in bb]
            ys = [v.y for v in bb]
            zs = [v.z for v in bb]
            print(f'{obj.name:32} | X=[{min(xs):6.2f}, {max(xs):6.2f}], Y=[{min(ys):6.2f}, {max(ys):6.2f}], Z=[{min(zs):6.2f}, {max(zs):6.2f}] | ha_entity={obj.get("ha_entity")}')
        else:
            print(f'{obj.name:32} | loc={obj.location} | ha_entity={obj.get("ha_entity")}')

print('\n=== INSPECT SHOWER WALLS ===')
for obj in bpy.data.objects:
    if 'part' in obj.name.lower() or 'doccia' in obj.name.lower() or 'lav' in obj.name.lower():
        if hasattr(obj.data, 'vertices') and len(obj.data.vertices) > 0:
            bb = [obj.matrix_world @ v.co for v in obj.data.vertices]
            xs = [v.x for v in bb]
            ys = [v.y for v in bb]
            zs = [v.z for v in bb]
            if -16.0 <= min(ys) <= -12.0 and 0.0 <= min(xs) <= 5.0:
                print(f'{obj.name:32} | X=[{min(xs):6.2f}, {max(xs):6.2f}], Y=[{min(ys):6.2f}, {max(ys):6.2f}], Z=[{min(zs):6.2f}, {max(zs):6.2f}]')

