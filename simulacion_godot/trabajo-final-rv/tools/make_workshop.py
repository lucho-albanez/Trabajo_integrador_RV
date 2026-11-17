#!/usr/bin/env python3
"""Genera Scenes/Workshop.tscn (taller industrial). Uso: python3 tools/make_workshop.py
Los props (.glb) salen de tools/blender/make_models.py. Coordenadas Godot, piso en y=0."""
import math, os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
X0, X1, Z0, Z1, H = -7.0, 7.0, -5.0, 7.0, 5.0
CX, CZ = (X0 + X1) / 2, (Z0 + Z1) / 2
W, D = X1 - X0, Z1 - Z0

ext, subs, nodes = [], [], []
_ids = {}


def T(pos, roty=0.0):
    c, s = math.cos(math.radians(roty)), math.sin(math.radians(roty))
    return "Transform3D(%.5f, 0, %.5f, 0, 1, 0, %.5f, 0, %.5f, %.4f, %.4f, %.4f)" % (c, s, -s, c, *pos)


def sub(kind, body):
    key = kind + body
    if key in _ids:
        return _ids[key]
    sid = "%s_%d" % (kind, len(_ids) + 1)
    _ids[key] = sid
    subs.append('[sub_resource type="%s" id="%s"]\n%s\n' % (kind, sid, body))
    return sid


def mat(name, color, rough=0.8, metal=0.0, emis=None, alpha=False, unshaded=False, extra=""):
    b = "albedo_color = Color(%s, 1.0)\nroughness = %.2f\nmetallic = %.2f\n" % (", ".join("%.3f" % c for c in color), rough, metal)
    if alpha:
        b += "transparency = 1\ncull_mode = 2\n"
    if emis:
        b += "emission_enabled = true\nemission = Color(%s)\nemission_energy_multiplier = %.2f\n" % (", ".join("%.3f" % c for c in (tuple(emis[:3]) + (1.0,))), emis[3])
    if unshaded:
        b += "shading_mode = 0\n"
    return sub("StandardMaterial3D", b + extra + "resource_name = \"%s\"" % name)


def model(name):
    if name not in _ids:
        _ids[name] = "m_" + name
        ext.append('[ext_resource type="PackedScene" path="res://Assets/models/%s.glb" id="m_%s"]' % (name, name))
    return _ids[name]


def node(name, kind, parent, props=""):
    nodes.append('[node name="%s" type="%s" parent="%s"]\n%s' % (name, kind, parent, props))


def inst(name, mdl, parent, pos, roty=0.0):
    nodes.append('[node name="%s" parent="%s" instance=ExtResource("%s")]\ntransform = %s\n' % (name, parent, model(mdl), T(pos, roty)))


def mesh_box(name, parent, pos, size, m, roty=0.0, shadow=True):
    mid = sub("BoxMesh", "material = SubResource(\"%s\")\nsize = Vector3(%.4f, %.4f, %.4f)" % (m, *size))
    node(name, "MeshInstance3D", parent, "transform = %s\nmesh = SubResource(\"%s\")\n%s" % (T(pos, roty), mid, "" if shadow else "cast_shadow = 0\n"))


def body_box(name, parent, pos, size, m=None, roty=0.0, visible=True):
    node(name, "StaticBody3D", parent, "transform = %s\ncollision_layer = 1\ncollision_mask = 0\n" % T(pos, roty))
    sid = sub("BoxShape3D", "size = Vector3(%.4f, %.4f, %.4f)" % size)
    node("Shape", "CollisionShape3D", "%s/%s" % (parent, name), "shape = SubResource(\"%s\")\n" % sid)
    if visible and m:
        mesh_box("Mesh", "%s/%s" % (parent, name), (0, 0, 0), size, m)


def prop(name, mdl, pos, roty, col_size, col_center):
    """Instancia un .glb con una caja de colisión simple (capa 1)."""
    node(name, "StaticBody3D", ".", "transform = %s\ncollision_layer = 1\ncollision_mask = 0\n" % T(pos, roty))
    sid = sub("BoxShape3D", "size = Vector3(%.3f, %.3f, %.3f)" % col_size)
    node("Shape", "CollisionShape3D", name, "transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, %.3f, %.3f, %.3f)\nshape = SubResource(\"%s\")\n" % (*col_center, sid))
    nodes.append('[node name="Model" parent="%s" instance=ExtResource("%s")]\n' % (name, model(mdl)))


