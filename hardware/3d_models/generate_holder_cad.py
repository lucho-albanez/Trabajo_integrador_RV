#!/usr/bin/env python3
"""
ArcSim_VR - Generador CAD Paramétrico del Portaelectrodo SMAW Sensorizado (v2.2)
================================================================================
Mejoras v2.2 (auditoría completa de tornillería y montaje):
  - Soporte ArUco con 2 orejas exteriores (Z=75.5 y Z=118.5) fuera de la sombra
    del prisma (acceso 100% libre con destornillador desde arriba) + tuercas M3
    cautivas internas con paso libre para tornillos largos.
  - Montaje MPU6050 (GY-521) directo contra la pared plana interior derecha:
    2 agujeros pasantes M3 (Ø3.4 mm, entre centros 15.6 mm) abiertos hasta el
    exterior con alojamientos hexagonales para tuerca M3 en la cara externa
    derecha (admite tornillos M3 largos sin interferencias, cables salen hacia
    abajo por la cámara libre del cabezal).
  - Módulo porta-sensor inferior (ToF / HC-SR04) con 2 tornillos M3 diagonales
    (+14.5, Z=90) y (-14.5, Z=114) 100% accesibles desde abajo sin tocar PCBs
    ni transductores.
  - Nicho exacto 6.4x6.4 mm para pulsador táctil 6x6 mm + canaleta trasera 4 mm
    + varilla deslizante con colisa 2.5 mm y tornillo M3 de ajuste en cabeza.

Sistema de coordenadas (en milímetros):
  - X = 0   : Plano de partición longitudinal (Mitad Derecha X >= 0, Izquierda X <= 0)
  - +Y      : Arriba (soporte ArUco)
  - -Y      : Abajo hacia la chapa (electrodo y sensor ToF apuntan en -Y)
  - +Z      : Adelante (cabezal / mordaza)
  - -Z      : Atrás (mango y salida prensacable USB)
"""

from pathlib import Path
import math
import cadquery as cq

# =============================================================================
# PARÁMETROS EDITABLES (todas las cotas en mm)
# =============================================================================
TOL = 0.30              # Holgura general para impresión 3D FDM
WALL = 3.0              # Espesor mínimo de pared de la carcasa

# Mango ergonómico (a lo largo de Z)
HANDLE_Z0 = -150.0
HANDLE_Z1 = 50.0
HANDLE_OD = 46.0
HANDLE_R = HANDLE_OD / 2.0

# Prensacable trasero USB (Z = -182 a -150)
GLAND_LEN = 32.0
GLAND_Z0 = HANDLE_Z0 - GLAND_LEN
GLAND_END_OD = 22.0
USB_CABLE_DIA = 5.4

# Collarín aislante y guarda-mano
COLLAR_Z0 = 48.0
COLLAR_Z1 = 60.0
COLLAR_OD = 50.0

GUARD_Z0 = 60.0
GUARD_Z1 = 72.0
GUARD_W = 54.0
GUARD_H = 66.0

# Cabezal / Mordaza (Z = 72 a 142)
HEAD_Z0 = 72.0
HEAD_Z1 = 142.0
HEAD_W = 42.0           # Ancho total en X (-21 a +21)
HEAD_Y_BOT = -26.0
HEAD_Y_TOP = 30.0
HEAD_H = HEAD_Y_TOP - HEAD_Y_BOT  # 56 mm
HEAD_YC = 0.5 * (HEAD_Y_BOT + HEAD_Y_TOP)  # +2.0 mm

# Cavidad interna ESP32 DevKit v1 (30 pines: 51.5 x 28.5; 38 pines: 55 x 28)
ESP_Z0 = -114.0
ESP_Z1 = -58.0
ESP_W_Y = 29.6

# Cavidad conector USB detrás del ESP32
USB_PLUG_Z0 = -148.0
USB_PLUG_Z1 = ESP_Z0

# Cavidad etapa MOSFET + diodo flyback (delante del ESP32)
MOSFET_Z0 = -54.0
MOSFET_Z1 = -26.0

