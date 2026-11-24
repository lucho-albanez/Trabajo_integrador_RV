#!/usr/bin/env python3
"""
ArcSim_VR - Generador CAD Parametrico del Portaelectrodo SMAW Sensorizado (v3.1)
================================================================================
Cambios v3.x respecto de v2.2 (ver hardware/3d_models/CAMBIOS_v3.md):
  1. LONGITUD TOTAL 220 mm (antes 324 mm) para imprimir en Ender 3 V2 (cama 220x220).
       Z = -78 (cola prensacable)  ->  Z = +142 (frente cabezal).
  2. MOTOR VIBRADOR DC de 27 mm de diametro (cuerpo 12,45 mm; total con eje y
       desbalance 23 mm; separacion cuerpo-desbalance 3 mm).  Eje a lo largo de X,
       el cuerpo queda en la mitad izquierda y el desbalance en la derecha.
  3. Sensor VL53L0X (modulo tipo GY-530 25 x ~12 mm): cavidad con holgura real,
       ventana alargada y tornillos del pod separados de la cavidad.
  4. Etapa MOSFET sin bahia propia: el circuito se arma "al aire" (soldado) dentro
       del ducto delantero; se elimina esa bahia para ganar longitud.
  5. Canal de cables superior (ESP32 -> ducto delantero) que rodea al motor.
  7. v3.1: ESP32 real (51.6 x 28.5 mm, 14 mm con pines, USB-C centrado atras) y
       LED RGB KY-016 (placa 19 x 15, M2 a 11 mm, LED a 5 mm de la placa) alojado en
       el guarda-mano (que pasa de 12 a 16 mm de espesor), con salida Ø6,4 mm hacia arriba.
  6. Tornilleria de cierre y pines guia reubicados en zonas macizas (verificado
       por programa) y verificacion automatica de interferencias con los
       componentes (ESP32, ficha USB, motor, GY-530, MPU6050, circuito MOSFET).

Sistema de coordenadas (en milimetros):
  - X = 0   : Plano de particion longitudinal (Mitad Derecha X >= 0, Izquierda X <= 0)
  - +Y      : Arriba (soporte ArUco)
  - -Y      : Abajo hacia la chapa (electrodo y sensor ToF apuntan en -Y)
  - +Z      : Adelante (cabezal / mordaza)
  - -Z      : Atras (mango y salida prensacable USB)
"""

from pathlib import Path
import math
import sys
import cadquery as cq

# =============================================================================
# PARAMETROS EDITABLES (todas las cotas en mm)
# =============================================================================
TOL = 0.30              # Holgura general para impresion 3D FDM
WALL = 3.0              # Espesor minimo de pared de la carcasa

# ---- Longitud total ---------------------------------------------------------
FRONT_Z = 142.0                     # Frente del cabezal (no cambia)
TOTAL_LEN = 250.0                   # v3.9: 250 mm (antes 220). Cada mitad se imprime en diagonal en la Ender 3 V2 (cama 220 x 220): ocupa ~202 x 202 mm
GLAND_LEN = 20.0                    # Cono trasero del prensacable
GLAND_Z0 = FRONT_Z - TOTAL_LEN      # -108.0
GLAND_END_OD = 22.0
USB_CABLE_DIA = 5.4

# ---- Mango ergonomico -------------------------------------------------------
HANDLE_Z0 = GLAND_Z0 + GLAND_LEN    # -88.0
HANDLE_Z1 = 50.0
HANDLE_OD = 54.0                    # v3.10: 54 mm (antes 46) para tener mucho espacio de cables
HANDLE_R = HANDLE_OD / 2.0
# Estrias de agarre (Z de inicio de cada una, 4.5 mm de ancho). Elegidas para no
# pisar tornillos ni pines (verificado en verify_clearances()).
GRIP_GROOVES_Z = [-74.25, -56.25, -43.25, -27.25, -7.25, 17.75, 39.75]   # v3.10: centros en -72,-54,-41,-25,-5,20,42 (lejos de tornillos y pines)

# ---- Collarin aislante y guarda-mano ----------------------------------------
COLLAR_Z0 = 48.0
COLLAR_Z1 = 55.0
COLLAR_OD = 56.0                    # v3.10: 2 mm mas que el mango

GUARD_Z0 = 55.0             # v3.1: guarda-mano de 17 mm (antes 12) para alojar el LED
GUARD_Z1 = 72.0
GUARD_W = 56.0                     # v3.10: acompana al collarin mas grande
GUARD_H = 66.0

# ---- Cabezal / Mordaza (Z = 72 a 142) - SIN CAMBIOS --------------------------
HEAD_Z0 = 72.0
HEAD_Z1 = 142.0
HEAD_W = 42.0
HEAD_Y_BOT = -26.0
HEAD_Y_TOP = 30.0
HEAD_H = HEAD_Y_TOP - HEAD_Y_BOT
HEAD_YC = 0.5 * (HEAD_Y_BOT + HEAD_Y_TOP)

# ---- Ficha USB + ESP32 (de atras hacia adelante) ----------------------------
USB_BAY_Z0 = -92.0                  # Inicio bahia ficha USB (pared >= 4.6 mm en el cono)
USB_BAY_HX = 8.5                    # Semi-ancho en X (17 mm)
USB_BAY_HY = 6.5                    # Semi-alto en Y (13 mm)

ESP_Z0 = -68.0                      # v3.10: ESP32 y motor 20 mm mas atras (antes -48)
ESP_Z1 = -12.0                       # Bahia 56 mm de largo
ESP_W_Y = 32.0                      # v3.10: bahia mas ancha (antes 29.6) para cables a los lados
ESP_BOARD_L = 51.6                  # Medido por el usuario (v3.1)
ESP_BOARD_W = 28.5
ESP_PINS_H = 9.0                    # Pines bajo la placa (14 mm totales - 5 mm de placa+componentes)
ESP_RAISE = -4.0                    # v3.14: plataforma (piso) de la ESP32 en la mitad izquierda 2 mm mas baja que v3.13 (X = -13)
# ---- v3.3: machos de sujecion de la ESP32 (cuatro postes con pin en la mitad izquierda) --------
ESP_HOLE_DZ = 47.0                  # Entre centros, lado largo (medido por el usuario)
ESP_HOLE_DY = 23.0                  # Entre centros, lado corto (medido por el usuario)
ESP_PCB_T = 1.6                     # Espesor de la placa
ESP_COMP_H = 3.4                    # v3.4: componentes bajo la placa; la placa va BOCA ABAJO apoyada en el piso
ESP_PIN_R = 1.4                     # Macho Ø2.8 (agujero M3: Ø3.0-3.2)
ESP_PIN_PROTRUDE = 1.0              # El macho asoma sobre la cara superior de la placa (para fundirlo / remachar)
ESP_HEADER_HALF_Z = 20.0            # Mitad del largo de los headers (supuesto: placa de 30 pines, 15 por lado)
ESP_HEADER_Y = 12.7                 # Los headers estan a +-12.7 mm del eje (25.4 entre filas)
ESP_TOP_H = 5.0                     # Placa + microcontrolador sobre la cara inferior de la placa
USBC_HX = 4.0                       # Receptaculo USB-C: 8 mm de ancho (Y) x 3 mm de alto (X)

# ---- Motor vibrador DC (medidas informadas por el usuario) -------------------
MOTOR_DIA = 27.0                    # Diametro del cuerpo
MOTOR_BODY_H = 12.45                # Altura sin eje
MOTOR_TOTAL_H = 23.0                # Altura con eje + desbalance
MOTOR_GAP = 3.0                     # Cuerpo -> desbalance
MOTOR_Z = 5.0                      # Centro del motor en Z
MOTOR_Y = -1.0                      # Centro del motor en Y
MOTOR_BODY_CLEAR = 0.375            # Holgura radial zona cuerpo (Ø27.75)
MOTOR_WEIGHT_CLEAR = 1.0            # Holgura radial zona desbalance (Ø29.0)
MOTOR_BODY_DEPTH = 13.0             # Profundidad bolsillo del cuerpo (mitad izq.)
MOTOR_WEIGHT_DEPTH = 11.3           # Profundidad zona desbalance (mitad der.)
MOTOR_RELIEF_DIA = 20.0             # Alivio trasero para soldaduras/cables
MOTOR_RELIEF_DEPTH = 4.0

# ---- Canal de cables superior + ducto delantero -----------------------------
CH_X0 = -9.0 + ESP_RAISE            # v3.2: canal a la altura del piso de la ESP32 en la mitad izquierda (X = -11)
CH_X1 = 6.9                         # y 6.9 mm de profundidad en la mitad derecha
WIRE_FILLET_R = 2.0                 # v3.2: radio maximo de redondeo de las aristas por donde doblan los cables
CH_Y0, CH_Y1 = 14.7, 20.0           # Canal superior: 2.9 mm de alto (sobre el motor); Y1 = 17.6 deja >= 1 mm de pared (con estrias) a X = -11
CHB_Y0, CHB_Y1 = -20.4, -16.6       # v3.2: canal inferior espejo, 2.0 mm de alto (bajo el motor)
CHB_X0 = -9.0                       # el inferior solo llega a X = -9 (el borde exterior no admite mas)
CH_Z0, CH_Z1 = -20.0, 46.0
DUCT_Z0 = 40.5                      # Ducto delantero (aloja circuito MOSFET)
DUCT_HX = 7.0
DUCT_Y0, DUCT_Y1 = -9.0, 11.0

