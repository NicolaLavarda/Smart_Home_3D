import bpy

print("=== KITCHEN OBJECTS INSPECTION ===")
for obj in bpy.data.objects:
    loc = obj.location
    dim = obj.dimensions
    name = obj.name
    # Filter for kitchen objects: Y between -8.5 and -5.0, X between 6.0 and 10.0, or name contains 'Cucina' or 'Dish' or 'Lav'
    if ("cucina" in name.lower() or "dish" in name.lower() or "lav" in name.lower() or "casset" in name.lower() or "fuoch" in name.lower() or "piano" in name.lower() or (7.0 <= loc.x <= 10.0 and -8.5 <= loc.y <= -5.5)):
        print(f"Name: {name:30} | Loc: ({loc.x:.3f}, {loc.y:.3f}, {loc.z:.3f}) | Dim: ({dim.x:.3f}, {dim.y:.3f}, {dim.z:.3f}) | Parent: {obj.parent.name if obj.parent else 'None'}")

