#!/usr/bin/env python3
"""
ArcSim_VR - Compensación cinemática de la punta del electrodo
=============================================================
La cámara ve el marcador ArUco del soporte (ID 0), que está a una distancia L
de la punta a lo largo del eje de la herramienta. Al inclinar la herramienta con
la punta quieta, el marcador se desplaza sobre la mesa aunque la punta no se
mueva. Este módulo calcula ese desplazamiento a partir del IMU y lo resta.

Modelo
------
Con la herramienta inclinada, la componente horizontal del eje punta->marcador
es la proyección del vector gravedad sobre los ejes X y Z del sensor. Con el
firmware actual (pitch = atan2(az, -ay), roll = atan2(ax, sqrt(az^2 + ay^2))):

    s = [ cos(roll) * sin(pitch) ,  sin(roll) ]      (= [az, ax] normalizados)

    marcador_mesa = punta_mesa + L * M @ s

M es una matriz 2x2 (adimensional) que indica hacia dónde de la mesa apunta cada
eje de inclinación. Por defecto es la identidad (ejes de la mesa), suponiendo que
el cordón corre sobre el eje X de la plantilla y el yaw está tarado con [T].
Con la "calibración de pivote" (ver fit_pivot) M se mide en lugar de suponerla,
lo que resuelve de una vez signos, rotación del yaw y escala real de L.

Por qué s absoluto y no (pitch - pitch_ref)
-------------------------------------------
El desplazamiento horizontal es L*sin(theta), no L*sin(theta - theta_ref):
    L*(sin(theta) - sin(theta_ref))  !=  L*sin(theta - theta_ref)
s también es continuo cuando el pitch cruza +-180 deg (el ESP32 montado
"cabeza abajo" reporta pitch cercano a 180).
"""

import math
import numpy as np

DEFAULT_LEVER_MM = 115.0


def tilt_vector(pitch_deg, roll_deg):
    """Componentes horizontales (adimensionales) del eje de la herramienta."""
    p = math.radians(pitch_deg)
    r = math.radians(roll_deg)
    return np.array([math.cos(r) * math.sin(p), math.sin(r)], dtype=np.float64)


def default_tilt_matrix():
    """M por defecto: ejes de la mesa (pitch -> +X, roll -> +Y).

    Es válida cuando el cordón corre a lo largo del eje X de la plantilla A4 (así está
    definida la plantilla) y el yaw del IMU se taró con [T] en esa dirección. Para no
    depender de esas suposiciones (ni de los signos), usar fit_pivot.
    """
    return np.eye(2, dtype=np.float64)


def marker_offset_mm(tilt, lever_mm, M):
    """Desplazamiento horizontal punta->marcador en el plano de la mesa [mm]."""
    return lever_mm * (np.asarray(M, dtype=np.float64) @ np.asarray(tilt, dtype=np.float64))


def tip_from_marker(marker_mm, tilt, lever_mm, M):
    """Posición de la punta en la mesa [mm] a partir del marcador y la inclinación."""
    return np.asarray(marker_mm, dtype=np.float64) - marker_offset_mm(tilt, lever_mm, M)


