import cv2
import numpy as np
from PIL import Image

img = Image.open(r'C:/Users/Nicola Lavarda/.gemini/antigravity/brain/964a90ba-c8c7-46e3-bead-f0525b2be973/.user_uploaded/media_1794303166494_f8f26c9d.jpg')
w, h = img.size

# Let's crop into several specific sub-regions:
# 1. Top dimension line with all its numbers
img.crop((70, 0, 950, 120)).save('crop_top_dims.png')
# 2. Left dimension line
img.crop((0, 0, 150, 600)).save('crop_left_dims.png')
# 3. Middle horizontal dimension line (under the left room and right room)
img.crop((50, 420, 950, 560)).save('crop_mid_h_dims.png')
# 4. Small room at the bottom-left
img.crop((50, 650, 480, 960)).save('crop_bottom_room.png')
# 5. Right side vertical dimensions
img.crop((850, 0, 1000, 960)).save('crop_right_dims.png')
# 6. Stairs and central bathroom area
img.crop((400, 60, 750, 320)).save('crop_center_stairs.png')
# 7. Left room center with door
img.crop((100, 350, 460, 480)).save('crop_left_room_door.png')

print("Done cropping.")

