from PIL import Image

img = Image.open('crop_zoom_stairs.png')
w, h = img.size

# Crop specifically the stair arrow and winders
img.crop((int(w*0.3), int(h*0.1), int(w*0.75), int(h*0.55))).save('crop_stair_arrow.png')
print("Saved stair arrow crop.")

