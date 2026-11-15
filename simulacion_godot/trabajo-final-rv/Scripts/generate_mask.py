# -*- coding: utf-8 -*-
"""Genera una máscara de soldadura con un hueco transparente en el centro.
Guarda la imagen como "mask_overlay.png" dentro de la carpeta "textures" del proyecto.

Ajusta los valores de WIDTH, HEIGHT, HOLE_W, HOLE_H y los colores si lo deseas.
"""

import os
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    raise ImportError("Pillow no está instalado. Ejecuta 'pip install pillow' antes de usar este script.")

# Parámetros de la imagen (puedes cambiar la resolución si lo necesitas)
WIDTH, HEIGHT = 1920, 1080               # resolución de pantalla objetivo
HOLE_W, HOLE_H = 600, 400                # tamaño del hueco (visor) en píxeles
BG_COLOR = (0, 0, 0, 255)                # negro semi‑opaco (A = 180/255 ≈ 0.71)
TRANSPARENT = (0, 0, 0, 0)               # zona del hueco

# Cálculo del rectángulo del hueco centrado
left = (WIDTH - HOLE_W) // 2
top = (HEIGHT - HOLE_H) // 2
right = left + HOLE_W
bottom = top + HOLE_H

# Crear la imagen RGBA
img = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR)
# Pintar el hueco transparente
for y in range(top, bottom):
    for x in range(left, right):
        img.putpixel((x, y), TRANSPARENT)

# Ruta de salida (crea la carpeta si no existe)
out_dir = Path(__file__).parent.parent / "textures"
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "mask_overlay.png"
img.save(out_path)
print(f"Máscara generada en {out_path}")
