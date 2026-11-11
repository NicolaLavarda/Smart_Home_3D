from PIL import Image

img = Image.open(r'C:/Users/Nicola Lavarda/.gemini/antigravity/brain/964a90ba-c8c7-46e3-bead-f0525b2be973/.user_uploaded/media_1794305755981_d69e0fc4.jpg')
w, h = img.size

# Let's crop the center area (bagno, scala, sgabuzzino)
img.crop((int(w*0.25), int(h*0.05), int(w*0.8), int(h*0.55))).save('crop_zoom_stairs.png')
print("Saved zoom stairs crop.")

