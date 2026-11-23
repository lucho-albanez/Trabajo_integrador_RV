#!/usr/bin/env python3
"""
ArcSim_VR - Probador y Calibrador de Seguimiento Óptico ArUco (v2 - Filtrado Antirruido)
======================================================================================
Mejoras implementadas para eliminar lecturas falsas y picos de velocidad:
  1. Refinamiento subpixel en esquinas (CORNER_REFINE_SUBPIX): elimina el salto de pixeles.
  2. Filtro pasa-bajos en posición (X, Y) antes de calcular la derivada.
  3. Ventana temporal rodante de 250 ms: velocidad calculada sobre intervalo estable.
  4. Zona muerta (Deadband de 0.5 mm): en reposo la velocidad marca exactamente 0.0 mm/s.
  5. Escala milimétrica estabilizada desde el marcador fijo de la mesa.

Controles:
  [ESPACIO] o [C] : Poner a cero la posición actual (Tara de inicio).
  [Q] o [ESC]     : Salir del programa.
"""

import sys
import time
import math
from collections import deque
import numpy as np
import cv2

# ==============================================================================
# CONFIGURACIÓN
# ==============================================================================
MARKER_SIZE_MM = 40.0          # Lado del cuadrado negro del marcador en mm
ID_HERRAMIENTA = 0             # ID del marcador en el soporte 05_soporte_aruco
ID_MESA = 1                    # ID del marcador de referencia en la mesa

# Rango óptimo de velocidad de avance SMAW (mm/s)
V_MIN_OPT = 1.8
V_MAX_OPT = 4.5

# Zona muerta: desplazamientos menores a este umbral en 250 ms se consideran reposo (0.0 mm/s)
DEADBAND_MM = 0.45
WINDOW_DURATION_S = 0.25       # Ventana de 250 ms para cálculo de velocidad estable

def find_camera():
    """Busca y abre la primera cámara web disponible."""
    print("Buscando camara web disponible...")
    for idx in [0, 1, 2]:
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                print(f"[OK] Camara detectada en indice {idx} (DirectShow)")
                return cap
            cap.release()

        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                print(f"[OK] Camara detectada en indice {idx} (Default)")
                return cap
            cap.release()
    return None

