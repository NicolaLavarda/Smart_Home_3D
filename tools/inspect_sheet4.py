from PIL import Image

img = Image.open(r'C:/Users/Nicola Lavarda/.gemini/antigravity/brain/964a90ba-c8c7-46e3-bead-f0525b2be973/.user_uploaded/media_1794305077415_3e86f3b6.jpg')
w, h = img.size

# Let's crop the key dimension lines on sheet 4:
# 1. Left side dimensions (showing distance from Lavanderia to Garage)
img.crop((0, 0, int(w*0.35), h)).save('crop_s4_left.png')
# 2. Right side dimensions (showing Garage and wall to the right)
img.crop((int(w*0.65), 0, w, h)).save('crop_s4_right.png')
# 3. Between Lavanderia and Garage
img.crop((int(w*0.3), int(h*0.3), int(w*0.7), int(h*0.65))).save('crop_s4_mid.png')

print("Saved Sheet 4 crops.")

