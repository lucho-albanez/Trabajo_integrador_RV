#!/usr/bin/env python3
"""
ArcSim_VR - Seguimiento Espacial en Mesa de Soldadura (v3 - Calibración 2 Puntos)
================================================================================
Permite calibrar la escala exacta del cordón físico en 2 pasos:
  1. Apoyar la punta en el INICIO del cordón y presionar [ESPACIO] -> Fija Origen (0, 0).
  2. Apoyar la punta en el FINAL del cordón y presionar [F]       -> Calibra Longitud Exacta.

Funciona con cualquier medida de cordón (sea de 90 mm, 120 mm o 150 mm)
y compensa automáticamente cualquier desvío de escala o ángulo en el cartón.
"""

import sys
import os
import json
import socket
import time
import math
from collections import deque
import numpy as np
import cv2

# ==============================================================================
# CONFIGURACIÓN FÍSICA DE REFERENCIA (PLANTILLA A4)
# ==============================================================================
DEFAULT_SEAM_LENGTH_MM = 150.0 # Longitud objetivo nominal en el simulador
MARKER_SIZE_MM = 36.0
HALF_M_MM = MARKER_SIZE_MM / 2.0

MARKER_CENTERS_MM = {
    1: np.array([-45.0, +65.0], dtype=np.float32),  # Sup Izq
    2: np.array([+195.0, +65.0], dtype=np.float32), # Sup Der
    3: np.array([-45.0, -65.0], dtype=np.float32),  # Inf Izq
    4: np.array([+195.0, -65.0], dtype=np.float32)  # Inf Der
}

MARKER_CORNERS_PHYSICAL_MM = {}
for m_id, (cx, cy) in MARKER_CENTERS_MM.items():
    MARKER_CORNERS_PHYSICAL_MM[m_id] = np.array([
        [cx - HALF_M_MM, cy + HALF_M_MM],
        [cx + HALF_M_MM, cy + HALF_M_MM],
        [cx + HALF_M_MM, cy - HALF_M_MM],
        [cx - HALF_M_MM, cy - HALF_M_MM]
    ], dtype=np.float32)

CALIB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mesa_calibration.json")

def load_calibration():
    if os.path.exists(CALIB_FILE):
        try:
            with open(CALIB_FILE, "r") as f:
                data = json.load(f)
                start_pt = np.array(data["start_pt"], dtype=np.float32)
                end_pt = np.array(data["end_pt"], dtype=np.float32)
                target_len = float(data.get("target_len_mm", DEFAULT_SEAM_LENGTH_MM))
                meas_dist = float(np.linalg.norm(end_pt - start_pt))
                scale_fac = target_len / meas_dist if meas_dist > 1.0 else 1.0
                print(f"\n>>> [MEMORIA] Calibracion cargada de mesa_calibration.json:")
                print(f"    Medida real carton: {meas_dist:.1f} mm -> Sim Godot: {target_len:.0f} mm (Escala: {scale_fac:.2f}x)")
                return start_pt, end_pt, target_len
        except Exception as e:
            print(f">>> [MEMORIA] Error al leer calibracion: {e}")
    return None, None, DEFAULT_SEAM_LENGTH_MM

