import bpy
import re

print("\n=================== AUDIT REPORT: SCENE OBJECTS ===================")
print(f"Total objects in bpy.data.objects: {len(bpy.data.objects)}")
print(f"Total meshes: {len(bpy.data.meshes)}")
print(f"Total materials: {len(bpy.data.materials)}")

print("\n--- COLLECTIONS OVERVIEW ---")
for col in bpy.data.collections:
    print(f"  Collection [{col.name}]: {len(col.objects)} objects")

def find_objs(pattern):
    return [o.name for o in bpy.data.objects if re.search(pattern, o.name, re.IGNORECASE)]

categories = {
    "Cucina - Isola / Bancone": r"Isola|Bancone|Sgabell",
    "Cucina - Elettrodomestici": r"Frigo|Forno|Microonde|Piano_Cottura|Cappa|Lavello|Lavastoviglie",
    "Cucina - Mobili / Basi / Pensili": r"Cucina_Basi|Cucina_Pensile|Cucina_Top|Cucina_Paraschizzi|Kallax|Carrello",
    "Sala Pranzo - Tavolo e Sedie": r"Tavolo_Pranzo|Sedia_Pranzo|Capotavola|Vetrina",
    "Salotto - Divano e Relax": r"Divano|Cuscino|Plaid|Pouf",
    "Salotto - Tavoli e Sedie": r"Tavolo_Salotto|Sedia_Salotto|Tavolino|Tavolo_Laptop|Tavolo_Pacco",
    "Salotto - TV e Mobili": r"Mobile_TV|TV_Salotto|Madia|Libreria|Mensola_Salotto",
    "Camino e Panca": r"Fireplace|Camino|Bench_North|Pianerottolo",
    "Lavanderia": r"Lavatric|Asciugat|Caldaia|Puffer|Thermal_|Sensor_Puffer|Sensor_Caldaia|Lavanderia",
    "Bagno / Antibagno": r"Doccia|Lavabo|WC|Vaso|Bidet|Sanitar|Bagno|Antibagno",
    "Scale": r"Stair_|Scala",
    "Dispositivi HA": r"Bollard|Wall_Garden|Spot_|Applique_|Switch_|Portico_|Cam_",
    "Infissi / Porte / Finestre": r"Door_|Porta_|Win_|Finestra_"
}

for cat, pat in categories.items():
    objs = find_objs(pat)
    print(f"\n[{cat}] -> {len(objs)} objects found:")
    if len(objs) == 0:
        print("  *** ATTENTION: 0 objects found! ***")
    elif len(objs) <= 12:
        for name in sorted(objs):
            print(f"  - {name}")
    else:
        for name in sorted(objs)[:8]:
            print(f"  - {name}")
        print(f"  ... and {len(objs) - 8} more ({len(objs)} total)")

print("\n=================== END AUDIT REPORT ===================")

