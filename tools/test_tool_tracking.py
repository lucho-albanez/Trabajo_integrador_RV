#!/usr/bin/env python3
"""
Pruebas de tool_tracking.py con una cámara y una herramienta simuladas (sin hardware).

Herramienta simulada: punta en el origen, eje del electrodo hacia +z, ArUco DESPLAZADO del eje
(no hace falta que esté sobre el electrodo) y orientado hacia la cámara. Cámara oblicua como la
de la foto del banco. Se agrega ruido de 0.3 px a las esquinas detectadas.

Uso:  python tools/test_tool_tracking.py
"""
import math
import os
import sys

import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tool_tracking as tt

FAILS = []


def check(name, cond, detail=""):
    print(f"[{'OK' if cond else 'FALLA'}] {name} {detail}")
    if not cond:
        FAILS.append(name)


W, H = 1280, 720
F_TRUE = 950.0
K_TRUE = tt.camera_matrix(F_TRUE, W, H)
REAL_MARKER_MM = 36.0
# ArUco en el sistema de la herramienta: 22 mm al costado y 118 mm por encima de la punta
MARKER_CENTER_TOOL = np.array([0.0, 22.0, 118.0])


def look_at(C, target):
    C, target = np.array(C, float), np.array(target, float)
    z = target - C
    z /= np.linalg.norm(z)
    x = np.cross(z, [0, 0, 1.0])
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    R = np.vstack([x, y, z])
    return R, -R @ C


R_CAM, T_CAM = look_at((75, 330, 320), (75, 0, 20))


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


# marcador: x de la herramienta, normal hacia +y y arriba (mira a la cámara)
_zm = np.array([0, 0.75, 0.66]); _zm /= np.linalg.norm(_zm)
_xm = np.array([1.0, 0, 0])
_ym = np.cross(_zm, _xm)
R_MARKER_TOOL = np.column_stack([_xm, _ym, _zm])
P_TIP_TRUE = -R_MARKER_TOOL.T @ MARKER_CENTER_TOOL       # punta en el sistema del marcador


# IMU montado con una rotación arbitraria respecto del marcador ("cabeza abajo": pitch ~ 180)
R_IMU_MARKER = rot_x(math.radians(200)) @ rot_z(math.radians(30))   # IMU -> marcador
IMU_DELAY_S = 0.06


def imu_reading(R_tool, rng, noise_deg=0.3):
    """pitch/roll que mandaría el firmware para una orientación de la herramienta."""
    R_marker = R_tool @ R_MARKER_TOOL
    up_marker = R_marker.T @ np.array([0, 0, 1.0])
    u = R_IMU_MARKER.T @ up_marker
    u = u + rng.normal(0, math.radians(noise_deg), 3)
    u /= np.linalg.norm(u)
    ax, ay, az = u
    pitch = math.degrees(math.atan2(az, -ay))
    roll = math.degrees(math.atan2(ax, math.sqrt(az * az + ay * ay)))
    return pitch, roll


def tool_rotation(work_deg, travel_deg, yaw_deg=0.0):
    return rot_z(math.radians(yaw_deg)) @ rot_y(math.radians(travel_deg)) @ rot_x(math.radians(work_deg))


def project(X):
    p = (K_TRUE @ (R_CAM @ np.asarray(X).T + T_CAM[:, None])).T
    return p[:, :2] / p[:, 2:3]


def observe(tip, R_tool, rng, noise=0.3):
    obj = tt.marker_object_points(REAL_MARKER_MM)
    X = tip + (R_tool @ (MARKER_CENTER_TOOL[:, None] + R_MARKER_TOOL @ obj.T)).T
    return project(X) + rng.normal(0, noise, (4, 2))


def table_obs(rng, noise=0.3):
    img, obj = [], []
    for mid in tt.TABLE_MARKER_CENTERS_MM:
        c3 = tt.table_marker_corners_3d(mid)
        img.append(project(c3) + rng.normal(0, noise, (4, 2)))
        obj.append(c3)
    return np.vstack(img), np.vstack(obj)


def pivot_data(rng, tip, n=150, imu=None, t0=0.0):
    """imu: ImuHistory a llenar (las lecturas llegan IMU_DELAY_S antes que el cuadro de cámara)."""
    raw, times = [], []
    for i in range(n):
        t = t0 + i / 30.0
        work = 14 * math.sin(i * 0.21 + 0.5)
        travel = 15 + 20 * math.sin(i * 0.13)
        R_tool = tool_rotation(work, travel, rng.normal(0, 3))
        raw.append(observe(tip, R_tool, rng))
        times.append(t + IMU_DELAY_S)        # el cuadro se procesa con retardo
        if imu is not None:
            imu.add(t, *imu_reading(R_tool, rng))
    if imu is not None:
        return raw, times
    return raw


