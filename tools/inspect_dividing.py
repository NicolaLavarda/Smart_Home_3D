import cv2
import numpy as np

img = cv2.imread('crop_upper_building.png')

# In crop_upper_building.png, the dividing wall is around x=400..430
# Let's crop around that wall:
cv2.imwrite('crop_dividing_wall.png', img[100:500, 380:450])
print("Saved dividing wall crop.")