def fit_pivot(markers_mm, tilts, min_samples=25, min_tilt_std=0.03, max_rms_mm=2.5,
              lever_range_mm=(40.0, 300.0)):
    """Calibración de pivote: la punta se mantiene fija y se inclina la herramienta.

    Ajusta por mínimos cuadrados  marcador_i = c + A @ s_i  donde c es la punta
    (fija) y A = L * M. Devuelve un dict:
        ok        : bool
        reason    : motivo del rechazo si ok es False
        lever_mm  : L (promedio de la norma de las columnas de A)
        M         : A / L (2x2)
        A, tip_mm, rms_mm (residuo del ajuste = cuánto se movió la punta),
        tilt_std  : desvío estándar de s en sus ejes principales
        n         : cantidad de muestras
    """
    P = np.asarray(markers_mm, dtype=np.float64).reshape(-1, 2)
    S = np.asarray(tilts, dtype=np.float64).reshape(-1, 2)
    n = len(P)
    out = {"ok": False, "reason": "", "n": n}
    if n < min_samples:
        out["reason"] = f"pocas muestras ({n} < {min_samples})"
        return out

    Sc = S - S.mean(axis=0)
    sv = np.linalg.svd(Sc, compute_uv=False) / math.sqrt(n)
    out["tilt_std"] = [float(sv[0]), float(sv[1])]
    if sv[1] < min_tilt_std:
        out["reason"] = ("inclinación insuficiente en alguno de los ejes "
                         "(inclina en AVANCE y en LATERAL con la punta quieta)")
        return out

    X = np.hstack([S, np.ones((n, 1))])
    beta, *_ = np.linalg.lstsq(X, P, rcond=None)      # (3, 2)
    A = beta[:2].T                                    # 2x2, marcador = A @ s + c
    c = beta[2]
    res = P - X @ beta
    rms = float(math.sqrt(np.mean(np.sum(res ** 2, axis=1))))
    L = float(np.mean(np.linalg.norm(A, axis=0)))
    out.update({"A": A, "tip_mm": c, "rms_mm": rms, "lever_mm": L})

    if rms > max_rms_mm:
        out["reason"] = (f"la punta se movió durante el pivoteo (residuo {rms:.1f} mm > "
                         f"{max_rms_mm:.1f} mm)")
        return out
    if not (lever_range_mm[0] <= L <= lever_range_mm[1]):
        out["reason"] = f"brazo L={L:.0f} mm fuera de rango plausible {lever_range_mm}"
        return out

    out["M"] = A / L
    out["ok"] = True
    return out


# ==============================================================================
# MODELO 3D (cámara en perspectiva)
# ==============================================================================
# La homografía de la mesa solo es válida para puntos SOBRE el plano de los marcadores de la
# mesa. El marcador de la herramienta está elevado ~L sobre la mesa, así que proyectarlo con la
# homografía lo desplaza (paralaje) muchos cm. Aquí se estima la cámara (foco y pose) a partir
# de la propia homografía de la mesa y se intersecta el rayo del marcador con su altura real.

class Camera:
    """Cámara estimada en el sistema de la mesa (x, y en mm sobre el plano, z hacia arriba)."""

    def __init__(self, R, t, K):
        self.R = R                      # mesa -> cámara
        self.t = t
        self.K = K
        self.Kinv = np.linalg.inv(K)
        self.C = -R.T @ t               # centro de la cámara en coordenadas de la mesa

    def ray(self, px):
        """Dirección (en coordenadas de la mesa) del rayo que pasa por el píxel px."""
        d = self.R.T @ (self.Kinv @ np.array([px[0], px[1], 1.0]))
        return d / np.linalg.norm(d)

    def point_at_height(self, px, height_mm):
        """Punto 3D del rayo del píxel px a la altura z = height_mm sobre la mesa (o None)."""
        d = self.ray(px)
        if abs(d[2]) < 1e-9:
            return None
        lam = (height_mm - self.C[2]) / d[2]
        if lam <= 0:
            return None
        return self.C + lam * d