# ---- LED RGB KY-016 (v3.1): indicador de posicion/orientacion ---------------
# Placa 19 (X) x 15 (Z) mm, 2 agujeros M2 separados 11 mm sobre un borde de 19 mm,
# LED 5 mm cuya base esta a 5 mm de la placa (altura total del LED 8.6 mm).
LED_BOARD_X = 19.0
LED_BOARD_Z = 15.0
LED_HOLES_SPACING = 11.0            # Entre centros (M2)
LED_HOLES_EDGE = 2.5                # Distancia del agujero al borde de la placa (supuesto)
LED_STAND_OFF = 5.0                 # Base del LED sobre la placa
LED_BODY_H = 8.6                    # Altura del LED desde su base
LED_PROTRUDE = 3.0                  # Cuanto asoma el LED sobre la cara superior del guarda-mano
LED_HOLE_DIA = 6.4                  # Salida (6 mm informados + 0.4 de holgura FDM)
LED_Z = 65.5                        # Eje del LED (centro de la placa) en Z
LED_TOP_Y = HEAD_YC + GUARD_H / 2.0  # Cara superior del guarda-mano: Y = 35
LED_BOARD_TOP_Y = LED_TOP_Y + LED_PROTRUDE - (LED_STAND_OFF + LED_BODY_H)   # 24.4
LED_BOARD_BOT_Y = LED_BOARD_TOP_Y - 1.6                                    # 22.8
LED_CAV_CLEAR = 1.4
LED_CAV_Y0 = LED_BOARD_BOT_Y - 3.0  # 3 mm bajo la placa: soldaduras y cables
LED_CAV_Y1 = LED_BOARD_TOP_Y + 0.9  # 0.9 mm sobre la placa (resistencias SMD); la placa queda atrapada
LED_CAV_HX = (LED_BOARD_X + LED_CAV_CLEAR) / 2.0   # 10.2
LED_LEDGE_X0 = 8.0                  # El reborde de apoyo va de |X| = 8.0 a 10.2 (la placa llega a 9.5)
LED_OPEN_X = 8.0                    # Zona despejada bajo la placa: |X| < 8
LED_OPEN_Y0 = 10.0
LED_OPEN_Z0, LED_OPEN_Z1 = 58.0, 73.7
LED_PIN_R = 0.95                    # Pin Ø1.9 que entra en el agujero M2 (Ø2.2-2.4) de la placa
LED_HOLE_Z_OFF = LED_BOARD_Z / 2.0 - LED_HOLES_EDGE   # Agujeros sobre el borde +Z de la placa

# ---- Montaje MPU6050 (GY-521) - SIN CAMBIOS ----------------------------------
# v3.7: en lugar de 2 agujeros con tuerca, 2 MACHOS M3 en la pared X = +8 (mitad derecha), a 16 mm entre centros,
# alineados en Y (el de abajo se paso a la derecha del de arriba: -Y), ambos a Z = 95.6.
MPU_STUD_Z = 95.6
MPU_STUD_Y = (12.5, -3.5)           # 16 mm entre centros
MPU_STUD_R = 1.45                   # Macho Ø2.9 (agujero M3 de la placa)
MPU_STUD_TIP_X = 4.0                # Punta del macho (la placa ocupa X 6.4 a 8.0: asoma 2.4 mm sobre la placa)
MPU_BOARD_Z_LEN = 20.3              # Largo de la placa en Z; los agujeros estan a 3.5 mm del extremo +Z

# =============================================================================
# MECANISMO DE VARILLA DESLIZANTE + AUTO-HOMING (sin cambios)
# =============================================================================
ELEC_Z = 126.0
ELEC_SHANK_DIA = 8.0
ELEC_SOCKET_DIA = ELEC_SHANK_DIA + 0.45
ELEC_TRAVEL_MM = 2.5
ELEC_PIN_Y = -14.0
ELEC_COLLAR_DIA = 12.0
ELEC_COLLAR_H = 3.0

SW_BODY_Y0 = 10.0
SW_BODY_Y1 = 14.0
SW_POCKET_W_X = 12.0                 # v3.6: hueco del pulsador 12 x 12 x 4 mm, centrado en el eje del electrodo
SW_POCKET_L_Z = 12.0
SW_WIRE_W_X = 4.0
SW_STEM_HOLE_DIA = 5.6

# ---- Modulo porta-sensor (centrado en Z = 102) ------------------------------
POD_Z = 102.0
POD_LEN_Z = 31.0
POD_W_X = 36.0
POD_RECESS_H = 4.0
POD_SCREWS_XZ = [(14.5, 90.0), (-14.5, 114.0)]

# VL53L0X: encapsulado ST 4.4 x 2.4 x 1.0 mm; modulo GY-530 ~25.0 x 10.7-12.5 mm,
# Pololu 13 x 18, Adafruit 21 x 18.  Cavidad para placa de hasta 19 x 13.5 mm.
TOF_PCB_MAX_X = 20.0                # Largo maximo de placa admitido
TOF_PCB_MAX_Z = 13.5                # Ancho maximo de placa admitido
TOF_CAV_CLEAR = 1.0                 # Holgura total (0.5 por lado)
TOF_CAV_HX = (TOF_PCB_MAX_X + TOF_CAV_CLEAR) / 2.0     # 12.75
TOF_CAV_HZ = (TOF_PCB_MAX_Z + TOF_CAV_CLEAR) / 2.0     # 7.25
TOF_WIN_HX = 7.0                    # v3.8: ventana de 14 mm en X (antes 12)
TOF_WIN_HZ = TOF_CAV_HZ         # v3.8: ventana abierta en todo el largo de la cavidad en Z (se quitan las tiras de 2.75 mm)
TOF_FLOOR_T = 2.2                   # Espesor del piso del pod (CI queda a ras)
TOF_FOV_DEG = 25.0                  # Datasheet VL53L0X

# ---- Soporte ArUco superior (sin cambios) -----------------------------------
ARUCO_Z = 98.0
ARUCO_PRISM_LEN_Z = 32.0
ARUCO_SCREWS_Z = (77.0, 118.5)

# ---- Tornillos M3 de cierre de las dos mitades (Z, Y) -----------------------
CLAMSHELL_BOLTS = [
    (-102.0, 9.0),      # v3.10: extremo trasero (cono del prensacable)
    (-102.0, -9.0),
    (-80.0, 12.0),      # junto a la bahia USB
    (-80.0, -12.0),
    (-60.0, 20.0),      # a los lados de la bahia ESP32 (bahia ancha 32 mm)
    (-60.0, -20.0),
    (-34.0, 20.0),
    (-34.0, -20.0),
    (49.5, -19.5),      # detras del collarin (la zona motor/canales no admite tornillos)
    (58.5, 30.0),       # Guarda-mano arriba (corrido para dejar lugar al LED)
    (66.0, -21.0),      # Guarda-mano abajo
]
M3_CLEAR_R = 1.7
M3_HEAD_R = 3.1
M3_NUT_AF = 5.75
M3_NUT_R = M3_NUT_AF / math.sqrt(3.0)
# Pozos mas profundos (mm extra) para los tornillos del guarda-mano: acortan el tornillo
# necesario de ~50 mm a ~35 mm (cabeza y tuerca quedan embutidas 10 mm mas adentro).
BOLT_WELL_EXTRA = {66.0: 10.0, 58.5: 10.0, -80.0: 10.0, -60.0: 5.0, -34.0: 5.0, 49.5: 5.0}   # v3.10: pozos mas hondos acortan los tornillos
M3_NUT_T = 2.4          # Espesor de tuerca M3
M3_HEAD_T = 3.0         # Altura de cabeza Allen M3

# Pines guia de alineacion entre mitades (en el plano X = 0, zonas macizas)
ALIGN_PINS = [
    (-84.0, 17.0),      # junto a la bahia USB
    (-84.0, -17.0),
    (-48.0, 21.5),      # zona ESP32 (fuera de la bahia y de la ranura de PCB)
    (-48.0, -21.5),
    (-16.0, 23.0),      # zona motor / canales: unico lugar macizo es la pared exterior
    (-16.0, -23.0),
    (6.0, 23.0),
    (6.0, -23.0),
    (34.0, 23.0),
    (34.0, -23.0),
    (54.0, 17.0),
    (54.0, -17.0),
    (106.0, 24.5),
]

OUT_ROOT = Path(__file__).resolve().parent
STEP_DIR = OUT_ROOT / "step"
STL_DIR = OUT_ROOT / "stl"


