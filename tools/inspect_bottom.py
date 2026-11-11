from PIL import Image

img = Image.open(r'C:/Users/Nicola Lavarda/.gemini/antigravity/brain/964a90ba-c8c7-46e3-bead-f0525b2be973/.user_uploaded/media_1794303166494_f8f26c9d.jpg')
w, h = img.size

# Bottom room and surrounding
img.crop((50, 650, 500, 1000)).save('crop_bottom_all.png')
# Columns in the middle
img.crop((350, 650, 550, 950)).save('crop_pillars.png')
# Far right wall bottom
img.crop((800, 500, 1000, 1024)).save('crop_right_wall_bottom.png')
# Connection between left room extension (110) and bottom building extension (110)
img.crop((50, 450, 250, 750)).save('crop_left_connection.png')

print("Saved detailed bottom crops.")

