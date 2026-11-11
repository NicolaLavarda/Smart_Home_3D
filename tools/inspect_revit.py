from PIL import Image

img = Image.open(r'C:/Users/Nicola Lavarda/.gemini/antigravity/brain/964a90ba-c8c7-46e3-bead-f0525b2be973/.user_uploaded/media_1794305062538_ddc159d9.jpg')
w, h = img.size

# 1. Top down view on the right
img.crop((int(w*0.55), 0, w, int(h*0.75))).save('crop_revit_topdown.png')
# 2. Bottom-left axonometric
img.crop((0, int(h*0.4), int(w*0.58), h)).save('crop_revit_axono1.png')
# 3. Top-left axonometric
img.crop((0, 0, int(w*0.45), int(h*0.45))).save('crop_revit_axono2.png')

print("Saved Revit crops.")

