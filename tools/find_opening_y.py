import cv2
import numpy as np

img = cv2.imread('crop_upper_building.png')
# let's find the y coordinates of:
# 1. bottom of middle room wall:
# 2. top of opening in dividing wall:
# 3. bottom of opening in dividing wall:
# 4. bottom wall of left room:

# Column x=400 in crop_upper_building
col = img[:, 395:405]
# Let's inspect along Y
# In crop_dividing_wall:
# We cropped img[100:500, 380:450]
# In this sub-image, let's find transitions along x=395
sub = img[100:500, 395, 0] # grayscale
for y_rel in range(len(sub)-1):
    diff = int(sub[y_rel+1]) - int(sub[y_rel])
    if abs(diff) > 50:
        print(f"Y_abs = {100 + y_rel}: val {sub[y_rel]} -> {sub[y_rel+1]}")