def stability(rng, p_tip, K, dist, marker_mm, label, fusion=None, max_p95=5.0):
    """Punta quieta en (95, 0) y la herramienta inclinándose de forma continua (como al soldar).

    sesgo   = corrimiento medio de la punta por cuadro (lo que el pivoteo NO debe producir)
    filtrada = salida del TipTracker (lo que va a Godot)
    """
    img, obj = table_obs(rng)
    tp = tt.solve_table_pose(img, obj, K, dist)
    pose = tt.TablePose(tp[0], tp[1])
    tracker = tt.TipTracker(p_tip, None if fusion is None else fusion["p_tip"])
    imu = tt.ImuHistory()
    tip_true = np.array([95.0, 0.0, 0.0])
    raw_err, filt_err, naive = [], [], []
    hz = np.linalg.inv(cv2.findHomography(obj[:, :2].astype(np.float32), img.astype(np.float32))[0])
    for i in range(600):
        t = i / 30.0
        R_tool = tool_rotation(18 * math.sin(t * 1.3), 18 + 20 * math.sin(t * 0.9), 4 * math.sin(t * 0.5))
        corners = observe(tip_true, R_tool, rng)
        imu.add(t, *imu_reading(R_tool, rng))
        cands = pose.candidates_in_table(tt.marker_candidates(corners, marker_mm, K, dist))
        n_imu = None
        t_proc = t + IMU_DELAY_S                # el cuadro capturado en t se procesa en t + retardo
        if fusion is not None:
            u = imu.at(t_proc - fusion["delay_s"])   # lo que hace test_vision_table en tiempo real
            n_imu = None if u is None else fusion["Q"] @ u
        filt, raw, _ = tracker.update(cands, t_proc, n_imu)
        if raw is not None:
            raw_err.append(raw[:2] - tip_true[:2])
        if i >= 30:
            filt_err.append(np.linalg.norm(filt[:2] - tip_true[:2]))
        m = hz @ np.array([*corners.mean(axis=0), 1.0])
        naive.append(np.linalg.norm(m[:2] / m[2] - tip_true[:2]))
    raw_err = np.array(raw_err)
    bias = float(np.linalg.norm(raw_err.mean(axis=0)))
    fe = np.array(filt_err)
    check(f"{label}: sin sesgo al inclinar", bias < 1.0, f"(sesgo {bias:.2f} mm)")
    check(f"{label}: punta filtrada quieta [{tracker.mode}]", np.percentile(fe, 95) < max_p95,
          f"(p95 {np.percentile(fe, 95):.2f} mm, max {fe.max():.2f} mm)")
    print(f"       sin filtrar: p95 {np.percentile(np.linalg.norm(raw_err, axis=1), 95):.1f} mm (ruido de rotación) | "
          f"centro del marcador proyectado a la mesa: media {np.mean(naive):.0f} mm")


rng = np.random.default_rng(3)
tip_pivot = np.array([60.0, 0.0, 0.0])

print("\n--- 1. Intrínsecos conocidos, tamaño del ArUco correcto ---")
img, obj = table_obs(rng)
raw = pivot_data(rng, tip_pivot)
r = tt.pivot_calibrate_raw(raw, img, obj, REAL_MARKER_MM, W, H, K=K_TRUE)
check("pivote aceptado", r["ok"], f"(rms {r.get('rms_mm', 0):.2f} mm, {r.get('n_inliers')}/{r['n']}) {r['reason']}")
check("offset punta-marcador recuperado", np.linalg.norm(r["p_tip"] - P_TIP_TRUE) < 2.0,
      f"(error {np.linalg.norm(r['p_tip'] - P_TIP_TRUE):.2f} mm, |p| = {np.linalg.norm(r['p_tip']):.0f})")
check("punto de pivote", np.linalg.norm(r["pivot_mm"] - tip_pivot) < 1.5, f"({np.round(r['pivot_mm'], 1)})")
stability(rng, r["p_tip"], K_TRUE, np.zeros(5), REAL_MARKER_MM, "caso 1")

print("\n--- 2. Tamaño del ArUco mal configurado (40 mm en vez de 36) ---")
r2 = tt.pivot_calibrate_raw(raw, img, obj, 40.0, W, H, K=K_TRUE)
check("pivote aceptado", r2["ok"], r2["reason"])
check("tamaño efectivo corregido", abs(r2["marker_mm_eff"] - REAL_MARKER_MM) < 0.6,
      f"({r2['marker_mm_eff']:.2f} mm)")
stability(rng, r2["p_tip"], K_TRUE, np.zeros(5), r2["marker_mm_eff"], "caso 2")

print("\n--- 3. Focal desconocida (estimada de la plantilla y ajustada por el pivote) ---")
f_est = tt.estimate_focal([img], [obj], W, H)
check("focal estimada de la plantilla", f_est is not None and abs(f_est - F_TRUE) / F_TRUE < 0.10,
      f"({f_est:.0f} vs {F_TRUE:.0f})" if f_est else "(None)")
