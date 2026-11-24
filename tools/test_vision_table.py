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
import threading
from collections import deque
import numpy as np
import cv2

try:
    import serial
    import serial.tools.list_ports
    HAS_PYSERIAL = True
except ImportError:
    HAS_PYSERIAL = False

# ==============================================================================
# GESTOR HÍBRIDO DE IMU (UDP 4244 O SERIAL DIRECTO SI EL PUENTE NO ESTÁ ACTIVO)
# ==============================================================================
imu_lock = threading.Lock()
imu_state = {
    "pitch": 0.0,
    "roll": 0.0,
    "yaw": 0.0,
    "has_imu": False,
    "source": "",
    "last_time": 0.0
}
ser_direct_conn = None
stop_serial_thread = threading.Event()

ESP32_VIDS = {0x10C4, 0x1A86, 0x0403, 0x303A}  # CP210x, CH340, FTDI, Espressif

def find_esp32_port():
    if not HAS_PYSERIAL:
        return None
    try:
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            return None
        # 1. Buscar por VID conocido
        for p in ports:
            if p.vid in ESP32_VIDS:
                return p.device
        # 2. Buscar por descripción con palabras clave USB / Serial
        for p in ports:
            desc = (p.description or "").lower()
            if any(k in desc for k in ["usb", "ch340", "cp210", "uart", "serial", "esp32"]):
                return p.device
        # 3. Candidato que no sea puerto COM1/COM2 de placa madre
        usb_candidates = [p.device for p in ports if p.device.upper() not in ["COM1", "COM2"]]
        if usb_candidates:
            return usb_candidates[0]
        return ports[0].device
    except Exception:
        return None

def serial_fallback_worker():
    global ser_direct_conn
    last_scan = 0.0
    while not stop_serial_thread.is_set():
        now = time.time()
        # Si recibimos datos frescos por UDP (del serial_bridge), liberamos el COM
        with imu_lock:
            recent_udp = (imu_state["source"].startswith("UDP") and (now - imu_state["last_time"] < 1.5))

        if recent_udp:
            if ser_direct_conn is not None:
                try:
                    ser_direct_conn.close()
                except Exception:
                    pass
                ser_direct_conn = None
            time.sleep(0.4)
            continue

        # Si no hay UDP activo y no tenemos COM abierto, intentar conectar directo al ESP32
        if ser_direct_conn is None:
            if now - last_scan > 2.0:
                last_scan = now
                p = find_esp32_port()
                if p:
                    try:
                        s = serial.Serial(p, 115200, timeout=0.05)
                        ser_direct_conn = s
                        print(f"\n>>> [IMU DIRECTO] Conectado a {p} (Lectura autónoma sin puente)")
                    except Exception:
                        ser_direct_conn = None
            if ser_direct_conn is None:
                time.sleep(0.3)
                continue

        # Lectura continua del puerto serial si está abierto
        try:
            line = ser_direct_conn.readline()
            if line:
                line = line.strip()
                if line.startswith(b"{") and line.endswith(b"}"):
                    d = json.loads(line.decode("utf-8", "ignore"))
                    if "p" in d and "r" in d:
                        with imu_lock:
                            imu_state["pitch"] = float(d["p"])
                            imu_state["roll"] = float(d["r"])
                            imu_state["yaw"] = float(d.get("y", 0.0))
                            imu_state["has_imu"] = True
                            imu_state["source"] = f"USB Directo ({ser_direct_conn.port})"
                            imu_state["last_time"] = time.time()
        except (serial.SerialException, OSError):
            try:
                ser_direct_conn.close()
            except Exception:
                pass
            ser_direct_conn = None
            time.sleep(1.0)
        except Exception:
            pass

    if ser_direct_conn is not None:
        try:
            ser_direct_conn.close()
        except Exception:
            pass
        ser_direct_conn = None

