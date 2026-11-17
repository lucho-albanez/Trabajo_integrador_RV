"""Genera los modelos 3D del simulador (máquina, pinza de masa y portaelectrodo).

Uso (desde la carpeta del proyecto):
    pip install bpy            # Blender como módulo de Python (una sola vez)
    python tools/blender/make_models.py            # exporta Assets/models/*.glb
    python tools/blender/make_models.py --blend    # además guarda tools/blender/modelos.blend
    python tools/blender/make_models.py --preview  # además renderiza previews en /tmp

También se puede abrir en Blender (Scripting > Open > Run Script) y editar.
Todo está modelado en el sistema de coordenadas de Godot (Y arriba, +Z al frente,
metros) y convertido internamente. Materiales PBR lisos, sin texturas.
"""
import math
import os
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "Assets", "models"))

# Godot (x, y, z)  ->  Blender (x, -z, y)   (rotación propia, det = +1)
C = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
C_INV = C.inverted()


# --------------------------------------------------------------------------
# Materiales
# --------------------------------------------------------------------------
_materials = {}


def material(name, color, metallic=0.0, roughness=0.5, emission=None):
    if name in _materials:
        return _materials[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = roughness
    if emission:
        b.inputs["Emission Color"].default_value = (*emission, 1.0)
        b.inputs["Emission Strength"].default_value = 1.5
    _materials[name] = m
    return m


def palette():
    return {
        "paint": material("pintura_grafito", (0.085, 0.092, 0.10), 0.55, 0.48),
        "paint2": material("pintura_gris", (0.16, 0.17, 0.18), 0.5, 0.5),
        "alu": material("aluminio_cepillado", (0.62, 0.64, 0.66), 0.9, 0.38),
        "steel": material("acero", (0.50, 0.51, 0.53), 0.95, 0.35),
        "dark_metal": material("metal_oscuro", (0.12, 0.12, 0.13), 0.9, 0.45),
        "rubber": material("goma", (0.025, 0.025, 0.027), 0.0, 0.85),
        "plastic": material("plastico_negro", (0.05, 0.05, 0.055), 0.0, 0.55),
        "brass": material("laton", (0.74, 0.55, 0.22), 1.0, 0.3),
        "copper": material("cobre", (0.72, 0.38, 0.2), 1.0, 0.32),
        "orange": material("aislante_naranja", (0.88, 0.30, 0.04), 0.0, 0.5),
        "red": material("rojo", (0.75, 0.05, 0.04), 0.0, 0.45),
        "blue": material("azul", (0.05, 0.18, 0.7), 0.0, 0.45),
        "glass": material("vidrio_display", (0.006, 0.01, 0.012), 0.0, 0.08),
        "white": material("marca_blanca", (0.9, 0.9, 0.88), 0.0, 0.6),
        "wood": material("madera", (0.42, 0.29, 0.16), 0.0, 0.8),
        "cardboard": material("carton", (0.55, 0.42, 0.27), 0.0, 0.9),
        "yellow": material("amarillo_seguridad", (0.9, 0.7, 0.04), 0.0, 0.5),
        "toolred": material("rojo_gabinete", (0.5, 0.04, 0.035), 0.35, 0.42),
        "chrome": material("cromo", (0.8, 0.8, 0.82), 1.0, 0.18),
        "bluepaint": material("pintura_azul", (0.05, 0.16, 0.45), 0.35, 0.45),
        "tank_blue": material("tubo_azul", (0.06, 0.2, 0.5), 0.45, 0.4),
        "tank_red": material("tubo_rojo", (0.55, 0.05, 0.04), 0.45, 0.4),
        "drum": material("tambor", (0.1, 0.22, 0.34), 0.5, 0.5),
        "lamp_light": material("luz_lampara", (1.0, 0.97, 0.9), 0.0, 0.4, emission=(1.0, 0.95, 0.85)),
        "alu_duct": material("ducto_aluminio", (0.7, 0.72, 0.74), 0.85, 0.4),
    }


# --------------------------------------------------------------------------
# Primitivas (coordenadas de Godot)
# --------------------------------------------------------------------------
def _finish(bm, name, mat, bevel, bevel_seg=3):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(mat)
    if bevel > 0:
        bm2 = ob.modifiers.new("bisel", "BEVEL")
        bm2.width = bevel
        bm2.segments = bevel_seg
        bm2.limit_method = "ANGLE"
        bm2.angle_limit = math.radians(35)
        bm2.harden_normals = True
    for p in me.polygons:
        p.use_smooth = True
    wn = ob.modifiers.new("normales", "WEIGHTED_NORMAL")
    wn.keep_sharp = True
    return ob


def _bake(ob):
    """Aplica los modificadores al mesh."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    new = bpy.data.meshes.new_from_object(ev)
    old = ob.data
    ob.modifiers.clear()
    ob.data = new
    bpy.data.meshes.remove(old)
    return ob


def box(name, center, size, mat, bevel=0.002, seg=3, xf=None):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    return _place(bm, name, center, mat, bevel, seg, xf)


def cyl(name, center, radius, length, axis, mat, radius2=None, seg=40, bevel=0.0015, xf=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg,
                          radius1=radius, radius2=radius if radius2 is None else radius2, depth=length)
    rot = {"z": Matrix.Identity(4), "y": Matrix.Rotation(math.radians(-90), 4, "X"),
           "x": Matrix.Rotation(math.radians(90), 4, "Y")}[axis]
    bmesh.ops.transform(bm, matrix=rot, verts=bm.verts)
    return _place(bm, name, center, mat, bevel, 2, xf)


def prism(name, center, profile, depth, axis, mat, bevel=0.0, xf=None):
    """Extruye un contorno 2D (lista de (x, y)) a lo largo del eje, centrado."""
    bm = bmesh.new()
    verts = [bm.verts.new((x, y, -depth / 2)) for x, y in profile]
    f = bm.faces.new(verts)
    r = bmesh.ops.extrude_face_region(bm, geom=[f])
    vs = [e for e in r["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, 0, depth), verts=vs)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    rot = {"z": Matrix.Identity(4), "y": Matrix.Rotation(math.radians(-90), 4, "X"),
           "x": Matrix.Rotation(math.radians(90), 4, "Y")}[axis]
    bmesh.ops.transform(bm, matrix=rot, verts=bm.verts)
    return _place(bm, name, center, mat, bevel, 2, xf)


def ring(name, center, r_out, r_in, depth, axis, mat, seg=48):
    prof_o = [(r_out * math.cos(2 * math.pi * i / seg), r_out * math.sin(2 * math.pi * i / seg)) for i in range(seg)]
    bm = bmesh.new()
    n = seg
    z0, z1 = -depth / 2, depth / 2
    ro = [[bm.verts.new((r_out * math.cos(a), r_out * math.sin(a), z)) for a in [2 * math.pi * i / n for i in range(n)]] for z in (z0, z1)]
    ri = [[bm.verts.new((r_in * math.cos(a), r_in * math.sin(a), z)) for a in [2 * math.pi * i / n for i in range(n)]] for z in (z0, z1)]
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((ro[0][i], ro[0][j], ro[1][j], ro[1][i]))           # exterior
        bm.faces.new((ri[0][j], ri[0][i], ri[1][i], ri[1][j]))           # interior
        bm.faces.new((ro[1][i], ro[1][j], ri[1][j], ri[1][i]))           # tapa +
        bm.faces.new((ro[0][j], ro[0][i], ri[0][i], ri[0][j]))           # tapa -
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    rot = {"z": Matrix.Identity(4), "y": Matrix.Rotation(math.radians(-90), 4, "X"),
           "x": Matrix.Rotation(math.radians(90), 4, "Y")}[axis]
    bmesh.ops.transform(bm, matrix=rot, verts=bm.verts)
    return _place(bm, name, center, mat, 0.0, 1, None)


def _place(bm, name, center, mat, bevel, seg, xf):
    g = Matrix.Translation(center)
    if xf is not None:
        g = xf @ g
    bmesh.ops.transform(bm, matrix=C @ g, verts=bm.verts)
    ob = _finish(bm, name, mat, bevel, seg)
    return ob


def rot_about(axis, deg, pivot):
    """Rotación en coordenadas de Godot alrededor de un pivote."""
    ax = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[axis]
    return Matrix.Translation(pivot) @ Matrix.Rotation(math.radians(deg), 4, ax) @ Matrix.Translation(-Vector(pivot))


def export(name, objects, out_dir=OUT_DIR):
    for o in objects:
        _bake(o)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    joined = bpy.context.view_layer.objects.active
    joined.name = name
    joined.data.name = name
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name + ".glb")
    bpy.ops.object.select_all(action="DESELECT")
    joined.select_set(True)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True,
                              export_yup=True, export_apply=False, export_materials="EXPORT",
                              export_image_format="NONE")
    print("exportado", path)
    return joined


def new_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _materials.clear()


# --------------------------------------------------------------------------
# Máquina de soldar (inversor MMA ~200 A)
# --------------------------------------------------------------------------
def build_machine_body(M):
    o = []
    # Gabinete (el fondo queda en y = -0.225 incluyendo las patas)
    o.append(box("gabinete", (0, 0.006, 0), (0.30, 0.45, 0.50), M["paint"], bevel=0.014, seg=4))
    o.append(box("tapa", (0, 0.2315, -0.01), (0.27, 0.004, 0.44), M["paint2"], bevel=0.0015))
    # Chapa frontal de aluminio
    o.append(box("frente", (0, 0.006, 0.254), (0.288, 0.432, 0.008), M["alu"], bevel=0.003))
    for sx in (-1, 1):
        for sy in (-1, 1):
            o.append(cyl("tornillo", (sx * 0.131, 0.006 + sy * 0.198, 0.2605), 0.006, 0.003, "z", M["dark_metal"], seg=16, bevel=0.0006))
    # Visor del display
    o.append(box("marco_display", (0, 0.12, 0.2635), (0.156, 0.076, 0.006), M["plastic"], bevel=0.003))
    o.append(box("vidrio", (0, 0.12, 0.2668), (0.138, 0.058, 0.002), M["glass"], bevel=0.0008))
    # Escala de amperaje alrededor de la perilla (11 marcas de -135° a 135°)
    cx, cy = 0.0, -0.01
    for i in range(11):
        a = math.radians(135 - 27 * i)       # 135° (izq.-abajo) -> -135° (der.-abajo)
        big = i % 5 == 0
        r = 0.064
        L = 0.012 if big else 0.007
        px, py = cx + math.sin(a) * (r + L / 2), cy + math.cos(a) * (r + L / 2)
        xf = rot_about("z", -math.degrees(a), (px, py, 0.0))
        o.append(box("marca", (px, py, 0.2585), (0.0025, L, 0.001), M["paint"], bevel=0.0003, seg=1, xf=xf))
    o.append(ring("aro_perilla", (cx, cy, 0.2595), 0.052, 0.047, 0.003, "z", M["dark_metal"]))
    # Terminales tipo Dinse: collar de color, aro de latón y orificio
    for x, col in ((-0.085, "red"), (0.085, "blue")):
        o.append(cyl("collar", (x, -0.135, 0.266), 0.025, 0.016, "z", M[col], bevel=0.002))
        o.append(cyl("aro_laton", (x, -0.135, 0.2745), 0.019, 0.003, "z", M["brass"], seg=32, bevel=0.0006))
        o.append(cyl("orificio", (x, -0.135, 0.2765), 0.011, 0.002, "z", M["glass"], seg=24, bevel=0.0))
    # Interruptor: carcasa (la tecla se exporta aparte para poder inclinarla)
    o.append(box("carcasa_int", (0, -0.185, 0.2605), (0.05, 0.062, 0.004), M["plastic"], bevel=0.0015))
    # LED de encendido: bisel
    o.append(cyl("bisel_led", (-0.1, -0.01, 0.2585), 0.011, 0.003, "z", M["dark_metal"], seg=24, bevel=0.0006))
    o.append(cyl("bisel_led2", (0.1, -0.01, 0.2585), 0.011, 0.003, "z", M["dark_metal"], seg=24, bevel=0.0006))
    o.append(cyl("led_aux", (0.1, -0.01, 0.2605), 0.005, 0.002, "z", M["orange"], seg=16, bevel=0.0003))
    # Rejillas laterales
    for s in (-1, 1):
        x = s * 0.1515
        o.append(box("marco_rejilla", (x, 0.03, -0.04), (0.003, 0.16, 0.27), M["rubber"], bevel=0.001, seg=2))
        for k in range(9):
            o.append(box("lama", (x + s * 0.0012, -0.035 + k * 0.0145 + 0.03 - 0.0, -0.04), (0.003, 0.007, 0.25), M["paint2"], bevel=0.0008, seg=2))
    # Ventilador trasero
    o.append(cyl("rejilla_fondo", (0, 0.0, -0.2515), 0.12, 0.004, "z", M["rubber"], seg=48, bevel=0.0008))
    for r in (0.11, 0.08, 0.05):
        o.append(ring("aro_vent", (0, 0.0, -0.2545), r + 0.0035, r - 0.0035, 0.004, "z", M["dark_metal"]))
    o.append(box("barra_v", (0, 0, -0.2545), (0.006, 0.23, 0.004), M["dark_metal"], bevel=0.0008, seg=2))
    o.append(box("barra_h", (0, 0, -0.2545), (0.23, 0.006, 0.004), M["dark_metal"], bevel=0.0008, seg=2))
    # Patas de goma
    for sx in (-1, 1):
        for sz in (-1, 1):
            o.append(cyl("pata", (sx * 0.11, -0.222, sz * 0.19), 0.022, 0.006, "y", M["rubber"], seg=24, bevel=0.0012))
    # Manija de transporte
    for sz in (-1, 1):
        o.append(box("soporte_manija", (0, 0.2425, sz * 0.12), (0.06, 0.02, 0.02), M["plastic"], bevel=0.003))
    o.append(box("manija", (0, 0.2775, 0), (0.05, 0.016, 0.27), M["rubber"], bevel=0.007, seg=4))
    for sz in (-1, 1):
        o.append(box("puntal", (0, 0.2575, sz * 0.12), (0.05, 0.03, 0.018), M["rubber"], bevel=0.005, seg=3))
    return o


def build_knob(M):
    o = []
    teeth = 28
    prof = []
    for i in range(teeth * 4):
        a = 2 * math.pi * i / (teeth * 4)
        r = 0.0335 if (i % 4) in (0, 1) else 0.0305
        prof.append((r * math.cos(a), r * math.sin(a)))
    o.append(prism("estriado", (0, 0, 0.014), prof, 0.028, "z", M["plastic"], bevel=0.0008))
    o.append(cyl("faldon", (0, 0, 0.0025), 0.04, 0.005, "z", M["dark_metal"], seg=48, bevel=0.0008))
    o.append(cyl("tapa", (0, 0, 0.0295), 0.024, 0.004, "z", M["paint2"], seg=48, bevel=0.0012))
    o.append(box("indicador", (0, 0.0235, 0.0305), (0.0045, 0.02, 0.003), M["white"], bevel=0.0006, seg=2))
    return o


def build_rocker(M):
    o = []
    o.append(box("tecla", (0, 0, 0.007), (0.034, 0.044, 0.012), M["rubber"], bevel=0.003))
    o.append(box("tecla_marca", (0, 0.012, 0.0135), (0.004, 0.012, 0.002), M["white"], bevel=0.0004, seg=1))
    o.append(cyl("tecla_marca_o", (0, -0.012, 0.0135), 0.0045, 0.002, "z", M["red"], seg=20, bevel=0.0004))
    return o


# --------------------------------------------------------------------------
# Portaelectrodo (mango a lo largo de Z, electrodo en +Y desde z = 0.119)
# --------------------------------------------------------------------------
def build_holder(M):
    o = []
    # Prensacable de goma
    o.append(cyl("prensacable", (0, 0, -0.155), 0.0125, 0.026, "z", M["rubber"], radius2=0.0215, seg=32, bevel=0.0008))
    # Mango aislante
    o.append(cyl("mango", (0, 0, -0.04), 0.0225, 0.21, "z", M["plastic"], seg=48, bevel=0.003))
    for k in range(9):
        o.append(cyl("estria", (0, 0, -0.125 + k * 0.016), 0.0237, 0.0045, "z", M["rubber"], seg=40, bevel=0.0008))
    o.append(cyl("anillo", (0, 0, 0.0645), 0.0245, 0.012, "z", M["orange"], seg=48, bevel=0.0015))
    # Cabeza: protector aislante + mordaza de cobre
    o.append(box("protector", (0, 0, 0.0905), (0.046, 0.06, 0.03), M["plastic"], bevel=0.005))
    o.append(box("cuerpo_mordaza", (0, -0.004, 0.1195), (0.034, 0.05, 0.03), M["copper"], bevel=0.004))
    o.append(box("mordaza_sup", (0, 0.0225, 0.1195), (0.03, 0.01, 0.032), M["brass"], bevel=0.0025))
    for k in range(4):
        o.append(box("diente", (0, 0.0285, 0.108 + k * 0.0075), (0.026, 0.002, 0.003), M["dark_metal"], bevel=0.0004, seg=1))
    o.append(cyl("entrada", (0, 0.0275, 0.1195), 0.0042, 0.003, "y", M["glass"], seg=16, bevel=0.0))
    # Palanca de apertura con resorte
    o.append(box("palanca", (0.0265, 0.0, 0.0955), (0.012, 0.056, 0.026), M["orange"], bevel=0.003))
    o.append(box("palanca_grip", (0.0265, 0.0, 0.0955), (0.0125, 0.03, 0.018), M["rubber"], bevel=0.002))
    o.append(cyl("resorte", (0.0, -0.034, 0.1195), 0.006, 0.014, "y", M["steel"], seg=16, bevel=0.0006))
    o.append(cyl("perno", (0.0, 0.0, 0.1195), 0.0045, 0.054, "x", M["dark_metal"], seg=16, bevel=0.0005))
    return o


# --------------------------------------------------------------------------
# Pinza de masa (mandíbulas abiertas 6 cm para abrazar la mesa, ejes a lo largo de Z)
# --------------------------------------------------------------------------
def build_clamp(M):
    o = []
    pivot = (0.0, 0.03, 0.0)
    # Mandíbula inferior (cobre) y su brazo trasero inclinado
    o.append(box("jaw_inf", (0, -0.006, 0.05), (0.024, 0.012, 0.10), M["copper"], bevel=0.0025))
    o.append(box("brazo_inf", (0, -0.006, -0.05), (0.024, 0.012, 0.10), M["steel"], bevel=0.0025, xf=rot_about("x", -14, pivot)))
    o.append(box("grip_inf", (0, -0.006, -0.065), (0.032, 0.022, 0.06), M["rubber"], bevel=0.005, xf=rot_about("x", -14, pivot)))
    # Mandíbula superior
    o.append(box("jaw_sup", (0, 0.066, 0.05), (0.024, 0.012, 0.10), M["copper"], bevel=0.0025))
    o.append(box("brazo_sup", (0, 0.066, -0.05), (0.024, 0.012, 0.10), M["steel"], bevel=0.0025, xf=rot_about("x", 14, pivot)))
    o.append(box("grip_sup", (0, 0.066, -0.065), (0.032, 0.022, 0.06), M["rubber"], bevel=0.005, xf=rot_about("x", 14, pivot)))
    # Dientes de las mandíbulas (enfrentados)
    for k in range(6):
        z = 0.03 + k * 0.012
        o.append(box("diente_i", (0, 0.0004, z), (0.02, 0.0035, 0.004), M["dark_metal"], bevel=0.0005, seg=1))
        o.append(box("diente_s", (0, 0.0596, z), (0.02, 0.0035, 0.004), M["dark_metal"], bevel=0.0005, seg=1))
    # Remaches y pivote: columna que une ambos brazos
    o.append(cyl("pivote", (0, 0.03, 0.0), 0.0075, 0.082, "y", M["dark_metal"], seg=24, bevel=0.001))
    o.append(cyl("pivote_cab", (0, 0.073, 0.0), 0.011, 0.004, "y", M["steel"], seg=24, bevel=0.001))
    o.append(cyl("pivote_cab2", (0, -0.013, 0.0), 0.011, 0.004, "y", M["steel"], seg=24, bevel=0.001))
    # Resorte entre los brazos traseros (abarca la separación en z = -0.068)
    for k in range(11):
        o.append(cyl("espira", (0, -0.014 + k * 0.0085, -0.068), 0.0085, 0.003, "y", M["steel"], seg=20, bevel=0.0004))
    # Prensacable: el cable sale por el extremo del mango inferior
    o.append(cyl("bota", (0, -0.006, -0.125), 0.009, 0.034, "z", M["rubber"], radius2=0.0145, seg=24, bevel=0.001,
                 xf=rot_about("x", -14, pivot)))
    return o


# --------------------------------------------------------------------------
# Utilería del taller (origen en el piso salvo indicación)
# --------------------------------------------------------------------------
def build_gas_cylinder(M, tank):
    o = []
    o.append(cyl("cuerpo", (0, 0.62, 0), 0.115, 1.14, "y", M[tank], seg=40, bevel=0.01))
    o.append(cyl("hombro", (0, 1.27, 0), 0.115, 0.14, "y", M[tank], radius2=0.045, seg=40, bevel=0.004))
    o.append(cyl("cuello", (0, 1.38, 0), 0.04, 0.09, "y", M["steel"], seg=24, bevel=0.003))
    o.append(cyl("valvula", (0, 1.46, 0), 0.03, 0.07, "y", M["brass"], seg=20, bevel=0.003))
    o.append(box("volante", (0, 1.515, 0), (0.1, 0.012, 0.022), M["red"], bevel=0.003))
    o.append(cyl("salida", (0.045, 1.44, 0), 0.012, 0.05, "x", M["brass"], seg=16, bevel=0.002))
    o.append(cyl("base", (0, 0.025, 0), 0.12, 0.05, "y", M["dark_metal"], seg=40, bevel=0.005))
    o.append(cyl("faja", (0, 0.9, 0), 0.1165, 0.05, "y", M["white"], seg=40, bevel=0.002))
    return o


def build_shelf(M):
    o = []
    w, d, h = 1.3, 0.5, 1.9
    for sx in (-1, 1):
        for sz in (-1, 1):
            o.append(box("montante", (sx * (w / 2 - 0.025), h / 2, sz * (d / 2 - 0.025)), (0.05, h, 0.05), M["bluepaint"], bevel=0.003))
    for k, y in enumerate((0.15, 0.7, 1.25, 1.8)):
        for sz in (-1, 1):
            o.append(box("larguero", (0, y, sz * (d / 2 - 0.025)), (w, 0.07, 0.04), M["orange"], bevel=0.004))
        o.append(box("estante", (0, y + 0.03, 0), (w - 0.06, 0.012, d - 0.06), M["steel"], bevel=0.002))
    # Cajas y piezas
    o.append(box("caja1", (-0.38, 0.28, 0.0), (0.4, 0.22, 0.34), M["cardboard"], bevel=0.004))
    o.append(box("caja2", (0.12, 0.26, 0.02), (0.3, 0.18, 0.3), M["cardboard"], bevel=0.004))
    o.append(box("cajon", (0.45, 0.30, 0.0), (0.26, 0.24, 0.36), M["plastic"], bevel=0.006))
    o.append(box("caja3", (-0.3, 0.83, 0.0), (0.5, 0.26, 0.36), M["cardboard"], bevel=0.004))
    o.append(box("cajon2", (0.3, 0.84, 0.0), (0.4, 0.28, 0.34), M["bluepaint"], bevel=0.006))
    for k in range(5):
        o.append(cyl("tubo", (-0.45 + k * 0.0, 1.31 + k * 0.0, -0.1 + k * 0.05), 0.022, 1.1, "x", M["steel"], seg=16, bevel=0.001, xf=Matrix.Translation((0.45, 0, 0))))
    o.append(box("caja4", (0.35, 1.38, 0.0), (0.3, 0.2, 0.34), M["cardboard"], bevel=0.004))
    o.append(box("caja5", (-0.3, 1.9, 0.0), (0.45, 0.2, 0.34), M["cardboard"], bevel=0.004))
    return o


def build_extractor(M):
    """Mástil con brazo de extracción de humos; el brazo se extiende hacia -Z."""
    o = []
    o.append(cyl("base", (0, 0.015, 0), 0.2, 0.03, "y", M["dark_metal"], seg=32, bevel=0.004))
    o.append(cyl("mastil", (0, 1.0, 0), 0.05, 2.0, "y", M["paint2"], seg=24, bevel=0.004))
    o.append(cyl("rotula", (0, 2.02, 0), 0.075, 0.1, "y", M["yellow"], seg=24, bevel=0.005))
    o.append(cyl("brazo1", (0, 2.02, -0.55), 0.07, 1.0, "z", M["alu_duct"], seg=28, bevel=0.003))
    o.append(cyl("junta", (0, 2.02, -1.05), 0.085, 0.1, "y", M["yellow"], seg=24, bevel=0.005))
    o.append(cyl("brazo2", (0, 1.88, -1.12), 0.07, 0.3, "y", M["alu_duct"], seg=28, bevel=0.003))
    o.append(cyl("campana", (0, 1.62, -1.12), 0.2, 0.22, "y", M["alu_duct"], radius2=0.07, seg=36, bevel=0.003))
    o.append(ring("aro_campana", (0, 1.505, -1.12), 0.2, 0.185, 0.012, "y", M["yellow"]))
    return o


def build_extinguisher(M):
    """Origen en la base; placa de pared hacia -Z."""
    o = []
    o.append(box("placa", (0, 0.3, -0.1), (0.14, 0.5, 0.01), M["dark_metal"], bevel=0.002))
    o.append(cyl("cuerpo", (0, 0.24, 0), 0.08, 0.44, "y", M["red"], seg=32, bevel=0.012))
    o.append(cyl("hombro", (0, 0.49, 0), 0.08, 0.05, "y", M["red"], radius2=0.03, seg=32, bevel=0.004))
    o.append(cyl("cabezal", (0, 0.54, 0), 0.03, 0.05, "y", M["dark_metal"], seg=20, bevel=0.003))
    o.append(box("palanca", (0, 0.575, 0.03), (0.02, 0.012, 0.09), M["steel"], bevel=0.003))
    o.append(box("etiqueta", (0, 0.28, 0.0795), (0.1, 0.14, 0.003), M["white"], bevel=0.0008, seg=1))
    o.append(box("correa", (0, 0.34, -0.02), (0.18, 0.025, 0.14), M["rubber"], bevel=0.004))
    return o


def build_toolbox(M):
    o = []
    w, d, h = 0.75, 0.46, 0.85
    o.append(box("cuerpo", (0, 0.1 + h / 2, 0), (w, h - 0.1, d), M["toolred"], bevel=0.008))
    o.append(box("tapa", (0, 0.1 + h + 0.01, 0), (w + 0.02, 0.025, d + 0.02), M["dark_metal"], bevel=0.005))
    for k in range(4):
        y = 0.22 + k * 0.17
        o.append(box("cajon_marco", (0, y, d / 2 + 0.002), (w - 0.06, 0.15, 0.004), M["paint"], bevel=0.003))
        o.append(box("manija", (0, y + 0.03, d / 2 + 0.02), (0.3, 0.014, 0.025), M["chrome"], bevel=0.005))
    for sx in (-1, 1):
        for sz in (-1, 1):
            o.append(cyl("rueda", (sx * 0.3, 0.05, sz * 0.15), 0.05, 0.04, "x", M["rubber"], seg=24, bevel=0.004))
            o.append(box("horquilla", (sx * 0.3, 0.09, sz * 0.15), (0.05, 0.06, 0.05), M["dark_metal"], bevel=0.003))
    return o


def build_drum(M):
    o = []
    o.append(cyl("cuerpo", (0, 0.44, 0), 0.29, 0.88, "y", M["drum"], seg=40, bevel=0.008))
    for y in (0.15, 0.44, 0.73):
        o.append(cyl("nervio", (0, y, 0), 0.298, 0.03, "y", M["drum"], seg=40, bevel=0.006))
    o.append(ring("borde", (0, 0.885, 0), 0.3, 0.27, 0.03, "y", M["dark_metal"]))
    o.append(cyl("tapa", (0, 0.878, 0), 0.272, 0.01, "y", M["dark_metal"], seg=40, bevel=0.002))
    o.append(cyl("tapon", (0.12, 0.89, 0.08), 0.03, 0.012, "y", M["brass"], seg=16, bevel=0.002))
    return o


def build_pallet(M):
    o = []
    for k in range(3):
        o.append(box("larguero", (0, 0.07, -0.4 + k * 0.4), (1.2, 0.09, 0.1), M["wood"], bevel=0.003))
    for k in range(7):
        o.append(box("tabla", (-0.55 + k * 0.183, 0.13, 0), (0.1, 0.022, 0.98), M["wood"], bevel=0.002))
    o.append(box("caja1", (-0.28, 0.33, 0.0), (0.55, 0.4, 0.7), M["cardboard"], bevel=0.005))
    o.append(box("caja2", (0.3, 0.3, 0.05), (0.5, 0.34, 0.6), M["cardboard"], bevel=0.005))
    o.append(box("caja3", (-0.28, 0.72, 0.0), (0.5, 0.36, 0.6), M["cardboard"], bevel=0.005))
    o.append(box("cinta", (-0.28, 0.5, 0.0), (0.56, 0.01, 0.1), M["white"], bevel=0.0008, seg=1))
    return o


def build_lamp(M):
    """Campana industrial colgante; el origen está en el punto de sujeción al techo."""
    o = []
    o.append(cyl("cadena", (0, -0.3, 0), 0.008, 0.6, "y", M["dark_metal"], seg=8, bevel=0.0))
    o.append(cyl("sujecion", (0, -0.62, 0), 0.04, 0.05, "y", M["dark_metal"], seg=16, bevel=0.003))
    o.append(cyl("campana", (0, -0.74, 0), 0.34, 0.2, "y", M["paint2"], radius2=0.06, seg=40, bevel=0.004))
    o.append(cyl("difusor", (0, -0.843, 0), 0.25, 0.012, "y", M["lamp_light"], seg=40, bevel=0.0))
    return o


def render_preview(path, loc, target, objects=None, size=(900, 700), samples=24):
    """Render rápido con Cycles (CPU) para revisar el aspecto."""
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = samples
    sc.cycles.device = "CPU"
    sc.render.resolution_x, sc.render.resolution_y = size
    sc.render.filepath = path
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.28, 0.3, 0.33, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    sc.world = world
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.lens = 55
    cam.location = Vector(loc)
    d = Vector(target) - cam.location
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    for pos, energy in (((2, -2, 3), 600), ((-3, -1, 1.5), 250)):
        ld = bpy.data.lights.new("l", "AREA")
        ld.energy = energy
        ld.size = 2
        lo = bpy.data.objects.new("l", ld)
        sc.collection.objects.link(lo)
        lo.location = pos
        lo.rotation_euler = (Vector((0, 0, 0.3)) - lo.location).to_track_quat("-Z", "Y").to_euler()
    plane = bpy.data.meshes.new("p")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=3)
    bm.to_mesh(plane)
    po = bpy.data.objects.new("suelo", plane)
    po.data.materials.append(material("suelo", (0.3, 0.3, 0.3), 0, 0.9))
    sc.collection.objects.link(po)
    po.location = (0, 0, -0.226)
    bpy.ops.render.render(write_still=True)


def main():
    preview = "--preview" in sys.argv
    save_blend = "--blend" in sys.argv

    new_scene()
    M = palette()
    objs = build_machine_body(M)
    body = export("machine_body", objs)
    if preview:
        render_preview("/tmp/prev_machine.png", (0.55, -0.9, 0.35), (0, 0, 0.02))
    new_scene(); M = palette(); export("machine_knob", build_knob(M))
    new_scene(); M = palette(); export("machine_rocker", build_rocker(M))
    new_scene(); M = palette()
    h = export("electrode_holder", build_holder(M))
    if preview:
        render_preview("/tmp/prev_holder.png", (0.35, -0.2, 0.25), (0, 0.0, 0.02), size=(800, 600))
    new_scene(); M = palette()
    c = export("ground_clamp", build_clamp(M))
    if preview:
        render_preview("/tmp/prev_clamp.png", (0.28, -0.28, 0.2), (0, 0, 0.0), size=(800, 600))
    for name, builder, args in (
        ("gas_cylinder_blue", build_gas_cylinder, ("tank_blue",)),
        ("gas_cylinder_red", build_gas_cylinder, ("tank_red",)),
        ("shelf", build_shelf, ()),
        ("extractor_arm", build_extractor, ()),
        ("fire_extinguisher", build_extinguisher, ()),
        ("toolbox", build_toolbox, ()),
        ("drum", build_drum, ()),
        ("pallet_boxes", build_pallet, ()),
        ("ceiling_lamp", build_lamp, ()),
    ):
        new_scene(); M = palette()
        export(name, builder(M, *args))
    if preview:
        new_scene(); M = palette()
        export("_preview_props", build_shelf(M) + [o for o in build_toolbox(M)], out_dir="/tmp/prev_out")
        render_preview("/tmp/prev_props.png", (1.6, -2.4, 1.6), (0, 0, 0.8), size=(900, 700))
    if save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "modelos.blend"))


if __name__ == "__main__":
    main()
