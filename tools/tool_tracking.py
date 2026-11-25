#!/usr/bin/env python3
"""
ArcSim_VR - Seguimiento óptico 6D de la herramienta y calibración de pivote
===========================================================================
Método estándar de seguimiento de instrumentos (como en navegación quirúrgica):

1. POSE DE LA MESA: con las esquinas de los 4 marcadores de la plantilla A4 (posiciones
   conocidas, z = 0) se obtiene la pose de la cámara respecto de la mesa (solvePnP).
2. POSE DEL MARCADOR DE LA HERRAMIENTA: con las 4 esquinas del ArUco ID 0 se obtiene su
   rotación R y su traslación t completas (solvePnP IPPE_SQUARE), expresadas en la mesa.
3. LA PUNTA ES UN PUNTO FIJO DEL MARCADOR: p (3D, en el sistema del marcador). En cualquier
   pose:  punta_mesa = R @ p + t.  Si p es correcto, inclinar la herramienta NO mueve la punta.
4. CALIBRACIÓN DE PIVOTE: con la punta quieta en un punto q se inclina la herramienta. Cada
   muestra cumple R_i p + t_i = q  ->  sistema lineal [R_i  -I][p; q] = -t_i (mínimos cuadrados).

No hace falta el IMU, ni el brazo L, ni que el marcador esté sobre el eje del electrodo.

Robustez:
  - Ambigüedad de pose de un marcador plano (IPPE da 2 soluciones): en el pivote se elige, por
    muestra, la solución coherente con el punto fijo (iterativo); en el seguimiento, la que deja
    la punta cerca de la mesa y del frame anterior.
  - Muestras malas (detección ruidosa, punta que resbala un instante): se descartan por residuo.
  - Tamaño real del ArUco impreso: un error de tamaño escala la distancia marcador-cámara y NO se
    nota en el residuo del pivote, pero sí en la altura del punto de pivote (debe estar sobre la
    mesa, z = 0). Se corrige automáticamente con ese dato.
  - Focal de la cámara: si no hay calibración de cámara, se estima con la propia plantilla (y,
    si eso falla, se busca la que minimiza el residuo del pivote).
  - Fusión con el IMU (opcional, automática): la inclinación de un ArUco chico medida por cámara
    es ruidosa. Durante el mismo pivote se mide la rotación fija IMU->marcador (y el retardo
    IMU-cámara) comparando la gravedad que ve el IMU con la que ve la cámara. En tiempo real la
    cámara aporta posición y giro, y el IMU la inclinación. Solo se activa si en los datos del
    pivote reduce el residuo; si no hay IMU o el ajuste es malo, se usa solo la cámara.
"""

import math
import numpy as np
import cv2

# ==============================================================================
# PLANTILLA A4 (hardware/aruco/generate_table_board.py)
# ==============================================================================
TABLE_MARKER_SIZE_MM = 36.0
TABLE_MARKER_CENTERS_MM = {
    1: (-45.0, +65.0),   # Sup Izq
    2: (+195.0, +65.0),  # Sup Der
    3: (-45.0, -65.0),   # Inf Izq
    4: (+195.0, -65.0),  # Inf Der
}
TEMPLATE_SEAM_START_MM = (0.0, 0.0)     # el cordón dibujado en la plantilla
TEMPLATE_SEAM_END_MM = (150.0, 0.0)
TOOL_MARKER_ID = 0
DEFAULT_TOOL_MARKER_MM = 36.0           # lado del cuadrado negro del ArUco del soporte


def table_marker_corners_3d(marker_id):
    """Esquinas 3D (mm, z=0) de un marcador de la mesa en el orden de ArUco (TL, TR, BR, BL)."""
    cx, cy = TABLE_MARKER_CENTERS_MM[marker_id]
    h = TABLE_MARKER_SIZE_MM / 2.0
    return np.array([[cx - h, cy + h, 0], [cx + h, cy + h, 0],
                     [cx + h, cy - h, 0], [cx - h, cy - h, 0]], dtype=np.float64)


def marker_object_points(size_mm):
    """Esquinas del marcador en su propio sistema (orden ArUco, requerido por IPPE_SQUARE)."""
    h = size_mm / 2.0
    return np.array([[-h, h, 0], [h, h, 0], [h, -h, 0], [-h, -h, 0]], dtype=np.float64)


