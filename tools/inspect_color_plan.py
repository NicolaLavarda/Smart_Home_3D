from PIL import Image

img = Image.open(r'C:/Users/Nicola Lavarda/.gemini/antigravity/brain/964a90ba-c8c7-46e3-bead-f0525b2be973/.user_uploaded/media_1794305205339_9703d1df.jpg')
w, h = img.size

# Let's crop:
# Top house: Salotto, Bagno, Sala da pranzo
img.crop((int(w*0.4), 0, w, int(h*0.35))).save('crop_color_house.png')
# Center: Lavanderia, Portico, Giardino 2
img.crop((int(w*0.35), int(h*0.2), w, int(h*0.65))).save('crop_color_mid.png')
# Bottom: Garage, Giardino 1, Driveway
img.crop((0, int(h*0.55), w, h)).save('crop_color_bottom.png')
# Left: Giardino 3, All'aperto
img.crop((0, 0, int(w*0.5), int(h*0.65))).save('crop_color_left.png')

print("Saved color plan crops.")

