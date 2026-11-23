#!/usr/bin/env python3
"""
ArcSim_VR - Seguimiento Espacial 3D con Mesa de Soldadura (ArUco Multi-Marcador)
==============================================================================
Rastrea la posición de la herramienta en el espacio físico sobre la plantilla A4:
  - Mesa (IDs 1, 2, 3, 4): Define el plano de trabajo milimétrico y el origen (0,0)
  - Herramienta (ID 0): Mide la posición exacta en el cordón de soldadura (0 a 150 mm)

Ventajas:
  - Si el brazo tapa 1 o 2 marcadores de la mesa, el tracking NUNCA se pierde.
  - Mapeo directo en milímetros reales sin deriva ni saltos.
  - Minimapa interactivo 2D del cordón en tiempo real.
"""

import sys
import time
import math
from collections import deque
import numpy as np
import cv2

# ==============================================================================
# COORDENADAS FÍSICAS DE LA PLANTILLA A4 (en milímetros respecto al inicio de cordón)
# ==============================================================================
MARKER_SIZE_MM = 36.0          # Marcadores de la mesa (36 mm)
TOOL_MARKER_SIZE_MM = 40.0     # Marcador de la herramienta (40 mm)

# Coordenadas (X, Y) físicas en mm donde (0,0) es el punto INICIO DE CORDÓN
TABLE_MARKERS_PHYSICAL_MM = {
    1: np.array([-45.0, +65.0], dtype=np.float32),  # Sup Izq
    2: np.array([+195.0, +65.0], dtype=np.float32), # Sup Der
    3: np.array([-45.0, -65.0], dtype=np.float32),  # Inf Izq
    4: np.array([+195.0, -65.0], dtype=np.float32)  # Inf Der
}

SEAM_LENGTH_MM = 150.0

def find_camera():
    print("Buscando camara web...")
    for idx in [0, 1, 2]:
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                return cap
            cap.release()

        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                return cap
            cap.release()
    return None

