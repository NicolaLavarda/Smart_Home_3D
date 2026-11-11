try:
    import pytesseract
    from PIL import Image
    for name in ['crop_top_dims.png', 'crop_left_dims.png', 'crop_mid_h_dims.png', 'crop_bottom_room.png', 'crop_right_dims.png', 'crop_center_stairs.png']:
        txt = pytesseract.image_to_string(Image.open(name))
        print(f"=== {name} ===")
        print(txt.strip())
except Exception as e:
    print("pytesseract error:", e)