def send_esp32_command(cmd_str, udp_sock, cmd_addr):
    # 1. Enviar siempre por UDP (por si corre serial_bridge)
    try:
        udp_sock.sendto(cmd_str.encode("utf-8"), cmd_addr)
    except Exception:
        pass
    # 2. Si tenemos el puerto serie abierto directamente, escribir en el bus físico
    if ser_direct_conn is not None:
        try:
            ser_direct_conn.write(cmd_str.encode("utf-8"))
            ser_direct_conn.flush()
        except Exception:
            pass

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

def load_lever_arm():
    cfg_candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "tool_config.json"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "simulacion_godot", "trabajo-final-rv", "tool_config.json")
    ]
    for cp in cfg_candidates:
        if os.path.exists(cp):
            try:
                with open(cp, "r") as f:
                    cfg = json.load(f)
                    if "tool_tip_lever_mm" in cfg:
                        return float(cfg["tool_tip_lever_mm"])
            except Exception:
                pass
    return 115.0

def load_calibration():
    if os.path.exists(CALIB_FILE):
        try:
            with open(CALIB_FILE, "r") as f:
                data = json.load(f)
                start_pt = np.array(data["start_pt"], dtype=np.float32)
                end_pt = np.array(data["end_pt"], dtype=np.float32)
                target_len = float(data.get("target_len_mm", DEFAULT_SEAM_LENGTH_MM))
                ref_pitch = float(data.get("ref_pitch", 0.0))
                ref_roll = float(data.get("ref_roll", 0.0))
                lever_mm = float(data.get("tip_lever_mm", 0.0))
                meas_dist = float(np.linalg.norm(end_pt - start_pt))
                scale_fac = target_len / meas_dist if meas_dist > 1.0 else 1.0
                print(f"\n>>> [MEMORIA] Calibracion cargada de mesa_calibration.json:")
                print(f"    Medida real carton: {meas_dist:.1f} mm -> Sim Godot: {target_len:.0f} mm (Escala: {scale_fac:.2f}x)")
                return start_pt, end_pt, target_len, ref_pitch, ref_roll, lever_mm
        except Exception as e:
            print(f">>> [MEMORIA] Error al leer calibracion: {e}")
    return None, None, DEFAULT_SEAM_LENGTH_MM, 0.0, 0.0, 0.0

