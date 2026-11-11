from PIL import Image

img = Image.open('crop_zoom_stairs.png')
w, h = img.size

# Crop specifically x=0.2 to 0.6, y=0.05 to 0.55
img.crop((int(w*0.15), int(h*0.05), int(w*0.65), int(h*0.55))).save('crop_stair_arrow_correct.png')
print("Saved stair arrow correct.")

