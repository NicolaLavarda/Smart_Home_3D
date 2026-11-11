import bpy

print('--- SEARCHING RELEVANT OBJECTS ---')
for obj in bpy.data.objects:
    name = obj.name
    lower = name.lower()
    if any(k in lower for k in ['ped', 'gate', 'doccia', 'shower', 'vialett', 'strada', 'portico', 'camminament', 'muro_cinta', 'porta_finestra', 'vetrata', 'lavanderia', 'salotto']):
        bb = [obj.matrix_world @ v.co for v in obj.data.vertices] if hasattr(obj.data, 'vertices') and len(obj.data.vertices) > 0 else []
        if bb:
            xs = [v.x for v in bb]
            ys = [v.y for v in bb]
            zs = [v.z for v in bb]
            print(f'{name:35} | X=[{min(xs):6.2f}, {max(xs):6.2f}], Y=[{min(ys):6.2f}, {max(ys):6.2f}], Z=[{min(zs):6.2f}, {max(zs):6.2f}]')
        else:
            print(f'{name:35} | loc=[{obj.location.x:6.2f}, {obj.location.y:6.2f}, {obj.location.z:6.2f}]')

