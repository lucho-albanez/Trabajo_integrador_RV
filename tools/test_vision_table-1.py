#!/usr/bin/env python3
"""
ArcSim_VR - Seguimiento de la punta del electrodo sobre la mesa (v4: pose 6D + pivote)
=====================================================================================
La cámara ve el ArUco del soporte de la herramienta (ID 0), no la punta. En vez de suponer
dónde está la punta (brazo L + inclinación del IMU), se usa el método estándar de seguimiento
de instrumentos:

  1. Pose de la mesa con los 4 marcadores de la plantilla A4 (posiciones conocidas).
  2. Pose 6D del ArUco de la herramienta (rotación + traslación) con sus 4 esquinas.
  3. La punta es un punto FIJO en el sistema del marcador: punta = R @ p + t. Si p es correcto,
     inclinar la herramienta no mueve la punta, por construcción.
  4. p se mide con la CALIBRACIÓN DE PIVOTE [P]: punta quieta sobre la hoja, se inclina la
     herramienta en todas direcciones y se resuelve R_i p + t_i = q por mínimos cuadrados.

El cordón por defecto es el dibujado en la plantilla (0,0)->(150,0): no hace falta calibrarlo.
El IMU no es necesario para la posición; si está conectado durante el pivote, se calibra solo
una fusión que usa su inclinación para reducir el temblor (ver tool_tracking.py).

Controles:
  [C] Calibrar gyro del MPU-6050 (herramienta quieta)   [T] Tara de yaw
  [P] Pivote (inicio / fin)                              [ESPACIO]/[F] Cordón propio (opcional)
  [R] Volver al cordón de la plantilla                   [Q]/[ESC] Salir

Configuración (tool_config.json): "tool_marker_mm" = lado del cuadrado NEGRO del ArUco de la
herramienta (por defecto 36). Si está mal, el pivote lo corrige.
Opcional: python tools/calibrar_camara.py -> camera_intrinsics.json (focal + distorsión).
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tool_tracking import (TABLE_MARKER_CENTERS_MM, TEMPLATE_SEAM_START_MM, TEMPLATE_SEAM_END_MM,
                           TOOL_MARKER_ID, DEFAULT_TOOL_MARKER_MM, table_marker_corners_3d,
                           camera_matrix, estimate_focal, solve_table_pose, marker_candidates,
                           TablePose, rotation_spread_deg, pivot_calibrate_raw, ImuHistory,
                           TipTracker)

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
imu_queue = deque(maxlen=4000)   # (t_recepcion, pitch, roll): todas las lecturas, para la fusión
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
                            imu_queue.append((imu_state["last_time"], imu_state["pitch"], imu_state["roll"]))
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


# ==============================================================================
# ARCHIVOS Y CONFIGURACIÓN
# ==============================================================================
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
CALIB_FILE = os.path.join(TOOLS_DIR, "mesa_calibration.json")
INTRINSICS_FILE = os.path.join(TOOLS_DIR, "camera_intrinsics.json")
CFG_CANDIDATES = [
    os.path.join(TOOLS_DIR, "tool_config.json"),
    os.path.join(TOOLS_DIR, "..", "simulacion_godot", "trabajo-final-rv", "tool_config.json"),
]
CALIB_VERSION = 4   # v4: seguimiento 6D + pivote (offset de la punta en el sistema del marcador)
DEFAULT_SEAM_LENGTH_MM = 150.0
GODOT_UDP_ADDR = ("127.0.0.1", 4242)
COMMAND_UDP_ADDR = ("127.0.0.1", 4243)


def load_tool_config():
    for cp in CFG_CANDIDATES:
        if os.path.exists(cp):
            try:
                with open(cp, "r") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


def update_tool_config(values):
    for cp in CFG_CANDIDATES:
        if os.path.exists(cp):
            try:
                with open(cp, "r") as f:
                    cfg = json.load(f)
                cfg.update(values)
                with open(cp, "w") as f:
                    json.dump(cfg, f, indent=2)
            except Exception:
                pass


def load_intrinsics(width, height):
    """camera_intrinsics.json (de calibrar_camara.py). Devuelve (K, dist) o (None, None)."""
    if not os.path.exists(INTRINSICS_FILE):
        return None, None
    try:
        with open(INTRINSICS_FILE, "r") as f:
            d = json.load(f)
        K = np.array(d["K"], np.float64).reshape(3, 3)
        dist = np.array(d["dist"], np.float64).ravel()
        w0, h0 = int(d["width"]), int(d["height"])
        if (w0, h0) != (width, height):
            if abs(w0 / h0 - width / height) > 0.01:
                print(f">>> [CAMARA] camera_intrinsics.json es de {w0}x{h0} y la camara da {width}x{height}: se ignora.")
                return None, None
            sc = width / w0
            K = K.copy()
            K[:2] *= sc
        return K, dist
    except Exception as e:
        print(f">>> [CAMARA] Error leyendo camera_intrinsics.json: {e}")
        return None, None


def default_calibration():
    return {"p_tip": None, "marker_mm_eff": None, "pivot_rms_mm": None, "focal_px": None,
            "image_size": None, "imu": None,
            "seam_start": np.array(TEMPLATE_SEAM_START_MM, np.float64),
            "seam_end": np.array(TEMPLATE_SEAM_END_MM, np.float64),
            "seam_custom": False, "target_len": DEFAULT_SEAM_LENGTH_MM}


def load_calibration():
    cal = default_calibration()
    if not os.path.exists(CALIB_FILE):
        return cal
    try:
        with open(CALIB_FILE, "r") as f:
            d = json.load(f)
        ver = int(d.get("version", 1))
        if ver < CALIB_VERSION:
            bak = CALIB_FILE + f".v{ver}.bak"
            try:
                os.replace(CALIB_FILE, bak)
            except Exception:
                pass
            print(f"\n>>> [MEMORIA] mesa_calibration.json es de un metodo anterior (v{ver}). Se guardo como")
            print(f"    {os.path.basename(bak)} y se empieza de cero: haz el pivote con [P].")
            return cal
        cal["target_len"] = float(d.get("target_len_mm", DEFAULT_SEAM_LENGTH_MM))
        if d.get("tool_tip_offset_mm") is not None:
            cal["p_tip"] = np.array(d["tool_tip_offset_mm"], np.float64)
            cal["marker_mm_eff"] = float(d["tool_marker_mm_eff"])
            cal["pivot_rms_mm"] = d.get("pivot_rms_mm")
        if d.get("camera_focal_px") is not None:
            cal["focal_px"] = float(d["camera_focal_px"])
            cal["image_size"] = tuple(d.get("image_size", (0, 0)))
        if d.get("imu_fusion"):
            fu = d["imu_fusion"]
            cal["imu"] = {"enabled": True, "Q": np.array(fu["Q"], np.float64).reshape(3, 3),
                          "delay_s": float(fu["delay_s"]), "p_tip": np.array(fu["p_tip"], np.float64),
                          "resid_deg": float(fu.get("resid_deg", 0.0))}
        if d.get("seam_custom") and d.get("start_pt") is not None and d.get("end_pt") is not None:
            cal["seam_start"] = np.array(d["start_pt"], np.float64)
            cal["seam_end"] = np.array(d["end_pt"], np.float64)
            cal["seam_custom"] = True
    except Exception as e:
        print(f">>> [MEMORIA] Error al leer calibracion: {e}")
    return cal


def save_calibration(cal):
    try:
        meas = float(np.linalg.norm(cal["seam_end"] - cal["seam_start"]))
        d = {
            "version": CALIB_VERSION,
            "metodo": "pose 6D del ArUco + calibracion de pivote",
            "target_len_mm": float(cal["target_len"]),
            "seam_custom": bool(cal["seam_custom"]),
            "start_pt": [float(v) for v in cal["seam_start"]],
            "end_pt": [float(v) for v in cal["seam_end"]],
            "measured_len_mm": round(meas, 2),
            "scale_factor": round(float(cal["target_len"] / meas) if meas > 1 else 1.0, 4),
            "tool_tip_offset_mm": None if cal["p_tip"] is None else [round(float(v), 3) for v in cal["p_tip"]],
            "tool_marker_mm_eff": None if cal["marker_mm_eff"] is None else round(float(cal["marker_mm_eff"]), 3),
            "pivot_rms_mm": None if cal["pivot_rms_mm"] is None else round(float(cal["pivot_rms_mm"]), 3),
            "camera_focal_px": None if cal["focal_px"] is None else round(float(cal["focal_px"]), 1),
            "image_size": None if cal["image_size"] is None else list(cal["image_size"]),
            "imu_fusion": None,
        }
        fu = cal.get("imu")
        if fu and fu.get("enabled"):
            d["imu_fusion"] = {"Q": [[float(v) for v in row] for row in fu["Q"]],
                               "delay_s": round(float(fu["delay_s"]), 3),
                               "p_tip": [round(float(v), 3) for v in fu["p_tip"]],
                               "resid_deg": round(float(fu["resid_deg"]), 2)}
        with open(CALIB_FILE, "w") as f:
            json.dump(d, f, indent=2)
        if cal["p_tip"] is not None:
            # Informativo para Godot (distancia punta-marcador)
            update_tool_config({"tool_tip_lever_mm": round(float(np.linalg.norm(cal["p_tip"])), 1)})
    except Exception as e:
        print(f">>> [MEMORIA] Error guardando calibracion: {e}")


def seam_coords(tip_xy, cal):
    """Punto de la mesa [mm] -> (avance, desvío) en mm del simulador (cordón = target_len)."""
    s0, s1 = cal["seam_start"], cal["seam_end"]
    v = s1 - s0
    L = float(np.linalg.norm(v))
    if L < 10.0:
        return float(tip_xy[0] - s0[0]), float(tip_xy[1] - s0[1])
    u = v / L
    n = np.array([-u[1], u[0]])
    d = np.asarray(tip_xy, np.float64) - s0
    k = cal["target_len"] / L
    return float(d @ u) * k, float(d @ n) * k


def put(frame, text, org, scale=0.46, color=(220, 225, 235), thick=1):
    cv2.putText(frame, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


# ==============================================================================
# PROGRAMA PRINCIPAL
# ==============================================================================
def main():
    cap = find_camera()
    if cap is None:
        print("\n>>> ERROR: No se pudo abrir la camara web.")
        input("Presiona Enter para salir...")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)
    ret, frame = cap.read()
    if not ret or frame is None:
        print("\n>>> ERROR: la camara no entrega imagen.")
        sys.exit(1)
    fh, fw = frame.shape[:2]

    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    detector_params = cv2.aruco.DetectorParameters()
    detector_params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    detector_params.cornerRefinementWinSize = 5
    detector_params.cornerRefinementMaxIterations = 30
    detector_params.cornerRefinementMinAccuracy = 0.05
    detector = cv2.aruco.ArucoDetector(aruco_dict, detector_params)

    cfg = load_tool_config()
    marker_cfg_mm = float(cfg.get("tool_marker_mm", DEFAULT_TOOL_MARKER_MM))
    cal = load_calibration()

    print("\n============================================================")
    print("  ArcSim_VR - Seguimiento en Mesa (v4: pose 6D + pivote)")
    print("============================================================")
    print("  [C] Calibrar gyro (herramienta QUIETA)   [T] Tara yaw")
    print("  [P] PIVOTE: punta apoyada y QUIETA en la hoja, inclinar en")
    print("      avance y lateral 5-10 s, [P] otra vez para calcular")
    print("  [ESPACIO]/[F] Cordon propio (opcional; por defecto el de la plantilla)")
    print("  [R] Volver al cordon de la plantilla     [Q]/[ESC] Salir")
    print("============================================================\n")

    # --- Intrínsecos de la cámara ---------------------------------------------
    K, dist = load_intrinsics(fw, fh)
    if K is not None:
        cam_src = "calibrada (camera_intrinsics.json)"
        K_reliable = True
    elif cal["focal_px"] is not None and cal["image_size"] and tuple(cal["image_size"]) == (fw, fh):
        K, dist = camera_matrix(cal["focal_px"], fw, fh), np.zeros(5)
        cam_src = "guardada del pivote"
        K_reliable = True
    else:
        K, dist = None, np.zeros(5)
        cam_src = "estimando con la plantilla..."
        K_reliable = False
    focal_views_img, focal_views_obj = [], []
    frames_without_focal = 0

    if cal["p_tip"] is not None:
        print(f">>> [MEMORIA] Pivote cargado: punta a {np.linalg.norm(cal['p_tip']):.0f} mm del marcador"
              f" (residuo {cal['pivot_rms_mm'] or 0:.1f} mm)"
              + (", fusion con IMU activa" if cal["imu"] else ""))
    else:
        print(">>> Falta la calibracion de pivote: apoya la punta en la hoja y usa [P].")
    print(f">>> Cordon: {'propio (ESPACIO/F)' if cal['seam_custom'] else 'el de la plantilla (0 a 150 mm)'}")

    def make_tracker():
        if cal["p_tip"] is None:
            return None
        fu = cal["imu"]
        return TipTracker(cal["p_tip"], fu["p_tip"] if fu else None)

    tracker = make_tracker()
    imu_hist = ImuHistory(seconds=60.0)

    # --- Sockets ----------------------------------------------------------------
    imu_rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    imu_rx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        imu_rx_sock.bind(("127.0.0.1", 4244))
        imu_rx_sock.setblocking(False)
    except Exception:
        pass
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    last_sent_pos = None
    last_udp_time = 0.0

    serial_th = threading.Thread(target=serial_fallback_worker, daemon=True)
    serial_th.start()

    # --- Estado ----------------------------------------------------------------
    table_rvec = table_tvec = None
    table_pose = None
    ref_table_img = ref_table_obj = None     # vista de la mesa con más puntos (para el pivote)
    pivot_active = False
    pivot_corners, pivot_times, pivot_Rs = [], [], []
    pivot_spread = (0.0, 0.0)
    cmd_msg, cmd_timer, cmd_color = "", 0.0, (0, 255, 0)
    history = deque(maxlen=30)
    speed_filtered = 0.0
    fps_count, fps_start, current_fps = 0, time.time(), 0.0
    tip3 = None
    pending_seam_start = None

    def status(msg, color=(0, 255, 0), secs=3.0):
        nonlocal cmd_msg, cmd_timer, cmd_color
        cmd_msg, cmd_color, cmd_timer = msg, color, time.time() + secs

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            break
        now = time.time()
        fps_count += 1
        if now - fps_start >= 1.0:
            current_fps = fps_count / (now - fps_start)
            fps_count, fps_start = 0, now

        # ------------------------------------------------------------------
        # DETECCIÓN
        # ------------------------------------------------------------------
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = detector.detectMarkers(gray)
        t_img, t_obj, visible_table_ids = [], [], []
        tool_corners = None
        if ids is not None:
            for i, mid in enumerate(ids.flatten()):
                c = corners[i][0].astype(np.float64)
                if int(mid) in TABLE_MARKER_CENTERS_MM:
                    t_img.append(c)
                    t_obj.append(table_marker_corners_3d(int(mid)))
                    visible_table_ids.append(int(mid))
                    cv2.polylines(frame, [c.astype(np.int32)], True, (0, 255, 0), 2)
                    put(frame, f"ID {mid}", (int(c[:, 0].mean()) - 15, int(c[:, 1].mean()) - 10), 0.45, (0, 255, 0))
                elif int(mid) == TOOL_MARKER_ID:
                    tool_corners = c
                    cv2.polylines(frame, [c.astype(np.int32)], True, (255, 255, 0), 2)
        if t_img:
            t_img = np.vstack(t_img)
            t_obj = np.vstack(t_obj)

        # ------------------------------------------------------------------
        # IMU (solo para la fusión opcional y para mostrar; [C] y [T] no cambian)
        # ------------------------------------------------------------------
        try:
            while True:
                data, _ = imu_rx_sock.recvfrom(1024)
                d = json.loads(data.decode("utf-8", "ignore"))
                if "p" in d and "r" in d:
                    tr = time.time()
                    with imu_lock:
                        imu_state["pitch"] = float(d["p"])
                        imu_state["roll"] = float(d["r"])
                        imu_state["yaw"] = float(d.get("y", 0.0))
                        imu_state["has_imu"] = True
                        imu_state["source"] = "UDP 4244 (Puente)"
                        imu_state["last_time"] = tr
                    imu_queue.append((tr, float(d["p"]), float(d["r"])))
        except Exception:
            pass
        while imu_queue:
            tq, pq, rq = imu_queue.popleft()
            imu_hist.add(tq, pq, rq)
        with imu_lock:
            latest_pitch, latest_roll = imu_state["pitch"], imu_state["roll"]
            has_imu = imu_state["has_imu"] and (time.time() - imu_state["last_time"] < 0.5)
            imu_source_str = imu_state["source"]

        # ------------------------------------------------------------------
        # CÁMARA: focal (si no está calibrada) y pose de la mesa
        # ------------------------------------------------------------------
        if K is None:
            if len(visible_table_ids) >= 3:
                focal_views_img.append(t_img.copy())
                focal_views_obj.append(t_obj.copy())
            frames_without_focal += 1
            if len(focal_views_img) >= 15:
                f_est = estimate_focal(focal_views_img[-15:], focal_views_obj[-15:], fw, fh)
                if f_est is not None:
                    K = camera_matrix(f_est, fw, fh)
                    cam_src = "estimada de la plantilla"
                    K_reliable = True
                    print(f">>> [CAMARA] Focal estimada con la plantilla: {f_est:.0f} px")
                elif len(focal_views_img) >= 45:
                    K = camera_matrix(0.8 * fw, fw, fh)
                    cam_src = "aproximada (se ajusta en el pivote)"
                    K_reliable = False
                    print(">>> [CAMARA] No se pudo estimar la focal (plantilla muy de frente?). Se usa una")
                    print("    aproximada y se ajusta en el pivote. Mejor: python tools/calibrar_camara.py")

        if K is not None and len(visible_table_ids) >= 2:
            tp = solve_table_pose(t_img, t_obj, K, dist)
            if tp is not None:
                rv = cv2.Rodrigues(tp[0])[0].ravel()
                tv = tp[1]
                if table_rvec is None or np.linalg.norm(tv - table_tvec) > 15.0 or \
                        np.linalg.norm(rv - table_rvec) > 0.05:
                    table_rvec, table_tvec = rv, tv            # primera vez o la cámara se movió
                else:
                    table_rvec = 0.9 * table_rvec + 0.1 * rv  # mesa y cámara fijas: promedio
                    table_tvec = 0.9 * table_tvec + 0.1 * tv
                table_pose = TablePose(cv2.Rodrigues(table_rvec)[0], table_tvec)
                if ref_table_img is None or len(t_img) >= len(ref_table_img):
                    ref_table_img, ref_table_obj = t_img.copy(), t_obj.copy()

        # Plantilla y cordón proyectados (verificación visual del modelo de cámara)
        if table_pose is not None:
            sp = table_pose.project(np.array([[*cal["seam_start"], 0], [*cal["seam_end"], 0]]), K, dist)
            cv2.line(frame, tuple(sp[0].astype(int)), tuple(sp[1].astype(int)), (255, 140, 0), 2, cv2.LINE_AA)
            cv2.circle(frame, tuple(sp[0].astype(int)), 5, (0, 255, 0), -1)
            cv2.circle(frame, tuple(sp[1].astype(int)), 5, (0, 0, 255), -1)

        # ------------------------------------------------------------------
        # POSE 6D DE LA HERRAMIENTA Y PUNTA
        # ------------------------------------------------------------------
        cands_cam, cands_tab = [], []
        if table_pose is not None and tool_corners is not None:
            m_mm = cal["marker_mm_eff"] if cal["marker_mm_eff"] else marker_cfg_mm
            cands_cam = marker_candidates(tool_corners, m_mm, K, dist)
            cands_tab = table_pose.candidates_in_table(cands_cam)

        n_imu = None
        fu = cal["imu"]
        if fu and fu.get("enabled") and has_imu:
            u = imu_hist.at(now - fu["delay_s"])
            if u is not None:
                n_imu = fu["Q"] @ u

        idx = None
        if tracker is not None and cands_tab:
            tip3, _, idx = tracker.update(cands_tab, now, n_imu)
        elif tracker is not None and tool_corners is None:
            tip3 = None
            tracker.reset()

        if idx is not None and cands_cam:
            Rc, tc, _ = cands_cam[idx]
            cv2.drawFrameAxes(frame, K, dist, cv2.Rodrigues(Rc)[0], tc, 20.0, 2)

        # Grabación del pivote
        if pivot_active and cands_tab:
            pivot_corners.append(tool_corners.copy())
            pivot_times.append(now)
            pivot_Rs.append(min(cands_tab, key=lambda c: c[2])[0])
            if len(pivot_Rs) >= 10 and len(pivot_Rs) % 5 == 0:
                sp_deg, _ = rotation_spread_deg(pivot_Rs)
                pivot_spread = (float(sp_deg[0]), float(sp_deg[1]))

        # ------------------------------------------------------------------
        # COORDENADAS DEL CORDÓN, ENVÍO A GODOT Y VELOCIDAD
        # ------------------------------------------------------------------
        tip_pos_mm = None
        pos_x = pos_y = 0.0
        if tip3 is not None:
            pos_x, pos_y = seam_coords(tip3[:2], cal)
            tip_pos_mm = np.array([pos_x, pos_y])

        if tip_pos_mm is not None:
            if last_sent_pos is None:
                last_sent_pos = tip_pos_mm.copy()
            dx, dy = pos_x - last_sent_pos[0], pos_y - last_sent_pos[1]
            if abs(dx) >= 0.15 or abs(dy) >= 0.15 or (now - last_udp_time >= 0.04):
                pkt = {"dx": round(float(dx), 2), "dy": round(float(dy), 2),
                       "x": round(float(pos_x), 2), "y": round(float(pos_y), 2)}
                try:
                    udp_sock.sendto(json.dumps(pkt).encode("ascii"), GODOT_UDP_ADDR)
                except Exception:
                    pass
                last_sent_pos = tip_pos_mm.copy()
                last_udp_time = now
        else:
            last_sent_pos = None

        if tip_pos_mm is not None:
            history.append((now, pos_x, pos_y))
            ref_idx = 0
            for k_ in range(len(history)):
                if now - history[k_][0] >= 0.25:
                    ref_idx = k_
                else:
                    break
            t_old, x_old, y_old = history[ref_idx]
            dt_win = now - t_old
            if dt_win >= 0.10:
                dist_moved = math.hypot(pos_x - x_old, pos_y - y_old)
                v_target = 0.0 if dist_moved < 0.45 else min(dist_moved / dt_win, 25.0)
                if v_target == 0.0:
                    speed_filtered *= 0.5
                    if speed_filtered < 0.1:
                        speed_filtered = 0.0
                else:
                    speed_filtered = 0.7 * speed_filtered + 0.3 * v_target
        else:
            history.clear()
            speed_filtered *= 0.5
            if speed_filtered < 0.1:
                speed_filtered = 0.0

        # ------------------------------------------------------------------
        # DIBUJO
        # ------------------------------------------------------------------
        if tip3 is not None and table_pose is not None:
            tp_px = table_pose.project(tip3, K, dist)[0]
            tx, ty = int(round(tp_px[0])), int(round(tp_px[1]))
            if 0 <= tx < fw and 0 <= ty < fh:
                if tool_corners is not None:
                    mc = tool_corners.mean(axis=0)
                    cv2.line(frame, (int(mc[0]), int(mc[1])), (tx, ty), (0, 220, 255), 1, cv2.LINE_AA)
                cv2.circle(frame, (tx, ty), 5, (0, 255, 0), -1)
                cv2.circle(frame, (tx, ty), 12, (0, 255, 0), 2)
                cv2.line(frame, (tx - 16, ty), (tx + 16, ty), (0, 255, 0), 2)
                cv2.line(frame, (tx, ty - 16), (tx, ty + 16), (0, 255, 0), 2)
                put(frame, f"PUNTA  z={tip3[2]:+.0f} mm", (tx + 16, ty + 5), 0.5, (0, 255, 0), 2)

        # Minimapa
        mm_w, mm_h = 360, 150
        mm_x0, mm_y0 = fw - mm_w - 20, 20
        cv2.rectangle(frame, (mm_x0, mm_y0), (mm_x0 + mm_w, mm_y0 + mm_h), (25, 30, 38), -1)
        cv2.rectangle(frame, (mm_x0, mm_y0), (mm_x0 + mm_w, mm_y0 + mm_h), (80, 95, 120), 1)
        put(frame, f"MINIMAPA DEL CORDON ({cal['target_len']:.0f} mm)", (mm_x0 + 15, mm_y0 + 22), 0.45, (200, 220, 240))
        ox, oy, sc = mm_x0 + 40, mm_y0 + mm_h // 2 + 5, 1.5
        Lpx = int(cal["target_len"] * sc)
        cv2.rectangle(frame, (ox, oy - 12), (ox + Lpx, oy + 12), (50, 60, 75), -1)
        cv2.line(frame, (ox, oy), (ox + Lpx, oy), (100, 140, 180), 2)
        cv2.circle(frame, (ox, oy), 5, (0, 255, 0), -1)
        cv2.circle(frame, (ox + Lpx, oy), 5, (0, 0, 255), -1)
        if tip_pos_mm is not None:
            cx_ = int(np.clip(ox + pos_x * sc, mm_x0 + 8, mm_x0 + mm_w - 8))
            cy_ = int(np.clip(oy - pos_y * sc, mm_y0 + 30, mm_y0 + mm_h - 8))
            cv2.circle(frame, (cx_, cy_), 7, (0, 255, 120), -1)

        # HUD
        overlay = frame.copy()
        cv2.rectangle(overlay, (20, 20), (560, 300), (15, 18, 24), -1)
        cv2.addWeighted(overlay, 0.70, frame, 0.30, 0, frame)
        cv2.rectangle(frame, (20, 20), (560, 300), (60, 70, 90), 1)
        put(frame, "ArcSim VR - Seguimiento 6D de la punta", (35, 48), 0.6, (255, 255, 255), 2)
        put(frame, f"FPS: {current_fps:.0f}", (480, 48), 0.45, (180, 180, 180))
        n_t = len(visible_table_ids)
        put(frame, f"Mesa: {n_t}/4 marcadores | Camara: "
                   f"{('f=%.0f px, ' % K[0, 0]) if K is not None else ''}{cam_src}", (35, 76), 0.44,
            (0, 255, 0) if n_t >= 2 else (0, 0, 220))
        put(frame, f"Herramienta: {'DETECTADA' if tool_corners is not None else 'BUSCANDO...'}", (35, 98), 0.46,
            (255, 255, 0) if tool_corners is not None else (0, 0, 220))
        if cal["p_tip"] is None:
            put(frame, "PIVOTE PENDIENTE: punta apoyada en la hoja -> [P]", (35, 122), 0.5, (0, 180, 255), 2)
        else:
            mode = tracker.mode if tracker is not None else "-"
            put(frame, f"Pivote OK: punta a {np.linalg.norm(cal['p_tip']):.0f} mm del marcador, residuo "
                       f"{cal['pivot_rms_mm'] or 0:.1f} mm [{mode}]", (35, 122), 0.44, (0, 255, 120))
        if tip_pos_mm is not None:
            on_seam = 0 <= pos_x <= cal["target_len"] and abs(pos_y) < 15
            put(frame, f"Punta: {pos_x:+6.1f} / {cal['target_len']:.0f} mm", (35, 150), 0.56, (0, 255, 120), 2)
            put(frame, f"Desvio lateral: {pos_y:+5.1f} mm  [{'SOBRE EL CORDON' if on_seam else 'FUERA DE JUNTA'}]",
                (35, 174), 0.48, (0, 255, 0) if on_seam else (180, 180, 180))
            put(frame, f"Altura de la punta sobre la hoja: {tip3[2]:+5.1f} mm", (35, 198), 0.46, (200, 210, 220))
        else:
            put(frame, "Punta: --", (35, 150), 0.52, (120, 130, 140))
        if has_imu:
            put(frame, f"IMU [{imu_source_str}]: Pitch {latest_pitch:+5.1f}  Roll {latest_roll:+5.1f}"
                       + ("  (fusion activa)" if n_imu is not None else ""), (35, 222), 0.44, (0, 220, 255))
        else:
            put(frame, "IMU: sin senal (no hace falta para la posicion)", (35, 222), 0.44, (140, 150, 160))
        if speed_filtered < 0.2:
            v_col, v_txt = (180, 180, 180), "REPOSO"
        elif speed_filtered < 1.8:
            v_col, v_txt = (0, 180, 255), "LENTA"
        elif speed_filtered <= 4.5:
            v_col, v_txt = (0, 255, 0), "OPTIMA SMAW"
        else:
            v_col, v_txt = (0, 0, 255), "MUY RAPIDA"
        put(frame, f"Velocidad: {speed_filtered:4.1f} mm/s  [{v_txt}]", (35, 248), 0.52, v_col, 2)
        put(frame, "[C] Gyro | [T] Yaw | [P] Pivote | [ESP]/[F] Cordon propio | [R] Cordon plantilla | [Q] Salir",
            (35, 285), 0.40, (160, 175, 190))
        if time.time() < cmd_timer and cmd_msg:
            put(frame, f">>> {cmd_msg}", (35, 322), 0.5, cmd_color, 2)

        if pivot_active:
            n_pv = len(pivot_corners)
            okn = n_pv >= 60
            oks = pivot_spread[1] >= 5.0
            cv2.rectangle(frame, (0, fh - 64), (fw, fh), (20, 40, 70), -1)
            put(frame, f"PIVOTE: punta QUIETA en la hoja; inclina adelante/atras y a los costados.  "
                       f"Muestras {n_pv} {'OK' if okn else '(min 60)'}", (20, fh - 40), 0.52, (0, 200, 255), 2)
            put(frame, f"Variacion de angulo: {pivot_spread[0]:.0f} / {pivot_spread[1]:.0f} grados "
                       f"{'OK' if oks else '(inclina mas en las dos direcciones)'}   ->  [P] para calcular",
                (20, fh - 14), 0.48, (200, 220, 240))

        cv2.imshow("ArcSim_VR - Seguimiento en Mesa de Soldadura", frame)

        # ------------------------------------------------------------------
        # TECLADO
        # ------------------------------------------------------------------
        key = cv2.waitKey(1) & 0xFF
        if key in (ord('q'), ord('Q'), 27):
            break
        elif key in (ord('t'), ord('T')):
            send_esp32_command("RESET_YAW\n", udp_sock, COMMAND_UDP_ADDR)
            status("TARA YAW ENVIADA (Yaw = 0.0 - rumbo longitudinal alineado)", (0, 255, 255), 2.5)
            print("\n>>> [TARA] Comando RESET_YAW enviado al ESP32 (Yaw = 0).")
        elif key in (ord('c'), ord('C')):
            send_esp32_command("CALIBRATE\n", udp_sock, COMMAND_UDP_ADDR)
            status("CALIBRANDO GYRO (MANTEN LA HERRAMIENTA QUIETA SOBRE LA MESA)...", (0, 180, 255), 3.0)
            print("\n>>> [CALIBRACION GYRO] Comando CALIBRATE enviado al ESP32.")
            print("    MANTEN LA HERRAMIENTA TOTALMENTE INMOVIL SOBRE LA MESA DURANTE 2 SEGUNDOS!")
        elif key in (ord('p'), ord('P')):
            if not pivot_active:
                if table_pose is None:
                    status("PIVOTE: no se ve la mesa (minimo 2 marcadores de la plantilla)", (0, 0, 255))
                elif tool_corners is None:
                    status("PIVOTE: no se ve el marcador de la herramienta", (0, 0, 255))
                else:
                    pivot_active = True
                    pivot_corners, pivot_times, pivot_Rs = [], [], []
                    pivot_spread = (0.0, 0.0)
                    status("PIVOTE: grabando... punta QUIETA, inclina la herramienta", (0, 200, 255))
                    print("\n>>> [PIVOTE] Grabando. Punta apoyada y QUIETA sobre la hoja; inclina la")
                    print("    herramienta adelante/atras y a los costados 5-10 s. [P] para calcular.")
            else:
                pivot_active = False
                print(f"\n>>> [PIVOTE] Calculando con {len(pivot_corners)} muestras...")
                if ref_table_img is None:
                    r = {"ok": False, "reason": "no se vio la mesa", "n": 0}
                else:
                    r = pivot_calibrate_raw(
                        pivot_corners, ref_table_img, ref_table_obj, marker_cfg_mm, fw, fh,
                        K=K if K_reliable else None, dist=dist,
                        f0=K[0, 0] if K is not None else 0.8 * fw,
                        sample_times=pivot_times if len(imu_hist) > 20 else None,
                        imu_history=imu_hist if len(imu_hist) > 20 else None)
                if r.get("ok"):
                    cal["p_tip"] = r["p_tip"]
                    cal["marker_mm_eff"] = r["marker_mm_eff"]
                    cal["pivot_rms_mm"] = r["rms_mm"]
                    if not os.path.exists(INTRINSICS_FILE):
                        cal["focal_px"] = r["focal_px"]
                        cal["image_size"] = (fw, fh)
                        K = r["K"]
                        if not K_reliable:
                            cam_src = "ajustada en el pivote"
                        K_reliable = True
                    fu = r.get("imu")
                    cal["imu"] = fu if (fu and fu.get("enabled")) else None
                    tracker = make_tracker()
                    table_rvec = None          # recalcular la pose de la mesa con la K final
                    save_calibration(cal)
                    sp = r.get("spread_deg", [0, 0, 0])
                    msg = f"PIVOTE OK: residuo {r['rms_mm']:.1f} mm, {r['n_inliers']}/{r['n']} muestras"
                    print(f"    OK. Punta a {np.linalg.norm(r['p_tip']):.1f} mm del centro del marcador.")
                    print(f"    Residuo {r['rms_mm']:.2f} mm | muestras usadas {r['n_inliers']}/{r['n']} | "
                          f"variacion de angulo {sp[0]:.0f}/{sp[1]:.0f} grados")
                    print(f"    Tamano efectivo del ArUco: {r['marker_mm_eff']:.2f} mm (configurado {marker_cfg_mm:.1f})"
                          f" | focal {r['focal_px']:.0f} px")
                    if fu is None:
                        print("    Fusion con IMU: no (sin datos del IMU durante el pivote). Se usa solo camara.")
                    elif fu.get("enabled"):
                        msg += " | fusion IMU activa"
                        print(f"    Fusion con IMU: ACTIVA (residuo {fu['resid_deg']:.1f} grados, retardo "
                              f"{fu['delay_s'] * 1000:.0f} ms, residuo del pivote {fu['rms_mm']:.2f} vs "
                              f"{fu['rms_cam_mm']:.2f} mm solo camara)")
                    else:
                        print(f"    Fusion con IMU: no ({fu['reason']}). Se usa solo camara.")
                    print("    Verifica: punta quieta e inclina -> 'Punta' no debe moverse; z cerca de 0.")
                    status(msg, (0, 255, 0), 6.0)
                else:
                    status(f"PIVOTE RECHAZADO: {r.get('reason', '')}", (0, 0, 255), 7.0)
                    print(f"    RECHAZADO: {r.get('reason', '')}. Se mantiene la calibracion anterior.")
        elif key == ord(' '):
            if tip3 is not None:
                pending_seam_start = tip3[:2].copy()
                status("INICIO del cordon propio fijado. Lleva la punta al FINAL y presiona [F]", (0, 255, 0))
            else:
                status("Primero haz el pivote [P] (no hay punta calculada)", (0, 0, 255))
        elif key in (ord('f'), ord('F')):
            if tip3 is not None and pending_seam_start is not None and \
                    np.linalg.norm(tip3[:2] - pending_seam_start) > 10.0:
                cal["seam_start"] = pending_seam_start
                cal["seam_end"] = tip3[:2].copy()
                pending_seam_start = None
                cal["seam_custom"] = True
                save_calibration(cal)
                L_ = float(np.linalg.norm(cal["seam_end"] - cal["seam_start"]))
                status(f"CORDON PROPIO GUARDADO: {L_:.0f} mm reales -> {cal['target_len']:.0f} mm en Godot", (0, 255, 0))
            else:
                status("Primero [ESPACIO] en el INICIO, despues [F] en el FINAL (a mas de 10 mm)", (0, 0, 255))
        elif key in (ord('r'), ord('R')):
            d0 = default_calibration()
            cal["seam_start"], cal["seam_end"], cal["seam_custom"] = d0["seam_start"], d0["seam_end"], False
            save_calibration(cal)
            status("Cordon: el de la plantilla (0 a 150 mm)", (0, 180, 255))

    stop_serial_thread.set()
    serial_th.join(timeout=1.0)
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