def estimate_focal_px(H_img2table, width, height):
    """Distancia focal [px] a partir de la homografía de un plano (Zhang, punto principal al centro).

    Devuelve None si la vista es casi cenital (la focal no es observable) o la estimación es absurda.
    """
    try:
        H = np.linalg.inv(np.asarray(H_img2table, dtype=np.float64))   # mesa -> imagen
    except np.linalg.LinAlgError:
        return None
    cx, cy = width / 2.0, height / 2.0
    a = np.array([H[0, 0] - cx * H[2, 0], H[1, 0] - cy * H[2, 0], H[2, 0]])
    b = np.array([H[0, 1] - cx * H[2, 1], H[1, 1] - cy * H[2, 1], H[2, 1]])
    cands = []
    d1 = a[2] * b[2]
    if abs(d1) > 1e-14:
        f2 = -(a[0] * b[0] + a[1] * b[1]) / d1
        if f2 > 0:
            cands.append(math.sqrt(f2))
    d2 = b[2] ** 2 - a[2] ** 2
    if abs(d2) > 1e-14:
        f2 = (a[0] ** 2 + a[1] ** 2 - b[0] ** 2 - b[1] ** 2) / d2
        if f2 > 0:
            cands.append(math.sqrt(f2))
    if not cands:
        return None
    f = cands[0]
    if not (0.3 * width <= f <= 4.0 * width):
        return None
    return float(f)


def camera_from_homography(H_img2table, focal_px, width, height):
    """Cámara (R, t, K) a partir de la homografía imagen->mesa y una focal dada."""
    K = np.array([[focal_px, 0, width / 2.0], [0, focal_px, height / 2.0], [0, 0, 1.0]])
    Ht = np.linalg.inv(np.asarray(H_img2table, dtype=np.float64))      # mesa -> imagen
    B = np.linalg.inv(K) @ Ht
    lam = 1.0 / np.linalg.norm(B[:, 0])
    r1, r2, t = B[:, 0] * lam, B[:, 1] * lam, B[:, 2] * lam
    if t[2] < 0:                                                         # la mesa delante de la cámara
        r1, r2, t = -r1, -r2, -t
    R = np.column_stack([r1, r2, np.cross(r1, r2)])
    U, _, Vt = np.linalg.svd(R)
    R = U @ Vt
    cam = Camera(R, t, K)
    if cam.C[2] < 0:                                                     # z hacia la cámara
        R = R.copy()
        R[:, 2] *= -1.0
        cam = Camera(R, t, K)
    return cam


def tip_from_pixel(px, tilt, lever_mm, M, cam):
    """Punta [mm, mesa] a partir del píxel del marcador, la inclinación y la cámara estimada.

    El centro del marcador está a L sobre la punta a lo largo del eje de la herramienta:
    altura L*cos(inclinación) y desplazamiento horizontal L*M@s. Se intersecta el rayo con esa
    altura y se resta el desplazamiento horizontal.
    """
    s = np.asarray(tilt, dtype=np.float64)
    az = math.sqrt(max(0.0, 1.0 - float(s @ s)))
    P = cam.point_at_height(px, lever_mm * az)
    if P is None:
        return None
    return P[:2] - lever_mm * (np.asarray(M, dtype=np.float64) @ s)


def _rays(cam, pixels):
    """Rayos (n,3) en coordenadas de la mesa para un arreglo de píxeles (n,2)."""
    P = np.hstack([pixels, np.ones((len(pixels), 1))])
    d = (cam.R.T @ (cam.Kinv @ P.T)).T
    return d / np.linalg.norm(d, axis=1, keepdims=True)


def _pivot_eval(cam, PX, S, az, L, dirs=None):
    """Dispersión de la punta para una L dada. Devuelve (rms, Q, tip) o None."""
    d = _rays(cam, PX) if dirs is None else dirs
    dz = d[:, 2]
    if np.any(np.abs(dz) < 1e-9):
        return None
    lam = (L * az - cam.C[2]) / dz
    if np.any(lam <= 0):
        return None
    P = (cam.C[None, :] + lam[:, None] * d)[:, :2]
    Sc = S - S.mean(axis=0)
    Pc = P - P.mean(axis=0)
    U, _, Vt = np.linalg.svd(Pc.T @ Sc)
    Q = U @ Vt                                   # O(2): incluye reflexiones (signos)
    res = Pc - L * (Sc @ Q.T)
    rms = math.sqrt(float(np.mean(np.sum(res ** 2, axis=1))))
    tip = (P - L * (S @ Q.T)).mean(axis=0)
    return rms, Q, tip


