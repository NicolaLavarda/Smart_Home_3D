import cv2
import numpy as np

img = cv2.imread(r'C:/Users/Nicola Lavarda/.gemini/antigravity/brain/964a90ba-c8c7-46e3-bead-f0525b2be973/.user_uploaded/media_1794303166494_f8f26c9d.jpg')

# Let's inspect the entire left dimension line from top to bottom
# In the original image:
# Left column of image has the dimension line
# Let's look at y of the tick marks on the far left
cv2.imwrite('crop_far_left.png', img[:, :130])

# Also let's check the right side:
cv2.imwrite('crop_far_right.png', img[:, 850:])
print("Saved far left and right")