# ---------------- materiales ----------------
m_floor = mat("hormigon", (0.36, 0.36, 0.37), 0.6, 0.05)
m_wall_hi = mat("pared_alta", (0.72, 0.72, 0.70), 0.95)
m_wall_lo = mat("pared_zocalo", (0.16, 0.22, 0.28), 0.7)
m_ceiling = mat("techo", (0.12, 0.12, 0.13), 0.9)
m_steel = mat("acero_estructural", (0.10, 0.14, 0.2), 0.55, 0.5)
m_yellow = mat("amarillo", (0.9, 0.68, 0.05), 0.6)
m_black = mat("negro", (0.04, 0.04, 0.04), 0.8)
m_green = mat("verde_seguridad", (0.05, 0.4, 0.15), 0.5, emis=(0.05, 0.5, 0.15, 0.6))
m_window = mat("ventana", (0.7, 0.85, 1.0), 0.3, emis=(0.55, 0.75, 1.0, 1.1))
m_frame = mat("marco", (0.06, 0.06, 0.07), 0.6, 0.6)
m_door = mat("porton", (0.38, 0.4, 0.42), 0.5, 0.7)
m_curtain = mat("cortina", (1.0, 0.45, 0.05), 0.9, alpha=True)
m_curtain.__class__  # (solo nombre)
subs[-1] = subs[-1].replace("albedo_color = Color(1.000, 0.450, 0.050, 1.0)", "albedo_color = Color(1.0, 0.42, 0.04, 0.32)")
m_rail = mat("riel", (0.55, 0.57, 0.6), 0.4, 0.8)
m_sign = mat("cartel", (0.9, 0.68, 0.05), 0.6)

# ---------------- raíz ----------------
nodes.append('[node name="Workshop" type="Node3D"]\n')

# Piso
body_box("Floor", ".", (CX, -0.25, CZ), (W + 0.8, 0.5, D + 0.8), m_floor)
# Paredes (colisión de altura completa + zócalo oscuro y parte alta clara)
walls = [
    ("WallN", (CX, H / 2, Z1 + 0.2), (W + 0.8, H, 0.4), (0, 0, -0.2)),
    ("WallS", (CX, H / 2, Z0 - 0.2), (W + 0.8, H, 0.4), (0, 0, 0.2)),
    ("WallE", (X1 + 0.2, H / 2, CZ), (0.4, H, D + 0.8), (-0.2, 0, 0)),
    ("WallW", (X0 - 0.2, H / 2, CZ), (0.4, H, D + 0.8), (0.2, 0, 0)),
]
for n, pos, size, inward in walls:
    body_box(n, ".", pos, size, None, visible=False)
    # caras interiores
    lo = (size[0], 1.3, size[2]); hi = (size[0], H - 1.3, size[2])
    mesh_box("Zocalo", n, (0, 1.3 / 2 - H / 2, 0), lo, m_wall_lo)
    mesh_box("Alta", n, (0, 1.3 + (H - 1.3) / 2 - H / 2, 0), hi, m_wall_hi)
    mesh_box("Franja", n, (inward[0] * 0.5 * 0.01, 1.32 - H / 2, 0), (size[0] + 0.001 if size[0] > 1 else size[0] + 0.02, 0.06, size[2] + 0.001 if size[2] > 1 else size[2] + 0.02), m_yellow)

# Techo (sin sombras para no tapar la luz) + vigas
mesh_box("Techo", ".", (CX, H + 0.1, CZ), (W + 0.8, 0.2, D + 0.8), m_ceiling, shadow=False)
for i, x in enumerate((-5.25, -1.75, 1.75, 5.25)):
    mesh_box("ViguetaX%d" % i, ".", (x, H - 0.2, CZ), (0.2, 0.4, D), m_steel, shadow=False)
for i, z in enumerate((-2.5, 1.0, 4.5)):
    mesh_box("VigaZ%d" % i, ".", (CX, H - 0.12, z), (W, 0.24, 0.16), m_steel, shadow=False)
# Columnas junto a las paredes laterales
for i, z in enumerate((-2.5, 1.0, 4.5)):
    for sx, x in (("W", X0 + 0.15), ("E", X1 - 0.15)):
        mesh_box("Columna%s%d" % (sx, i), ".", (x, H / 2, z), (0.3, H, 0.3), m_steel)
        mesh_box("ColBase%s%d" % (sx, i), ".", (x, 0.15, z), (0.4, 0.3, 0.4), m_yellow)
