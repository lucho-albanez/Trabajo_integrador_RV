#!/usr/bin/env python3
"""
Pruebas de tip_compensation.py con una herramienta simulada (sin cámara ni ESP32).

Se fija la punta del electrodo, se inclina la herramienta (pitch/roll) y se genera
la posición que vería la cámara para el marcador ArUco. Se verifica que:
  1. El modelo nuevo mantiene la punta quieta (error < 1 mm) para cualquier inclinación.
  2. El modelo anterior (sin(pitch - pitch_ref) + signo fijo) NO lo hace.
  3. fit_pivot recupera L, signos y rotación del yaw, incluso con pitch cerca de 180 deg.
  4. fit_pivot rechaza datos malos (punta que se mueve / sin inclinación suficiente).

Uso:  python tools/test_tip_compensation.py
"""

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tip_compensation import tilt_vector, tip_from_marker, fit_pivot

rng = np.random.default_rng(1234)
FAILS = []


def check(name, cond, detail=""):
    print(f"[{'OK' if cond else 'FALLA'}] {name} {detail}")
    if not cond:
        FAILS.append(name)


def rot(deg):
    a = math.radians(deg)
    return np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])


def simulate_sensor(theta_f_deg, theta_s_deg, pitch_offset=0.0):
    """Ángulos que reportaría el firmware para una inclinación física dada.

    theta_f: inclinación en el plano de avance, theta_s: inclinación lateral.
    El eje del electrodo (punta->marcador) es el vector unitario
    a = (sin(tf)*cos(ts), sin(ts), cos(tf)*cos(ts)) en (avance, lateral, vertical).
    pitch_offset=180 emula el ESP32 montado "cabeza abajo" (pitch cercano a 180).
    """
    tf, ts = math.radians(theta_f_deg), math.radians(theta_s_deg)
    a = np.array([math.sin(tf) * math.cos(ts), math.sin(ts), math.cos(tf) * math.cos(ts)])
    # Acelerómetro: az -> avance, ax -> lateral, |ay| -> vertical
    az, ax, ay_mag = a[0], a[1], a[2]
    ay = -ay_mag if pitch_offset == 0.0 else +ay_mag
    pitch = math.degrees(math.atan2(az, -ay))
    roll = math.degrees(math.atan2(ax, math.sqrt(az * az + ay * ay)))
    return pitch, roll, a


def camera_marker(tip, a, L, heading_deg, sign_f=+1.0, sign_s=+1.0):
    """Posición del marcador proyectada en la mesa (parte horizontal de L*a)."""
    horiz = np.array([sign_f * a[0], sign_s * a[1]]) * L
    return tip + rot(heading_deg) @ horiz


def run_case(label, L, heading_deg, sign_f, sign_s, pitch_offset, ref_f=18.0):
    print(f"\n--- {label} (L={L}, heading={heading_deg} deg, signos=({sign_f:+.0f},{sign_s:+.0f}), "
          f"pitch_offset={pitch_offset}) ---")
    tip = np.array([37.0, -12.0])
    true_M = rot(heading_deg) @ np.diag([sign_f, sign_s])

    # Pivoteo: punta quieta, inclinación en avance (-10..40) y lateral (-25..25)
    markers, tilts = [], []
    for _ in range(120):
        tf = rng.uniform(-10, 40)
        ts = rng.uniform(-25, 25)
        p, r, a = simulate_sensor(tf, ts, pitch_offset)
        m = camera_marker(tip, a, L, heading_deg, sign_f, sign_s) + rng.normal(0, 0.3, 2)
        markers.append(m)
        tilts.append(tilt_vector(p, r))
    fit = fit_pivot(markers, tilts)
    check("fit_pivot acepta el pivoteo", fit["ok"], f"(rms={fit.get('rms_mm', 0):.2f} mm)")
    if not fit["ok"]:
        return
    check("L recuperado", abs(fit["lever_mm"] - L) < 2.0, f"({fit['lever_mm']:.1f} vs {L})")
    check("M recuperada (signos y yaw)", np.allclose(fit["M"], true_M, atol=0.03))
    check("punta del pivote", np.linalg.norm(fit["tip_mm"] - tip) < 1.0)

    # Estabilidad de la punta compensada en inclinaciones nuevas (no usadas en el ajuste)
    errs_new, errs_old = [], []
    p0, r0, _ = simulate_sensor(ref_f, 5.0, pitch_offset)
    for _ in range(300):
        tf = rng.uniform(-5, 45)
        ts = rng.uniform(-30, 30)
        p, r, a = simulate_sensor(tf, ts, pitch_offset)
        m = camera_marker(tip, a, L, heading_deg, sign_f, sign_s)
        tip_new = tip_from_marker(m, tilt_vector(p, r), fit["lever_mm"], fit["M"])
        errs_new.append(np.linalg.norm(tip_new - tip))
        # Modelo anterior: resta L*sin(delta) con ejes del cordón (signo +) y ref de la calibración
        dp = math.radians(p - p0)
        dr = math.radians(r - r0)
        ref_marker = camera_marker(tip, simulate_sensor(ref_f, 5.0, pitch_offset)[2], L,
                                   heading_deg, sign_f, sign_s)
        legacy = (m - ref_marker) - np.array([L * math.sin(dp), L * math.sin(dr)])
        errs_old.append(np.linalg.norm(legacy))
    e_new, e_old = np.array(errs_new), np.array(errs_old)
    check("punta compensada estable (nuevo)", e_new.max() < 1.0,
          f"(max {e_new.max():.2f} mm, media {e_new.mean():.2f} mm)")
    print(f"       modelo anterior: max {e_old.max():.1f} mm, media {e_old.mean():.1f} mm")


