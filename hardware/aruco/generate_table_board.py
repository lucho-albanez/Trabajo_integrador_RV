#!/usr/bin/env python3
"""
ArcSim_VR - Generador de Plantilla A4 para Mesa de Soldadura (ArUco Workboard)
==============================================================================
Genera un PDF oficial A4 apaisado (297 x 210 mm) a escala 1:1 exacta para
pegar sobre una base rígida de cartón o madera.

Contiene:
  - 4 Marcadores perimetrales (DICT_4X4_50 de 36 mm):
      * ID 1: Superior Izquierdo (-40, +65 mm)
      * ID 2: Superior Derecho   (+190, +65 mm)
      * ID 3: Inferior Izquierdo (-40, -65 mm)
      * ID 4: Inferior Derecho   (+190, -65 mm)
  - Probeta central de soldadura a escala 1:1:
      * Longitud exacta: 150.0 mm (coincide con SEAM_LENGTH_MM en Godot)
      * Regla graduada milimétrica cada 10 mm (0 a 150 mm)
      * Línea de bisel central y flecha de sentido de avance
      * Origen físico (0, 0) ubicado en el INICIO del cordón
  - Barra de verificación de 100.0 mm para corroborar escala física con regla
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

PDF_PATH = OUT_DIR / "plantilla_mesa_soldadura_A4.pdf"
PNG_PATH = OUT_DIR / "plantilla_mesa_soldadura_A4.png"

# Parámetros físicos en milímetros
PAGE_W_MM = 297.0
PAGE_H_MM = 210.0

SEAM_LEN_MM = 150.0
SEAM_W_MM = 24.0

MARKER_BLACK_MM = 36.0
MARKER_BORDER_MM = 3.0
MARKER_TOTAL_MM = MARKER_BLACK_MM + 2 * MARKER_BORDER_MM # 42.0 mm

# Centro del cordón en coordenadas de la hoja A4
# Centramos el cordón horizontalmente:
# Origen del cordón (x=0) estará en X_OFFSET_MM de la hoja
X_ORIGIN_PAGE = (PAGE_W_MM - SEAM_LEN_MM) / 2.0  # (297 - 150)/2 = 73.5 mm
Y_ORIGIN_PAGE = PAGE_H_MM / 2.0                 # 105.0 mm

# Posiciones de los centros de los marcadores relativas al inicio del cordón (0,0)
MARKER_COORDS_REL = {
    1: (-45.0, +65.0),   # Sup Izq
    2: (+195.0, +65.0),  # Sup Der
    3: (-45.0, -65.0),   # Inf Izq
    4: (+195.0, -65.0),  # Inf Der
}

def generate_marker_image(marker_id, black_mm, border_mm, dpi=300):
    px_per_mm = dpi / 25.4
    black_px = int(round(black_mm * px_per_mm))
    border_px = int(round(border_mm * px_per_mm))
    total_px = black_px + 2 * border_px

    dict_aruco = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    raw = aruco.generateImageMarker(dict_aruco, marker_id, black_px)

    img = np.ones((total_px, total_px), dtype=np.uint8) * 255
    img[border_px:border_px+black_px, border_px:border_px+black_px] = raw
    return img

def main():
    fig = plt.figure(figsize=(PAGE_W_MM / 25.4, PAGE_H_MM / 25.4), dpi=300)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, PAGE_W_MM)
    ax.set_ylim(0, PAGE_H_MM)
    ax.set_aspect("equal")
    ax.axis("off")

    # 1. Fondo blanco y borde exterior de recorte de la hoja A4
    ax.add_patch(patches.Rectangle((0, 0), PAGE_W_MM, PAGE_H_MM, fill=True, color="white"))
    ax.add_patch(patches.Rectangle((5, 5), PAGE_W_MM - 10, PAGE_H_MM - 10,
                                   fill=False, edgecolor="#cccccc", linestyle=":", linewidth=0.8))

    # 2. Encabezado y Regla de Calibración
    ax.text(PAGE_W_MM / 2.0, PAGE_H_MM - 14.0,
            "ArcSim_VR - Plantilla de Mesa de Soldadura (Escala 1:1)",
            fontsize=13, fontweight="bold", ha="center", va="center", color="#111111")
    ax.text(PAGE_W_MM / 2.0, PAGE_H_MM - 20.0,
            "Pegar esta hoja sobre cartón rígido plano. Asegurar impresión a Escala 100% (Tamaño Real).",
            fontsize=8, ha="center", va="center", color="#555555")

    # Regla de verificación de 100 mm
    ruler_x = (PAGE_W_MM - 100.0) / 2.0
    ruler_y = PAGE_H_MM - 27.0
    ax.add_patch(patches.Rectangle((ruler_x, ruler_y - 1.5), 100.0, 3.0, fill=True, color="#111111"))
    for tick_mm in range(0, 101, 10):
        h = 5.0 if tick_mm % 50 == 0 else (3.5 if tick_mm % 10 == 0 else 2.0)
        ax.plot([ruler_x + tick_mm, ruler_x + tick_mm], [ruler_y + 1.5, ruler_y + 1.5 + h], color="#111111", lw=0.8)
    ax.text(PAGE_W_MM / 2.0, ruler_y + 8.5,
            "Barra de verificación física: 100.0 mm (comprobar con regla común)",
            fontsize=7, fontweight="bold", ha="center", va="center", color="#222222")

    # 3. Dibujar los 4 Marcadores ArUco perimetrales
    for m_id, (rel_x, rel_y) in MARKER_COORDS_REL.items():
        page_cx = X_ORIGIN_PAGE + rel_x
        page_cy = Y_ORIGIN_PAGE + rel_y

        # Generar bitmap ArUco
        marker_img = generate_marker_image(m_id, MARKER_BLACK_MM, MARKER_BORDER_MM, dpi=300)
        
        # Bbox en milímetros
        left = page_cx - MARKER_TOTAL_MM / 2.0
        right = page_cx + MARKER_TOTAL_MM / 2.0
        bottom = page_cy - MARKER_TOTAL_MM / 2.0
        top = page_cy + MARKER_TOTAL_MM / 2.0

        ax.imshow(marker_img, cmap="gray", extent=[left, right, bottom, top], origin="upper", zorder=3)
        ax.add_patch(patches.Rectangle((left, bottom), MARKER_TOTAL_MM, MARKER_TOTAL_MM,
                                       fill=False, edgecolor="#999999", linestyle="--", linewidth=0.6))
        
        # Etiqueta del marcador
        label_y = top + 3.0 if rel_y > 0 else bottom - 4.5
        ax.text(page_cx, label_y, f"MESA ARUCO ID {m_id}",
                fontsize=7.5, fontweight="bold", ha="center", va="center", color="#333333")

    # 4. Probeta Central de Soldadura (150 mm x 24 mm)
    seam_x0 = X_ORIGIN_PAGE
    seam_y0 = Y_ORIGIN_PAGE - SEAM_W_MM / 2.0

    # Chapa metálica simulada (fondo gris acero)
    ax.add_patch(patches.Rectangle((seam_x0 - 5.0, seam_y0 - 8.0), SEAM_LEN_MM + 10.0, SEAM_W_MM + 16.0,
                                   fill=True, color="#e6eaed", zorder=1))
    ax.add_patch(patches.Rectangle((seam_x0 - 5.0, seam_y0 - 8.0), SEAM_LEN_MM + 10.0, SEAM_W_MM + 16.0,
                                   fill=False, edgecolor="#8a9ba8", linewidth=1.2, zorder=2))

    # Área de la junta / bisel central (150 mm)
    ax.add_patch(patches.Rectangle((seam_x0, seam_y0), SEAM_LEN_MM, SEAM_W_MM,
                                   fill=True, color="#cbd3d9", zorder=2))
    ax.add_patch(patches.Rectangle((seam_x0, seam_y0), SEAM_LEN_MM, SEAM_W_MM,
                                   fill=False, edgecolor="#556677", linewidth=0.8, zorder=2))

    # Línea central de la junta (Eje X de avance)
    ax.plot([seam_x0, seam_x0 + SEAM_LEN_MM], [Y_ORIGIN_PAGE, Y_ORIGIN_PAGE],
            color="#223344", linestyle="-", linewidth=1.5, zorder=3)

    # Graduaciones milimétricas a lo largo del cordón
    for d_mm in range(0, int(SEAM_LEN_MM) + 1, 5):
        is_major = (d_mm % 10 == 0)
        tick_h = 3.5 if is_major else 2.0
        # Ticks arriba y abajo
        ax.plot([seam_x0 + d_mm, seam_x0 + d_mm], [Y_ORIGIN_PAGE - tick_h, Y_ORIGIN_PAGE + tick_h],
                color="#334455", linewidth=0.7 if is_major else 0.4, zorder=3)
        if is_major:
            ax.text(seam_x0 + d_mm, seam_y0 + 2.5, str(d_mm),
                    fontsize=6, ha="center", va="center", color="#334455", zorder=3)

    # Indicador de Inicio de Cordón (Punto Cero 0,0)
    ax.plot(seam_x0, Y_ORIGIN_PAGE, marker="o", markersize=6, color="#00aa33", zorder=4)
    ax.text(seam_x0, Y_ORIGIN_PAGE + 15.0, "INICIO DEL CORDÓN\n(X=0, Y=0) [HOMING]",
            fontsize=8, fontweight="bold", ha="center", va="center", color="#008822")
    ax.annotate("", xy=(seam_x0, Y_ORIGIN_PAGE + 4.0), xytext=(seam_x0, Y_ORIGIN_PAGE + 11.0),
                arrowprops=dict(arrowstyle="->", color="#008822", lw=1.5), zorder=4)

    # Indicador de Fin de Cordón (150 mm)
    ax.plot(seam_x0 + SEAM_LEN_MM, Y_ORIGIN_PAGE, marker="o", markersize=6, color="#cc2200", zorder=4)
    ax.text(seam_x0 + SEAM_LEN_MM, Y_ORIGIN_PAGE + 15.0, "FIN DEL CORDÓN\n(150.0 mm)",
            fontsize=8, fontweight="bold", ha="center", va="center", color="#aa1100")
    ax.annotate("", xy=(seam_x0 + SEAM_LEN_MM, Y_ORIGIN_PAGE + 4.0),
                xytext=(seam_x0 + SEAM_LEN_MM, Y_ORIGIN_PAGE + 11.0),
                arrowprops=dict(arrowstyle="->", color="#aa1100", lw=1.5), zorder=4)

    # Flecha de Sentido de Avance (Arrastre hacia la derecha)
    ax.annotate("SENTIDO DE AVANCE (Técnica de arrastre SMAW)",
                xy=(seam_x0 + SEAM_LEN_MM - 15.0, Y_ORIGIN_PAGE - 13.0),
                xytext=(seam_x0 + 15.0, Y_ORIGIN_PAGE - 13.0),
                arrowprops=dict(arrowstyle="->", color="#114488", lw=2.0),
                fontsize=8, fontweight="bold", ha="center", va="center", color="#114488")

    # Guardar en PDF vectorial y PNG de alta resolución
    plt.savefig(PDF_PATH, format="pdf", dpi=300)
    plt.savefig(PNG_PATH, format="png", dpi=300)
    plt.close()

    print(f"[OK] PDF de mesa generado en: {PDF_PATH}")
    print(f"[OK] PNG de mesa generado en: {PNG_PATH}")

if __name__ == "__main__":
    main()