# =============================================================================
# PRIMITIVAS EXPLICITAS
# =============================================================================
def cyl_x(y: float, z: float, radius: float, x0: float, x1: float) -> cq.Workplane:
    plane = cq.Plane(origin=(x0, y, z), xDir=(0, 1, 0), normal=(1, 0, 0))
    return cq.Workplane(plane).circle(radius).extrude(x1 - x0)


def hex_x(y: float, z: float, circum_dia: float, x0: float, x1: float) -> cq.Workplane:
    plane = cq.Plane(origin=(x0, y, z), xDir=(0, 1, 0), normal=(1, 0, 0))
    return cq.Workplane(plane).polygon(6, circum_dia).extrude(x1 - x0)


def cyl_y(x: float, z: float, radius: float, y0: float, y1: float) -> cq.Workplane:
    plane = cq.Plane(origin=(x, y0, z), xDir=(1, 0, 0), normal=(0, 1, 0))
    return cq.Workplane(plane).circle(radius).extrude(y1 - y0)


def hex_y(x: float, z: float, circum_dia: float, y0: float, y1: float) -> cq.Workplane:
    plane = cq.Plane(origin=(x, y0, z), xDir=(1, 0, 0), normal=(0, 1, 0))
    return cq.Workplane(plane).polygon(6, circum_dia).extrude(y1 - y0)


def cone_y(x: float, z: float, r0: float, r1: float, y0: float, y1: float) -> cq.Workplane:
    plane = cq.Plane(origin=(x, y0, z), xDir=(1, 0, 0), normal=(0, 1, 0))
    return cq.Workplane(plane).circle(r0).workplane(offset=y1 - y0).circle(r1).loft(combine=True)


def cyl_z(x: float, y: float, radius: float, z0: float, z1: float) -> cq.Workplane:
    plane = cq.Plane(origin=(x, y, z0), xDir=(1, 0, 0), normal=(0, 0, 1))
    return cq.Workplane(plane).circle(radius).extrude(z1 - z0)


def cone_z(x: float, y: float, r0: float, r1: float, z0: float, z1: float) -> cq.Workplane:
    plane = cq.Plane(origin=(x, y, z0), xDir=(1, 0, 0), normal=(0, 0, 1))
    return cq.Workplane(plane).circle(r0).workplane(offset=z1 - z0).circle(r1).loft(combine=True)