def camera_matrix(f, width, height):
    return np.array([[f, 0, width / 2.0], [0, f, height / 2.0], [0, 0, 1.0]], dtype=np.float64)


# ==============================================================================
# CÁMARA Y MESA
# ==============================================================================
def estimate_focal(img_pts_list, obj_pts_list, width, height):
    """Focal [px] desde vistas de la plantilla (punto principal al centro, sin distorsión).

    Necesita que la plantilla se vea en perspectiva (no de frente). Devuelve None si no es fiable.
    """
    try:
        K0 = camera_matrix(0.8 * width, width, height)
        flags = (cv2.CALIB_USE_INTRINSIC_GUESS | cv2.CALIB_FIX_PRINCIPAL_POINT |
                 cv2.CALIB_FIX_ASPECT_RATIO | cv2.CALIB_ZERO_TANGENT_DIST |
                 cv2.CALIB_FIX_K1 | cv2.CALIB_FIX_K2 | cv2.CALIB_FIX_K3)
        obj = [np.asarray(o, np.float32).reshape(-1, 3) for o in obj_pts_list]
        img = [np.asarray(i, np.float32).reshape(-1, 1, 2) for i in img_pts_list]
        rms, K, _, _, _ = cv2.calibrateCamera(obj, img, (int(width), int(height)), K0,
                                              np.zeros(5), flags=flags)
        f = float(K[0, 0])
        if not (0.4 * width <= f <= 3.0 * width) or rms > 3.0:
            return None
        return f
    except cv2.error:
        return None


def solve_table_pose(img_pts, obj_pts, K, dist):
    """Pose mesa->cámara (R, t) con las esquinas de la plantilla. Devuelve (R, t, err_px) o None."""
    img = np.asarray(img_pts, np.float64).reshape(-1, 1, 2)
    obj = np.asarray(obj_pts, np.float64).reshape(-1, 3)
    if len(obj) < 4:
        return None
    try:
        n, rvecs, tvecs, errs = cv2.solvePnPGeneric(obj, img, K, dist, flags=cv2.SOLVEPNP_IPPE)
    except cv2.error:
        return None
    if n == 0:
        return None
    i = int(np.argmin(np.asarray(errs).ravel()))
    rvec, tvec = cv2.solvePnPRefineLM(obj, img, K, dist, rvecs[i].copy(), tvecs[i].copy())
    proj, _ = cv2.projectPoints(obj, rvec, tvec, K, dist)
    err = float(np.sqrt(np.mean(np.sum((proj.reshape(-1, 2) - img.reshape(-1, 2)) ** 2, axis=1))))
    R = cv2.Rodrigues(rvec)[0]
    t = tvec.ravel()
    if (-R.T @ t)[2] < 0:     # la cámara tiene que quedar del lado de la cara impresa (z > 0)
        return None
    return R, t, err


def marker_candidates(corners, size_mm, K, dist):
    """Las (hasta) 2 poses posibles del marcador en la cámara: lista de (R_cm, t_cm, err_px)."""
    img = np.asarray(corners, np.float64).reshape(4, 1, 2)
    try:
        n, rvecs, tvecs, errs = cv2.solvePnPGeneric(marker_object_points(size_mm), img, K, dist,
                                                    flags=cv2.SOLVEPNP_IPPE_SQUARE)
    except cv2.error:
        return []
    errs = np.asarray(errs).ravel()
    return [(cv2.Rodrigues(rvecs[i])[0], tvecs[i].ravel().astype(np.float64), float(errs[i]))
            for i in range(n)]


class TablePose:
    """Pose de la mesa en la cámara: X_cam = R @ X_mesa + t."""

    def __init__(self, R, t):
        self.R = np.asarray(R, np.float64)
        self.t = np.asarray(t, np.float64).ravel()
        self.C = -self.R.T @ self.t          # centro de la cámara en la mesa

    def to_table(self, R_cm, t_cm):
        return self.R.T @ R_cm, self.R.T @ (np.asarray(t_cm) - self.t)

    def candidates_in_table(self, cands):
        return [(*self.to_table(Rc, tc), e) for Rc, tc, e in cands]

    def project(self, X_table, K, dist):
        X = np.asarray(X_table, np.float64).reshape(-1, 3)
        rvec = cv2.Rodrigues(self.R)[0]
        p, _ = cv2.projectPoints(X, rvec, self.t, K, dist)
        return p.reshape(-1, 2)