def save_calibration(start_pt, end_pt, target_len):
    try:
        meas_dist = float(np.linalg.norm(end_pt - start_pt))
        scale_fac = float(target_len / meas_dist) if meas_dist > 1.0 else 1.0
        data = {
            "start_pt": [float(start_pt[0]), float(start_pt[1])],
            "end_pt": [float(end_pt[0]), float(end_pt[1])],
            "measured_len_mm": round(meas_dist, 2),
            "target_len_mm": float(target_len),
            "scale_factor": round(scale_fac, 4)
        }
        with open(CALIB_FILE, "w") as f:
            json.dump(data, f, indent=2)
        print(f"\n============================================================")
        print(f"  ¡CALIBRACION 1:1 GUARDADA EXITOSAMENTE EN DISCO!")
        print(f"============================================================")
        print(f"  - Longitud en tu cartón físico: {meas_dist:.1f} mm")
        print(f"  - Longitud en el simulador:     {target_len:.0f} mm")
        print(f"  - Factor de escala aplicado:    {scale_fac:.2f}x")
        print(f"  (Se recordará automáticamente cada vez que inicies el programa)")
        print(f"============================================================\n")
    except Exception as e:
        print(f">>> [MEMORIA] Error guardando calibracion: {e}")

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

    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    detector_params = cv2.aruco.DetectorParameters()
    detector_params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    detector_params.cornerRefinementWinSize = 5
    detector_params.cornerRefinementMaxIterations = 30
    detector_params.cornerRefinementMinAccuracy = 0.05
    detector = cv2.aruco.ArucoDetector(aruco_dict, detector_params)

    print("\n============================================================")
    print("  ArcSim_VR - Seguimiento en Mesa de Soldadura (v3 Calibrada)")
    print("============================================================")
    print("Calibración del cordón en 2 pasos:")
    print("  1. Apoya la punta en el INICIO y presiona [ESPACIO]")
    print("  2. Apoya la punta en el FINAL  y presiona [F]")
    print("Controles:")
    print("  [ESPACIO] o [C] : Calibrar INICIO (0,0)")
    print("  [F]             : Calibrar FINAL del cordón (Auto-escala 150mm)")
    print("  [R]             : Resetear calibración")
    print("  [Q] o [ESC]     : Salir")
    print("============================================================\n")

    # Variables de homografía y posición
    smoothed_H = None
    smoothed_tool_mm = None
    
    # Cargar calibración persistente si existe previamente
    calib_start_pt, calib_end_pt, seam_len_target_mm = load_calibration()
    calib_scale_factor = 1.0

    # Socket UDP para enviar seguimiento 1:1 a Godot
    GODOT_UDP_ADDR = ("127.0.0.1", 4242)
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    last_sent_pos = None

    history = deque(maxlen=20)
    speed_filtered = 0.0

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

        table_corners_img = []
        table_corners_real = []
        visible_table_ids = []
        pos_tool_px = None

        if ids is not None and len(ids) > 0:
            ids_flat = ids.flatten()
            for i, marker_id in enumerate(ids_flat):
                c = corners[i][0]

                if marker_id in MARKER_CORNERS_PHYSICAL_MM:
                    for k in range(4):
                        table_corners_img.append([float(c[k, 0]), float(c[k, 1])])
                        table_corners_real.append(MARKER_CORNERS_PHYSICAL_MM[marker_id][k])

                    visible_table_ids.append(marker_id)
                    cv2.polylines(frame, [c.astype(np.int32)], True, (0, 255, 0), 2)
                    cx = int(np.mean(c[:, 0]))
                    cy = int(np.mean(c[:, 1]))
                    cv2.circle(frame, (cx, cy), 4, (0, 255, 0), -1)
                    cv2.putText(frame, f"ID {marker_id}", (cx - 15, cy - 12),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

                elif marker_id == 0:
                    cx = float(np.mean(c[:, 0]))
                    cy = float(np.mean(c[:, 1]))
                    pos_tool_px = np.array([cx, cy], dtype=np.float32)
                    cv2.polylines(frame, [c.astype(np.int32)], True, (255, 255, 0), 2)
                    cv2.circle(frame, (int(cx), int(cy)), 5, (255, 255, 0), -1)
                    cv2.putText(frame, "HERRAMIENTA (ID 0)", (int(cx) - 60, int(cy) - 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 2)

        # ----------------------------------------------------------------------
        # CÁLCULO DE LA HOMOGRAFÍA DE LA MESA
        # ----------------------------------------------------------------------
        if len(table_corners_img) >= 4:
            pts_img = np.array(table_corners_img, dtype=np.float32)
            pts_real = np.array(table_corners_real, dtype=np.float32)
            H_measured, _ = cv2.findHomography(pts_img, pts_real, cv2.RANSAC, 4.0)

            if H_measured is not None:
                if abs(H_measured[2, 2]) > 1e-6:
                    H_measured /= H_measured[2, 2]
                if smoothed_H is None:
                    smoothed_H = H_measured.copy()
                else:
                    smoothed_H = 0.90 * smoothed_H + 0.10 * H_measured

        # Proyectar la posición del marcador de la herramienta al plano de la mesa
        raw_tool_table_mm = None
        if smoothed_H is not None and pos_tool_px is not None:
            tool_homogeneous = np.array([pos_tool_px[0], pos_tool_px[1], 1.0], dtype=np.float32)
            transformed = smoothed_H @ tool_homogeneous
            if abs(transformed[2]) > 1e-6:
                raw_tool_table_mm = np.array([transformed[0] / transformed[2],
                                              transformed[1] / transformed[2]], dtype=np.float32)

                if smoothed_tool_mm is None:
                    smoothed_tool_mm = raw_tool_table_mm.copy()
                else:
                    smoothed_tool_mm = 0.80 * smoothed_tool_mm + 0.20 * raw_tool_table_mm

        # ----------------------------------------------------------------------
        # CALCULO DE LA POSICIÓN RELATIVA DE LA PUNTA (AVANCE Y DESVÍO)
        # ----------------------------------------------------------------------
        tip_pos_mm = None
        pos_x = 0.0
        pos_y = 0.0

        if smoothed_tool_mm is not None:
            if calib_start_pt is not None:
                # Vector desde el punto de inicio calibrado
                delta = smoothed_tool_mm - calib_start_pt

                if calib_end_pt is not None:
                    # Si ambos puntos fueron calibrados (Inicio y Fin):
                    seam_vec = calib_end_pt - calib_start_pt
                    seam_measured_len = float(np.linalg.norm(seam_vec))
                    if seam_measured_len > 10.0:
                        u_dir = seam_vec / seam_measured_len
                        v_dir = np.array([-u_dir[1], u_dir[0]], dtype=np.float32)
                        
                        # Proyección a lo largo del cordón y desvío lateral
                        dist_along = float(np.dot(delta, u_dir))
                        dist_perp  = float(np.dot(delta, v_dir))

                        # Escalar exactamente a la longitud del cordón de Godot (150 mm)
                        pos_x = dist_along * (seam_len_target_mm / seam_measured_len)
                        pos_y = dist_perp  * (seam_len_target_mm / seam_measured_len)
                        tip_pos_mm = np.array([pos_x, pos_y], dtype=np.float32)
                else:
                    # Solo inicio calibrado
                    pos_x = delta[0] * calib_scale_factor
                    pos_y = delta[1] * calib_scale_factor
                    tip_pos_mm = np.array([pos_x, pos_y], dtype=np.float32)
            else:
                # Sin calibrar (muestra la posición cruda del marcador)
                pos_x = smoothed_tool_mm[0]
                pos_y = smoothed_tool_mm[1]
                tip_pos_mm = smoothed_tool_mm

        # ----------------------------------------------------------------------
        # TRANSMISIÓN UDP A GODOT (dx, dy)
        # ----------------------------------------------------------------------
        if tip_pos_mm is not None and calib_start_pt is not None:
            if last_sent_pos is None:
                last_sent_pos = np.array([pos_x, pos_y], dtype=np.float32)
            else:
                dx = pos_x - last_sent_pos[0]
                dy = pos_y - last_sent_pos[1]
                if abs(dx) >= 0.15 or abs(dy) >= 0.15:
                    pkt = {"dx": round(float(dx), 2), "dy": round(float(dy), 2)}
                    try:
                        udp_sock.sendto(json.dumps(pkt).encode("ascii"), GODOT_UDP_ADDR)
                    except Exception:
                        pass
                    last_sent_pos = np.array([pos_x, pos_y], dtype=np.float32)
        else:
            last_sent_pos = None

        # ----------------------------------------------------------------------
        # VELOCIDAD DE AVANCE
        # ----------------------------------------------------------------------
        if tip_pos_mm is not None:
            history.append((now, tip_pos_mm[0], tip_pos_mm[1]))
            ref_idx = 0
            for k in range(len(history)):
                if now - history[k][0] >= 0.25:
                    ref_idx = k
                else:
                    break

            t_old, x_old, y_old = history[ref_idx]
            dt_win = now - t_old
            if dt_win >= 0.10:
                dist_moved = math.hypot(tip_pos_mm[0] - x_old, tip_pos_mm[1] - y_old)
                if dist_moved < 0.45:
                    v_target = 0.0
                else:
                    v_target = min(dist_moved / dt_win, 25.0)

                if v_target == 0.0:
                    speed_filtered *= 0.50
                    if speed_filtered < 0.1: speed_filtered = 0.0
                else:
                    speed_filtered = 0.70 * speed_filtered + 0.30 * v_target
        else:
            history.clear()
            speed_filtered *= 0.50
            if speed_filtered < 0.1: speed_filtered = 0.0

        # ----------------------------------------------------------------------
        # MINIMAPA 2D (ESQUINA SUPERIOR DERECHA)
        # ----------------------------------------------------------------------
        mm_w, mm_h = 320, 160
        mm_x0, mm_y0 = frame.shape[1] - mm_w - 20, 20
        cv2.rectangle(frame, (mm_x0, mm_y0), (mm_x0 + mm_w, mm_y0 + mm_h), (25, 30, 38), -1)
        cv2.rectangle(frame, (mm_x0, mm_y0), (mm_x0 + mm_w, mm_y0 + mm_h), (80, 95, 120), 1)

        cv2.putText(frame, "MINIMAPA DEL CORDON (150 mm)", (mm_x0 + 15, mm_y0 + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 220, 240), 1)

        map_origin_x = mm_x0 + 40
        map_origin_y = mm_y0 + mm_h // 2
        map_scale = 1.4

        seam_len_px = int(seam_len_target_mm * map_scale)
        cv2.rectangle(frame, (map_origin_x, map_origin_y - 12),
                             (map_origin_x + seam_len_px, map_origin_y + 12), (50, 60, 75), -1)
        cv2.line(frame, (map_origin_x, map_origin_y),
                        (map_origin_x + seam_len_px, map_origin_y), (100, 140, 180), 2)
        cv2.circle(frame, (map_origin_x, map_origin_y), 5, (0, 255, 0), -1)
        cv2.circle(frame, (map_origin_x + seam_len_px, map_origin_y), 5, (0, 0, 255), -1)
        cv2.putText(frame, "0mm", (map_origin_x - 12, map_origin_y + 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 0), 1)
        cv2.putText(frame, "150mm", (map_origin_x + seam_len_px - 15, map_origin_y + 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 100, 255), 1)

        if tip_pos_mm is not None:
            tx = int(map_origin_x + pos_x * map_scale)
            ty = int(map_origin_y - pos_y * map_scale)
            tx = np.clip(tx, mm_x0 + 5, mm_x0 + mm_w - 5)
            ty = np.clip(ty, mm_y0 + 5, mm_y0 + mm_h - 5)

            cv2.circle(frame, (tx, ty), 7, (255, 255, 0), -1)
            cv2.circle(frame, (tx, ty), 10, (255, 255, 0), 1)

        # ----------------------------------------------------------------------
        # HUD EN PANTALLA (IZQUIERDA)
        # ----------------------------------------------------------------------
        overlay = frame.copy()
        cv2.rectangle(overlay, (20, 20), (480, 275), (15, 18, 24), -1)
        cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
        cv2.rectangle(frame, (20, 20), (480, 275), (60, 70, 90), 1)

        cv2.putText(frame, "ArcSim VR - Seguimiento en Mesa A4", (35, 48),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.60, (255, 255, 255), 2)
        cv2.putText(frame, f"FPS: {current_fps:.0f}", (405, 48),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)

        n_table = len(visible_table_ids)
        c_table = (0, 255, 0) if n_table >= 2 else (0, 160, 255) if n_table >= 1 else (0, 0, 200)
        cv2.putText(frame, f"Mesa: {n_table}/4 marcadores visibles {visible_table_ids}", (35, 78),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, c_table, 1)

        c_tool = (255, 255, 0) if pos_tool_px is not None else (0, 0, 200)
        cv2.putText(frame, f"Herramienta: {'DETECTADA' if pos_tool_px is not None else 'BUSCANDO...'}", (35, 102),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, c_tool, 1)

        # Estado de la Calibración de 2 Puntos
        if calib_start_pt is None:
            cv2.putText(frame, "PASO 1: Punta en INICIO -> Presiona [ESPACIO]", (35, 126),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 180, 255), 1)
        elif calib_end_pt is None:
            cv2.putText(frame, "PASO 2: Punta en FINAL de linea -> Presiona [F]", (35, 126),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 255, 255), 1)
        else:
            seam_vec = calib_end_pt - calib_start_pt
            s_len = float(np.linalg.norm(seam_vec))
            s_fac = (seam_len_target_mm / s_len) if s_len > 1.0 else 1.0
            cv2.putText(frame, f"CALIBRADA: Real {s_len:.0f}mm -> Godot 150mm (x{s_fac:.2f})", (35, 126),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 255, 120), 1)

        if tip_pos_mm is not None:
            status_cordon = "SOBRE EL CORDÓN" if (0 <= pos_x <= seam_len_target_mm and abs(pos_y) < 15) else "FUERA DE JUNTA"
            color_cordon = (0, 255, 0) if status_cordon == "SOBRE EL CORDÓN" else (180, 180, 180)

            cv2.putText(frame, f"Avance en Cordón: {pos_x:+5.1f} / {seam_len_target_mm:.0f} mm", (35, 155),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.52, (220, 230, 240), 1)
            cv2.putText(frame, f"Desvío Lateral:  {pos_y:+5.1f} mm  [{status_cordon}]", (35, 179),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, color_cordon, 1)

            if speed_filtered < 0.2:
                v_col, v_txt = (180, 180, 180), "REPOSO"
            elif speed_filtered < 1.8:
                v_col, v_txt = (0, 180, 255), "LENTA"
            elif speed_filtered <= 4.5:
                v_col, v_txt = (0, 255, 0), "ÓPTIMA SMAW"
            else:
                v_col, v_txt = (0, 0, 255), "MUY RÁPIDA"

            cv2.putText(frame, f"Velocidad: {speed_filtered:4.1f} mm/s  [{v_txt}]", (35, 212),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, v_col, 2)
        else:
            cv2.putText(frame, "Avance en Cordón: --.- mm", (35, 155), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (120, 130, 140), 1)
            cv2.putText(frame, "Desvío Lateral:  --.- mm", (35, 179), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (120, 130, 140), 1)
            cv2.putText(frame, "Velocidad: --.- mm/s", (35, 212), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (120, 130, 140), 1)

        cv2.putText(frame, "[ESPACIO]: Inicio  |  [F]: Fin  |  [R]: Reset  |  [Q]: Salir", (35, 252),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.41, (160, 175, 190), 1)

        cv2.imshow("ArcSim_VR - Seguimiento en Mesa de Soldadura", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == ord('Q') or key == 27:
            break
        elif key == ord(' ') or key == ord('c') or key == ord('C'):
            if smoothed_tool_mm is not None:
                calib_start_pt = smoothed_tool_mm.copy()
                calib_end_pt = None # resetear fin para forzar paso 2
                last_sent_pos = None
                print("\n>>> [PASO 1 OK] Inicio (0,0) calibrado en la punta actual.")
                print(">>> PASO 2: Lleva la punta al FINAL de tu linea y presiona [F].")
        elif key == ord('f') or key == ord('F'):
            if smoothed_tool_mm is not None and calib_start_pt is not None:
                calib_end_pt = smoothed_tool_mm.copy()
                last_sent_pos = None
                save_calibration(calib_start_pt, calib_end_pt, seam_len_target_mm)
            elif calib_start_pt is None:
                print("\n>>> [AVISO] Primero apoya la punta en el INICIO y presiona [ESPACIO] antes de presionar [F].")
        elif key == ord('r') or key == ord('R'):
            calib_start_pt = None
            calib_end_pt = None
            last_sent_pos = None
            if os.path.exists(CALIB_FILE):
                try: os.remove(CALIB_FILE)
                except: pass
            print("\n>>> [RESET] Calibracion reiniciada. Apoya la punta en INICIO y presiona [ESPACIO].")

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