# Conductos
mesh_box("Ducto", ".", (-3.5, H - 0.7, 6.4), (7.0, 0.4, 0.4), mat("ducto", (0.6, 0.62, 0.65), 0.45, 0.8), shadow=False)

# Luces colgantes
lamps = [(-3.0, 0.2), (3.0, 0.2), (-3.0, 4.3), (3.0, 4.3)]
for i, (x, z) in enumerate(lamps):
    inst("Lampara%d" % i, "ceiling_lamp", ".", (x, H, z))
    node("Foco%d" % i, "SpotLight3D", ".",
         "transform = Transform3D(1, 0, 0, 0, 0, 1, 0, -1, 0, %.2f, %.2f, %.2f)\nlight_color = Color(1, 0.96, 0.88, 1)\nlight_energy = 5.0\nspot_range = 9.0\nspot_angle = 62.0\nspot_attenuation = 0.8\n" % (x, H - 0.95, z))

# Marcas en el piso (franjas amarillas) y sendero verde
for i, (pos, size) in enumerate([
    ((CX, 0.004, -1.3), (W - 0.6, 0.008, 0.1)),
    ((-5.0, 0.004, 3.0), (0.1, 0.008, 8.0)),
    ((5.0, 0.004, 3.0), (0.1, 0.008, 8.0)),
    ((CX, 0.004, 6.4), (W - 0.6, 0.008, 0.1)),
]):
    mesh_box("MarcaPiso%d" % i, ".", pos, size, m_yellow, shadow=False)
# Zona de soldadura delimitada (rectángulo amarillo y negro)
for i, (pos, size) in enumerate([
    ((0.9, 0.005, 0.75), (7.6, 0.008, 0.12)),
    ((0.9, 0.005, 3.5), (7.6, 0.008, 0.12)),
    ((-2.9, 0.005, 2.12), (0.12, 0.008, 2.88)),
    ((4.7, 0.005, 2.12), (0.12, 0.008, 2.88)),
]):
    mesh_box("ZonaSoldadura%d" % i, ".", pos, size, m_yellow, shadow=False)
    pass

# Portón y ventanas
body_box("Porton", ".", (4.0, 1.6, Z1 - 0.06), (3.6, 3.2, 0.1), m_door)
for k in range(8):
    mesh_box("PortonNervio%d" % k, ".", (4.0, 0.2 + k * 0.4, Z1 - 0.13), (3.6, 0.04, 0.04), m_frame, shadow=False)
mesh_box("PortonMarco", ".", (4.0, 3.28, Z1 - 0.1), (3.9, 0.16, 0.14), m_yellow)
for i, z in enumerate((0.0, 4.0)):
    for sn, x, sg in (("E", X1 - 0.04, -1), ("W", X0 + 0.04, 1)):
        mesh_box("Ventana%s%d" % (sn, i), ".", (x, 3.7, z), (0.04, 0.9, 2.4), m_window, shadow=False)
        mesh_box("VentanaMarco%s%d" % (sn, i), ".", (x + sg * 0.01, 3.7, z), (0.06, 0.05, 2.5), m_frame, shadow=False)
        mesh_box("VentanaTravesano%s%d" % (sn, i), ".", (x + sg * 0.01, 3.7, z), (0.06, 1.0, 0.05), m_frame, shadow=False)

# Cortina de soldadura (naranja translúcida) tras la mesa de trabajo
mesh_box("RielCortina", ".", (0.0, 2.25, 3.45), (3.9, 0.06, 0.06), m_rail, shadow=False)
mesh_box("Cortina", ".", (0.0, 1.15, 3.45), (3.7, 2.1, 0.015), m_curtain, shadow=False)
for sx in (-1, 1):
    mesh_box("PostCortina%d" % sx, ".", (sx * 1.95, 1.1, 3.45), (0.06, 2.2, 0.06), m_rail, shadow=False)