# ==============================================================================
# CALIBRACIÓN DE PIVOTE
# ==============================================================================
def _solve_pivot_lstsq(Rs, ts):
    n = len(Rs)
    A = np.zeros((3 * n, 6))
    b = np.zeros(3 * n)
    for i in range(n):
        A[3 * i:3 * i + 3, :3] = Rs[i]
        A[3 * i:3 * i + 3, 3:] = -np.eye(3)
        b[3 * i:3 * i + 3] = -ts[i]
    x, *_ = np.linalg.lstsq(A, b, rcond=None)
    sv = np.linalg.svd(A, compute_uv=False)
    return x[:3], x[3:], sv


def _residuals(Rs, ts, p, q):
    return np.linalg.norm(np.einsum("nij,j->ni", Rs, p) + ts - q, axis=1)


def rotation_spread_deg(Rs):
    """Desvío (grados) de las rotaciones alrededor de su media en los 3 ejes principales."""
    Rs = np.asarray(Rs)
    U, _, Vt = np.linalg.svd(Rs.sum(axis=0))
    Rm = U @ Vt
    if np.linalg.det(Rm) < 0:
        U[:, -1] *= -1
        Rm = U @ Vt
    rv = np.array([cv2.Rodrigues(R @ Rm.T)[0].ravel() for R in Rs])
    sv = np.linalg.svd(rv - rv.mean(axis=0), compute_uv=False) / math.sqrt(len(Rs))
    max_angle = float(np.degrees(np.max(np.linalg.norm(rv, axis=1))))
    return np.degrees(sv), max_angle


