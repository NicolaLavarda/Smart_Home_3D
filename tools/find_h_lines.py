import cv2
import numpy as np

img = cv2.imread('crop_upper_building.png')
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
edges = cv2.Canny(gray, 50, 150)
lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=80, minLineLength=50, maxLineGap=5)

h_lines = []
if lines is not None:
    for l in lines:
        x1, y1, x2, y2 = l.flatten()
        if abs(y2 - y1) <= 1:
            h_lines.append((y1, min(x1, x2), max(x1, x2)))

h_lines.sort(key=lambda x: x[0])
clusters = []
for y, x1, x2 in h_lines:
    if not clusters or abs(y - clusters[-1]['y']) > 3:
        clusters.append({'y': y, 'lines': [(x1, x2)]})
    else:
        clusters[-1]['lines'].append((x1, x2))

for c in clusters:
    min_x = min(l[0] for l in c['lines'])
    max_x = max(l[1] for l in c['lines'])
    print(f"Y={c['y']:3d}, span=({min_x:3d}, {max_x:3d})")
