#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera docs_referencia/figura_8_comparativa.png a partir de pasada_buena.csv y pasada_errores.csv."""

from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
CSV_GOOD = ROOT / "docs_referencia" / "pasada_buena.csv"
CSV_BAD = ROOT / "docs_referencia" / "pasada_errores.csv"
OUT_PNG = ROOT / "docs_referencia" / "figura_8_comparativa.png"


def parse_session_csv(path: Path):
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    summary = {}
    criteria = []
    series_header = None
    series_rows = []
    section = ""

    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("sep="):
            continue
        if s.startswith("# "):
            section = s[2:].strip().upper()
            continue
        parts = s.split(";")
        if section == "RESUMEN DEL EJERCICIO" and len(parts) >= 2:
            summary[parts[0]] = parts[1]
        elif section == "CRITERIOS" and parts[0] != "criterio" and len(parts) >= 3:
            criteria.append((parts[0], float(parts[2].replace(",", "."))))
        elif section.startswith("SERIE TEMPORAL"):
            if series_header is None:
                series_header = parts
            else:
                vals = [float(x.replace(",", ".")) for x in parts]
                series_rows.append(vals)

    arr = np.array(series_rows, dtype=float)
    cols = {name: arr[:, idx] for idx, name in enumerate(series_header)}
    return summary, criteria, cols


def main():
    sum_g, crit_g, col_g = parse_session_csv(CSV_GOOD)
    sum_b, crit_b, col_b = parse_session_csv(CSV_BAD)

    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Segoe UI", "Arial", "DejaVu Sans"],
        "font.size": 9.5,
        "axes.titlesize": 10.5,
        "axes.titleweight": "bold",
    })

    fig, axes = plt.subplots(2, 2, figsize=(11.6, 6.8), dpi=220)
    fig.patch.set_facecolor("#ffffff")

    c_good = "#15803d"
    c_bad = "#dc2626"

    # 1) Barras horizontales por criterio
    ax = axes[0, 0]
    short_names = [
        "Long. arco", "Velocidad", "Áng. trabajo", "Áng. avance", "Amperaje",
        "Trayectoria", "Ancho cordón", "Regularidad", "Penetración", "Cobertura"
    ]
    vals_g = [c[1] for c in crit_g]
    vals_b = [c[1] for c in crit_b]
    y = np.arange(len(short_names))
    h = 0.38
    ax.barh(y - h / 2, vals_g, height=h, color=c_good, alpha=0.88, label="Aprobada (7,2/10 — Bueno)")
    ax.barh(y + h / 2, vals_b, height=h, color=c_bad, alpha=0.85, label="Con errores (3,4/10 — Deficiente)")
    ax.axvline(60, color="#64748b", linestyle="--", linewidth=0.9, alpha=0.7)
    ax.set_yticks(y)
    ax.set_yticklabels(short_names, fontsize=8.5)
    ax.invert_yaxis()
    ax.set_xlim(0, 108)
    ax.set_xlabel("Puntaje del criterio (0 a 100 %)")
    ax.set_title("a) Desglose comparativo de los 10 criterios")
    ax.grid(axis="x", linestyle=":", alpha=0.5)
    ax.legend(loc="lower right", fontsize=8, framealpha=0.92)

    # Filtrar muestras con arco encendido
    mg = col_g["arco_encendido"] > 0.5
    mb = col_b["arco_encendido"] > 0.5

    # 2) Trayectoria sobre la junta
    ax = axes[0, 1]
    ax.axhspan(-1.5, 1.5, color="#bbf7d0", alpha=0.55, label="Banda óptima (±1,5 mm)")
    ax.axhline(0.0, color="#16a34a", linestyle="--", linewidth=0.9)
    ax.plot(col_g["posicion_avance_mm"][mg], col_g["desvio_lateral_mm"][mg], color=c_good, lw=1.8, label="Aprobada (desvío 2,6 mm)")
    ax.plot(col_b["posicion_avance_mm"][mb], col_b["desvio_lateral_mm"][mb], color=c_bad, lw=1.8, ls="--", label="Con errores (desvío 3,9 mm)")
    ax.set_xlim(0, 152)
    ax.set_xlabel("Posición a lo largo de la junta (mm)")
    ax.set_ylabel("Desvío lateral (mm)")
    ax.set_title("b) Trayectoria y centrado sobre la junta (150 mm)")
    ax.grid(True, linestyle=":", alpha=0.5)
    ax.legend(loc="lower right", fontsize=8, framealpha=0.92)

    # 3) Ancho del cordón a lo largo de la junta
    ax = axes[1, 0]
    ax.axhspan(4.5, 9.5, color="#bbf7d0", alpha=0.55, label="Banda óptima (4,5–9,5 mm)")
    ax.plot(col_g["posicion_avance_mm"][mg], col_g["ancho_cordon_mm"][mg], color=c_good, lw=1.7, label="Aprobada (media 6,67 mm — v=4,9 mm/s)")
    ax.plot(col_b["posicion_avance_mm"][mb], col_b["ancho_cordon_mm"][mb], color=c_bad, lw=1.7, ls="--", label="Con errores (media 3,63 mm — v=52,6 mm/s)")
    ax.set_xlim(0, 152)
    ax.set_ylim(0, 13.5)
    ax.set_xlabel("Posición a lo largo de la junta (mm)")
    ax.set_ylabel("Ancho del cordón (mm)")
    ax.set_title("c) Morfología: ancho del cordón vs. velocidad")
    ax.grid(True, linestyle=":", alpha=0.5)
    ax.legend(loc="upper right", fontsize=8, framealpha=0.92)

    # 4) Penetración estimada
    ax = axes[1, 1]
    ax.axhspan(1.8, 5.0, color="#bbf7d0", alpha=0.55, label="Banda óptima (1,8–5,0 mm)")
    ax.plot(col_g["posicion_avance_mm"][mg], col_g["penetracion_mm"][mg], color=c_good, lw=1.7, label="Aprobada (media 1,32 mm @ 125 A)")
    ax.plot(col_b["posicion_avance_mm"][mb], col_b["penetracion_mm"][mb], color=c_bad, lw=1.7, ls="--", label="Con errores (media 0,61 mm @ 95 A + sin careta)")
    ax.set_xlim(0, 152)
    ax.set_ylim(0, 4.2)
    ax.set_xlabel("Posición a lo largo de la junta (mm)")
    ax.set_ylabel("Penetración (mm)")
    ax.set_title("d) Penetración estimada en raíz")
    ax.grid(True, linestyle=":", alpha=0.5)
    ax.legend(loc="upper right", fontsize=8, framealpha=0.92)

    fig.suptitle(
        "Comparativa experimental de sesiones exportadas (.csv) — Nivel 1 (E6013 Ø3,2 mm, junta 1G de 150 mm)",
        fontsize=11.5,
        fontweight="bold",
        y=0.985,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.955])
    fig.savefig(OUT_PNG, dpi=220)
    print(f"[OK] Figura 8 guardada en {OUT_PNG} ({OUT_PNG.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