def save_calibration(start_pt, end_pt, target_len, ref_pitch=0.0, ref_roll=0.0, tip_lever_mm=115.0):
    try:
        meas_dist = float(np.linalg.norm(end_pt - start_pt))
        scale_fac = float(target_len / meas_dist) if meas_dist > 1.0 else 1.0
        data = {
            "start_pt": [float(start_pt[0]), float(start_pt[1])],
            "end_pt": [float(end_pt[0]), float(end_pt[1])],
            "measured_len_mm": round(meas_dist, 2),
            "target_len_mm": float(target_len),
            "scale_factor": round(scale_fac, 4),
            "ref_pitch": round(float(ref_pitch), 2),
            "ref_roll": round(float(ref_roll), 2),
            "tip_lever_mm": round(float(tip_lever_mm), 1)
        }
        with open(CALIB_FILE, "w") as f:
            json.dump(data, f, indent=2)
            
        # Actualizar también tool_config.json si existe
        cfg_candidates = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "tool_config.json"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "simulacion_godot", "trabajo-final-rv", "tool_config.json")
        ]
        for cp in cfg_candidates:
            if os.path.exists(cp):
                try:
                    with open(cp, "r") as f:
                        cfg = json.load(f)
                    cfg["tool_tip_lever_mm"] = round(float(tip_lever_mm), 1)
                    with open(cp, "w") as f:
                        json.dump(cfg, f, indent=2)
                except Exception:
                    pass
                    
        print(f"\n============================================================")
        print(f"  ¡CALIBRACION 1:1 GUARDADA EXITOSAMENTE EN DISCO!")
        print(f"============================================================")
        print(f"  - Longitud en tu cartón físico: {meas_dist:.1f} mm")
        print(f"  - Longitud en el simulador:     {target_len:.0f} mm")
        print(f"  - Factor de escala aplicado:    {scale_fac:.2f}x")
        print(f"  - Brazo palanca cinemático L:   {tip_lever_mm:.0f} mm")
        print(f"  - Inclinación de referencia:    Pitch {ref_pitch:.1f}°, Roll {ref_roll:.1f}°")
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
    print("  [ESPACIO]       : Calibrar INICIO (0,0)")
    print("  [F]             : Calibrar FINAL del cordón (Auto-escala 150mm)")
    print("  [T]             : TARA YAW (Alinear rumbo longitudinal del cordón a 0°)")
    print("  [C]             : CALIBRAR GYRO MPU-6050 (¡Herramienta INMÓVIL sobre la mesa!)")
    print("  [ [ / ] ]       : Ajustar longitud del brazo de palanca L (±5mm)")
    print("  [R]             : Resetear calibración")
    print("  [Q] o [ESC]     : Salir")
    print("============================================================\n")

    # Variables de homografía y posición
    smoothed_H = None
    smoothed_tool_mm = None
    
    # Cargar calibración persistente y brazo cinemático si existen previamente
    calib_start_pt, calib_end_pt, seam_len_target_mm, calib_ref_pitch, calib_ref_roll, saved_lever_mm = load_calibration()
    tip_lever_mm = saved_lever_mm if saved_lever_mm > 10.0 else load_lever_arm()
    calib_scale_factor = 1.0

    # Socket UDP para recibir telemetría del IMU (puerto 4244 desde serial_bridge)
    imu_rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    imu_rx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        imu_rx_sock.bind(("127.0.0.1", 4244))
        imu_rx_sock.setblocking(False)
    except Exception:
        pass

    latest_pitch = 0.0
    latest_roll = 0.0
    latest_yaw = 0.0
    has_imu = False

    # Socket UDP para enviar seguimiento 1:1 a Godot y comandos al ESP32
    GODOT_UDP_ADDR = ("127.0.0.1", 4242)
    COMMAND_UDP_ADDR = ("127.0.0.1", 4243)
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    last_sent_pos = None
    last_udp_time = 0.0

    cmd_status_msg = ""
    cmd_status_timer = 0.0
    cmd_status_color = (0, 255, 0)
    imu_source_str = "Buscando..."

    # Iniciar hilo de lectura serial autónoma en segundo plano
    serial_th = threading.Thread(target=serial_fallback_worker, daemon=True)
    serial_th.start()

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
        # LECTURA DE TELEMETRÍA IMU (PUENTE UDP 4244 O SERIAL DIRECTO)
        # ----------------------------------------------------------------------
        try:
            while True:
                data, _ = imu_rx_sock.recvfrom(1024)
                d = json.loads(data.decode("utf-8", "ignore"))
                if "p" in d and "r" in d:
                    with imu_lock:
                        imu_state["pitch"] = float(d["p"])
                        imu_state["roll"] = float(d["r"])
                        imu_state["yaw"] = float(d.get("y", 0.0))
                        imu_state["has_imu"] = True
                        imu_state["source"] = "UDP 4244 (Puente)"
                        imu_state["last_time"] = time.time()
        except Exception:
            pass

        with imu_lock:
            latest_pitch = imu_state["pitch"]
            latest_roll = imu_state["roll"]
            latest_yaw = imu_state["yaw"]
            has_imu = imu_state["has_imu"] and (time.time() - imu_state["last_time"] < 3.0)
            imu_source_str = imu_state["source"]

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

        raw_pos_x = pos_x
        raw_pos_y = pos_y
        lever_dx = 0.0
        lever_dy = 0.0

        # COMPENSACIÓN CINEMÁTICA 3D DE LA PUNTA:
        # Desacopla la inclinación: al cambiar pitch o roll, la punta de apoyo permanece inmóvil
        if has_imu and calib_start_pt is not None:
            d_pitch_rad = math.radians(latest_pitch - calib_ref_pitch)
            d_roll_rad = math.radians(latest_roll - calib_ref_roll)
            lever_dx = tip_lever_mm * math.sin(d_pitch_rad)
            lever_dy = tip_lever_mm * math.sin(d_roll_rad)
            pos_x = raw_pos_x - lever_dx
            pos_y = raw_pos_y - lever_dy
            tip_pos_mm = np.array([pos_x, pos_y], dtype=np.float32)

        # Proyección inversa de la punta corregida a píxeles de la cámara en vivo
        tip_cam_px = None
        if smoothed_H is not None and smoothed_tool_mm is not None:
            try:
                if calib_start_pt is not None and calib_end_pt is not None:
                    seam_vec = calib_end_pt - calib_start_pt
                    seam_len = float(np.linalg.norm(seam_vec))
                    if seam_len > 10.0:
                        u_dir = seam_vec / seam_len
                        v_dir = np.array([-u_dir[1], u_dir[0]], dtype=np.float32)
                        ratio = seam_len / seam_len_target_mm
                        tip_table_mm = calib_start_pt + (pos_x * ratio) * u_dir + (pos_y * ratio) * v_dir
                    else:
                        tip_table_mm = smoothed_tool_mm - np.array([lever_dx, lever_dy], dtype=np.float32)
                else:
                    tip_table_mm = smoothed_tool_mm - np.array([lever_dx, lever_dy], dtype=np.float32)

                inv_H = np.linalg.inv(smoothed_H)
                tip_h = inv_H @ np.array([tip_table_mm[0], tip_table_mm[1], 1.0], dtype=np.float32)
                if abs(tip_h[2]) > 1e-6:
                    tip_cam_px = (int(round(tip_h[0] / tip_h[2])), int(round(tip_h[1] / tip_h[2])))
            except Exception:
                tip_cam_px = None

        # Dibujar visualización sobre la imagen en vivo de la cámara
        if pos_tool_px is not None:
            m_cx, m_cy = int(pos_tool_px[0]), int(pos_tool_px[1])
            cv2.circle(frame, (m_cx, m_cy), 6, (0, 165, 255), -1)
            cv2.putText(frame, "Marcador (Bruto)", (m_cx - 50, m_cy - 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 165, 255), 2)

        if tip_cam_px is not None:
            t_cx, t_cy = tip_cam_px
            if 0 <= t_cx < frame.shape[1] and 0 <= t_cy < frame.shape[0]:
                if pos_tool_px is not None:
                    cv2.line(frame, (int(pos_tool_px[0]), int(pos_tool_px[1])), (t_cx, t_cy), (0, 220, 255), 2)
                # Cruceta y aro verde en la punta física calculada
                cv2.circle(frame, (t_cx, t_cy), 6, (0, 255, 0), -1)
                cv2.circle(frame, (t_cx, t_cy), 13, (0, 255, 0), 2)
                cv2.line(frame, (t_cx - 15, t_cy), (t_cx + 15, t_cy), (0, 255, 0), 2)
                cv2.line(frame, (t_cx, t_cy - 15), (t_cx, t_cy + 15), (0, 255, 0), 2)
                cv2.putText(frame, "PUNTA CORREGIDA", (t_cx + 16, t_cy + 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.46, (0, 255, 0), 2)

        # ----------------------------------------------------------------------
        # TRANSMISIÓN UDP A GODOT (dx, dy, x, y absoluto)
        # ----------------------------------------------------------------------
        if tip_pos_mm is not None and calib_start_pt is not None:
            if last_sent_pos is None:
                last_sent_pos = np.array([pos_x, pos_y], dtype=np.float32)
            dx = pos_x - last_sent_pos[0]
            dy = pos_y - last_sent_pos[1]
            now_t = time.time()

            # Transmitir si hay movimiento >= 0.15 mm O de forma periódica a 25 Hz (cada 40 ms)
            if abs(dx) >= 0.15 or abs(dy) >= 0.15 or (now_t - last_udp_time >= 0.04):
                pkt = {
                    "dx": round(float(dx), 2),
                    "dy": round(float(dy), 2),
                    "x": round(float(pos_x), 2),
                    "y": round(float(pos_y), 2)
                }
                try:
                    udp_sock.sendto(json.dumps(pkt).encode("ascii"), GODOT_UDP_ADDR)
                except Exception:
                    pass
                last_sent_pos = np.array([pos_x, pos_y], dtype=np.float32)
                last_udp_time = now_t
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
        mm_w, mm_h = 360, 180
        mm_x0, mm_y0 = frame.shape[1] - mm_w - 20, 20
        cv2.rectangle(frame, (mm_x0, mm_y0), (mm_x0 + mm_w, mm_y0 + mm_h), (25, 30, 38), -1)
        cv2.rectangle(frame, (mm_x0, mm_y0), (mm_x0 + mm_w, mm_y0 + mm_h), (80, 95, 120), 1)

        cv2.putText(frame, "MINIMAPA DEL CORDÓN (150 mm)", (mm_x0 + 15, mm_y0 + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 220, 240), 1)

        map_origin_x = mm_x0 + 40
        map_origin_y = mm_y0 + mm_h // 2 - 8
        map_scale = 1.5

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
            # 1. Posición del marcador bruto en el minimapa (Naranja)
            raw_tx = int(map_origin_x + raw_pos_x * map_scale)
            raw_ty = int(map_origin_y - raw_pos_y * map_scale)
            raw_tx = np.clip(raw_tx, mm_x0 + 8, mm_x0 + mm_w - 8)
            raw_ty = np.clip(raw_ty, mm_y0 + 28, mm_y0 + mm_h - 28)

            # 2. Posición de la punta corregida en el minimapa (Verde)
            comp_tx = int(map_origin_x + pos_x * map_scale)
            comp_ty = int(map_origin_y - pos_y * map_scale)
            comp_tx = np.clip(comp_tx, mm_x0 + 8, mm_x0 + mm_w - 8)
            comp_ty = np.clip(comp_ty, mm_y0 + 28, mm_y0 + mm_h - 28)

            # Línea conectora entre ambos en el minimapa
            cv2.line(frame, (raw_tx, raw_ty), (comp_tx, comp_ty), (0, 220, 255), 1)

            # Dibujar Marcador Bruto
            cv2.circle(frame, (raw_tx, raw_ty), 6, (0, 165, 255), -1)
            cv2.circle(frame, (raw_tx, raw_ty), 9, (0, 165, 255), 1)

            # Dibujar Punta Corregida
            cv2.circle(frame, (comp_tx, comp_ty), 7, (0, 255, 120), -1)
            cv2.circle(frame, (comp_tx, comp_ty), 11, (0, 255, 120), 2)

        # Leyenda de los dos puntos
        cv2.circle(frame, (mm_x0 + 20, mm_y0 + mm_h - 14), 5, (0, 165, 255), -1)
        cv2.putText(frame, "Marcador bruto", (mm_x0 + 30, mm_y0 + mm_h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)
        cv2.circle(frame, (mm_x0 + 175, mm_y0 + mm_h - 14), 5, (0, 255, 120), -1)
        cv2.putText(frame, "Punta corregida", (mm_x0 + 185, mm_y0 + mm_h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)

        # ----------------------------------------------------------------------
        # HUD EN PANTALLA (IZQUIERDA)
        # ----------------------------------------------------------------------
        overlay = frame.copy()
        cv2.rectangle(overlay, (20, 20), (510, 310), (15, 18, 24), -1)
        cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
        cv2.rectangle(frame, (20, 20), (510, 310), (60, 70, 90), 1)

        cv2.putText(frame, "ArcSim VR - Seguimiento en Mesa A4", (35, 48),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.60, (255, 255, 255), 2)
        cv2.putText(frame, f"FPS: {current_fps:.0f}", (420, 48),
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

            # Punta compensada 3D
            cv2.putText(frame, f"Punta Compensada: {pos_x:+5.1f} / {seam_len_target_mm:.0f} mm", (35, 150),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 255, 120), 2)
            cv2.putText(frame, f"Desvío Lateral:   {pos_y:+5.1f} mm  [{status_cordon}]", (35, 172),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, color_cordon, 1)

            # Marcador bruto vs compensación
            if has_imu:
                cv2.putText(frame, f"Marcador Bruto:   {raw_pos_x:+5.1f} mm | Desv: {raw_pos_y:+5.1f} mm", (35, 194),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.44, (255, 255, 0), 1)
                cv2.putText(frame, f"IMU [{imu_source_str}]: Pitch {latest_pitch:+4.1f}° | Roll {latest_roll:+4.1f}° (Comp dX:{-lever_dx:+4.1f}mm)", (35, 216),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 220, 255), 1)
            else:
                cv2.putText(frame, "IMU: Buscando señal... (Conecta el ESP32 por USB)", (35, 216),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.44, (140, 150, 160), 1)

            cv2.putText(frame, f"Brazo Palanca L:  {tip_lever_mm:.0f} mm  [Teclas [ / ] para regular]", (35, 238),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.44, (200, 210, 220), 1)

            if speed_filtered < 0.2:
                v_col, v_txt = (180, 180, 180), "REPOSO"
            elif speed_filtered < 1.8:
                v_col, v_txt = (0, 180, 255), "LENTA"
            elif speed_filtered <= 4.5:
                v_col, v_txt = (0, 255, 0), "ÓPTIMA SMAW"
            else:
                v_col, v_txt = (0, 0, 255), "MUY RÁPIDA"

            cv2.putText(frame, f"Velocidad: {speed_filtered:4.1f} mm/s  [{v_txt}]", (35, 262),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.52, v_col, 2)
        else:
            cv2.putText(frame, "Punta Compensada: --.- mm", (35, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (120, 130, 140), 1)
            cv2.putText(frame, "Desvío Lateral:   --.- mm", (35, 172), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (120, 130, 140), 1)
            if has_imu:
                cv2.putText(frame, f"IMU [{imu_source_str}]: Pitch {latest_pitch:+4.1f}° | Roll {latest_roll:+4.1f}°", (35, 216),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 220, 255), 1)
            else:
                cv2.putText(frame, "IMU: Buscando señal... (Conecta el ESP32 por USB)", (35, 216),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.44, (140, 150, 160), 1)
            cv2.putText(frame, f"Brazo Palanca L:  {tip_lever_mm:.0f} mm  [Teclas [ / ] para regular]", (35, 238), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (200, 210, 220), 1)
            cv2.putText(frame, "Velocidad: --.- mm/s", (35, 262), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (120, 130, 140), 1)

        cv2.putText(frame, "[ESPACIO]: Inicio  |  [F]: Fin  |  [T]: Tara Yaw  |  [C]: Calib Gyro  |  [ [ / ] ]: L  |  [R]: Reset", (35, 292),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.41, (160, 175, 190), 1)

        # Mensaje de retroalimentación de comandos
        if time.time() < cmd_status_timer and cmd_status_msg:
            cv2.putText(frame, f">>> {cmd_status_msg}", (35, 316),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, cmd_status_color, 2)

        cv2.imshow("ArcSim_VR - Seguimiento en Mesa de Soldadura", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == ord('Q') or key == 27:
            break
        elif key == ord('t') or key == ord('T'):
            send_esp32_command("RESET_YAW\n", udp_sock, COMMAND_UDP_ADDR)
            cmd_status_msg = "TARA YAW ENVIADA (Yaw = 0.0° - Rumbo longitudinal alineado)"
            cmd_status_timer = time.time() + 2.5
            cmd_status_color = (0, 255, 255)
            print("\n>>> [TARA] Comando RESET_YAW enviado al ESP32 (Yaw = 0°).")
        elif key == ord('c') or key == ord('C'):
            send_esp32_command("CALIBRATE\n", udp_sock, COMMAND_UDP_ADDR)
            cmd_status_msg = "CALIBRANDO GYRO (¡MANTEN LA HERRAMIENTA QUIETA SOBRE LA MESA!)..."
            cmd_status_timer = time.time() + 3.0
            cmd_status_color = (0, 180, 255)
            print("\n>>> [CALIBRACION GYRO] Comando CALIBRATE enviado al ESP32.")
            print("    ¡MANTEN LA HERRAMIENTA TOTALMENTE INMÓVIL SOBRE LA MESA DURANTE 2 SEGUNDOS!")
        elif key == ord(']') or key == ord('+'):
            tip_lever_mm = min(300.0, tip_lever_mm + 5.0)
            cmd_status_msg = f"Brazo cinemático L: {tip_lever_mm:.0f} mm"
            cmd_status_timer = time.time() + 1.5
            cmd_status_color = (0, 255, 120)
            print(f">>> Brazo cinemático L aumentado a: {tip_lever_mm:.0f} mm")
        elif key == ord('[') or key == ord('-'):
            tip_lever_mm = max(20.0, tip_lever_mm - 5.0)
            cmd_status_msg = f"Brazo cinemático L: {tip_lever_mm:.0f} mm"
            cmd_status_timer = time.time() + 1.5
            cmd_status_color = (0, 255, 120)
            print(f">>> Brazo cinemático L reducido a: {tip_lever_mm:.0f} mm")
        elif key == ord(' '):
            if smoothed_tool_mm is not None:
                calib_start_pt = smoothed_tool_mm.copy()
                calib_ref_pitch = latest_pitch
                calib_ref_roll = latest_roll
                calib_end_pt = None # resetear fin para forzar paso 2
                last_sent_pos = None
                cmd_status_msg = "PASO 1 OK: Inicio (0,0) calibrado. Lleva la punta a FIN y presiona [F]"
                cmd_status_timer = time.time() + 3.0
                cmd_status_color = (0, 255, 0)
                print("\n>>> [PASO 1 OK] Inicio (0,0) calibrado en la punta actual.")
                print(f"    Orientación de referencia: Pitch {calib_ref_pitch:.1f}°, Roll {calib_ref_roll:.1f}°")
                print(">>> PASO 2: Lleva la punta al FINAL de tu linea y presiona [F].")
        elif key == ord('f') or key == ord('F'):
            if smoothed_tool_mm is not None and calib_start_pt is not None:
                calib_end_pt = smoothed_tool_mm.copy()
                last_sent_pos = None
                save_calibration(calib_start_pt, calib_end_pt, seam_len_target_mm, calib_ref_pitch, calib_ref_roll, tip_lever_mm)
                cmd_status_msg = "¡CALIBRACIÓN GUARDADA CON ÉXITO!"
                cmd_status_timer = time.time() + 3.0
                cmd_status_color = (0, 255, 0)
            elif calib_start_pt is None:
                cmd_status_msg = "Primero apoya la punta en INICIO y presiona [ESPACIO]"
                cmd_status_timer = time.time() + 2.5
                cmd_status_color = (0, 0, 255)
                print("\n>>> [AVISO] Primero apoya la punta en el INICIO y presiona [ESPACIO] antes de presionar [F].")
        elif key == ord('r') or key == ord('R'):
            calib_start_pt = None
            calib_end_pt = None
            last_sent_pos = None
            if os.path.exists(CALIB_FILE):
                try: os.remove(CALIB_FILE)
                except: pass
            cmd_status_msg = "Calibración reiniciada. Apoya la punta en INICIO y presiona [ESPACIO]"
            cmd_status_timer = time.time() + 2.5
            cmd_status_color = (0, 180, 255)
            print("\n>>> [RESET] Calibracion reiniciada. Apoya la punta en INICIO y presiona [ESPACIO].")

    stop_serial_thread.set()
    serial_th.join(timeout=1.0)
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