def fit_pivot_3d(pixels, tilts, cam, cam_factory=None, focal_px=None, min_samples=25,
                 min_tilt_std=0.03, max_rms_mm=2.5, lever_range_mm=(40.0, 300.0)):
    """Calibración de pivote con el modelo 3D: punta quieta, herramienta inclinada.

    Para cada L candidata se calcula, por muestra, el punto 3D del marcador a la altura
    L*cos(inclinación); la punta es ese punto menos L*Q@s (Q ortogonal: signos y yaw). Se elige la
    L con menor dispersión de la punta (Procrustes ortogonal para Q).

    Si se pasa cam_factory (f -> Camera) y focal_px, también se ajusta la focal de la cámara
    (la dispersión de la punta la delata: una focal mala deja un residuo grande).

    Devuelve un dict: ok, reason, lever_mm, M (=Q), A, tip_mm, rms_mm, tilt_std, n, focal_px.
    """
    PX = np.asarray(pixels, dtype=np.float64).reshape(-1, 2)
    S = np.asarray(tilts, dtype=np.float64).reshape(-1, 2)
    n = len(PX)
    out = {"ok": False, "reason": "", "n": n}
    if n < min_samples:
        out["reason"] = f"pocas muestras ({n} < {min_samples})"
        return out
    Sc = S - S.mean(axis=0)
    sv = np.linalg.svd(Sc, compute_uv=False) / math.sqrt(n)
    out["tilt_std"] = [float(sv[0]), float(sv[1])]
    if sv[1] < min_tilt_std:
        out["reason"] = ("inclinación insuficiente en alguno de los ejes "
                         "(inclina en AVANCE y en LATERAL con la punta quieta)")
        return out

    az = np.sqrt(np.clip(1.0 - np.sum(S * S, axis=1), 0.0, 1.0))
    lo, hi = lever_range_mm

    def best_for_camera(c):
        dirs = _rays(c, PX)
        best = None
        for L in np.arange(lo, hi + 1e-9, 2.0):
            r = _pivot_eval(c, PX, S, az, float(L), dirs)
            if r is not None and (best is None or r[0] < best[0]):
                best = (r[0], float(L), r[1], r[2])
        if best is None:
            return None
        for L in np.arange(best[1] - 2.0, best[1] + 2.0 + 1e-9, 0.25):
            r = _pivot_eval(c, PX, S, az, float(L), dirs)
            if r is not None and r[0] < best[0]:
                best = (r[0], float(L), r[1], r[2])
        return best

    f_best, best = focal_px, best_for_camera(cam)
    if cam_factory is not None and focal_px is not None:
        for scale in np.arange(0.6, 1.6001, 0.05):
            c = cam_factory(float(focal_px * scale))
            b = best_for_camera(c)
            if b is not None and (best is None or b[0] < best[0] - 1e-9):
                best, f_best = b, float(focal_px * scale)
        for scale in np.arange(-0.04, 0.0401, 0.01):          # refinamiento fino
            f = float(f_best * (1.0 + scale))
            b = best_for_camera(cam_factory(f))
            if b is not None and b[0] < best[0] - 1e-9:
                best, f_best = b, f
    if best is None:
        out["reason"] = "no se pudo intersectar el rayo del marcador con la mesa"
        return out
    rms, L, Q, tip = best
    out.update({"rms_mm": rms, "lever_mm": L, "tip_mm": tip, "focal_px": f_best})
    if rms > max_rms_mm:
        out["reason"] = (f"la punta se movió durante el pivoteo (residuo {rms:.1f} mm > "
                         f"{max_rms_mm:.1f} mm)")
        return out
    if L <= lo + 2.0 or L >= hi - 2.0:
        out["reason"] = f"brazo L={L:.0f} mm en el borde del rango de búsqueda {lever_range_mm}"
        return out
    out["M"] = Q
    out["A"] = L * Q
    out["ok"] = True
    return out