# Caso base: coincide con las suposiciones del código anterior
run_case("Caso base", 115.0, 0.0, +1, +1, 0.0)
# Signos invertidos (el código anterior los supone fijos en +)
run_case("Signos invertidos", 115.0, 0.0, -1, +1, 0.0)
# Yaw que no coincide con el eje del cordón
run_case("Yaw desalineado 25 deg", 115.0, 25.0, +1, +1, 0.0)
# ESP32 montado cabeza abajo -> pitch ~ 180 deg (ref_pitch real del proyecto = 161.9)
run_case("Pitch cerca de 180", 115.0, 0.0, -1, +1, 180.0)
# Escala efectiva distinta de la nominal (homografía/marcador distinto)
run_case("L efectivo 90 mm", 90.0, 10.0, +1, -1, 0.0)

# ---- Rechazo de datos malos --------------------------------------------------
print("\n--- Rechazos ---")
tip = np.array([0.0, 0.0])
mk, tl = [], []
for _ in range(80):
    p, r, a = simulate_sensor(rng.uniform(-10, 40), rng.uniform(-25, 25))
    mk.append(camera_marker(tip, a, 115.0, 0.0) + rng.normal(0, 8.0, 2))  # punta "deslizándose"
    tl.append(tilt_vector(p, r))
check("rechaza si la punta se mueve", not fit_pivot(mk, tl)["ok"])

mk, tl = [], []
for _ in range(80):
    p, r, a = simulate_sensor(rng.uniform(-10, 40), rng.uniform(-0.3, 0.3))  # sin lateral
    mk.append(camera_marker(tip, a, 115.0, 0.0))
    tl.append(tilt_vector(p, r))
check("rechaza si falta inclinación en un eje", not fit_pivot(mk, tl)["ok"])
check("rechaza pocas muestras", not fit_pivot(mk[:5], tl[:5])["ok"])


# ==============================================================================
# Modelo 3D con cámara en perspectiva (como en la foto: vista oblicua, marcador elevado)
# ==============================================================================
import cv2
from tip_compensation import (estimate_focal_px, camera_from_homography, tip_from_pixel,
                              fit_pivot_3d)

W_IMG, H_IMG, F_TRUE = 1280, 720, 1000.0
MARKER_CENTERS = {1: (-45, 65), 2: (195, 65), 3: (-45, -65), 4: (195, -65)}


def look_at_camera(C, target):
    C, target = np.array(C, float), np.array(target, float)
    z = target - C
    z /= np.linalg.norm(z)
    x = np.cross(z, [0, 0, 1.0])
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    R = np.vstack([x, y, z])
    return R, -R @ C


def project(R, t, X):
    K = np.array([[F_TRUE, 0, W_IMG / 2], [0, F_TRUE, H_IMG / 2], [0, 0, 1.0]])
    p = K @ (R @ np.asarray(X, float) + t)
    return p[:2] / p[2]


def table_homography(R, t, noise_px, rng):
    img, tab = [], []
    for cx, cy in MARKER_CENTERS.values():
        for dx, dy in ((-18, 18), (18, 18), (18, -18), (-18, -18)):
            X = (cx + dx, cy + dy, 0.0)
            img.append(project(R, t, X) + rng.normal(0, noise_px, 2))
            tab.append((X[0], X[1]))
    Hm, _ = cv2.findHomography(np.array(img, np.float32), np.array(tab, np.float32), 0)
    return Hm / Hm[2, 2]