def pivot_calibrate(samples, camera_center=None, min_samples=30, max_rms_mm=5.0,
                    min_spread_deg=4.0, offset_range_mm=(30.0, 350.0), scale_range=(0.75, 1.35)):
    """Calibración de pivote robusta.

    samples: por cada frame, la lista de poses candidatas del marcador EN LA MESA [(R, t, err)].
    camera_center: centro de la cámara en la mesa; si se da, se corrige la escala para que el
        punto de pivote quede sobre la mesa (z = 0), lo que compensa un tamaño de ArUco mal
        configurado.
    Devuelve dict: ok, reason, p_tip (sistema del marcador), pivot_mm (mesa), rms_mm, n,
        n_inliers, spread_deg, scale.
    """
    samples = [s for s in samples if len(s) > 0]
    n = len(samples)
    out = {"ok": False, "reason": "", "n": n, "n_inliers": 0}
    if n < min_samples:
        out["reason"] = f"pocas muestras ({n} < {min_samples}): se tiene que ver la mesa y el marcador"
        return out

    def run(init):
        if init == "err":
            choice = [int(np.argmin([c[2] for c in s])) for s in samples]
        else:                                   # continuidad temporal de la rotación
            choice = [int(np.argmin([c[2] for c in samples[0]]))]
            for s in samples[1:]:
                Rp = samples[len(choice) - 1][choice[-1]][0]
                choice.append(int(np.argmin([np.linalg.norm(c[0] - Rp) for c in s])))
        inl = np.ones(n, bool)
        p = q = None
        for _ in range(12):
            Rs = np.array([samples[i][choice[i]][0] for i in range(n)])
            ts = np.array([samples[i][choice[i]][1] for i in range(n)])
            if inl.sum() < 6:
                return None
            p, q, sv = _solve_pivot_lstsq(Rs[inl], ts[inl])
            new_choice = []
            res = np.empty(n)
            for i, s in enumerate(samples):
                r = [float(np.linalg.norm(c[0] @ p + c[1] - q)) for c in s]
                j = int(np.argmin(r))
                new_choice.append(j)
                res[i] = r[j]
            med = float(np.median(res))
            thr = max(3.0 * 1.4826 * med, 1.0)
            new_inl = res <= thr
            if new_choice == choice and np.array_equal(new_inl, inl):
                break
            choice, inl = new_choice, new_inl
        Rs = np.array([samples[i][choice[i]][0] for i in range(n)])
        ts = np.array([samples[i][choice[i]][1] for i in range(n)])
        p, q, sv = _solve_pivot_lstsq(Rs[inl], ts[inl])
        rms = float(np.sqrt(np.mean(_residuals(Rs[inl], ts[inl], p, q) ** 2)))
        return {"p": p, "q": q, "sv": sv, "rms": rms, "inl": inl, "Rs": Rs, "ts": ts}

    sols = [s for s in (run("err"), run("temporal")) if s is not None]
    if not sols:
        out["reason"] = "no se pudo resolver el pivote (demasiadas muestras inválidas)"
        return out
    sol = min(sols, key=lambda s: (0 if s["inl"].sum() >= 0.6 * n else 1, s["rms"]))
    inl, Rs, ts, p, q = sol["inl"], sol["Rs"], sol["ts"], sol["p"], sol["q"]
    out["n_inliers"] = int(inl.sum())

    spread, max_angle = rotation_spread_deg(Rs[inl])
    out["spread_deg"] = [float(v) for v in spread]
    out["max_angle_deg"] = max_angle

    # Corrección de escala (tamaño efectivo del ArUco): el punto de pivote debe estar en z = 0.
    k = 1.0
    if camera_center is not None:
        C = np.asarray(camera_center, np.float64)
        if abs(C[2] - q[2]) > 1e-6:
            k = float(C[2] / (C[2] - q[2]))
        ts = C + k * (ts - C)
        p, q, _ = _solve_pivot_lstsq(Rs[inl], ts[inl])
    rms = float(np.sqrt(np.mean(_residuals(Rs[inl], ts[inl], p, q) ** 2)))
    out.update({"p_tip": p, "pivot_mm": q, "rms_mm": rms, "scale": k,
                "cond": float(sol["sv"][-1] / sol["sv"][0]),
                "_Rs": Rs, "_ts": ts, "_inliers": inl})

    if out["n_inliers"] < max(min_samples, 0.6 * n):
        out["reason"] = (f"demasiadas muestras inconsistentes ({out['n_inliers']}/{n} válidas): "
                         "¿la punta resbaló?")
    elif spread[1] < min_spread_deg:
        out["reason"] = (f"inclinación insuficiente ({spread[0]:.0f}° / {spread[1]:.0f}°): inclina "
                         "hacia adelante/atrás Y hacia los costados")
    elif rms > max_rms_mm:
        out["reason"] = f"la punta se movió durante el pivoteo (residuo {rms:.1f} mm > {max_rms_mm:.1f} mm)"
    elif not (scale_range[0] <= k <= scale_range[1]):
        out["reason"] = (f"escala {k:.2f} fuera de rango: revisa 'tool_marker_mm' (lado del cuadrado "
                         "negro del ArUco de la herramienta) o que la punta esté apoyada en la hoja")
    elif not (offset_range_mm[0] <= np.linalg.norm(p) <= offset_range_mm[1]):
        out["reason"] = f"distancia punta-marcador {np.linalg.norm(p):.0f} mm fuera de rango"
    else:
        out["ok"] = True
    return out


def pivot_calibrate_raw(raw_corners, table_img_pts, table_obj_pts, marker_mm, width, height,
                        K=None, dist=None, f0=None, sample_times=None, imu_history=None, **kw):
    """Pivote a partir de los datos crudos (esquinas del ArUco por frame + esquinas de la mesa).

    Si K es None se busca además la focal (desde f0) que minimiza el residuo del pivote.
    Si se pasan sample_times e imu_history (ImuHistory) se intenta la fusión con el IMU.
    Devuelve el dict de pivot_calibrate más: K, dist, focal_px, marker_mm_eff y "imu" (dict o None).
    """
    r = _pivot_calibrate_raw_cam(raw_corners, table_img_pts, table_obj_pts, marker_mm, width,
                                 height, K, dist, f0, **kw)
    r["imu"] = None
    if r.get("ok") and sample_times is not None and imu_history is not None and len(imu_history) > 10:
        r["imu"] = fit_imu_fusion(r, sample_times, imu_history)
    return r


