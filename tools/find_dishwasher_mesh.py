import bpy

print("=== CHECK ALL DISHWASHER OBJECTS ===")
for obj in bpy.data.objects:
    if "dish" in obj.name.lower() or "lavastov" in obj.name.lower():
        print(f"Object: {obj.name}, Type: {obj.type}, Loc: {obj.location}, Dim: {obj.dimensions}, Parent: {obj.parent}")
        if obj.data and hasattr(obj.data, "materials"):
            print("  Materials:", [m.name for m in obj.data.materials if m])

