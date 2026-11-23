#!/usr/bin/env python3
"""
ArcSim_VR - Generador de Marcadores ArUco Imprimibles a Escala 1:1
===================================================================
Genera archivos PNG de alta resolución y un PDF en hoja A4 listo para imprimir.
Diccionario: DICT_4X4_50
Dimensiones exactas:
  - Cuadrado negro ArUco: 40.0 mm x 40.0 mm
  - Borde blanco de guarda (quiet zone): 3.0 mm en cada lado
  - Cuadrado total recortable: 46.0 mm x 46.0 mm (encaja en la placa de 48x48 mm)
"""

from pathlib import Path
import cv2
import cv2.aruco as aruco
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches

OUT_DIR = Path(__file__).resolve().parent
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 1. Configuración de diccionario y tamaños
DICT_TYPE = aruco.DICT_4X4_50
dict_aruco = aruco.getPredefinedDictionary(DICT_TYPE)

DPI = 300
MM_PER_INCH = 25.4
PX_PER_MM = DPI / MM_PER_INCH  # ~11.811 px/mm

BLACK_SIZE_MM = 40.0
BORDER_MM = 3.0
TOTAL_SIZE_MM = BLACK_SIZE_MM + 2 * BORDER_MM  # 46.0 mm

black_px = int(round(BLACK_SIZE_MM * PX_PER_MM))   # 472 px
border_px = int(round(BORDER_MM * PX_PER_MM))      # 35 px
total_px = black_px + 2 * border_px                # 542 px

markers_data = [
    (0, "HERRAMIENTA (Soporte Carcasa)", "marker_0_herramienta_40mm.png"),
    (1, "PROBETA / MESA (Referencia)", "marker_1_probeta_40mm.png"),
    (2, "REPUESTO / AUXILIAR", "marker_2_repuesto_40mm.png"),
]

# 2. Generar imágenes PNG de alta resolución individuales
generated_images = {}
for m_id, label, filename in markers_data:
    # Generar marcador binario sin bordes extras
    raw_marker = aruco.generateImageMarker(dict_aruco, m_id, black_px, 1)

    # Crear lienzo blanco con el borde de guarda (quiet zone)
    full_img = np.ones((total_px, total_px), dtype=np.uint8) * 255
    full_img[border_px:border_px + black_px, border_px:border_px + black_px] = raw_marker

    # Agregar una línea gris muy fina en el borde exterior como guía de corte con tijera
    cv2.rectangle(full_img, (0, 0), (total_px - 1, total_px - 1), 180, 1)

    out_png = OUT_DIR / filename
    cv2.imwrite(str(out_png), full_img)
    generated_images[m_id] = full_img
    print(f"  [OK] PNG generado: {out_png.name} ({total_px}x{total_px} px)")

# 3. Generar PDF listo para imprimir en hoja A4 (210 x 297 mm) escala 1:1 exacta
fig_w_in = 210.0 / MM_PER_INCH  # 8.2677 in
fig_h_in = 297.0 / MM_PER_INCH  # 11.6929 in

fig = plt.figure(figsize=(fig_w_in, fig_h_in), dpi=DPI)
# El eje ocupa el 100% de la hoja en coordenadas milimétricas (0 a 210 en X, 0 a 297 en Y)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 210)
ax.set_ylim(0, 297)
ax.axis("off")

# Título y encabezado
ax.text(105, 280, "ArcSim_VR - Marcadores ArUco Imprimibles (Escala 1:1)",
        ha="center", va="top", fontsize=15, fontweight="bold", family="sans-serif")
ax.text(105, 272, "Diccionario: DICT_4X4_50 | Cuadrado negro: 40.0 x 40.0 mm | Recorte: 46.0 x 46.0 mm",
        ha="center", va="top", fontsize=9.5, color="#444444", family="sans-serif")
ax.plot([20, 190], [266, 266], color="#888888", lw=0.8)

