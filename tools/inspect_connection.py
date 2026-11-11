from PIL import Image

img = Image.open(r'C:/Users/Nicola Lavarda/.gemini/antigravity/brain/964a90ba-c8c7-46e3-bead-f0525b2be973/.user_uploaded/media_1794303166494_f8f26c9d.jpg')
w, h = img.size

# Let's crop the connection between top and bottom
img.crop((0, int(h*0.4), int(w*0.55), int(h*0.8))).save('crop_connection.png')
# Let's crop the bottom right area as well
img.crop((int(w*0.4), int(h*0.5), w, h)).save('crop_bottom_right.png')
print("Done")

