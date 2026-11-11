from PIL import Image

img1 = Image.open(r'C:/Users/Nicola Lavarda/.gemini/antigravity/brain/964a90ba-c8c7-46e3-bead-f0525b2be973/.user_uploaded/media_1794305062538_ddc159d9.jpg')
img2 = Image.open(r'C:/Users/Nicola Lavarda/.gemini/antigravity/brain/964a90ba-c8c7-46e3-bead-f0525b2be973/.user_uploaded/media_1794305077415_3e86f3b6.jpg')
img3 = Image.open(r'C:/Users/Nicola Lavarda/.gemini/antigravity/brain/964a90ba-c8c7-46e3-bead-f0525b2be973/.user_uploaded/media_1794305205339_9703d1df.jpg')

print("Img 1 size:", img1.size)
print("Img 2 size:", img2.size)
print("Img 3 size:", img3.size)

# From img2 (garage plan):
w2, h2 = img2.size
# Crop the garage area
img2.crop((int(w2*0.3), int(h2*0.45), int(w2*0.75), int(h2*0.95))).save('crop_garage_plan.png')
# Crop the title block / overview in top right of img2
img2.crop((int(w2*0.75), 0, w2, int(h2*0.35))).save('crop_overview_plan.png')
# Crop middle portico columns in img2
img2.crop((int(w2*0.3), int(h2*0.05), int(w2*0.6), int(h2*0.5))).save('crop_portico_plan.png')

print("Saved garage crops")

