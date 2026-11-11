import cv2
import numpy as np
from PIL import Image

# Let's inspect the vertical dimensions of the middle room, stairs, and right room.
img = Image.open(r'C:/Users/Nicola Lavarda/.gemini/antigravity/brain/964a90ba-c8c7-46e3-bead-f0525b2be973/.user_uploaded/media_1794303166494_f8f26c9d.jpg')
w, h = img.size

# Let's crop:
# Middle room & stairs vertical dimensions:
# The dimensions inside and to the right of the middle room
img.crop((400, 150, 650, 450)).save('crop_middle_room_full.png')
# The bottom wall of the right living room
img.crop((400, 400, 950, 600)).save('crop_right_room_bottom.png')
# The vertical dimension line on the far right
img.crop((800, 50, 980, 550)).save('crop_right_dim_line.png')
# The whole upper building
img.crop((50, 0, 950, 550)).save('crop_upper_building.png')

print("Saved upper building crops.")