def main():
    cap = find_camera()
    if cap is None:
        print("\n>>> ERROR: No se pudo abrir la camara web.")
        input("Presiona Enter para salir...")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)

    # Configurar detector ArUco con subpíxel
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    detector_params = cv2.aruco.DetectorParameters()
    detector_params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    detector = cv2.aruco.ArucoDetector(aruco_dict, detector_params)

    print("\n============================================================")
    print("  ArcSim_VR - Seguimiento Espacial con Mesa de Soldadura")
    print("============================================================")
    print("Detectando:")
    print("  - Marcadores de mesa: IDs 1, 2, 3, 4")
    print("  - Marcador de herramienta: ID 0")
    print("Controles:")
    print("  [Q] o [ESC] : Salir")
    print("============================================================\n")

    # Variables de cinemática y suavizado
    smoothed_tool_mm = None
    history = deque(maxlen=20)
    speed_filtered = 0.0

    last_time = time.time()
    fps_count = 0
    fps_start = time.time()
    current_fps = 0.0

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            break

        now = time.time()
        fps_count += 1
        if now - fps_start >= 1.0:
            current_fps = fps_count / (now - fps_start)
            fps_count = 0
            fps_start = now

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, rejected = detector.detectMarkers(gray)

        # Detectar marcadores presentes
        detected_table_pts_img = []
        detected_table_pts_real = []
        visible_table_ids = []
        pos_tool_px = None

        if ids is not None and len(ids) > 0:
            ids_flat = ids.flatten()
            for i, marker_id in enumerate(ids_flat):
                c = corners[i][0]
                cx = float(np.mean(c[:, 0]))
                cy = float(np.mean(c[:, 1]))

                if marker_id in TABLE_MARKERS_PHYSICAL_MM:
                    detected_table_pts_img.append([cx, cy])
                    detected_table_pts_real.append(TABLE_MARKERS_PHYSICAL_MM[marker_id])
                    visible_table_ids.append(marker_id)
                    cv2.polylines(frame, [c.astype(np.int32)], True, (0, 255, 0), 2)
                    cv2.circle(frame, (int(cx), int(cy)), 4, (0, 255, 0), -1)
                    cv2.putText(frame, f"MESA {marker_id}", (int(cx) - 25, int(cy) - 15),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

                elif marker_id == 0:
                    pos_tool_px = np.array([cx, cy], dtype=np.float32)
                    cv2.polylines(frame, [c.astype(np.int32)], True, (255, 255, 0), 2)
                    cv2.circle(frame, (int(cx), int(cy)), 5, (255, 255, 0), -1)
                    cv2.putText(frame, "HERRAMIENTA (ID 0)", (int(cx) - 50, int(cy) - 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 2)

        # ----------------------------------------------------------------------
        # CÁLCULO DE LA TRANSFORMACIÓN HOMOGRÁFICA MESA -> PLANO FÍSICO (MM)
        # ----------------------------------------------------------------------
        tool_pos_table_mm = None

        if len(detected_table_pts_img) >= 2 and pos_tool_px is not None:
            pts_img = np.array(detected_table_pts_img, dtype=np.float32)
            pts_real = np.array(detected_table_pts_real, dtype=np.float32)

            if len(detected_table_pts_img) >= 4:
                # Homografía de perspectiva completa (4 puntos o más)
                H, _ = cv2.findHomography(pts_img, pts_real, cv2.RANSAC, 5.0)
            else:
                # Transformación afín / similar robusta para 2 o 3 puntos
                M, _ = cv2.estimateAffinePartial2D(pts_img, pts_real)
                if M is not None:
                    H = np.vstack([M, [0, 0, 1]])
                else:
                    H = None

            if H is not None:
                # Proyectar la posición de la herramienta al plano de la mesa (en milímetros)
                tool_homogeneous = np.array([pos_tool_px[0], pos_tool_px[1], 1.0], dtype=np.float32)
                transformed = H @ tool_homogeneous
                if abs(transformed[2]) > 1e-6:
                    raw_x = transformed[0] / transformed[2]
                    raw_y = transformed[1] / transformed[2]
                    raw_tool_mm = np.array([raw_x, raw_y], dtype=np.float32)

                    # Filtro pasa-bajos
                    if smoothed_tool_mm is None:
                        smoothed_tool_mm = raw_tool_mm.copy()
                    else:
                        smoothed_tool_mm = 0.80 * smoothed_tool_mm + 0.20 * raw_tool_mm
                    tool_pos_table_mm = smoothed_tool_mm

        # ----------------------------------------------------------------------
        # CÁLCULO DE VELOCIDAD DE AVANCE
        # ----------------------------------------------------------------------
        if tool_pos_table_mm is not None:
            history.append((now, tool_pos_table_mm[0], tool_pos_table_mm[1]))
            ref_idx = 0
            for k in range(len(history)):
                if now - history[k][0] >= 0.25:
                    ref_idx = k
                else:
                    break

            t_old, x_old, y_old = history[ref_idx]
            dt_win = now - t_old
            if dt_win >= 0.10:
                dist_moved = math.hypot(tool_pos_table_mm[0] - x_old, tool_pos_table_mm[1] - y_old)
                if dist_moved < 0.45:
                    v_target = 0.0
                else:
                    v_target = min(dist_moved / dt_win, 25.0)

                if v_target == 0.0:
                    speed_filtered *= 0.60
                    if speed_filtered < 0.1: speed_filtered = 0.0
                else:
                    speed_filtered = 0.70 * speed_filtered + 0.30 * v_target
        else:
            history.clear()
            smoothed_tool_mm = None
            speed_filtered *= 0.50
            if speed_filtered < 0.1: speed_filtered = 0.0

        # ----------------------------------------------------------------------
        # DIBUJAR MINIMAPA 2D DEL CORDÓN DE SOLDADURA (ESQUINA SUPERIOR DERECHA)
        # ----------------------------------------------------------------------
        mm_w, mm_h = 320, 160
        mm_x0, mm_y0 = frame.shape[1] - mm_w - 20, 20
        # Fondo del minimapa
        cv2.rectangle(frame, (mm_x0, mm_y0), (mm_x0 + mm_w, mm_y0 + mm_h), (25, 30, 38), -1)
        cv2.rectangle(frame, (mm_x0, mm_y0), (mm_x0 + mm_w, mm_y0 + mm_h), (80, 95, 120), 1)

        cv2.putText(frame, "MINIMAPA DE LA MESA (150 mm)", (mm_x0 + 15, mm_y0 + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 220, 240), 1)

        # Coordenadas en el minimapa (mapeo mm -> px en ventana)
        map_origin_x = mm_x0 + 40
        map_origin_y = mm_y0 + mm_h // 2
        map_scale = 1.4 # px por mm

        # Dibujar probeta de 150 mm
        seam_len_px = int(SEAM_LENGTH_MM * map_scale)
        cv2.rectangle(frame, (map_origin_x, map_origin_y - 12),
                             (map_origin_x + seam_len_px, map_origin_y + 12), (50, 60, 75), -1)
        # Línea central del bisel
        cv2.line(frame, (map_origin_x, map_origin_y),
                        (map_origin_x + seam_len_px, map_origin_y), (100, 140, 180), 2)
        # Puntos de inicio y fin
        cv2.circle(frame, (map_origin_x, map_origin_y), 4, (0, 255, 0), -1)
        cv2.circle(frame, (map_origin_x + seam_len_px, map_origin_y), 4, (0, 0, 255), -1)
        cv2.putText(frame, "0mm", (map_origin_x - 12, map_origin_y + 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 0), 1)
        cv2.putText(frame, "150mm", (map_origin_x + seam_len_px - 15, map_origin_y + 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 100, 255), 1)

        # Dibujar posición de la herramienta en el minimapa
        if tool_pos_table_mm is not None:
            tx = int(map_origin_x + tool_pos_table_mm[0] * map_scale)
            ty = int(map_origin_y - tool_pos_table_mm[1] * map_scale)
            # Clamping dentro del minimapa
            tx = np.clip(tx, mm_x0 + 5, mm_x0 + mm_w - 5)
            ty = np.clip(ty, mm_y0 + 5, mm_y0 + mm_h - 5)

            # Punto de la herramienta con estela
            cv2.circle(frame, (tx, ty), 7, (255, 255, 0), -1)
            cv2.circle(frame, (tx, ty), 10, (255, 255, 0), 1)

        # ----------------------------------------------------------------------
        # HUD EN PANTALLA (IZQUIERDA)
        # ----------------------------------------------------------------------
        overlay = frame.copy()
        cv2.rectangle(overlay, (20, 20), (450, 230), (15, 18, 24), -1)
        cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
        cv2.rectangle(frame, (20, 20), (450, 230), (60, 70, 90), 1)

        cv2.putText(frame, "ArcSim VR - Seguimiento en Mesa A4", (35, 48),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.60, (255, 255, 255), 2)
        cv2.putText(frame, f"FPS: {current_fps:.0f}", (385, 48),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)

        # Estado de marcadores visibles
        n_table = len(visible_table_ids)
        c_table = (0, 255, 0) if n_table >= 2 else (0, 0, 200)
        t_table = f"Marcadores Mesa: {n_table}/4 visibles {visible_table_ids}"
        cv2.putText(frame, t_table, (35, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.48, c_table, 1)

        c_tool = (255, 255, 0) if pos_tool_px is not None else (0, 0, 200)
        t_tool = "Herramienta (ID 0): DETECTADA" if pos_tool_px is not None else "Herramienta (ID 0): BUSCANDO..."
        cv2.putText(frame, t_tool, (35, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.48, c_tool, 1)

        if tool_pos_table_mm is not None:
            # Posición en el cordón
            pos_x = tool_pos_table_mm[0]
            pos_y = tool_pos_table_mm[1]
            status_cordon = "SOBRE EL CORDÓN" if (0 <= pos_x <= 150 and abs(pos_y) < 15) else "FUERA DE JUNTA"
            color_cordon = (0, 255, 0) if status_cordon == "SOBRE EL CORDÓN" else (180, 180, 180)

            cv2.putText(frame, f"Avance en Cordón: {pos_x:+5.1f} / 150 mm", (35, 138),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.52, (220, 230, 240), 1)
            cv2.putText(frame, f"Desvío Lateral:  {pos_y:+5.1f} mm  [{status_cordon}]", (35, 162),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, color_cordon, 1)

            # Velocidad
            if speed_filtered < 0.2:
                v_col = (180, 180, 180)
                v_txt = "REPOSO"
            elif speed_filtered < 1.8:
                v_col = (0, 180, 255)
                v_txt = "LENTA"
            elif speed_filtered <= 4.5:
                v_col = (0, 255, 0)
                v_txt = "ÓPTIMA SMAW"
            else:
                v_col = (0, 0, 255)
                v_txt = "MUY RÁPIDA"

            cv2.putText(frame, f"Velocidad: {speed_filtered:4.1f} mm/s  [{v_txt}]", (35, 195),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, v_col, 2)
        else:
            cv2.putText(frame, "Avance en Cordón: --.- mm", (35, 138),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.50, (120, 130, 140), 1)
            cv2.putText(frame, "Desvío Lateral:  --.- mm", (35, 162),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.50, (120, 130, 140), 1)
            cv2.putText(frame, "Velocidad: --.- mm/s", (35, 195),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.50, (120, 130, 140), 1)

        cv2.putText(frame, "[Q] o [ESC]: Salir", (35, 218),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, (150, 160, 170), 1)

        cv2.imshow("ArcSim_VR - Seguimiento en Mesa de Soldadura", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == ord('Q') or key == 27:
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