# Alojamiento Motor Vibrador moneda 10mm x 3mm (IT&T) - zona trasera palma
MOTOR_Z = -134.0
MOTOR_Y = -12.0
MOTOR_DIA = 10.6

# Montaje MPU6050 (GY-521) sobre pared plana interior derecha (X = +8.0 mm):
# 2 tornillos pasantes M3 abiertos al exterior + tuercas hexagonales M3 externas.
# Distancia entre centros 15.6 mm (compatible con GY-521 estándar 15.24 mm y medida ~16 mm con holgura).
# Los pines VCC/GND/SCL/SDA quedan mirando hacia abajo (-Y) dentro de la cámara libre del cabezal.
MPU_HOLES_Z = (80.0, 95.6)
MPU_HOLE_Y = 12.5

# =============================================================================
# MECANISMO DE VARILLA DESLIZANTE + AUTO-HOMING (PULSADOR TÁCTIL 6x6 mm)
# =============================================================================
ELEC_Z = 126.0
ELEC_SHANK_DIA = 8.0
ELEC_SOCKET_DIA = ELEC_SHANK_DIA + 0.45  # 8.45 mm
ELEC_TRAVEL_MM = 2.5
ELEC_PIN_Y = -14.0
ELEC_COLLAR_DIA = 12.0
ELEC_COLLAR_H = 3.0

# Nicho fijo tipo "sándwich" para pulsador táctil 6x6 mm
SW_BODY_Y0 = 10.0
SW_BODY_Y1 = 14.0
SW_POCKET_W_X = 6.4
SW_POCKET_L_Z = 6.4
SW_WIRE_W_X = 4.0
SW_STEM_HOLE_DIA = 5.6

# Módulo porta-sensor intercambiable (cara inferior del cabezal, centrado en Z = 102 mm)
# Separación centro-a-centro respecto al electrodo: 126 - 102 = 24.0 mm
# Tornillos diagonales en (+14.5, Z=90) y (-14.5, Z=114): 100% accesibles desde abajo
# sin interferir con la PCB ToF ni con los transductores del HC-SR04.
POD_Z = 102.0
POD_LEN_Z = 31.0        # De Z = 86.5 a Z = 117.5
POD_W_X = 36.0          # De X = -18 a X = +18
POD_RECESS_H = 4.0
POD_SCREWS_XZ = [(14.5, 90.0), (-14.5, 114.0)]

# Soporte ArUco superior (cara superior Y = +30 mm)
# Prisma centrado en Z = 98 mm (Z = 82..114 mm); orejas de fijación M3 AFUERA
# del prisma en Z = 77.0 y Z = 118.5 -> acceso 100% libre desde arriba (y despejado del guarda-mano Z=72).
ARUCO_Z = 98.0
ARUCO_PRISM_LEN_Z = 32.0
ARUCO_SCREWS_Z = (77.0, 118.5)

# Tornillos M3 de cierre de las dos mitades (posiciones en Z, Y)
CLAMSHELL_BOLTS = [
    (-156.0, 11.5),     # Prensacable arriba
    (-156.0, -11.5),    # Prensacable abajo
    (-40.0, 17.5),      # Mango medio arriba
    (-40.0, -17.5),     # Mango medio abajo
    (66.0, 24.5),       # Guarda-mano arriba
    (66.0, -21.0),      # Guarda-mano abajo
    (135.5, 12.0),      # Cabezal frente
]
M3_CLEAR_R = 1.7        # Agujero pasante Ø3.4 mm
M3_HEAD_R = 3.1         # Cabeza Allen M3 Ø6.2 mm
M3_NUT_AF = 5.75        # Tuerca M3 entre caras (5.5 + holgura)
M3_NUT_R = M3_NUT_AF / math.sqrt(3.0)

# Pines guía de alineación entre mitades (en plano X = 0, zonas de pared sólida)
ALIGN_PINS = [
    (-118.0, 18.0),
    (-118.0, -18.0),
    (26.0, 18.0),
    (26.0, -18.0),
    (106.0, 24.5),      # Despejado de ArUco (75.5 y 118.5) y de la cámara (Y<=16)
]