r3 = tt.pivot_calibrate_raw(raw, img, obj, REAL_MARKER_MM, W, H, K=tt.camera_matrix(f_est, W, H))
check("pivote aceptado (focal de la plantilla)", r3["ok"], r3["reason"])
r3b = tt.pivot_calibrate_raw(raw, img, obj, REAL_MARKER_MM, W, H, K=None, f0=0.8 * W)
check("respaldo: búsqueda de focal si la plantilla no alcanza", r3b["ok"] and abs(r3b["focal_px"] - F_TRUE) / F_TRUE < 0.12,
      f"({r3b.get('focal_px', 0):.0f} px) {r3b['reason']}")
stability(rng, r3["p_tip"], r3["K"], r3["dist"], r3["marker_mm_eff"], "caso 3")

print("\n--- 5. Fusión con el IMU (montado cabeza abajo, 60 ms de retardo, 0.3° de ruido) ---")
imu_h = tt.ImuHistory()
raw_i, times_i = pivot_data(rng, tip_pivot, imu=imu_h)
r8 = tt.pivot_calibrate_raw(raw_i, img, obj, REAL_MARKER_MM, W, H, K=K_TRUE,
                            sample_times=times_i, imu_history=imu_h)
fu = r8["imu"]
check("pivote aceptado", r8["ok"], r8["reason"])
check("fusión habilitada", fu is not None and fu["enabled"],
      f"(residuo {fu.get('resid_deg', 0):.2f}°, retardo {fu.get('delay_s', 0)*1000:.0f} ms, "
      f"rms {fu.get('rms_mm', 0):.2f} vs {fu.get('rms_cam_mm', 0):.2f} mm) {fu.get('reason', '')}" if fu else "")
check("retardo IMU-cámara medido", fu is not None and abs(fu["delay_s"] - IMU_DELAY_S) <= 0.02)
check("offset punta-marcador (fusión)", np.linalg.norm(fu["p_tip"] - P_TIP_TRUE) < 1.5,
      f"(error {np.linalg.norm(fu['p_tip'] - P_TIP_TRUE):.2f} mm)")
# en tiempo real el IMU se consulta en t - retardo: emularlo en stability
stability(rng, r8["p_tip"], K_TRUE, np.zeros(5), REAL_MARKER_MM, "caso 5", fusion=fu, max_p95=1.5)
# IMU que no corresponde a la herramienta (montaje "espejado"): la fusión debe quedar apagada
imu_bad = tt.ImuHistory()
for tt_, (rw, tm) in enumerate(zip(raw_i, times_i)):
    p_, r_ = imu_reading(tool_rotation(rng.uniform(-20, 20), rng.uniform(-5, 40)), rng)
    imu_bad.add(tm - IMU_DELAY_S, p_, r_)
r9 = tt.pivot_calibrate_raw(raw_i, img, obj, REAL_MARKER_MM, W, H, K=K_TRUE,
                            sample_times=times_i, imu_history=imu_bad)
check("fusión rechazada con un IMU incoherente", r9["imu"] is not None and not r9["imu"]["enabled"],
      f"({r9['imu']['reason']})" if r9["imu"] else "")

print("\n--- 4. Rechazos ---")
# la punta resbala: la segunda mitad del pivoteo con la punta 15 mm más allá
raw_slip = raw[:75] + pivot_data(rng, tip_pivot + np.array([15.0, 0, 0]), 75)
r4 = tt.pivot_calibrate_raw(raw_slip, img, obj, REAL_MARKER_MM, W, H, K=K_TRUE)
check("rechaza si la punta se mueve", not r4["ok"], f"({r4['reason']})")
raw_one = [observe(tip_pivot, tool_rotation(0.0, 10 + 20 * math.sin(i * 0.2)), rng) for i in range(120)]
r5 = tt.pivot_calibrate_raw(raw_one, img, obj, REAL_MARKER_MM, W, H, K=K_TRUE)
check("rechaza si se inclina en un solo eje", not r5["ok"], f"({r5['reason']})")
r6 = tt.pivot_calibrate_raw(raw[:10], img, obj, REAL_MARKER_MM, W, H, K=K_TRUE)
check("rechaza pocas muestras", not r6["ok"], f"({r6['reason']})")
# muestras aisladas malas (detección falsa): deben descartarse, no hacer fallar el pivote
raw_out = [c + (rng.normal(0, 30, 2) if i % 15 == 0 else 0) for i, c in enumerate(raw)]
r7 = tt.pivot_calibrate_raw(raw_out, img, obj, REAL_MARKER_MM, W, H, K=K_TRUE)
check("tolera algunas muestras malas", r7["ok"] and np.linalg.norm(r7["p_tip"] - P_TIP_TRUE) < 2.5,
      f"({r7.get('n_inliers')}/{r7['n']} usadas) {r7['reason']}")

print("\n" + ("TODO OK" if not FAILS else f"FALLARON: {FAILS}"))
sys.exit(1 if FAILS else 0)