def run_case_3d(label, cam_pos, noise_px, f_error=1.0, L=110.0, heading=0.0, sf=-1.0, ss=1.0,
                pitch_offset=0.0, max_tip_err=1.5, max_L_err=0.08):
    print(f"\n--- 3D: {label} ---")
    rng3 = np.random.default_rng(99)
    R, t = look_at_camera(cam_pos, (75, 0, 30))
    Hm = table_homography(R, t, noise_px, rng3)
    f_est = estimate_focal_px(Hm, W_IMG, H_IMG)
    check("focal estimada", f_est is not None and abs(f_est - F_TRUE) / F_TRUE < 0.12,
          f"(est {f_est:.0f} vs {F_TRUE:.0f} px)" if f_est else "(None)")
    f_used = (f_est or F_TRUE) * f_error
    cam = camera_from_homography(Hm, f_used, W_IMG, H_IMG)
    true_M = rot(heading) @ np.diag([sf, ss])
    tip = np.array([60.0, 0.0])

    def marker_px(tip_xy, tf, ts):
        p, r, a = simulate_sensor(tf, ts, pitch_offset)
        horiz = true_M @ np.array([a[0], a[1]]) * L
        X = np.array([tip_xy[0] + horiz[0], tip_xy[1] + horiz[1], L * a[2]])
        return project(R, t, X) + rng3.normal(0, noise_px, 2), tilt_vector(p, r)

    px, tl = [], []
    for _ in range(150):
        m, s_ = marker_px(tip, rng3.uniform(-5, 40), rng3.uniform(-20, 20))
        px.append(m)
        tl.append(s_)
    fit = fit_pivot_3d(px, tl, cam,
                       cam_factory=lambda f: camera_from_homography(Hm, f, W_IMG, H_IMG),
                       focal_px=f_used)
    if fit["ok"]:
        cam = camera_from_homography(Hm, fit["focal_px"], W_IMG, H_IMG)
        print(f"       focal ajustada por el pivote: {fit['focal_px']:.0f} px")
    check("pivote 3D aceptado", fit["ok"], f"(rms={fit.get('rms_mm', 0):.2f} mm, L={fit.get('lever_mm', 0):.1f})")
    if not fit["ok"]:
        print("      motivo:", fit["reason"])
        return
    check("L recuperado", abs(fit["lever_mm"] - L) / L < max_L_err, f"({fit['lever_mm']:.1f} vs {L})")
    check("M recuperada", np.allclose(fit["M"], true_M, atol=0.08))

    errs_new, errs_naive = [], []
    Hinv = np.linalg.inv(Hm)
    for _ in range(300):
        tip_i = tip
        m, s_ = marker_px(tip_i, rng3.uniform(-5, 45), rng3.uniform(-25, 25))
        est = tip_from_pixel(m, s_, fit["lever_mm"], fit["M"], cam)
        errs_new.append(np.linalg.norm(est - tip_i))
        naive = Hm @ np.array([m[0], m[1], 1.0])         # proyectar el marcador con la homografía de la mesa
        errs_naive.append(np.linalg.norm(naive[:2] / naive[2] - tip_i))
    e = np.array(errs_new)
    check("punta estable con perspectiva", e.max() < max_tip_err,
          f"(max {e.max():.2f} mm, media {e.mean():.2f} mm)")
    print(f"       homografía directa del marcador elevado: media {np.mean(errs_naive):.0f} mm de error")


# Cámara oblicua como en la foto (mira desde el lado +y, plantilla vista rotada 180 deg)
run_case_3d("cámara oblicua, sin ruido", (75, 330, 300), 0.0)
run_case_3d("cámara oblicua, ruido 0.4 px", (75, 330, 300), 0.4)
run_case_3d("cámara más cenital + signos/yaw raros", (75, 120, 420), 0.3, heading=20.0, sf=+1.0, ss=-1.0)
run_case_3d("focal estimada 15% mal (pivote lo compensa)", (75, 330, 300), 0.3, f_error=1.15,
            max_tip_err=1.5, max_L_err=0.08)

print("\n" + ("TODO OK" if not FAILS else f"FALLARON: {FAILS}"))
sys.exit(1 if FAILS else 0)