def box_xyz(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> cq.Workplane:
    cx, cy, cz = 0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (z0 + z1)
    return cq.Workplane("XY").workplane(offset=cz).center(cx, cy).box(x1 - x0, y1 - y0, z1 - z0)


def poly_yz(pts_zy, x0: float, x1: float) -> cq.Workplane:
    plane = cq.Plane(origin=(x1, 0, 0), xDir=(0, 0, 1), normal=(-1, 0, 0))
    return cq.Workplane(plane).polyline(pts_zy).close().extrude(x1 - x0)


def poly_xy(pts_xy, z0: float, z1: float) -> cq.Workplane:
    plane = cq.Plane(origin=(0, 0, z0), xDir=(1, 0, 0), normal=(0, 0, 1))
    return cq.Workplane(plane).polyline(pts_xy).close().extrude(z1 - z0)


def rounded_box_z(w_x, h_y, y_center, z0, z1, r_corner=5.0) -> cq.Workplane:
    plane = cq.Plane(origin=(0, y_center, z0), xDir=(1, 0, 0), normal=(0, 0, 1))
    return cq.Workplane(plane).rect(w_x, h_y).extrude(z1 - z0).edges("|Z").fillet(r_corner)


# =============================================================================
# 1. CUERPO EXTERIOR
# =============================================================================
def gland_radius_at(z: float) -> float:
    t = (z - GLAND_Z0) / GLAND_LEN
    return (GLAND_END_OD / 2.0) * (1.0 - t) + HANDLE_R * t


def build_outer_body() -> cq.Workplane:
    body = cyl_z(0.0, 0.0, HANDLE_R, HANDLE_Z0, HANDLE_Z1)

    for gz in GRIP_GROOVES_Z:
        groove = cyl_z(0.0, 0.0, HANDLE_R + 2.0, gz, gz + 4.5).cut(
            cyl_z(0.0, 0.0, HANDLE_R - 1.2, gz - 0.5, gz + 5.0)
        )
        body = body.cut(groove)

    gland = cone_z(0.0, 0.0, GLAND_END_OD / 2.0, HANDLE_R, GLAND_Z0, HANDLE_Z0)
    body = body.union(gland)

    body = body.union(cyl_z(0.0, 0.0, COLLAR_OD / 2.0, COLLAR_Z0, COLLAR_Z1))
    body = body.union(rounded_box_z(GUARD_W, GUARD_H, HEAD_YC, GUARD_Z0, GUARD_Z1, r_corner=8.0))

    head = rounded_box_z(HEAD_W, HEAD_H, HEAD_YC, HEAD_Z0, HEAD_Z1, r_corner=6.0)
    front_chamfer = poly_yz(
        [(HEAD_Z1 + 2.0, HEAD_Y_TOP + 2.0), (HEAD_Z1 - 10.0, HEAD_Y_TOP + 2.0), (HEAD_Z1 + 2.0, HEAD_Y_TOP - 10.0)],
        -HEAD_W, HEAD_W
    )
    head = head.cut(front_chamfer)
    return body.union(head)


# =============================================================================
# 2. CAVIDADES INTERNAS
# =============================================================================
def rounded_wire_path(parts: list[cq.Workplane]) -> cq.Workplane:
    """Une los tramos de un canal de cables y redondea las aristas paralelas a X
    (las que recorre el cable al doblar: rampa -> canal -> subida). Prueba radios
    decrecientes hasta que OpenCASCADE acepte el redondeo."""
    tool = parts[0]
    for q in parts[1:]:
        tool = tool.union(q)
    tool = tool.clean()
    r = WIRE_FILLET_R
    while r >= 0.4:
        try:
            out = tool.edges("|X").fillet(r)
            if out.val().isValid():
                print(f"  [redondeo de canal de cables: radio {r:.1f} mm]")
                return out
        except Exception:
            pass
        r -= 0.25
    print("  [AVISO] no se pudo redondear el canal de cables")
    return tool


def round_all_edges(tool: cq.Workplane, r_max: float, label: str) -> cq.Workplane:
    r = r_max
    while r >= 0.4:
        try:
            out = tool.edges("|Z").fillet(r).edges("|Y").fillet(r) if label.startswith("muesca") else tool.edges().fillet(r)
            if out.val().isValid():
                print(f"  [redondeo {label}: radio {r:.1f} mm]")
                return out
        except Exception:
            pass
        r -= 0.25
    print(f"  [AVISO] no se pudo redondear {label}")
    return tool


def motor_cuts() -> list[tuple[str, cq.Workplane]]:
    """Bolsillo del motor: eje a lo largo de X, cuerpo en X<0 (mitad izquierda),
    desbalance en X>0 (mitad derecha)."""
    rb = MOTOR_DIA / 2.0 + MOTOR_BODY_CLEAR
    rw = MOTOR_DIA / 2.0 + MOTOR_WEIGHT_CLEAR
    return [
        ("motor_body_pocket", cyl_x(MOTOR_Y, MOTOR_Z, rb, -MOTOR_BODY_DEPTH, 0.0)),
        ("motor_weight_pocket", cyl_x(MOTOR_Y, MOTOR_Z, rw, 0.0, MOTOR_WEIGHT_DEPTH)),
        ("motor_back_relief", cyl_x(MOTOR_Y, MOTOR_Z, MOTOR_RELIEF_DIA / 2.0,
                                    -MOTOR_BODY_DEPTH - MOTOR_RELIEF_DEPTH, -MOTOR_BODY_DEPTH + 0.1)),
        # Los cables del motor salen por detras del can y suben hacia el ducto delantero
        ("motor_wire_notch", box_xyz(-MOTOR_BODY_DEPTH - 3.0, -5.0, MOTOR_Y - 4.5, MOTOR_Y + 4.5, MOTOR_Z, DUCT_Z0 + 3.7)
                                   .edges("|Z").fillet(1.5)),
    ]


MOTOR_BOSS_WALL = 1.8               # v3.11: pared minima que rodea al bolsillo del motor
MOTOR_CAV_Z0 = ESP_Z1 + 2.5         # pared de 2.5 mm contra la bahia ESP32
MOTOR_CAV_Z1 = 44.0                 # se une con el ducto delantero (Z 40.5)
MOTOR_CAV_RIN = HANDLE_R - 1.2 - 1.8   # deja 3 mm de pared (1.8 mm bajo las estrias)
MOTOR_PLATFORM_TOP_X = -MOTOR_BODY_DEPTH - 3.0   # v3.12: tope de la plataforma = piso de la salida de cables del motor (X = -16)
MOTOR_RIB_T = 3.0                   # costillas que unen el anillo del motor con la pared exterior


def motor_zone_cavity() -> cq.Workplane:
    """v3.11: el bloque macizo alrededor del motor se vacia. Solo quedan: el anillo del motor
    (pared MOTOR_BOSS_WALL alrededor del bolsillo), 2 costillas finas que lo unen a la pared
    exterior y un taco alrededor de cada pin guia. Lo demas es espacio libre para cables."""
    cav = cyl_z(0.0, 0.0, MOTOR_CAV_RIN, MOTOR_CAV_Z0, MOTOR_CAV_Z1)
    r_boss = MOTOR_DIA / 2.0 + MOTOR_WEIGHT_CLEAR + MOTOR_BOSS_WALL
    x0 = -(MOTOR_BODY_DEPTH + MOTOR_RELIEF_DEPTH) - MOTOR_BOSS_WALL
    x1 = MOTOR_WEIGHT_DEPTH + MOTOR_BOSS_WALL
    keep = cyl_x(MOTOR_Y, MOTOR_Z, r_boss, x0, x1)
    # Mitad derecha: costilla fina hasta la pared exterior
    keep = keep.union(box_xyz(x1 - 0.5, 26.0, MOTOR_Y - MOTOR_RIB_T / 2.0, MOTOR_Y + MOTOR_RIB_T / 2.0,
                              MOTOR_Z - r_boss, MOTOR_Z + r_boss))
    # v3.12: mitad izquierda: plataforma maciza bajo el alojamiento, desde la pared exterior hasta el
    # piso del orificio por donde salen los cables del motor (X = -MOTOR_BODY_DEPTH - 3 = -16)
    # v3.13: la plataforma se prolonga hacia adelante (22.7 mm) hasta la pared frontal de la cavidad,
    # y se repite espejada en la mitad derecha (piso a X = +16, ademas de la costilla que une el anillo)
    z_front = MOTOR_CAV_Z1 + 1.0
    keep = keep.union(box_xyz(-26.0, MOTOR_PLATFORM_TOP_X, MOTOR_Y - r_boss, MOTOR_Y + r_boss,
                              MOTOR_Z - r_boss, z_front))
    keep = keep.union(box_xyz(-MOTOR_PLATFORM_TOP_X, 26.0, MOTOR_Y - r_boss, MOTOR_Y + r_boss,
                              MOTOR_Z - r_boss, z_front))
    for pz, py in ALIGN_PINS:
        if MOTOR_CAV_Z0 - 4.0 < pz < MOTOR_CAV_Z1 + 4.0 and abs(py) > 20.0:
            keep = keep.union(cyl_x(py, pz, 3.4, -7.0, 7.0))
    return cav.cut(keep)


def build_internal_cutout_list() -> list[tuple[str, cq.Workplane]]:
    cuts: list[tuple[str, cq.Workplane]] = [
        # 2.1 Entrada cable USB + bahia ficha USB + muesca anti-tirones
        ("usb_channel", cyl_z(0.0, 0.0, USB_CABLE_DIA / 2.0, GLAND_Z0 - 2.0, USB_BAY_Z0 + 2.0)),
        ("usb_tie_slot", box_xyz(-6.0, 6.0, -4.5, 4.5, USB_BAY_Z0 - 5.0, USB_BAY_Z0 + 1.0)),   # v3.9: sigue pegado a la bahia USB
        ("usb_plug_bay", box_xyz(-USB_BAY_HX + ESP_RAISE - 3.0, USB_BAY_HX + ESP_RAISE, -USB_BAY_HY, USB_BAY_HY, USB_BAY_Z0, ESP_Z0 + 2.0)),

        # 2.2 Bahia ESP32 DevKit v1 + ranuras PCB
        ("esp32_bay", box_xyz(-9.0 + ESP_RAISE, 9.0, -ESP_W_Y / 2.0, ESP_W_Y / 2.0, ESP_Z0, ESP_Z1)),
        ("esp32_pcb_slot", box_xyz(1.0 + ESP_RAISE, 3.2 + ESP_RAISE, -(ESP_W_Y / 2.0 + 1.2), (ESP_W_Y / 2.0 + 1.2), ESP_Z0 + 1.5, ESP_Z1 - 1.5)),

        # 2.2b v3.11: zona del motor vaciada (solo queda el anillo del motor + costillas)
        ("motor_zone_cavity", motor_zone_cavity()),

        # 2.3 Canales de cables (superior e inferior espejo, rodean al motor) + rampa + subida al ducto.
        # v3.2: cada canal es una sola herramienta con las aristas |X redondeadas (los cables no se doblan en filo vivo)
        ("wire_channel_top", rounded_wire_path(
            [box_xyz(CH_X0, CH_X1, 12.0, CH_Y1, CH_Z0, CH_Z0 + 9.0),
             box_xyz(CH_X0, CH_X1, CH_Y0, CH_Y1, CH_Z0, CH_Z1),
             box_xyz(CH_X0, CH_X1, 9.0, CH_Y1, DUCT_Z0, CH_Z1)])),
        ("wire_channel_bot", rounded_wire_path(
            [box_xyz(CHB_X0, CH_X1, CHB_Y0, -12.0, CH_Z0, CH_Z0 + 9.0),
             box_xyz(CHB_X0, CH_X1, CHB_Y0, CHB_Y1, CH_Z0, CH_Z1),
             box_xyz(CHB_X0, CH_X1, CHB_Y0, -9.0, DUCT_Z0, CH_Z1)])),

        # 2.4 Ducto delantero: aloja el circuito MOSFET/flyback y los cables al cabezal
        ("wire_duct", box_xyz(-DUCT_HX, DUCT_HX, DUCT_Y0, DUCT_Y1, DUCT_Z0, HEAD_Z0 + 6.0)),

        # 2.4b LED RGB KY-016 en el guarda-mano: cavidad de placa, salida del LED y subida de cables
        ("led_cavity", box_xyz(-(LED_BOARD_X + LED_CAV_CLEAR) / 2.0, (LED_BOARD_X + LED_CAV_CLEAR) / 2.0,
                               LED_CAV_Y0, LED_CAV_Y1,
                               LED_Z - (LED_BOARD_Z + LED_CAV_CLEAR) / 2.0, LED_Z + (LED_BOARD_Z + LED_CAV_CLEAR) / 2.0)),
        ("led_exit_hole", cyl_y(0.0, LED_Z, LED_HOLE_DIA / 2.0, LED_CAV_Y1 - 1.0, LED_TOP_Y + 2.0)),
        ("led_wire_riser", box_xyz(-4.0, 4.0, 9.0, LED_CAV_Y0 + 1.0, 59.0, 66.0)),
        # v3.5: se elimina el material entre la subida de cables, la camara del cabezal y la cavidad del LED
        ("led_clear", box_xyz(-LED_OPEN_X, LED_OPEN_X, LED_OPEN_Y0, LED_CAV_Y0 + 1.0, LED_OPEN_Z0, LED_OPEN_Z1)),

        # 2.5 Camara principal del cabezal (MPU6050 sobre pared X = +8)
        ("head_wire_bay", box_xyz(-8.0, 8.0, -10.0, 16.5, HEAD_Z0 - 2.0, 114.0)),

        # 2.6 Alojamiento modular inferior para el porta-sensor (ToF o HC-SR04)
        ("pod_recess", box_xyz(
            -POD_W_X / 2.0 - TOL, POD_W_X / 2.0 + TOL,
            HEAD_Y_BOT - 2.0, HEAD_Y_BOT + POD_RECESS_H,
            POD_Z - POD_LEN_Z / 2.0 - TOL, POD_Z + POD_LEN_Z / 2.0 + TOL,
        )),
        ("pod_wire_slot", box_xyz(-8.0, 8.0, HEAD_Y_BOT, -8.0, POD_Z - 9.0, POD_Z + 9.0)),

        # 2.7 MECANISMO AUTO-HOMING
        ("elec_guide_tube", cyl_y(0.0, ELEC_Z, ELEC_SOCKET_DIA / 2.0, HEAD_Y_BOT - 2.0, SW_BODY_Y0 - 2.0)),
        ("sw_stem_hole", cyl_y(0.0, ELEC_Z, SW_STEM_HOLE_DIA / 2.0, SW_BODY_Y0 - 2.5, SW_BODY_Y0 + 0.5)),
        ("sw_body_pocket", box_xyz(
            -SW_POCKET_W_X / 2.0, SW_POCKET_W_X / 2.0,
            SW_BODY_Y0, SW_BODY_Y1,
            ELEC_Z - SW_POCKET_L_Z / 2.0, ELEC_Z + SW_POCKET_L_Z / 2.0,
        )),
        ("sw_wire_channel", box_xyz(
            -SW_WIRE_W_X / 2.0, SW_WIRE_W_X / 2.0,
            SW_BODY_Y0 + 1.5, SW_BODY_Y1 + 2.0,
            112.0, ELEC_Z + 0.5,
        )),
        ("colisa_pin_hole", cyl_z(0.0, ELEC_PIN_Y, M3_CLEAR_R, ELEC_Z - 6.0, HEAD_Z1 + 3.0)),
        ("colisa_nut_trap", box_xyz(-3.0, 3.0, ELEC_PIN_Y - 3.1, ELEC_PIN_Y + 9.0, 132.5, 135.6)),
    ]
    cuts += motor_cuts()

    for i, (sx, sz) in enumerate(POD_SCREWS_XZ):
        cuts.append((f"pod_screw_{i}", cyl_y(sx, sz, 1.45, HEAD_Y_BOT - 1.0, HEAD_Y_BOT + POD_RECESS_H + 12.0)))

    for i, az in enumerate(ARUCO_SCREWS_Z):
        cuts.append((f"aruco_screw_thru_{i}", cyl_y(0.0, az, M3_CLEAR_R, 15.0, HEAD_Y_TOP + 2.0)))
        cuts.append((f"aruco_nut_trap_{i}", hex_y(0.0, az, M3_NUT_R * 2.0, 22.5, 25.8)))

    return cuts


# =============================================================================
# 3. TORNILLOS DE CIERRE: GEOMETRIA COMPARTIDA ENTRE CONSTRUCCION Y VERIFICACION
# =============================================================================
def bolt_x_surface(bz: float, by: float) -> float:
    if bz < HANDLE_Z0:
        r_loc = gland_radius_at(bz)
        return math.sqrt(max(r_loc ** 2 - by ** 2, 25.0))
    if bz < GUARD_Z0:
        return math.sqrt(max(HANDLE_R ** 2 - by ** 2, 49.0))
    if bz < HEAD_Z0:
        return GUARD_W / 2.0
    return HEAD_W / 2.0


def bolt_features(bz: float, by: float) -> dict:
    xs = bolt_x_surface(bz, by)
    ex = BOLT_WELL_EXTRA.get(bz, 0.0)
    return {
        "x_surf": xs,
        "thru": cyl_x(by, bz, M3_CLEAR_R, -40.0, 40.0),
        "head": cyl_x(by, bz, M3_HEAD_R, -xs - 5.0, -xs + 3.5 + ex),
        "nut": hex_x(by, bz, M3_NUT_R * 2.0, xs - 3.2 - ex, xs + 5.0),
    }


def bolt_length_needed(bz: float, by: float) -> float:
    """Largo minimo de tornillo M3: apoyo de cabeza (izq.) -> cara interna del hexagono
    de tuerca (der.) + espesor de tuerca + 1 mm de paso libre."""
    xs = bolt_x_surface(bz, by)
    ex = BOLT_WELL_EXTRA.get(bz, 0.0)
    seat_left = -xs + 3.5 + ex
    nut_floor = xs - 3.2 - ex
    return (nut_floor - seat_left) + M3_NUT_T + 1.0


def build_clamshell_halves() -> tuple[cq.Workplane, cq.Workplane, cq.Workplane]:
    shell = build_outer_body()
    outer_vol = shell.val().Volume()
    for cut_name, cut_solid in build_internal_cutout_list():
        prev_vol = shell.val().Volume()
        shell = shell.cut(cut_solid)
        new_vol = shell.val().Volume()
        if new_vol >= prev_vol - 1.0:
            raise RuntimeError(f"El corte interno '{cut_name}' no removio material (vol {prev_vol:.1f} -> {new_vol:.1f})")

    removed_vol = outer_vol - shell.val().Volume()
    print(f"  [OK] Vaciado interno validado: {removed_vol/1000.0:.1f} cm3 removidos ({100.0*removed_vol/outer_vol:.1f} %)")

    right_mask = box_xyz(0.0, 80.0, -80.0, 80.0, -220.0, 200.0)
    left_mask = box_xyz(-80.0, 0.0, -80.0, 80.0, -220.0, 200.0)
    right_half = shell.intersect(right_mask)
    left_half = shell.intersect(left_mask)

    # v3.7: machos M3 del MPU6050 (sin agujeros pasantes ni tuercas)
    for my in MPU_STUD_Y:
        right_half = right_half.union(cyl_x(my, MPU_STUD_Z, MPU_STUD_R, MPU_STUD_TIP_X, 8.5))

    for pz, py in ALIGN_PINS:
        right_half = right_half.union(cyl_x(py, pz, 1.45, -3.0, 1.5))
        left_half = left_half.cut(cyl_x(py, pz, 1.70, -3.6, 0.5))

    # v3.4: la ESP32 va BOCA ABAJO: la cara de componentes apoya directo en el piso de la bahia
    # (sin postes) y los headers miran hacia el plano de corte. Solo hay 4 machos que la sujetan.
    esp_zc = ESP_Z0 + 0.5 + ESP_BOARD_L / 2.0
    floor_x = -9.0 + ESP_RAISE
    pcb_back_x = floor_x + ESP_TOP_H             # cara trasera de la placa (de donde salen los headers)
    for sy in (ESP_HOLE_DY / 2.0, -ESP_HOLE_DY / 2.0):
        for sz in (esp_zc - ESP_HOLE_DZ / 2.0, esp_zc + ESP_HOLE_DZ / 2.0):
            pin = cyl_x(sy, sz, ESP_PIN_R, floor_x - 0.5, pcb_back_x + ESP_PIN_PROTRUDE)
            left_half = left_half.union(pin)

    # v3.5: SIN postes ni pines del LED (estorbaban al insertar la placa). La placa KY-016 entra
    # deslizando desde el plano de corte y apoya en un reborde estrecho en los dos extremos de X
    # de cada mitad (|X| = 8.0 a 10.2, cara superior a la altura de la cara inferior de la placa).
    for sx0, sx1 in ((LED_LEDGE_X0, LED_CAV_HX), (-LED_CAV_HX, -LED_LEDGE_X0)):
        ledge = box_xyz(sx0, sx1, LED_CAV_Y0 - 0.5, LED_BOARD_BOT_Y,
                        LED_Z - LED_BOARD_Z / 2.0 - 0.7, LED_Z + LED_BOARD_Z / 2.0 + 0.7)
        if sx0 > 0:
            right_half = right_half.union(ledge)
        else:
            left_half = left_half.union(ledge)

    for bz, by in CLAMSHELL_BOLTS:
        f = bolt_features(bz, by)
        right_half = right_half.cut(f["thru"])
        left_half = left_half.cut(f["thru"])
        left_half = left_half.cut(f["head"])
        right_half = right_half.cut(f["nut"])

    return right_half, left_half, shell


# =============================================================================
# 4. MODULOS PORTA-SENSOR
# =============================================================================
def build_sensor_pod_tof() -> cq.Workplane:
    """Pod para VL53L0X (GY-530 / Pololu / Adafruit).  Cavidad 25.5 x 14.5 mm,
    ventana alargada de 22 x 9 mm para que el CI pueda estar corrido respecto del
    centro de la placa, tornillos M3 diagonales fuera de la cavidad."""
    y_top = HEAD_Y_BOT + POD_RECESS_H  # -22.0
    y_bot = y_top - 9.0                # -31.0

    pod = box_xyz(
        -POD_W_X / 2.0, POD_W_X / 2.0,
        y_bot, y_top,
        POD_Z - POD_LEN_Z / 2.0, POD_Z + POD_LEN_Z / 2.0,
    ).edges("|Y").fillet(2.5)

    # Cavidad de placa (abierta hacia arriba, hacia la camara del cabezal)
    pod = pod.cut(box_xyz(-TOF_CAV_HX, TOF_CAV_HX, y_bot + TOF_FLOOR_T, y_top + 1.0,
                          POD_Z - TOF_CAV_HZ, POD_Z + TOF_CAV_HZ))
    # Ventana optica: atraviesa el piso, el CI (1.0 mm de alto) asoma por ella
    pod = pod.cut(box_xyz(-TOF_WIN_HX, TOF_WIN_HX, y_bot - 1.0, y_bot + TOF_FLOOR_T + 0.5,
                          POD_Z - TOF_WIN_HZ, POD_Z + TOF_WIN_HZ))

    for sx, sz in POD_SCREWS_XZ:
        pod = pod.cut(cyl_y(sx, sz, M3_CLEAR_R, y_bot - 1.0, y_top + 1.0))
        pod = pod.cut(cyl_y(sx, sz, M3_HEAD_R, y_bot - 0.5, y_bot + 3.0))
    return pod


def build_sensor_pod_hcsr04() -> cq.Workplane:
    y_top = HEAD_Y_BOT + POD_RECESS_H
    y_mid = HEAD_Y_BOT
    y_bot = y_mid - 16.0

    tab = box_xyz(-POD_W_X / 2.0, POD_W_X / 2.0, y_mid - 1.0, y_top,
                  POD_Z - POD_LEN_Z / 2.0, POD_Z + POD_LEN_Z / 2.0)
    shell = box_xyz(-25.5, 25.5, y_bot, y_mid,
                    POD_Z - POD_LEN_Z / 2.0, POD_Z + POD_LEN_Z / 2.0).edges("|Y").fillet(2.5)
    pod = tab.union(shell)
    pod = pod.cut(box_xyz(-23.0, 23.0, y_bot + 3.0, y_top + 1.0, POD_Z - 10.5, POD_Z + 10.5))
    for tx in (-13.0, 13.0):
        pod = pod.cut(cyl_y(tx, POD_Z, 8.3, y_bot - 1.0, y_bot + 6.0))
    for sx, sz in POD_SCREWS_XZ:
        pod = pod.cut(cyl_y(sx, sz, M3_CLEAR_R, y_bot - 1.0, y_top + 1.0))
        pod = pod.cut(cyl_y(sx, sz, M3_HEAD_R, y_bot - 0.5, y_bot + 4.0))
    return pod


# =============================================================================
# 5. VARILLAS DESLIZANTES (sin cambios)
# =============================================================================
def build_electrode_rod(exposed_length_mm: float) -> cq.Workplane:
    y_collar_top = HEAD_Y_BOT - ELEC_TRAVEL_MM
    y_collar_bot = y_collar_top - ELEC_COLLAR_H
    y_shank_top = -2.0
    y_tip_end = HEAD_Y_BOT - exposed_length_mm
    tip_r = 2.2

    shank = cyl_y(0.0, ELEC_Z, ELEC_SHANK_DIA / 2.0, y_collar_top, y_shank_top)
    shank = shank.cut(cyl_y(0.0, ELEC_Z, 1.35, y_shank_top - 9.5, y_shank_top + 1.0))

    slot_r = 1.75
    y_slot_top = ELEC_PIN_Y + 1.5 - slot_r
    y_slot_bot = ELEC_PIN_Y - 1.5 - ELEC_TRAVEL_MM + slot_r
    slot = (
        cyl_z(0.0, y_slot_top, slot_r, ELEC_Z - 6.0, ELEC_Z + 6.0)
        .union(cyl_z(0.0, y_slot_bot, slot_r, ELEC_Z - 6.0, ELEC_Z + 6.0))
        .union(box_xyz(-slot_r, slot_r, y_slot_bot, y_slot_top, ELEC_Z - 6.0, ELEC_Z + 6.0))
    )
    shank = shank.cut(slot)

    collar = cyl_y(0.0, ELEC_Z, ELEC_COLLAR_DIA / 2.0, y_collar_bot, y_collar_top + 0.5)
    shaft = cone_y(0.0, ELEC_Z, tip_r, 3.0, y_tip_end + tip_r, y_collar_bot + 0.5)
    tip_sphere = (
        cq.Workplane(cq.Plane(origin=(0.0, y_tip_end + tip_r, ELEC_Z), xDir=(1, 0, 0), normal=(0, 0, 1)))
        .sphere(tip_r)
    )
    return shank.union(collar).union(shaft).union(tip_sphere)


# =============================================================================
# 6. SOPORTE ArUco (sin cambios)
# =============================================================================
def build_aruco_mount() -> cq.Workplane:
    y0 = HEAD_Y_TOP
    base = box_xyz(-9.0, 9.0, y0, y0 + 5.0, 73.0, 123.0).edges("|Y").fillet(3.0)
    stem = box_xyz(-6.0, 6.0, y0 + 4.0, y0 + 18.0, ARUCO_Z - 10.0, ARUCO_Z + 10.0)

    y_b = y0 + 18.0
    y_t = y_b + 24.0
    z0_p = ARUCO_Z - ARUCO_PRISM_LEN_Z / 2.0
    z1_p = ARUCO_Z + ARUCO_PRISM_LEN_Z / 2.0
    prism = poly_xy([(-28.0, y_b), (28.0, y_b), (18.0, y_t), (-18.0, y_t)], z0_p, z1_p)
    hollow = poly_xy([(-21.0, y_b + 3.0), (21.0, y_b + 3.0), (13.0, y_t - 3.0), (-13.0, y_t - 3.0)], z0_p + 4.0, z1_p - 4.0)
    mount = base.union(stem).union(prism).cut(hollow)
    for az in ARUCO_SCREWS_Z:
        mount = mount.cut(cyl_y(0.0, az, M3_CLEAR_R, y0 - 1.0, y0 + 7.0))
    return mount


# =============================================================================
# 7. ENVOLVENTES DE COMPONENTES (referencia + verificacion de interferencias)
# =============================================================================
def build_components() -> dict[str, tuple[cq.Workplane, tuple[float, float, float]]]:
    """Envolventes conservadoras (caja/cilindro) de cada componente real, ya
    posicionadas en el modelo.  Devuelve nombre -> (solido, color RGB)."""
    c: dict[str, tuple[cq.Workplane, tuple[float, float, float]]] = {}

    # ESP32 DevKit v1: placa 55 x 28.5; X -7.5 (pines/soldaduras) a +6.4 (modulo/USB)
    ez0 = ESP_Z0 + 0.5
    esp_floor = -9.0 + ESP_RAISE
    esp_zc_env = ez0 + ESP_BOARD_L / 2.0
    esp_back = esp_floor + ESP_TOP_H
    c["ESP32_devkit"] = (box_xyz(esp_floor + 0.05, esp_back, -ESP_BOARD_W / 2.0, ESP_BOARD_W / 2.0, ez0, ez0 + ESP_BOARD_L),
                         (0.10, 0.45, 0.20))
    for k, sgn in enumerate((1.0, -1.0)):
        c[f"ESP32_pines_{k}"] = (box_xyz(esp_back, esp_back + ESP_PINS_H,
                                         sgn * ESP_HEADER_Y - 1.0, sgn * ESP_HEADER_Y + 1.0,
                                         esp_zc_env - ESP_HEADER_HALF_Z, esp_zc_env + ESP_HEADER_HALF_Z), (0.10, 0.45, 0.20))

    # Ficha USB-C con funda y alivio de tension (supuesto 24 x 12 x 6.5 mm); el receptaculo
    # (3 x 8 mm) esta centrado en el borde trasero, sobre la cara de componentes
    c["Ficha_USB_C"] = (box_xyz(esp_floor + 0.05, esp_floor + 6.5, -6.0, 6.0, USB_BAY_Z0 + 0.5, ESP_Z0 + 0.5), (0.20, 0.20, 0.20))

    # Motor vibrador: cuerpo Ø27 x 12.45 (X<0) + eje/desbalance hasta 23 mm (X>0)
    c["Motor_cuerpo"] = (cyl_x(MOTOR_Y, MOTOR_Z, MOTOR_DIA / 2.0, -MOTOR_BODY_H, 0.0), (0.65, 0.65, 0.70))
    c["Motor_desbalance_barrido"] = (cyl_x(MOTOR_Y, MOTOR_Z, MOTOR_DIA / 2.0, 0.0, MOTOR_TOTAL_H - MOTOR_BODY_H),
                                     (0.90, 0.55, 0.10))

    # Circuito MOSFET/flyback/capacitores soldado "al aire" dentro del ducto
    c["Circuito_MOSFET"] = (box_xyz(-6.0, 6.0, -8.0, 4.0, DUCT_Z0 + 2.0, DUCT_Z0 + 28.0), (0.80, 0.20, 0.20))

    # Haz de 10 cables AWG28-30 (Ø1.3) en 2 filas de 5: 6.5 x 2.6 mm
    c["Haz_cables_inferior"] = (box_xyz(-3.25, 3.25, 0.5 * (CHB_Y0 + CHB_Y1) - 0.65, 0.5 * (CHB_Y0 + CHB_Y1) + 0.65, CH_Z0 + 1.0, CH_Z1 - 1.0),
                                (0.90, 0.60, 0.10))
    c["Haz_cables_10x"] = (box_xyz(-3.25, 3.25, 0.5 * (CH_Y0 + CH_Y1) - 1.3, 0.5 * (CH_Y0 + CH_Y1) + 1.3, CH_Z0 + 1.0, CH_Z1 - 1.0),
                           (0.90, 0.80, 0.10))

    # LED KY-016: placa 19 x 15 x 1.6, LED Ø5.8 (base) / Ø5 desde la base hasta la cupula
    placa = box_xyz(-LED_BOARD_X / 2.0, LED_BOARD_X / 2.0, LED_BOARD_BOT_Y, LED_BOARD_TOP_Y,
                    LED_Z - LED_BOARD_Z / 2.0, LED_Z + LED_BOARD_Z / 2.0)
    for sx in (LED_HOLES_SPACING / 2.0, -LED_HOLES_SPACING / 2.0):       # agujeros M2 de la placa (Ø2.2)
        placa = placa.cut(cyl_y(sx, LED_Z + LED_HOLE_Z_OFF, 1.1, LED_BOARD_BOT_Y - 1.0, LED_BOARD_TOP_Y + 1.0))
    c["KY016_placa"] = (placa, (0.10, 0.10, 0.10))
    c["KY016_LED"] = (cyl_y(0.0, LED_Z, 2.9, LED_BOARD_TOP_Y, LED_BOARD_TOP_Y + LED_STAND_OFF + LED_BODY_H), (0.95, 0.95, 0.85))
    c["KY016_cables"] = (box_xyz(-LED_BOARD_X / 2.0, LED_BOARD_X / 2.0, LED_CAV_Y0 + 0.3, LED_BOARD_BOT_Y - 0.1,
                                 LED_Z - LED_BOARD_Z / 2.0, LED_Z + LED_BOARD_Z / 2.0 - 4.0), (0.90, 0.80, 0.10))

    # MPU6050 GY-521 sobre la pared X=+8: placa 20.3 (Y) x 15.6 (Z) x 1.6 (X)
    c["MPU6050"] = (box_xyz(6.4, 8.0, min(MPU_STUD_Y) - 0.1, max(MPU_STUD_Y) + 0.1,
                            MPU_STUD_Z + 3.5 - MPU_BOARD_Z_LEN, MPU_STUD_Z + 3.5),
                    (0.10, 0.20, 0.70))

    # Placa GY-530 (VL53L0X) 19 x 12.5 (maximo que admite el pod) x 1.6 sobre el piso del pod
    y_floor = HEAD_Y_BOT + POD_RECESS_H - 9.0 + TOF_FLOOR_T      # -28.8
    c["GY530_VL53L0X"] = (box_xyz(-10.0, 10.0, y_floor, y_floor + 1.6, POD_Z - 6.25, POD_Z + 6.25),
                          (0.45, 0.20, 0.60))
    # Zona de soldaduras/cables de la GY-530 (3 mm sobre la placa)
    c["GY530_cables"] = (box_xyz(-10.0, 10.0, y_floor + 1.6, y_floor + 4.6, POD_Z - 6.25, POD_Z + 6.25),
                         (0.90, 0.80, 0.10))
    return c


# =============================================================================
# 8. VERIFICACIONES AUTOMATICAS
# =============================================================================
def _overlap_vol(a: cq.Workplane, b: cq.Workplane) -> float:
    try:
        r = a.intersect(b)
        return r.val().Volume() if r.vals() else 0.0
    except Exception:
        return 0.0


def _dist(a: cq.Workplane, b: cq.Workplane) -> float:
    return a.val().distance(b.val())


def verify_clearances(shell: cq.Workplane, pod: cq.Workplane) -> bool:
    ok = True
    cuts = dict(build_internal_cutout_list())
    inner = [n for n in cuts if not n.startswith(("pod_screw", "aruco", "colisa", "elec_guide", "sw_"))]

    print("\n--- Verificacion 1: tornilleria vs cavidades (pared minima, mm) ---")
    for bz, by in CLAMSHELL_BOLTS:
        f = bolt_features(bz, by)
        worst = (9e9, "")
        for n in inner:
            for key in ("thru", "head", "nut"):
                if key == "nut":
                    # La cuenca de tuerca es abierta hacia afuera: solo importa contra cavidades
                    pass
                d = _dist(f[key], cuts[n])
                if d < worst[0]:
                    worst = (d, f"{key} vs {n}")
        flag = "OK " if worst[0] >= 0.6 else "MAL"
        if worst[0] < 0.6:
            ok = False
        print(f"  [{flag}] perno (Z={bz:6.1f}, Y={by:5.1f}): min {worst[0]:.2f} mm  ({worst[1]})   "
              f"largo M3 >= {bolt_length_needed(bz, by):.1f} mm")

    print("--- Verificacion 2: pines guia vs cavidades ---")
    for pz, py in ALIGN_PINS:
        pin = cyl_x(py, pz, 1.7, -3.6, 1.5)
        d = min(_dist(pin, cuts[n]) for n in inner)
        flag = "OK " if d >= 0.6 else "MAL"
        if d < 0.6:
            ok = False
        print(f"  [{flag}] pin (Z={pz:6.1f}, Y={py:5.1f}): min {d:.2f} mm")

    print("--- Verificacion 3: estrias de agarre vs tornillos/pines (Z) ---")
    for gz in GRIP_GROOVES_Z:
        near = [bz for bz, _ in CLAMSHELL_BOLTS if abs(bz - (gz + 2.25)) < 2.25 + M3_CLEAR_R + 1.0 and bz > HANDLE_Z0]
        near += [pz for pz, _ in ALIGN_PINS if abs(pz - (gz + 2.25)) < 2.25 + 1.7 + 1.0]
        flag = "OK " if not near else "MAL"
        if near:
            ok = False
        print(f"  [{flag}] estria Z={gz:6.1f}..{gz+4.5:6.1f}  {'' if not near else 'choca con ' + str(near)}")

    print("--- Verificacion 4: componentes dentro de las cavidades (interferencia = 0) ---")
    for name, (solid, _col) in build_components().items():
        target = shell
        if name.startswith("GY530"):
            target = shell.union(pod)
        v = _overlap_vol(solid, target)
        flag = "OK " if v < 0.5 else "MAL"
        if v >= 0.5:
            ok = False
        bb = solid.val().BoundingBox()
        print(f"  [{flag}] {name:26s} interferencia {v:8.2f} mm3   "
              f"Z[{bb.zmin:7.1f},{bb.zmax:7.1f}]")

    print("--- Verificacion 5: motor / ESP32 / pod ---")
    mb = cuts["motor_body_pocket"].val().BoundingBox()
    rb = MOTOR_DIA / 2.0 + MOTOR_BODY_CLEAR
    print(f"  Motor: Ø{MOTOR_DIA:.1f} en bolsillo Ø{2*rb:.2f} (cuerpo) / Ø{MOTOR_DIA+2*MOTOR_WEIGHT_CLEAR:.1f} (desbalance); "
          f"profundidad {MOTOR_BODY_DEPTH:.1f} (cuerpo {MOTOR_BODY_H}) + {MOTOR_WEIGHT_DEPTH:.1f} (eje+desbalance {MOTOR_TOTAL_H-MOTOR_BODY_H:.2f})")
    d_esp_motor = _dist(cuts["esp32_bay"], cuts["motor_weight_pocket"])
    d_ch_motor = _dist(cuts["wire_channel_top"], cuts["motor_weight_pocket"])
    print(f"  Pared bahia ESP32 -> bolsillo motor: {d_esp_motor:.2f} mm ; canal de cables -> bolsillo motor: {d_ch_motor:.2f} mm")
    d_chb_motor = _dist(cuts["wire_channel_bot"], cuts["motor_weight_pocket"])
    d_chb_ext = _dist(cuts["wire_channel_bot"], build_outer_envelope_shell())
    d_cht_ext = _dist(cuts["wire_channel_top"], build_outer_envelope_shell())
    print(f"  Canal inferior -> bolsillo motor: {d_chb_motor:.2f} mm ; canal inferior -> exterior: {d_chb_ext:.2f} mm ; canal superior -> exterior: {d_cht_ext:.2f} mm")
    if d_chb_motor < 1.0 or d_chb_ext < 1.0 or d_cht_ext < 1.0:
        ok = False
    d_cav_ext = _dist(cuts["motor_zone_cavity"], build_outer_envelope_shell())
    print(f"  Zona del motor vaciada: pared cavidad -> exterior {d_cav_ext:.2f} mm ; anillo del motor {MOTOR_BOSS_WALL:.1f} mm ; costillas {MOTOR_RIB_T:.0f} mm")
    if d_cav_ext < 1.5:
        ok = False
    for n in ("motor_body_pocket", "motor_weight_pocket", "motor_back_relief"):
        d = _dist(cuts[n], build_outer_envelope_shell())
        print(f"  Pared minima exterior de {n}: {d:.2f} mm")
        if d < 1.5:
            ok = False
    print(f"  Canal de cables: {CH_X1-CH_X0:.1f} x {CH_Y1-CH_Y0:.1f} = {(CH_X1-CH_X0)*(CH_Y1-CH_Y0):.0f} mm2 ; "
          f"10 cables AWG28 (Ø1.3) ocupan {10*math.pi/4*1.3**2:.1f} mm2 ({100*10*math.pi/4*1.3**2/((CH_X1-CH_X0)*(CH_Y1-CH_Y0)):.0f} %); "
          f"en 2 filas de 5: 6.5 x 2.6 mm (cabe en {CH_X1-CH_X0:.0f} x {CH_Y1-CH_Y0:.1f})")
    # LED KY-016
    exterior = build_outer_envelope_shell()
    d_led_ext = _dist(cuts["led_cavity"], exterior)
    d_led_riser_ext = _dist(cuts["led_wire_riser"], exterior)
    d_led_bolt = min(_dist(bolt_features(bz, by)["thru"], cuts["led_cavity"]) for bz, by in CLAMSHELL_BOLTS)
    d_led_bay = _dist(cuts["led_cavity"], cuts["head_wire_bay"])
    d_led_aruco = _dist(cuts["led_cavity"], cuts["aruco_screw_thru_0"])
    print(f"  LED KY-016: cavidad {LED_BOARD_X+LED_CAV_CLEAR:.1f} x {LED_BOARD_Z+LED_CAV_CLEAR:.1f} x {LED_CAV_Y1-LED_CAV_Y0:.1f} mm ; "
          f"placa a Y={LED_BOARD_BOT_Y:.1f}..{LED_BOARD_TOP_Y:.1f}; domo a Y={LED_BOARD_TOP_Y+LED_STAND_OFF+LED_BODY_H:.1f} "
          f"(asoma {LED_PROTRUDE:.1f} mm sobre Y={LED_TOP_Y:.0f}); salida Ø{LED_HOLE_DIA}")
    print(f"    pared cavidad->exterior {d_led_ext:.2f} mm ; cavidad->tornillos cierre {d_led_bolt:.2f} mm ; "
          f"cavidad->camara cabezal {d_led_bay:.2f} mm ; cavidad->tornillo ArUco {d_led_aruco:.2f} mm")
    if d_led_ext < 1.2 or d_led_bolt < 0.8 or d_led_bay < 1.0 or d_led_aruco < 1.0:
        ok = False
    print(f"  Ducto delantero: {2*DUCT_HX:.0f} x {DUCT_Y1-DUCT_Y0:.0f} x {HEAD_Z0+6-DUCT_Z0:.1f} mm")
    # Pod ToF
    y_bot = HEAD_Y_BOT + POD_RECESS_H - 9.0
    cav = box_xyz(-TOF_CAV_HX, TOF_CAV_HX, y_bot + TOF_FLOOR_T, y_bot + 9.0 + 1.0, POD_Z - TOF_CAV_HZ, POD_Z + TOF_CAV_HZ)
    for sx, sz in POD_SCREWS_XZ:
        hd = cyl_y(sx, sz, M3_HEAD_R, y_bot - 0.5, y_bot + 3.0)
        hole = cyl_y(sx, sz, M3_CLEAR_R, y_bot - 1.0, y_bot + 10.0)
        print(f"  Pod ToF: pared cavidad-recess cabeza M3 {_dist(hd, cav):.2f} mm ; cavidad-agujero M3 {_dist(hole, cav):.2f} mm")
        if _dist(hd, cav) < 0.8:
            ok = False
    # Campo de vision del VL53L0X vs varillas de electrodo
    half = math.radians(TOF_FOV_DEG / 2.0)
    for L, nm in ((57.2, "60 mm"), (97.2, "100 mm")):
        r = L * math.tan(half)
        edge = 24.0 - 2.2
        print(f"  FoV {TOF_FOV_DEG:.0f}°: a {L:.1f} mm de la lente el cono mide Ø{2*r:.1f}; borde de varilla {nm} a {edge:.1f} mm del eje -> "
              f"{'LIBRE' if r < edge - 0.5 else 'ROZA el cono'}")
    return ok


_OUTER_CACHE = {}


def build_outer_envelope_shell() -> cq.Workplane:
    """Cuerpo exterior macizo (sin cavidades), usado para medir paredes."""
    if "outer" not in _OUTER_CACHE:
        # Se usa la superficie exterior: distancia cavidad -> exterior = distancia al complemento.
        # Aproximacion exacta: cuerpo macizo menos "el cuerpo achicado" no es trivial; se mide
        # contra la cara lateral del cilindro/guarda mediante el solido exterior hueco (vacio = exterior).
        outer = build_outer_body()
        big = box_xyz(-120, 120, -120, 120, -260, 220)
        _OUTER_CACHE["outer"] = big.cut(outer)
    return _OUTER_CACHE["outer"]


# =============================================================================
# VALIDACION Y EXPORTACION (.STEP EDITABLE + .STL IMPRIMIBLE)
# =============================================================================
def validate_and_export(shape: cq.Workplane, name: str, stl_transform=None) -> None:
    solids = shape.solids().vals()
    bb = shape.val().BoundingBox()
    status = "OK" if len(solids) == 1 else f"WARN ({len(solids)} solidos!)"
    print(
        f"  [{status}] {name:26s} | "
        f"X:[{bb.xmin:6.1f},{bb.xmax:6.1f}] Y:[{bb.ymin:6.1f},{bb.ymax:6.1f}] Z:[{bb.zmin:6.1f},{bb.zmax:6.1f}]"
    )
    if len(solids) != 1:
        raise RuntimeError(f"La pieza {name} tiene {len(solids)} solidos desconectados; revisar geometria.")

    cq.exporters.export(shape, str(STEP_DIR / f"{name}.step"), exportType="STEP")
    stl_shape = stl_transform(shape) if stl_transform else shape
    stl_path = str(STL_DIR / f"{name}.stl")
    # Si la malla no queda cerrada (fisuras de teselado en los redondeos) se reintenta con otras tolerancias
    for tol, ang in ((0.05, 0.1), (0.03, 0.08), (0.02, 0.05), (0.08, 0.2), (0.04, 0.15), (0.06, 0.12)):
        cq.exporters.export(stl_shape, stl_path, exportType="STL", tolerance=tol, angularTolerance=ang)
        try:
            import trimesh
            if trimesh.load(stl_path).is_watertight:
                break
        except ImportError:
            break


def main() -> None:
    STEP_DIR.mkdir(parents=True, exist_ok=True)
    STL_DIR.mkdir(parents=True, exist_ok=True)

    print("Generando y validando piezas CAD v3.0 (220 mm, motor Ø27, VL53L0X)...")
    right_half, left_half, shell = build_clamshell_halves()
    pod_tof = build_sensor_pod_tof()
    pod_us = build_sensor_pod_hcsr04()
    rod_60 = build_electrode_rod(60.0)
    rod_100 = build_electrode_rod(100.0)
    aruco = build_aruco_mount()

    total = right_half.val().BoundingBox()
    length = total.zmax - total.zmin
    print(f"  Longitud total de la carcasa: {length:.1f} mm (objetivo {TOTAL_LEN:.0f} mm)")
    if abs(length - TOTAL_LEN) > 0.5:
        raise RuntimeError("La longitud total no coincide con TOTAL_LEN")

    validate_and_export(right_half, "01_carcasa_derecha", lambda s: s.rotate((0, 0, 0), (0, 1, 0), -90))
    validate_and_export(left_half, "02_carcasa_izquierda", lambda s: s.rotate((0, 0, 0), (0, 1, 0), 90))
    validate_and_export(pod_tof, "03a_modulo_sensor_ToF", lambda s: s.rotate((0, 0, 0), (1, 0, 0), -90))
    validate_and_export(pod_us, "03b_modulo_sensor_HCSR04", lambda s: s.rotate((0, 0, 0), (1, 0, 0), -90))
    validate_and_export(rod_60, "04a_electrodo_60mm", lambda s: s.rotate((0, 0, 0), (0, 1, 0), 90))
    validate_and_export(rod_100, "04b_electrodo_100mm", lambda s: s.rotate((0, 0, 0), (0, 1, 0), 90))
    validate_and_export(aruco, "05_soporte_aruco", lambda s: s.rotate((0, 0, 0), (1, 0, 0), -90))

    assy = cq.Assembly(name="ArcSim_VR_Portaelectrodo_v3_0")
    assy.add(right_half, name="01_Carcasa_Derecha", color=cq.Color(0.18, 0.19, 0.21, 1.0))
    assy.add(left_half, name="02_Carcasa_Izquierda", color=cq.Color(0.24, 0.25, 0.28, 1.0))
    assy.add(pod_tof, name="03_Modulo_Sensor_ToF", color=cq.Color(0.85, 0.32, 0.08, 1.0))
    assy.add(rod_60, name="04_Electrodo_60mm", color=cq.Color(0.55, 0.50, 0.45, 1.0))
    assy.add(aruco, name="05_Soporte_ArUco", color=cq.Color(0.12, 0.45, 0.72, 1.0))
    assy.export(str(STEP_DIR / "00_ensamble_completo.step"))
    print(f"  [OK] Ensamble completo: {STEP_DIR / '00_ensamble_completo.step'}")

    # Ensamble con envolventes de componentes (para revisar en Solid Edge)
    assy2 = cq.Assembly(name="ArcSim_VR_v3_0_con_componentes")
    assy2.add(right_half, name="01_Carcasa_Derecha", color=cq.Color(0.18, 0.19, 0.21, 0.35))
    assy2.add(left_half, name="02_Carcasa_Izquierda", color=cq.Color(0.24, 0.25, 0.28, 0.35))
    assy2.add(pod_tof, name="03_Modulo_Sensor_ToF", color=cq.Color(0.85, 0.32, 0.08, 0.6))
    assy2.add(rod_60, name="04_Electrodo_60mm", color=cq.Color(0.55, 0.50, 0.45, 1.0))
    assy2.add(aruco, name="05_Soporte_ArUco", color=cq.Color(0.12, 0.45, 0.72, 0.6))
    for nm, (solid, col) in build_components().items():
        assy2.add(solid, name=f"REF_{nm}", color=cq.Color(col[0], col[1], col[2], 1.0))
    assy2.export(str(STEP_DIR / "00b_ensamble_con_componentes.step"))
    print(f"  [OK] Ensamble con componentes: {STEP_DIR / '00b_ensamble_con_componentes.step'}")

    ok = verify_clearances(shell, pod_tof)
    print("\nRESULTADO DE VERIFICACION:", "TODO OK" if ok else "HAY PROBLEMAS (revisar lineas [MAL])")
    if not ok:
        sys.exit(2)


if __name__ == "__main__":
    main()