def _pivot_calibrate_raw_cam(raw_corners, table_img_pts, table_obj_pts, marker_mm, width, height,
                             K=None, dist=None, f0=None, **kw):
    def run(Kx, dx):
        tp = solve_table_pose(table_img_pts, table_obj_pts, Kx, dx)
        if tp is None:
            return None
        pose = TablePose(tp[0], tp[1])
        samples = [pose.candidates_in_table(marker_candidates(c, marker_mm, Kx, dx))
                   for c in raw_corners]
        r = pivot_calibrate(samples, camera_center=pose.C, **kw)
        r["K"], r["dist"] = Kx, dx
        r["focal_px"] = float(Kx[0, 0])
        r["marker_mm_eff"] = marker_mm * r.get("scale", 1.0)
        return r

    if K is not None:
        r = run(np.asarray(K, np.float64), np.zeros(5) if dist is None else np.asarray(dist, np.float64))
        return r if r is not None else {"ok": False, "reason": "no se ve la mesa", "n": len(raw_corners)}

    f0 = f0 if f0 else 0.8 * width
    z = np.zeros(5)

    def score(r):
        return float("inf") if (r is None or "rms_mm" not in r) else r["rms_mm"]

    best = None
    for s in np.arange(0.6, 1.601, 0.05):
        r = run(camera_matrix(f0 * s, width, height), z)
        if best is None or score(r) < score(best):
            best = r
    if best is not None and "focal_px" in best:
        fb = best["focal_px"]
        for s in np.arange(-0.05, 0.0501, 0.01):
            r = run(camera_matrix(fb * (1 + s), width, height), z)
            if score(r) < score(best):
                best = r
    return best if best is not None else {"ok": False, "reason": "no se ve la mesa", "n": len(raw_corners)}


# ==============================================================================
# FUSIÓN CON EL IMU (inclinación)
# ==============================================================================
EZ = np.array([0.0, 0.0, 1.0])


def imu_up_vector(pitch_deg, roll_deg):
    """Vector 'arriba' en el sistema del IMU, inverso exacto de las fórmulas del firmware:
    pitch = atan2(az, -ay), roll = atan2(ax, sqrt(az^2 + ay^2))."""
    p, r = math.radians(pitch_deg), math.radians(roll_deg)
    return np.array([math.sin(r), -math.cos(r) * math.cos(p), math.cos(r) * math.sin(p)])


class ImuHistory:
    """Historial (tiempo de recepción, vector arriba) para alinear el IMU con los cuadros de cámara."""

    def __init__(self, seconds=30.0):
        self.seconds = seconds
        self.t = []
        self.u = []

    def __len__(self):
        return len(self.t)

    def add(self, t, pitch_deg, roll_deg):
        if self.t and t <= self.t[-1]:
            return
        self.t.append(t)
        self.u.append(imu_up_vector(pitch_deg, roll_deg))
        while self.t and self.t[-1] - self.t[0] > self.seconds:
            self.t.pop(0)
            self.u.pop(0)

    def at(self, t, max_gap=0.15):
        """Vector arriba interpolado al instante t (o None si no hay datos cercanos)."""
        if not self.t or t < self.t[0] - max_gap or t > self.t[-1] + max_gap:
            return None
        i = int(np.searchsorted(self.t, t))
        if i <= 0:
            return self.u[0]
        if i >= len(self.t):
            return self.u[-1]
        t0, t1 = self.t[i - 1], self.t[i]
        if t1 - t0 > max_gap:
            return None
        a = (t - t0) / (t1 - t0)
        v = (1 - a) * self.u[i - 1] + a * self.u[i]
        return v / np.linalg.norm(v)


def kabsch(a, b):
    """Rotación Q que minimiza sum ||Q a_i - b_i||^2 (a, b: (n,3))."""
    M = np.asarray(b).T @ np.asarray(a)
    U, _, Vt = np.linalg.svd(M)
    D = np.diag([1.0, 1.0, np.sign(np.linalg.det(U @ Vt))])
    return U @ D @ Vt


def correct_tilt(R, n_target):
    """Gira R (marcador->mesa) lo mínimo para que la vertical de la mesa vista desde el marcador
    sea n_target. Conserva el giro alrededor de la vertical (yaw) medido por la cámara."""
    n_cam = R.T @ EZ
    n_t = n_target / np.linalg.norm(n_target)
    axis = np.cross(n_t, n_cam)
    sa, ca = np.linalg.norm(axis), float(np.dot(n_t, n_cam))
    if sa < 1e-12:
        return R
    S = cv2.Rodrigues(axis / sa * math.atan2(sa, ca))[0]     # S @ n_t = n_cam
    return R @ S


