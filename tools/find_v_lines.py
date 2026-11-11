import cv2
import numpy as np

img = cv2.imread(r'C:/Users/Nicola Lavarda/.gemini/antigravity/brain/964a90ba-c8c7-46e3-bead-f0525b2be973/.user_uploaded/media_1794303166494_f8f26c9d.jpg')
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

# Let's find:
# 1. Main house left wall outer X
# 2. Main house top wall outer Y
# 3. Main house left wall 110 extension bottom Y
# 4. Lower annex left wall outer X
# 5. Lower annex top 110 extension top Y
# 6. Lower annex bottom wall outer Y
# 7. Lower annex right wall outer X

# Let's find vertical lines
edges = cv2.Canny(gray, 50, 150)
lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=100, minLineLength=100, maxLineGap=10)

v_lines = []
if lines is not None:
    for l in lines:
        x1, y1, x2, y2 = l.flatten()
        if abs(x2 - x1) <= 1:
            v_lines.append((x1, min(y1, y2), max(y1, y2)))

v_lines.sort(key=lambda x: x[0])
# Cluster vertical lines by X
v_clusters = []
for x, y1, y2 in v_lines:
    if not v_clusters or abs(x - v_clusters[-1]['x']) > 4:
        v_clusters.append({'x': x, 'lines': [(y1, y2)]})
    else:
        v_clusters[-1]['lines'].append((y1, y2))

for c in v_clusters:
    min_y = min(l[0] for l in c['lines'])
    max_y = max(l[1] for l in c['lines'])
    print(f"X={c['x']:3d}, Y span=({min_y:3d}, {max_y:3d})")