OUT_ROOT = Path(__file__).resolve().parent
STEP_DIR = OUT_ROOT / "step"
STL_DIR = OUT_ROOT / "stl"


# =============================================================================
# PRIMITIVAS EXPLÍCITAS (SIN AMBIGÜEDAD DE EJES EN CADQUERY)
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
    return (
        cq.Workplane(plane)
        .circle(r0)
        .workplane(offset=y1 - y0)
        .circle(r1)
        .loft(combine=True)
    )


def cyl_z(x: float, y: float, radius: float, z0: float, z1: float) -> cq.Workplane:
    plane = cq.Plane(origin=(x, y, z0), xDir=(1, 0, 0), normal=(0, 0, 1))
    return cq.Workplane(plane).circle(radius).extrude(z1 - z0)


def cone_z(x: float, y: float, r0: float, r1: float, z0: float, z1: float) -> cq.Workplane:
    plane = cq.Plane(origin=(x, y, z0), xDir=(1, 0, 0), normal=(0, 0, 1))
    return (
        cq.Workplane(plane)
        .circle(r0)
        .workplane(offset=z1 - z0)
        .circle(r1)
        .loft(combine=True)
    )


def box_xyz(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> cq.Workplane:
    cx = 0.5 * (x0 + x1)
    cy = 0.5 * (y0 + y1)
    cz = 0.5 * (z0 + z1)
    return (
        cq.Workplane("XY")
        .workplane(offset=cz)
        .center(cx, cy)
        .box(x1 - x0, y1 - y0, z1 - z0)
    )


def poly_yz(pts_zy: list[tuple[float, float]], x0: float, x1: float) -> cq.Workplane:
    plane = cq.Plane(origin=(x1, 0, 0), xDir=(0, 0, 1), normal=(-1, 0, 0))
    return cq.Workplane(plane).polyline(pts_zy).close().extrude(x1 - x0)


def poly_xy(pts_xy: list[tuple[float, float]], z0: float, z1: float) -> cq.Workplane:
    plane = cq.Plane(origin=(0, 0, z0), xDir=(1, 0, 0), normal=(0, 0, 1))
    return cq.Workplane(plane).polyline(pts_xy).close().extrude(z1 - z0)


def rounded_box_z(w_x: float, h_y: float, y_center: float, z0: float, z1: float, r_corner: float = 5.0) -> cq.Workplane:
    plane = cq.Plane(origin=(0, y_center, z0), xDir=(1, 0, 0), normal=(0, 0, 1))
    return cq.Workplane(plane).rect(w_x, h_y).extrude(z1 - z0).edges("|Z").fillet(r_corner)


# =============================================================================
# 1. CUERPO EXTERIOR COMPLETO DEL PORTAELECTRODO
# =============================================================================
def build_outer_body() -> cq.Workplane:
    body = cyl_z(0.0, 0.0, HANDLE_R, HANDLE_Z0, HANDLE_Z1)

    for k in range(8):
        gz = -132.0 + k * 21.0
        groove = cyl_z(0.0, 0.0, HANDLE_R + 2.0, gz, gz + 4.5).cut(
            cyl_z(0.0, 0.0, HANDLE_R - 1.2, gz - 0.5, gz + 5.0)
        )
        body = body.cut(groove)

    gland = cone_z(0.0, 0.0, GLAND_END_OD / 2.0, HANDLE_R, GLAND_Z0, HANDLE_Z0)
    for gz in (-174.0, -166.0):
        groove = cyl_z(0.0, 0.0, HANDLE_R, gz, gz + 2.5).cut(
            cyl_z(0.0, 0.0, 13.5, gz - 0.5, gz + 3.0)
        )
        gland = gland.cut(groove)
    body = body.union(gland)

    body = body.union(cyl_z(0.0, 0.0, COLLAR_OD / 2.0, COLLAR_Z0, COLLAR_Z1))
    body = body.union(rounded_box_z(GUARD_W, GUARD_H, HEAD_YC, GUARD_Z0, GUARD_Z1, r_corner=8.0))

    head = rounded_box_z(HEAD_W, HEAD_H, HEAD_YC, HEAD_Z0, HEAD_Z1, r_corner=6.0)
    front_chamfer = poly_yz(
        [(HEAD_Z1 + 2.0, HEAD_Y_TOP + 2.0), (HEAD_Z1 - 10.0, HEAD_Y_TOP + 2.0), (HEAD_Z1 + 2.0, HEAD_Y_TOP - 10.0)],
        -HEAD_W, HEAD_W
    )
    head = head.cut(front_chamfer)
    body = body.union(head)
    return body


# =============================================================================
# 2. CAVIDADES INTERNAS (APLICADAS SECUENCIALMENTE CON VERIFICACIÓN DE VOLUMEN)
# =============================================================================
def build_internal_cutout_list() -> list[tuple[str, cq.Workplane]]:
    cuts: list[tuple[str, cq.Workplane]] = [
        # 2.1 Entrada cable USB + cámara ficha USB + muesca anti-tirones
        ("usb_channel", cyl_z(0.0, 0.0, USB_CABLE_DIA / 2.0, GLAND_Z0 - 2.0, HANDLE_Z0 + 4.0)),
        ("usb_plug_bay", box_xyz(-8.5, 8.5, -8.0, 8.0, USB_PLUG_Z0, USB_PLUG_Z1 + 2.0)),
        ("usb_tie_slot", box_xyz(-6.0, 6.0, -4.5, 4.5, -162.0, -153.0)),

        # 2.2 Bahía ESP32 DevKit v1 (30 o 38 pines) + ranuras PCB
        ("esp32_bay", box_xyz(-9.0, 9.0, -ESP_W_Y / 2.0, ESP_W_Y / 2.0, ESP_Z0, ESP_Z1)),
        ("esp32_pcb_slot", box_xyz(1.0, 3.2, -(ESP_W_Y / 2.0 + 1.2), (ESP_W_Y / 2.0 + 1.2), ESP_Z0 + 1.5, ESP_Z1 - 1.5)),

        # 2.3 Bahía MOSFET / Diodo flyback + ventana pasacables central
        ("mosfet_bay", box_xyz(-10.0, 10.0, -12.0, 12.0, MOSFET_Z0, MOSFET_Z1)),
        ("esp_mosfet_window", box_xyz(-6.5, 6.5, -8.5, 8.5, ESP_Z1 - 2.0, MOSFET_Z0 + 2.0)),

        # 2.4 Túnel de cableado hacia el cabezal (I2C + pulsador homing)
        ("wire_duct", box_xyz(-7.0, 7.0, -9.0, 11.0, -28.0, HEAD_Z0 + 6.0)),

        # 2.5 Bolsillo Motor Vibrador moneda 10mm x 3mm (pared derecha bajo palma)
        ("motor_pocket", cyl_x(MOTOR_Y, MOTOR_Z, MOTOR_DIA / 2.0, 6.0, 12.1)),
        ("motor_wire_duct", box_xyz(5.0, 9.5, MOTOR_Y - 2.5, -5.0, MOTOR_Z, ESP_Z0 + 4.0)),

        # 2.6 Cámara principal del cabezal (pared plana en X = +8.0 mm donde apoya el MPU6050
        # con sus pines mirando hacia abajo en la zona libre Y = -10..0 mm)
        ("head_wire_bay", box_xyz(-8.0, 8.0, -10.0, 16.5, HEAD_Z0 - 2.0, 114.0)),

        # 2.7 Alojamiento modular inferior para el porta-sensor (ToF o HC-SR04)
        ("pod_recess", box_xyz(
            -POD_W_X / 2.0 - TOL, POD_W_X / 2.0 + TOL,
            HEAD_Y_BOT - 2.0, HEAD_Y_BOT + POD_RECESS_H,
            POD_Z - POD_LEN_Z / 2.0 - TOL, POD_Z + POD_LEN_Z / 2.0 + TOL,
        )),
        ("pod_wire_slot", box_xyz(-8.0, 8.0, HEAD_Y_BOT, -8.0, POD_Z - 9.0, POD_Z + 9.0)),

        # 2.8 MECANISMO AUTO-HOMING: Casquillo guía + Nicho fijo 6.4x6.4 mm pulsador + canaleta 4 mm
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

        # Perno guía M3 frontal para la colisa de la varilla + alojamiento tuerca cautiva
        ("colisa_pin_hole", cyl_z(0.0, ELEC_PIN_Y, M3_CLEAR_R, ELEC_Z - 6.0, HEAD_Z1 + 3.0)),
        ("colisa_nut_trap", box_xyz(-3.0, 3.0, ELEC_PIN_Y - 3.1, ELEC_PIN_Y + 9.0, 132.5, 135.6)),
    ]

    # 2 tornillos diagonales M3 del pod inferior (en paredes sólidas X=±14.5, accesibles 100% desde abajo)
    for i, (sx, sz) in enumerate(POD_SCREWS_XZ):
        cuts.append((f"pod_screw_{i}", cyl_y(sx, sz, 1.45, HEAD_Y_BOT - 1.0, HEAD_Y_BOT + POD_RECESS_H + 12.0)))

    # 2 tornillos M3 del soporte ArUco superior (en Z=75.5 y Z=118.5, fuera del prisma ArUco):
    # Agujero pasante hasta la cámara interna (permite tornillos más largos) + tuerca hexagonal M3 cautiva
    # en Y = 22.5..25.8 mm (se inserta al abrir la carcasa en X=0).
    for i, az in enumerate(ARUCO_SCREWS_Z):
        cuts.append((f"aruco_screw_thru_{i}", cyl_y(0.0, az, M3_CLEAR_R, 15.0, HEAD_Y_TOP + 2.0)))
        cuts.append((f"aruco_nut_trap_{i}", hex_y(0.0, az, M3_NUT_R * 2.0, 22.5, 25.8)))

    return cuts


# =============================================================================
# 3. CONSTRUCCIÓN DE LAS DOS MITADES (DERECHA X>=0 E IZQUIERDA X<=0)
# =============================================================================
def build_clamshell_halves() -> tuple[cq.Workplane, cq.Workplane]:
    shell = build_outer_body()
    outer_vol = shell.val().Volume()
    for cut_name, cut_solid in build_internal_cutout_list():
        prev_vol = shell.val().Volume()
        shell = shell.cut(cut_solid)
        new_vol = shell.val().Volume()
        if new_vol >= prev_vol - 1.0:
            raise RuntimeError(f"El corte interno '{cut_name}' no removió material (vol {prev_vol:.1f} -> {new_vol:.1f})")

    removed_vol = outer_vol - shell.val().Volume()
    print(f"  [OK] Vaciado interno validado: {removed_vol/1000.0:.1f} cm3 removidos ({100.0*removed_vol/outer_vol:.1f} %)")

    right_mask = box_xyz(0.0, 80.0, -80.0, 80.0, -220.0, 200.0)
    left_mask = box_xyz(-80.0, 0.0, -80.0, 80.0, -220.0, 200.0)

    right_half = shell.intersect(right_mask)
    left_half = shell.intersect(left_mask)

    # Fijación del MPU6050 en la Mitad Derecha (pared plana X = +8.0 mm):
    # 2 agujeros pasantes M3 (Ø3.4 mm) abiertos hasta el exterior (X = +21.0 mm)
    # + 2 alojamientos hexagonales para tuerca M3 en la cara exterior derecha (X = +17.5..+22.0).
    # Permite usar tornillos M3 de cualquier largo apretando cómodamente con la mitad izquierda abierta.
    for mz in MPU_HOLES_Z:
        right_half = right_half.cut(cyl_x(MPU_HOLE_Y, mz, M3_CLEAR_R, 7.0, HEAD_W / 2.0 + 3.0))
        right_half = right_half.cut(hex_x(MPU_HOLE_Y, mz, M3_NUT_R * 2.0, HEAD_W / 2.0 - 3.3, HEAD_W / 2.0 + 3.0))

    # Pines guía de alineación entre mitades
    for pz, py in ALIGN_PINS:
        right_half = right_half.union(cyl_x(py, pz, 1.45, -3.0, 1.5))
        left_half = left_half.cut(cyl_x(py, pz, 1.70, -3.6, 0.5))

    # Tornillos M3 de cierre de las dos mitades (avellanado en Izquierda, tuerca M3 en Derecha)
    for bz, by in CLAMSHELL_BOLTS:
        thru = cyl_x(by, bz, M3_CLEAR_R, -40.0, 40.0)
        right_half = right_half.cut(thru)
        left_half = left_half.cut(thru)

        if bz < HANDLE_Z0:
            t = (bz - GLAND_Z0) / GLAND_LEN
            r_loc = (GLAND_END_OD / 2.0) * (1.0 - t) + HANDLE_R * t
            x_surf = math.sqrt(max(r_loc**2 - by**2, 25.0))
        elif bz < GUARD_Z0:
            x_surf = math.sqrt(max(HANDLE_R**2 - by**2, 49.0))
        elif bz < HEAD_Z0:
            x_surf = GUARD_W / 2.0
        else:
            x_surf = HEAD_W / 2.0

        left_half = left_half.cut(cyl_x(by, bz, M3_HEAD_R, -x_surf - 5.0, -x_surf + 3.5))
        right_half = right_half.cut(hex_x(by, bz, M3_NUT_R * 2.0, x_surf - 3.2, x_surf + 5.0))

    return right_half, left_half


# =============================================================================
# 4. MÓDULOS PORTA-SENSOR INTERCAMBIABLES (VL6180X / VL53L1X y HC-SR04)
# =============================================================================
def build_sensor_pod_tof() -> cq.Workplane:
    y_top = HEAD_Y_BOT + POD_RECESS_H  # -22.0
    y_bot = y_top - 9.0                # -31.0

    pod = box_xyz(
        -POD_W_X / 2.0, POD_W_X / 2.0,
        y_bot, y_top,
        POD_Z - POD_LEN_Z / 2.0, POD_Z + POD_LEN_Z / 2.0,
    ).edges("|Y").fillet(2.5)

    # Cavidad para plaqueta ToF (hasta 25 x 19 mm, libre de los tornillos diagonales en ±14.5, Z=90/114)
    pod = pod.cut(box_xyz(-12.5, 12.5, y_bot + 2.2, y_top + 1.0, POD_Z - 9.5, POD_Z + 9.5))
    pod = pod.cut(box_xyz(-5.5, 5.5, y_bot - 1.0, y_bot + 3.0, POD_Z - 4.0, POD_Z + 4.0))

    for sx, sz in POD_SCREWS_XZ:
        pod = pod.cut(cyl_y(sx, sz, M3_CLEAR_R, y_bot - 1.0, y_top + 1.0))
        pod = pod.cut(cyl_y(sx, sz, M3_HEAD_R, y_bot - 0.5, y_bot + 3.0))
    return pod


def build_sensor_pod_hcsr04() -> cq.Workplane:
    y_top = HEAD_Y_BOT + POD_RECESS_H  # -22.0
    y_mid = HEAD_Y_BOT                 # -26.0
    y_bot = y_mid - 16.0               # -42.0

    tab = box_xyz(
        -POD_W_X / 2.0, POD_W_X / 2.0,
        y_mid - 1.0, y_top,
        POD_Z - POD_LEN_Z / 2.0, POD_Z + POD_LEN_Z / 2.0,
    )
    shell = box_xyz(
        -25.5, 25.5,
        y_bot, y_mid,
        POD_Z - POD_LEN_Z / 2.0, POD_Z + POD_LEN_Z / 2.0,
    ).edges("|Y").fillet(2.5)
    pod = tab.union(shell)

    # Cavidad para PCB HC-SR04 (46 x 21 mm centrada en Z = 102 -> Z = 91.5..112.5, libre de los tornillos)
    pod = pod.cut(box_xyz(-23.0, 23.0, y_bot + 3.0, y_top + 1.0, POD_Z - 10.5, POD_Z + 10.5))
    for tx in (-13.0, 13.0):
        pod = pod.cut(cyl_y(tx, POD_Z, 8.3, y_bot - 1.0, y_bot + 6.0))
    # Tornillos diagonales en (+14.5, Z=90) y (-14.5, Z=114): completamente fuera de transductores y PCB
    for sx, sz in POD_SCREWS_XZ:
        pod = pod.cut(cyl_y(sx, sz, M3_CLEAR_R, y_bot - 1.0, y_top + 1.0))
        pod = pod.cut(cyl_y(sx, sz, M3_HEAD_R, y_bot - 0.5, y_bot + 4.0))
    return pod


# =============================================================================
# 5. VARILLAS DESLIZANTES DE ELECTRODO CON COLISA Y REGULACIÓN M3 (60 y 100 mm)
# =============================================================================
def build_electrode_rod(exposed_length_mm: float) -> cq.Workplane:
    y_collar_top = HEAD_Y_BOT - ELEC_TRAVEL_MM     # -28.5 mm
    y_collar_bot = y_collar_top - ELEC_COLLAR_H    # -31.5 mm
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
# 6. SOPORTE DESMONTABLE ArUco CON PLACA CUADRADA 48x48 mm E INCLINACIÓN DE 30°
# =============================================================================
def build_aruco_mount() -> cq.Workplane:
    y0 = HEAD_Y_TOP  # +30.0 mm
    # Base alargada con 2 orejas exteriores (Z = 73..123 mm, 1 mm libre del guarda-mano en Z=72)
    # para que los tornillos M3 en Z = 77.0 y Z = 118.5 queden 100% despejados de la placa (Z = 86.0..110.0 mm)
    base = box_xyz(-9.0, 9.0, y0, y0 + 5.0, 73.0, 123.0).edges("|Y").fillet(3.0)

    # Placa cuadrada plana de 48x48 mm con inclinación frontal de 30°
    # El vector normal apunta hacia la cámara (+Z / +Y): (0, sin(30°), cos(30°))
    ang = math.radians(30.0)
    nx = 0.0
    ny = math.sin(ang)
    nz = math.cos(ang)

    # Elevamos el centro a Y = 57.0 mm para que el borde inferior quede en Y = 36.2 mm
    # (completamente por encima del lomo de la base en Y = 35.0 mm), garantizando
    # 48.0 mm de altura útil plana continua al 100%, ideal para stickers de 45x45 mm.
    plate_w = 48.0
    plate_h = 48.0
    plate_center = (0.0, 57.0, ARUCO_Z)
    plane = cq.Plane(
        origin=plate_center,
        xDir=(1.0, 0.0, 0.0),
        normal=(nx, ny, nz)
    )
    plate = cq.Workplane(plane).rect(plate_w, plate_h).extrude(-3.5)

    back_plane = cq.Plane(
        origin=(0.0, plate_center[1] - 3.5 * ny, plate_center[2] - 3.5 * nz),
        xDir=(1.0, 0.0, 0.0),
        normal=(nx, ny, nz)
    )

    # Cuello / pilar de unión estructural exclusivamente detrás de la placa
    stem = box_xyz(-8.0, 8.0, y0 + 4.0, plate_center[1], 80.0, 102.0)
    stem = stem.cut(cq.Workplane(back_plane).rect(100.0, 100.0).extrude(50.0))

    mount = base.union(stem).union(plate)

    # 2 agujeros pasantes M3 en las orejas exteriores (100% cielo abierto desde arriba)
    for az in ARUCO_SCREWS_Z:
        mount = mount.cut(cyl_y(0.0, az, M3_CLEAR_R, y0 - 1.0, y0 + 7.0))

    return mount


# =============================================================================
# VALIDACIÓN Y EXPORTACIÓN (.STEP EDITABLE + .STL IMPRIMIBLE)
# =============================================================================
def validate_and_export(shape: cq.Workplane, name: str, stl_transform=None) -> None:
    solids = shape.solids().vals()
    bb = shape.val().BoundingBox()
    status = "OK" if len(solids) == 1 else f"WARN ({len(solids)} sólidos!)"
    print(
        f"  [{status}] {name:26s} | "
        f"X:[{bb.xmin:6.1f},{bb.xmax:6.1f}] Y:[{bb.ymin:6.1f},{bb.ymax:6.1f}] Z:[{bb.zmin:6.1f},{bb.zmax:6.1f}]"
    )
    if len(solids) != 1:
        raise RuntimeError(f"La pieza {name} tiene {len(solids)} sólidos desconectados; revisar geometría.")

    step_path = STEP_DIR / f"{name}.step"
    stl_path = STL_DIR / f"{name}.stl"
    cq.exporters.export(shape, str(step_path), exportType="STEP")
    stl_shape = stl_transform(shape) if stl_transform else shape
    cq.exporters.export(stl_shape, str(stl_path), exportType="STL", tolerance=0.05, angularTolerance=0.1)


def main() -> None:
    STEP_DIR.mkdir(parents=True, exist_ok=True)
    STL_DIR.mkdir(parents=True, exist_ok=True)

    print("Generando y validando piezas CAD v2.2 (tornillería 100% accesible + MPU6050 pasante)...")
    right_half, left_half = build_clamshell_halves()
    pod_tof = build_sensor_pod_tof()
    pod_us = build_sensor_pod_hcsr04()
    rod_60 = build_electrode_rod(60.0)
    rod_100 = build_electrode_rod(100.0)
    aruco = build_aruco_mount()

    validate_and_export(right_half, "01_carcasa_derecha", lambda s: s.rotate((0, 0, 0), (0, 1, 0), -90))
    validate_and_export(left_half, "02_carcasa_izquierda", lambda s: s.rotate((0, 0, 0), (0, 1, 0), 90))
    validate_and_export(pod_tof, "03a_modulo_sensor_ToF", lambda s: s.rotate((0, 0, 0), (1, 0, 0), -90))
    validate_and_export(pod_us, "03b_modulo_sensor_HCSR04", lambda s: s.rotate((0, 0, 0), (1, 0, 0), -90))
    validate_and_export(rod_60, "04a_electrodo_60mm", lambda s: s.rotate((0, 0, 0), (0, 1, 0), 90))
    validate_and_export(rod_100, "04b_electrodo_100mm", lambda s: s.rotate((0, 0, 0), (0, 1, 0), 90))
    validate_and_export(aruco, "05_soporte_aruco", lambda s: s.rotate((0, 0, 0), (1, 0, 0), -90))

    assy = cq.Assembly(name="ArcSim_VR_Portaelectrodo_v2_2")
    assy.add(right_half, name="01_Carcasa_Derecha", color=cq.Color(0.18, 0.19, 0.21, 1.0))
    assy.add(left_half, name="02_Carcasa_Izquierda", color=cq.Color(0.24, 0.25, 0.28, 1.0))
    assy.add(pod_tof, name="03_Modulo_Sensor_ToF", color=cq.Color(0.85, 0.32, 0.08, 1.0))
    assy.add(rod_60, name="04_Electrodo_60mm", color=cq.Color(0.55, 0.50, 0.45, 1.0))
    assy.add(aruco, name="05_Soporte_ArUco", color=cq.Color(0.12, 0.45, 0.72, 1.0))
    assy_path = STEP_DIR / "00_ensamble_completo.step"
    assy.export(str(assy_path))
    print(f"  [OK] Ensamble completo: {assy_path}")


if __name__ == "__main__":
    main()
