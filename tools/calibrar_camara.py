#!/usr/bin/env python3
"""
ArcSim_VR - Calibración de la cámara con la plantilla A4 (OPCIONAL, una vez por webcam)
======================================================================================
Mide la focal y la distorsión de la lente. Sin este archivo, test_vision_table.py estima la
focal con la plantilla (suele alcanzar); con él, el seguimiento es más exacto en los bordes.

Uso:
  1. Ejecutar:  python tools/calibrar_camara.py
  2. Tomar la plantilla A4 (pegada sobre cartón rígido) con las manos y mostrarla a la cámara
     en distintas posiciones e INCLINACIONES (de frente, inclinada a la izquierda, derecha,
     arriba, abajo, cerca, lejos, en las esquinas de la imagen).
  3. [ESPACIO] en cada posición (se necesitan los 4 marcadores visibles). Mínimo 12 vistas.
  4. [C] para calcular y guardar tools/camera_intrinsics.json.   [Q] para salir.
Usar la misma cámara y resolución que el seguimiento (1280x720).
"""
import json
import os
import sys

import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tool_tracking import TABLE_MARKER_CENTERS_MM, table_marker_corners_3d

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "camera_intrinsics.json")


def main():
    cap = None
    for idx in (0, 1, 2):
        for api in (cv2.CAP_DSHOW, cv2.CAP_ANY):
            c = cv2.VideoCapture(idx, api)
            if c.isOpened() and c.read()[0]:
                cap = c
                break
            c.release()
        if cap is not None:
            break
    if cap is None:
        print("No se pudo abrir la camara.")
        return
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    det = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),
                                  cv2.aruco.DetectorParameters())
    views_img, views_obj = [], []
    msg = "Muestra la plantilla inclinada y presiona [ESPACIO]"
    size = None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        size = (frame.shape[1], frame.shape[0])
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = det.detectMarkers(gray)
        img, obj = [], []
        if ids is not None:
            for i, mid in enumerate(ids.flatten()):
                if int(mid) in TABLE_MARKER_CENTERS_MM:
                    c = cv2.cornerSubPix(gray, corners[i][0].reshape(-1, 1, 2).astype(np.float32), (5, 5), (-1, -1),
                                         (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.01))
                    img.append(c.reshape(-1, 2))
                    obj.append(table_marker_corners_3d(int(mid)))
                    cv2.polylines(frame, [c.reshape(-1, 2).astype(np.int32)], True, (0, 255, 0), 2)
        cv2.putText(frame, f"Vistas: {len(views_img)} (min 12) | marcadores: {len(img)}/4", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        cv2.putText(frame, msg, (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(frame, "[ESPACIO] capturar  [C] calcular y guardar  [Q] salir", (20, size[1] - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
        cv2.imshow("ArcSim_VR - Calibracion de camara", frame)
        k = cv2.waitKey(1) & 0xFF
        if k in (ord('q'), 27):
            break
        if k == ord(' '):
            if len(img) == 4:
                views_img.append(np.vstack(img).astype(np.float32))
                views_obj.append(np.vstack(obj).astype(np.float32))
                msg = f"Vista {len(views_img)} capturada. Cambia la inclinacion/posicion."
            else:
                msg = "Faltan marcadores: se tienen que ver los 4"
        if k in (ord('c'), ord('C')):
            if len(views_img) < 12:
                msg = f"Faltan vistas ({len(views_img)}/12)"
                continue
            flags = cv2.CALIB_FIX_K3 | cv2.CALIB_ZERO_TANGENT_DIST
            rms, K, dist, _, _ = cv2.calibrateCamera(views_obj, [v.reshape(-1, 1, 2) for v in views_img],
                                                     size, None, None, flags=flags)
            with open(OUT, "w") as f:
                json.dump({"width": size[0], "height": size[1], "K": K.tolist(),
                           "dist": dist.ravel().tolist(), "rms_px": float(rms),
                           "n_views": len(views_img)}, f, indent=2)
            print(f"Guardado {OUT}: f = {K[0, 0]:.0f} px, error de reproyeccion {rms:.2f} px")
            if rms > 1.0:
                print("AVISO: error alto (> 1 px). Repeti con la plantilla bien plana y mas vistas variadas.")
            msg = f"GUARDADO: f={K[0, 0]:.0f} px, error {rms:.2f} px. Recalibra el pivote [P]."
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
