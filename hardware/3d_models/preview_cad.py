#!/usr/bin/env python3
"""Genera preview_cad.png (cortes del modelo v3.0 con componentes). Requiere cadquery, trimesh, matplotlib."""
import sys, tempfile, os
from pathlib import Path
import numpy as np, trimesh, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import cadquery as cq
sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_holder_cad as g

tmp = tempfile.mkdtemp()
def to_mesh(wp, name):
    p = os.path.join(tmp, name + ".stl")
    cq.exporters.export(wp, p, exportType="STL", tolerance=0.05, angularTolerance=0.1)
    return trimesh.load(p)

right, left, shell = g.build_clamshell_halves()
pod = g.build_sensor_pod_tof(); rod = g.build_electrode_rod(60.0); aruco = g.build_aruco_mount()
body = trimesh.util.concatenate([to_mesh(right, "r"), to_mesh(left, "l")])
others = {"pod": (to_mesh(pod, "pod"), "#d9531e"), "rod": (to_mesh(rod, "rod"), "#8c8070"), "aruco": (to_mesh(aruco, "ar"), "#1f77b4")}
comps = {n: (to_mesh(s, n), tuple(c)) for n, (s, c) in g.build_components().items()}

def sec(mesh, axis, val):
    o = [0, 0, 0]; n = [0, 0, 0]; o[axis] = val; n[axis] = 1
    p = mesh.section(plane_origin=o, plane_normal=n)
    if p is None: return []
    return p.discrete
def plot(ax, axis, val, h, v, title, xlim=None, ylim=None, with_comps=True):
    for ln in sec(body, axis, val): ax.plot(ln[:, h], ln[:, v], color="#2c3e50", lw=1.2)
    for n, (m, c) in others.items():
        for ln in sec(m, axis, val): ax.plot(ln[:, h], ln[:, v], color=c, lw=1.2)
    if with_comps:
        for n, (m, c) in comps.items():
            for ln in sec(m, axis, val): ax.fill(ln[:, h], ln[:, v], color=c, alpha=0.45, lw=0.8)
    ax.set_aspect("equal"); ax.grid(alpha=.3); ax.set_title(title, fontsize=10, fontweight="bold")
    if xlim: ax.set_xlim(*xlim)
    if ylim: ax.set_ylim(*ylim)

fig, axs = plt.subplots(2, 3, figsize=(30, 14))
plot(axs[0,0], 0, 0.5, 2, 1, "1. Corte longitudinal X = +0.5 mm (largo total 250 mm, Ø54 mm)")
axs[0,0].set_xlabel("Z (mm)"); axs[0,0].set_ylabel("Y (mm)")
plot(axs[0,1], 0, -7.0, 2, 1, "2. Corte X = -7 mm (ESP32, motor Ø27, canales de cables, ducto)", xlim=(-100, 80), ylim=(-30, 40))
axs[0,1].set_xlabel("Z (mm)")
plot(axs[0,2], 0, 0.5, 2, 1, "3. Guarda y cabezal: LED RGB, pod ToF, MPU6050 y ArUco 48x48 (30°)", xlim=(45, 148), ylim=(-45, 82))
axs[0,2].set_xlabel("Z (mm)")
plot(axs[1,0], 2, g.MOTOR_Z + 0.37, 0, 1, f"4. Corte Z = {g.MOTOR_Z:.0f}: motor Ø27, canales de cables y plataformas")
axs[1,0].set_xlabel("X (mm)"); axs[1,0].set_ylabel("Y (mm)")
plot(axs[1,1], 2, g.LED_Z + 0.3, 0, 1, f"5. Corte Z = {g.LED_Z:.1f}: LED RGB saliendo por el guarda-mano")
axs[1,1].set_xlabel("X (mm)")
plot(axs[1,2], 2, -30.3, 0, 1, "6. Corte Z = -30: ESP32 (con pines) y tornillos de cierre")
axs[1,2].set_xlabel("X (mm)")
fig.suptitle("ArcSim_VR Portaelectrodo Final (250 mm, Ø54 mm, ArUco 48x48 a 30°) - Cortes e interferencias", fontsize=14, fontweight="bold")
plt.tight_layout()
out = Path(__file__).resolve().parent / "preview_cad.png"
plt.savefig(out, dpi=90); print("OK", out)