def main():
    cap = find_camera()
    if cap is None:
        print("\n>>> ERROR: No se pudo abrir ninguna camara web.")
        print("    Verifica que la camara este enchufada y ninguna otra app la este usando.\n")
        input("Presiona Enter para salir...")
        sys.exit(1)

    # Configuración de captura de video
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)

    # Configurar detector ArUco (DICT_4X4_50) con REFINAMIENTO SUBPIXEL
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    detector_params = cv2.aruco.DetectorParameters()
    
    # Activar cálculo subpixel de esquinas (elimina el jitter de borde)
    detector_params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    detector_params.cornerRefinementWinSize = 5
    detector_params.cornerRefinementMaxIterations = 30
    detector_params.cornerRefinementMinAccuracy = 0.05
    
    detector = cv2.aruco.ArucoDetector(aruco_dict, detector_params)

    print("\n============================================================")
    print("  ArcSim_VR - Monitor de Vision Optica ArUco (v2 Estable)")
    print("============================================================")
    print("Optimizaciones activas:")
    print("  - Refinamiento Subpixel activado.")
    print("  - Zona muerta de reposo: < 0.45 mm -> 0.0 mm/s.")
    print("  - Ventana rodante de velocidad: 250 ms.")
    print("Controles:")
    print("  [ESPACIO] o [C] : Fijar punto cero de inicio")
    print("  [Q] o [ESC]     : Salir")
    print("============================================================\n")

    # Variables de seguimiento
    tare_offset_mm = np.array([0.0, 0.0])
    stable_scale_mm_per_px = None
    smoothed_pos_mm = None
    
    # Cola rodante para cálculo de velocidad en ventana temporal: (timestamp, x_mm, y_mm)
    history = deque(maxlen=20)
    speed_filtered = 0.0

    fps_count = 0
    fps_start = time.time()
    current_fps = 0.0

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            print("Error leyendo cuadro de video.")
            break

        now = time.time()

        # Contador de FPS
        fps_count += 1
        if now - fps_start >= 1.0:
            current_fps = fps_count / (now - fps_start)
            fps_count = 0
            fps_start = now

        # Detección de marcadores ArUco
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, rejected = detector.detectMarkers(gray)

        pos_mesa = None
        pos_tool = None

        if ids is not None and len(ids) > 0:
            ids_flat = ids.flatten()
            for i, marker_id in enumerate(ids_flat):
                c = corners[i][0] # 4 esquinas flotantes
                center_x = float(np.mean(c[:, 0]))
                center_y = float(np.mean(c[:, 1]))

                # Calcular y estabilizar escala con filtro lento desde la mesa fija
                perimeter_px = float(cv2.arcLength(c, True))
                if perimeter_px > 20:
                    current_scale = (MARKER_SIZE_MM * 4.0) / perimeter_px
                    if marker_id == ID_MESA:
                        if stable_scale_mm_per_px is None:
                            stable_scale_mm_per_px = current_scale
                        else:
                            # 98% anterior + 2% nuevo (escala roca que no tiembla)
                            stable_scale_mm_per_px = 0.98 * stable_scale_mm_per_px + 0.02 * current_scale

                if marker_id == ID_MESA:
                    pos_mesa = np.array([center_x, center_y], dtype=np.float32)
                    cv2.polylines(frame, [c.astype(np.int32)], True, (0, 255, 0), 2)
                    cv2.circle(frame, (int(center_x), int(center_y)), 5, (0, 255, 0), -1)
                    cv2.putText(frame, "MESA (ID 1)", (int(center_x) - 35, int(center_y) - 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

                elif marker_id == ID_HERRAMIENTA:
                    pos_tool = np.array([center_x, center_y], dtype=np.float32)
                    cv2.polylines(frame, [c.astype(np.int32)], True, (255, 255, 0), 2)
                    cv2.circle(frame, (int(center_x), int(center_y)), 5, (255, 255, 0), -1)
                    cv2.putText(frame, "HERRAMIENTA (ID 0)", (int(center_x) - 60, int(center_y) - 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 2)
                else:
                    cv2.polylines(frame, [c.astype(np.int32)], True, (150, 150, 150), 1)

        # Usar escala estable o fallback
        scale = stable_scale_mm_per_px if stable_scale_mm_per_px is not None else 0.5

        # ----------------------------------------------------------------------
        # CÁLCULOS CINEMÁTICOS CON FILTRADO ROBUSTO
        # ----------------------------------------------------------------------
        dx_mm = 0.0
        dy_mm = 0.0
        dist_total_mm = 0.0

        if pos_mesa is not None and pos_tool is not None:
            # Dibujar línea entre la mesa y la herramienta
            pt_mesa = (int(pos_mesa[0]), int(pos_mesa[1]))
            pt_tool = (int(pos_tool[0]), int(pos_tool[1]))
            cv2.line(frame, pt_mesa, pt_tool, (0, 200, 255), 2, cv2.LINE_AA)

            # Vector relativo instantáneo en milímetros
            delta_px = pos_tool - pos_mesa
            raw_pos_mm = delta_px * scale

            # 1. Filtro Pasa-Bajos en posición (80% anterior + 20% nuevo)
            if smoothed_pos_mm is None:
                smoothed_pos_mm = raw_pos_mm.copy()
            else:
                smoothed_pos_mm = 0.80 * smoothed_pos_mm + 0.20 * raw_pos_mm

            # Posición calibrada respecto al origen de tara
            pos_calibrada_mm = smoothed_pos_mm - tare_offset_mm
            dx_mm = pos_calibrada_mm[0]
            dy_mm = pos_calibrada_mm[1]
            dist_total_mm = math.hypot(dx_mm, dy_mm)

            # 2. Agregar punto a la cola de historial rodante
            history.append((now, smoothed_pos_mm[0], smoothed_pos_mm[1]))

            # 3. Cálculo de velocidad sobre ventana rodante de 250 ms
            # Buscamos el punto más antiguo que tenga al menos ~WINDOW_DURATION_S de antigüedad
            ref_idx = 0
            for k in range(len(history)):
                if now - history[k][0] >= WINDOW_DURATION_S:
                    ref_idx = k
                else:
                    break

            t_old, x_old, y_old = history[ref_idx]
            dt_window = now - t_old

            if dt_window >= 0.10: # al menos 100 ms de ventana
                displacement_mm = math.hypot(smoothed_pos_mm[0] - x_old, smoothed_pos_mm[1] - y_old)
                
                # 4. Zona muerta: si se movió menos de 0.45 mm en 250 ms, es reposo estricto
                if displacement_mm < DEADBAND_MM:
                    v_target = 0.0
                else:
                    v_target = displacement_mm / dt_window

                # Clamping de seguridad (máximo 20 mm/s)
                v_target = min(v_target, 20.0)

                # 5. Suavizado final de salida
                if v_target == 0.0:
                    speed_filtered *= 0.60 # frenado rápido a 0
                    if speed_filtered < 0.1: speed_filtered = 0.0
                else:
                    speed_filtered = 0.70 * speed_filtered + 0.30 * v_target
        else:
            # Si se pierde algún marcador, vaciar historial y decaer velocidad a cero
            history.clear()
            smoothed_pos_mm = None
            speed_filtered *= 0.50
            if speed_filtered < 0.1: speed_filtered = 0.0

        # ----------------------------------------------------------------------
        # HUD EN PANTALLA
        # ----------------------------------------------------------------------
        overlay = frame.copy()
        cv2.rectangle(overlay, (20, 20), (460, 230), (15, 18, 24), -1)
        cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
        cv2.rectangle(frame, (20, 20), (460, 230), (60, 70, 90), 1)

        cv2.putText(frame, "ArcSim VR - Vision Optica (Filtrada)", (35, 48),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.60, (255, 255, 255), 2)
        cv2.putText(frame, f"FPS: {current_fps:.0f}", (390, 48),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)

        c_mesa = (0, 255, 0) if pos_mesa is not None else (0, 0, 200)
        t_mesa = "Mesa (ID 1): DETECTADO" if pos_mesa is not None else "Mesa (ID 1): BUSCANDO..."
        cv2.putText(frame, t_mesa, (35, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.50, c_mesa, 1)

        c_tool = (255, 255, 0) if pos_tool is not None else (0, 0, 200)
        t_tool = "Herramienta (ID 0): DETECTADO" if pos_tool is not None else "Herramienta (ID 0): BUSCANDO..."
        cv2.putText(frame, t_tool, (35, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.50, c_tool, 1)

        cv2.putText(frame, f"Desplazamiento dX (Avance): {dx_mm:+6.1f} mm", (35, 138),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (220, 230, 240), 1)
        cv2.putText(frame, f"Desplazamiento dY (Transv): {dy_mm:+6.1f} mm", (35, 162),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (220, 230, 240), 1)

        if pos_mesa is not None and pos_tool is not None:
            if speed_filtered < 0.2:
                v_color = (180, 180, 180) # Gris: Reposo
                v_status = "REPOSO"
            elif speed_filtered < V_MIN_OPT:
                v_color = (0, 180, 255)   # Naranja: Lenta
                v_status = "LENTA"
            elif speed_filtered <= V_MAX_OPT:
                v_color = (0, 255, 0)     # Verde: Óptima
                v_status = "OPTIMA SMAW"
            else:
                v_color = (0, 0, 255)     # Roja: Rápida
                v_status = "MUY RAPIDA"

            cv2.putText(frame, f"Velocidad: {speed_filtered:4.1f} mm/s  [{v_status}]", (35, 195),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, v_color, 2)
        else:
            cv2.putText(frame, "Velocidad: --.- mm/s  (Esperando ambos marcadores)", (35, 195),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (120, 130, 140), 1)

        cv2.putText(frame, "[ESPACIO]: Tara de inicio (0 mm)   |   [Q]: Salir", (35, 218),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, (150, 160, 170), 1)

        cv2.imshow("ArcSim_VR - Camara ArUco", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == ord('Q') or key == 27:
            break
        elif key == ord(' ') or key == ord('c') or key == ord('C'):
            if smoothed_pos_mm is not None:
                tare_offset_mm = smoothed_pos_mm.copy()
                print(f">>> [TARA FIJADA] Origen (0,0) calibrado en la posicion actual de la herramienta.")

    cap.release()
    cv2.destroyAllWindows()
    print("Monitor de camara cerrado.")

if __name__ == "__main__":
    main()
