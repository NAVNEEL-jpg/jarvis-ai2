from PIL import Image
import os

png_path = r'd:\jarvis ai2\jarvis_icon.png'
ico_path = r'd:\jarvis ai2\jarvis_icon.ico'

img = Image.open(png_path).convert('RGBA')

# Generate multiple sizes for a proper multi-res .ico
sizes = [16, 24, 32, 48, 64, 128, 256]
img.save(ico_path, format='ICO', sizes=[(s, s) for s in sizes])

print(f"ICO saved to: {ico_path}")