# Barra de verificación y calibración con regla física
bar_x = 55
bar_y = 252
bar_len = 100.0  # 100 mm exactos
ax.plot([bar_x, bar_x + bar_len], [bar_y, bar_y], color="#000000", lw=2.5)
ax.plot([bar_x, bar_x], [bar_y - 3, bar_y + 3], color="#000000", lw=1.5)
ax.plot([bar_x + bar_len, bar_x + bar_len], [bar_y - 3, bar_y + 3], color="#000000", lw=1.5)
ax.plot([bar_x + 50, bar_x + 50], [bar_y - 2, bar_y + 2], color="#000000", lw=1.0)
ax.text(bar_x + 50, bar_y + 4, "Regla de Verificación: debe medir exactamente 100 mm (10.0 cm) con una regla",
        ha="center", va="bottom", fontsize=8.5, fontweight="bold", color="#222222")

# Posicionar 2 filas de marcadores (con copias de repuesto)
positions = [
    # Fila 1 (ID 0 - Herramienta)
    (30, 185, 0, "ID 0 - HERRAMIENTA\n(Pegar en Soporte 3D)", "#1a5fb4"),
    (90, 185, 0, "ID 0 - HERRAMIENTA\n(Copia de Repuesto)", "#1a5fb4"),
    (150, 185, 0, "ID 0 - HERRAMIENTA\n(Copia de Repuesto)", "#1a5fb4"),
    # Fila 2 (ID 1 - Probeta y Auxiliar)
    (30, 105, 1, "ID 1 - PROBETA / MESA\n(Referencia de Pieza)", "#26a269"),
    (90, 105, 1, "ID 1 - PROBETA / MESA\n(Copia de Repuesto)", "#26a269"),
    (150, 105, 2, "ID 2 - AUXILIAR\n(Reserva)", "#e5a50a"),
]

for x, y, m_id, label, color in positions:
    # Recuadro con línea de corte punteada
    rect_cut = patches.Rectangle((x, y), TOTAL_SIZE_MM, TOTAL_SIZE_MM,
                                 fill=False, edgecolor="#666666", ls="--", lw=0.7)
    ax.add_patch(rect_cut)

    # Insertar imagen del marcador
    img = generated_images[m_id]
    ax.imshow(img, cmap="gray", extent=[x, x + TOTAL_SIZE_MM, y, y + TOTAL_SIZE_MM],
              interpolation="nearest", zorder=2)

    # Etiqueta
    ax.text(x + TOTAL_SIZE_MM / 2.0, y - 4, label,
            ha="center", va="top", fontsize=8, fontweight="bold", color=color)

# Instrucciones de impresión y pegado
instrucciones_y = 65
ax.plot([20, 190], [instrucciones_y + 8, instrucciones_y + 8], color="#cccccc", lw=0.8)
ax.text(105, instrucciones_y, "INSTRUCCIONES IMPORTANTES PARA LA IMPRESIÓN:",
        ha="center", va="top", fontsize=10, fontweight="bold", color="#111111")

tips = [
    "1. AL IMPRIMIR EL PDF: Seleccionar siempre 'Tamaño real' o 'Escala: 100%' (NUNCA 'Ajustar a la página').",
    "2. VERIFICACIÓN: Mide con una regla la barra negra superior. Debe medir exactamente 100 mm.",
    "3. TIPO DE PAPEL: Usar papel obra/común mate (75 u 80 g) o cartulina mate. NUNCA papel brillante ni plastificado.",
    "4. RECORTE Y PEGADO: Recorta por la línea punteada exterior (46x46 mm) y pégalo bien plano en el soporte plástico.",
    "5. PRECISIÓN EN OPENCV: En el código de Python se configurará 'markerLength = 0.040' (40.0 mm del cuadrado negro)."
]

for i, t in enumerate(tips):
    ax.text(25, instrucciones_y - 8 - i * 6.5, t,
            ha="left", va="top", fontsize=8, color="#333333")

pdf_path = OUT_DIR / "hoja_impresion_A4_aruco.pdf"
fig.savefig(str(pdf_path), format="pdf", dpi=DPI)
plt.close(fig)
print(f"  [OK] PDF A4 generado: {pdf_path}")