def fit_imu_fusion(pivot, sample_times, imu_history, delays=np.arange(-0.10, 0.251, 0.01),
                   max_resid_deg=3.0, min_gain=0.8):
    """Ajusta la rotación IMU->marcador y el retardo con los datos del pivote.

    Devuelve dict: enabled, reason, Q (3x3), delay_s, resid_deg, p_tip, rms_mm (con fusión).
    """
    inl = pivot["_inliers"]
    Rs, ts = pivot["_Rs"][inl], pivot["_ts"][inl]
    times = np.asarray(sample_times, np.float64)[inl]
    n_cam = np.einsum("nji,j->ni", Rs, EZ)              # R^T e_z por muestra
    best = None
    for d in delays:
        u = [imu_history.at(t - d) for t in times]
        ok = np.array([v is not None for v in u])
        if ok.sum() < 0.8 * len(times):
            continue
        U = np.array([v for v in u if v is not None])
        Q = kabsch(U, n_cam[ok])
        ang = np.degrees(np.arccos(np.clip(np.einsum("ni,ni->n", (Q @ U.T).T, n_cam[ok]), -1, 1)))
        resid = float(np.sqrt(np.mean(ang ** 2)))
        if best is None or resid < best[0]:
            best = (resid, float(d), Q, ok, U)
    out = {"enabled": False, "reason": ""}
    if best is None:
        out["reason"] = "no hay datos del IMU durante el pivote"
        return out
    resid, d, Q, ok, U = best
    Rf = np.array([correct_tilt(R, Q @ u) for R, u in zip(Rs[ok], U)])
    p, q, _ = _solve_pivot_lstsq(Rf, ts[ok])
    rms_f = float(np.sqrt(np.mean(_residuals(Rf, ts[ok], p, q) ** 2)))
    rms_c = float(np.sqrt(np.mean(_residuals(Rs[ok], ts[ok], pivot["p_tip"], pivot["pivot_mm"]) ** 2)))
    out.update({"Q": Q, "delay_s": d, "resid_deg": resid, "p_tip": p, "rms_mm": rms_f,
                "rms_cam_mm": rms_c})
    if resid > max_resid_deg:
        out["reason"] = f"el IMU no coincide con la cámara (residuo {resid:.1f}°)"
    elif rms_f > min_gain * rms_c:
        out["reason"] = f"la fusión no mejora ({rms_f:.1f} vs {rms_c:.1f} mm)"
    else:
        out["enabled"] = True
    return out


# ==============================================================================
# SEGUIMIENTO EN TIEMPO REAL
# ==============================================================================
class OneEuroFilter:
    """Filtro adaptativo: suaviza mucho en reposo (quita el temblor) y poco en movimiento."""

    def __init__(self, min_cutoff=1.0, beta=0.03, d_cutoff=1.0):
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self.x = None
        self.dx = None
        self.t = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def reset(self, x=None, t=None):
        self.x = None if x is None else np.asarray(x, np.float64).copy()
        self.dx = None if x is None else np.zeros_like(self.x)
        self.t = t

    def __call__(self, x, t):
        x = np.asarray(x, np.float64)
        if self.x is None or self.t is None:
            self.reset(x, t)
            return self.x.copy()
        dt = max(t - self.t, 1e-3)
        self.t = t
        dx = (x - self.x) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        self.dx = a_d * dx + (1 - a_d) * self.dx
        cutoff = self.min_cutoff + self.beta * float(np.linalg.norm(self.dx))
        a = self._alpha(cutoff, dt)
        self.x = a * x + (1 - a) * self.x
        return self.x.copy()


