import cv2
import numpy as np
from PIL import Image

img = Image.open('crop_zoom_stairs.png')
w, h = img.size

# Let's crop:
# 1. Antibagno and two doors and closet
img.crop((int(w*0.1), int(h*0.3), int(w*0.6), int(h*0.95))).save('crop_antibagno_detail.png')
# 2. 3 steps, landing and sliding door
img.crop((int(w*0.4), int(h*0.1), int(w*0.8), int(h*0.7))).save('crop_stair_sliding_detail.png')

print("Saved stair details crops.")

