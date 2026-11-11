import bpy

print("\n=================== DETAILED AUDIT ===================")
target_cols = ["02_Edificio_Residenziale", "03_Lavanderia", "04_Garage", "05_Scale_e_Sottoscala", "08_Luci_e_Camere"]

for col_name in target_cols:
    col = bpy.data.collections.get(col_name)
    if col:
        print(f"\n--- COLLECTION: {col_name} ({len(col.objects)} objects) ---")
        for o in sorted([x.name for x in col.objects]):
            print(f"  {o}")

print("\n--- ALL OBJECTS IN 09_Arredi_Principali ---")
col_9 = bpy.data.collections.get("09_Arredi_Principali")
if col_9:
    print(f"Total in 09_Arredi_Principali: {len(col_9.objects)}")
    # Group by prefix
    prefixes = {}
    for o in col_9.objects:
        p = o.name.split("_")[0]
        prefixes[p] = prefixes.get(p, 0) + 1
    for p, c in sorted(prefixes.items()):
        print(f"  Prefix '{p}': {c} objects")

print("\n=================== END DETAILED AUDIT ===================")

