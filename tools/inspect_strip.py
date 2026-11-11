from PIL import Image

img = Image.open(r'C:/Users/Nicola Lavarda/.gemini/antigravity/brain/964a90ba-c8c7-46e3-bead-f0525b2be973/.user_uploaded/media_1794303166494_f8f26c9d.jpg')
w, h = img.size

# Bottom strip
img.crop((0, int(h*0.8), w, h)).save('crop_bottom_strip.png')
print("Saved bottom strip")