class TipTracker:
    """Elige la pose correcta del marcador y devuelve la punta filtrada en la mesa.

    p_tip: punta en el sistema del marcador (solo cámara).
    p_tip_fused: punta calibrada con la inclinación del IMU (si la fusión está habilitada).
    """

    def __init__(self, p_tip, p_tip_fused=None, z_plausible_mm=80.0, jump_mm=35.0,
                 confirm_frames=3, min_cutoff=0.8, beta=0.03, median_window=5):
        self.median_window = median_window
        self.max_ambiguous_frames = 15
        self.ambiguous_run = 0
        self.recent = []
        self.p = np.asarray(p_tip, np.float64)
        self.p_fused = None if p_tip_fused is None else np.asarray(p_tip_fused, np.float64)
        self.z_plausible = z_plausible_mm
        self.jump = jump_mm
        self.confirm = confirm_frames
        self.filter = OneEuroFilter(min_cutoff=min_cutoff, beta=beta)
        self.last_R = None
        self.pending = 0
        self.tip = None
        self.mode = "camara"

    def is_ambiguous(self, cands_table, err_ratio=0.6, min_angle_deg=6.0):
        """True si las dos poses tienen error de reproyección parecido y vertical distinta."""
        if len(cands_table) < 2:
            return False
        (R0, _, e0), (R1, _, e1) = sorted(cands_table, key=lambda c: c[2])[:2]
        if e1 <= 1e-9 or e0 / e1 < err_ratio:
            return False
        ang = math.degrees(math.acos(float(np.clip(np.dot(R0.T @ EZ, R1.T @ EZ), -1, 1))))
        return ang > min_angle_deg

    def reset(self):
        self.filter.reset()
        self.ambiguous_run = 0
        self.recent = []
        self.last_R = None
        self.pending = 0
        self.tip = None

    def select(self, cands_table, n_imu=None):
        """Devuelve (indice, R) de la pose más coherente.

        Con IMU: la que tiene la vertical más parecida a la del IMU. Sin IMU: menor error de
        reproyección, continuidad de la rotación y punta cerca de la mesa.
        """
        best, best_cost = None, float("inf")
        for i, (R, t, err) in enumerate(cands_table):
            if n_imu is not None:
                cost = float(np.degrees(np.arccos(np.clip(np.dot(R.T @ EZ, n_imu), -1, 1)))) + 2.0 * err
            else:
                tip = R @ self.p + t
                cost = 8.0 * err + 0.2 * abs(tip[2])
                if abs(tip[2]) > self.z_plausible:
                    cost += 1000.0
                if self.last_R is not None:
                    cost += 20.0 * float(np.linalg.norm(R - self.last_R))
            if cost < best_cost:
                best, best_cost = i, cost
        return best

    def update(self, cands_table, t_now, n_imu=None):
        """Procesa un frame. n_imu: vertical de la mesa en el sistema del marcador según el IMU
        (Q @ u), o None. Devuelve (punta_filtrada, punta_cruda, indice) o (None, None, None)."""
        if not cands_table:
            return None, None, None
        use_imu = n_imu is not None and self.p_fused is not None
        idx = self.select(cands_table, n_imu if use_imu else None)
        R, t, _ = cands_table[idx]
        if not use_imu and self.tip is not None and self.is_ambiguous(cands_table):
            # Marcador casi de frente: las dos poses posibles son igual de probables y la
            # inclinación no se puede medir con la cámara. No se usa el cuadro (se mantiene la
            # última punta), salvo que dure demasiado.
            self.ambiguous_run += 1
            if self.ambiguous_run <= self.max_ambiguous_frames:
                self.mode = "camara (cuadro ambiguo descartado)"
                return self.tip.copy(), None, idx
        else:
            self.ambiguous_run = 0
        self.last_R = R
        if use_imu:
            raw = correct_tilt(R, n_imu) @ self.p_fused + t
            self.mode = "camara+IMU"
        else:
            raw = R @ self.p + t
            self.mode = "camara"
        if self.tip is not None and np.linalg.norm(raw - self.tip) > self.jump:
            self.pending += 1                       # salto brusco: esperar confirmación
            if self.pending < self.confirm:
                return self.tip.copy(), raw, idx
            self.filter.reset()
            self.recent = []
        self.pending = 0
        # mediana corta (corta picos aislados de la pose) + filtro adaptativo (quita el temblor)
        self.recent.append(raw)
        if len(self.recent) > self.median_window:
            self.recent.pop(0)
        med = np.median(np.array(self.recent), axis=0)
        self.tip = self.filter(med, t_now)
        return self.tip.copy(), raw, idx