# Utilería con colisión
prop("Estanteria1", "shelf", (-2.6, 0, 6.65), 0, (1.3, 1.9, 0.5), (0, 0.95, 0))
prop("Estanteria2", "shelf", (-1.2, 0, 6.65), 0, (1.3, 1.9, 0.5), (0, 0.95, 0))
prop("CajaTubo1", "gas_cylinder_blue", (-6.55, 0, 3.0), 0, (0.24, 1.5, 0.24), (0, 0.75, 0))
prop("CajaTubo2", "gas_cylinder_red", (-6.55, 0, 3.32), 0, (0.24, 1.5, 0.24), (0, 0.75, 0))
prop("CajaTubo3", "gas_cylinder_blue", (-6.55, 0, 3.64), 0, (0.24, 1.5, 0.24), (0, 0.75, 0))
prop("Extractor", "extractor_arm", (1.35, 0, 2.9), 0, (0.4, 2.0, 0.4), (0, 1.0, 0))
prop("Matafuego", "fire_extinguisher", (X1 - 0.12, 1.0, 0.8), -90, (0.18, 0.6, 0.18), (0, 0.3, 0))
prop("Gabinete", "toolbox", (-4.6, 0, 2.0), 180, (0.78, 0.95, 0.5), (0, 0.47, 0))
prop("Tambor", "drum", (5.6, 0, 5.8), 0, (0.6, 0.9, 0.6), (0, 0.45, 0))
prop("Tambor2", "drum", (6.3, 0, 5.4), 0, (0.6, 0.9, 0.6), (0, 0.45, 0))
prop("Pallet1", "pallet_boxes", (-5.6, 0, 5.8), 15, (1.25, 1.0, 1.05), (0, 0.5, 0))
prop("Pallet2", "pallet_boxes", (6.0, 0, -3.6), -20, (1.25, 1.0, 1.05), (0, 0.5, 0))
# Cadena que sujeta los tubos
mesh_box("CadenaTubos", ".", (-6.72, 0.95, 3.32), (0.03, 0.03, 0.9), m_frame, shadow=False)

# Carteles
def sign(name, text, pos, roty, size, color_mat, font_color, fsize=32):
    mesh_box(name + "Panel", ".", pos, (size[0], size[1], 0.03), color_mat, roty=roty, shadow=False)
    # Label3D mira hacia +Z local; se separa 2 cm hacia el interior de la sala
    c, s = math.cos(math.radians(roty)), math.sin(math.radians(roty))
    lp = (pos[0] + 0.0 + s * 0.02, pos[1], pos[2] + c * 0.02)
    node(name, "Label3D", ".", 'transform = %s\ntext = "%s"\nfont_size = %d\npixel_size = 0.004\nmodulate = Color(%s)\noutline_size = 0\nwidth = %d\nautowrap_mode = 2\nshaded = true\n' % (
        T(lp, roty), text, fsize, font_color, int(size[0] / 0.004)))

# Pared norte (z=Z1): mira hacia -Z -> giro 180
sign("CartelCareta", "ZONA DE SOLDADURA\\nUSO OBLIGATORIO DE\\nCARETA Y GUANTES", (0.0, 2.7, Z1 - 0.03), 180, (1.7, 0.9), m_sign, "0.05, 0.05, 0.05, 1", 30)
sign("CartelSalida", "SALIDA", (6.0, 3.0, Z1 - 0.03), 180, (0.9, 0.28), m_green, "1, 1, 1, 1", 36)
# Pared este: mira hacia -X -> giro -90 (Z local -> -X)
sign("CartelMatafuego", "MATAFUEGO", (X1 - 0.03, 1.75, 0.8), -90, (0.5, 0.2), mat("cartel_rojo", (0.55, 0.05, 0.04), 0.6), "1, 1, 1, 1", 28)
# Pared oeste: mira hacia +X -> giro 90
sign("CartelGas", "CILINDROS DE GAS\\nASEGURAR CON CADENA", (X0 + 0.03, 2.0, 3.32), 90, (1.1, 0.5), m_sign, "0.05, 0.05, 0.05, 1", 24)
sign("CartelEPP", "SEGURIDAD PRIMERO", (0.0, 3.2, Z0 + 0.03), 0, (1.6, 0.3), m_green, "1, 1, 1, 1", 32)

out = "[gd_scene load_steps=%d format=3]\n\n" % (len(ext) + len(subs) + 1)
out += "\n".join(ext) + "\n\n" + "\n".join(subs) + "\n" + "\n".join(nodes)
with open(os.path.join(ROOT, "Scenes", "Workshop.tscn"), "w") as f:
    f.write(out)
print("Workshop.tscn:", len(subs), "subrecursos,", len(nodes), "nodos")
