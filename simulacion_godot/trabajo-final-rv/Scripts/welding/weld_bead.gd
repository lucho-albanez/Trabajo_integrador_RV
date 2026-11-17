class_name WeldBead
extends MeshInstance3D
## Generador procedural del cordón de soldadura.
##
## Guarda una sección transversal (ancho, altura, desvío, temperatura) cada
## SPACING_MM a lo largo de la junta y reconstruye una malla continua. La
## temperatura de cada sección decae con el tiempo (baño incandescente que se
## enfría a acero). Coordenadas en el marco local de la probeta (ver Coupon).

const SPACING_MM := 1.0
const PROFILE_POINTS := 9
const COOL_TIME_S := 2.5
const REBUILD_INTERVAL_S := 0.05
const BASE_LIFT_M := 0.0002
const SHADER_PATH := "res://Shaders/weld_bead.gdshader"
## Huecos de al menos este largo (mm) dentro del cordón cuentan como interrupción.
const INTERRUPTION_MM := 3.0

@export var seam_length_mm: float = 150.0

var _count: int = 0
var _filled: PackedByteArray = PackedByteArray()
var _flag: PackedByteArray = PackedByteArray()
var _width: PackedFloat32Array = PackedFloat32Array()
var _height: PackedFloat32Array = PackedFloat32Array()
var _lateral: PackedFloat32Array = PackedFloat32Array()
var _temp: PackedFloat32Array = PackedFloat32Array()
var _filled_count: int = 0
var _dirty: bool = false
var _hot: bool = false
var _timer: float = 0.0


func _ready() -> void:
	var mat := ShaderMaterial.new()
	mat.shader = load(SHADER_PATH) as Shader
	material_override = mat
	cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	if _count == 0:
		reset(seam_length_mm)


## Borra el cordón y lo dimensiona para una junta de length_mm.
func reset(length_mm: float) -> void:
	seam_length_mm = length_mm
	_count = int(ceil(length_mm / SPACING_MM)) + 1
	_filled = PackedByteArray()
	_filled.resize(_count)
	_flag = PackedByteArray()
	_flag.resize(_count)
	_width = PackedFloat32Array()
	_width.resize(_count)
	_height = PackedFloat32Array()
	_height.resize(_count)
	_lateral = PackedFloat32Array()
	_lateral.resize(_count)
	_temp = PackedFloat32Array()
	_temp.resize(_count)
	_filled_count = 0
	_hot = false
	_dirty = false
	mesh = null


## Deposita metal entre las posiciones (s0, v0) y (s1, v1) [mm] recorridas en este paso.
func deposit_span(s0: float, v0: float, s1: float, v1: float, width_mm: float, height_mm: float, defect: bool) -> void:
	var i0 := roundi(minf(s0, s1) / SPACING_MM)
	var i1 := roundi(maxf(s0, s1) / SPACING_MM)
	var span := float(maxi(i1 - i0, 1))
	for idx in range(i0, i1 + 1):
		if idx < 0 or idx >= _count:
			continue
		var t := float(idx - i0) / span
		# Si el paso fue hacia atrás, la interpolación se invierte.
		var frac := t if s1 >= s0 else 1.0 - t
		_deposit_at(idx, lerpf(v0, v1, frac), width_mm, height_mm, defect)
	_dirty = true
	_hot = true


## Fracción de la junta cubierta por cordón (0..1).
func coverage() -> float:
	return float(_filled_count) / float(maxi(_count, 1))


## Longitud de cordón depositado [mm].
func length_mm() -> float:
	return _filled_count * SPACING_MM


## Cantidad de interrupciones (huecos >= INTERRUPTION_MM entre secciones depositadas).
func interruptions() -> int:
	var first := -1
	var last := -1
	for i in range(_count):
		if _filled[i] != 0:
			if first < 0:
				first = i
			last = i
	if first < 0:
		return 0
	var gaps := 0
	var run := 0
	for i in range(first, last + 1):
		if _filled[i] == 0:
			run += 1
		else:
			if float(run) * SPACING_MM >= INTERRUPTION_MM:
				gaps += 1
			run = 0
	return gaps


func _deposit_at(idx: int, v_mm: float, width_mm: float, height_mm: float, defect: bool) -> void:
	if _filled[idx] == 0:
		_filled[idx] = 1
		_filled_count += 1
		_width[idx] = width_mm
		_height[idx] = height_mm
		_lateral[idx] = v_mm
	else:
		# Pasar de nuevo sobre metal ya depositado lo ensancha y acumula altura.
		_width[idx] = maxf(_width[idx], width_mm)
		_height[idx] = minf(_height[idx] + 0.25 * height_mm, 6.0)
		_lateral[idx] = lerpf(_lateral[idx], v_mm, 0.5)
	if defect:
		_flag[idx] = 1
	_temp[idx] = 1.0


func _process(delta: float) -> void:
	if _hot:
		var any_hot := false
		var step := delta / COOL_TIME_S
		for i in range(_count):
			if _temp[i] > 0.0:
				_temp[i] = maxf(_temp[i] - step, 0.0)
				if _temp[i] > 0.0:
					any_hot = true
		_hot = any_hot
		_dirty = true
	if _dirty:
		_timer += delta
		if _timer >= REBUILD_INTERVAL_S:
			_timer = 0.0
			_dirty = false
			_rebuild()


func _rebuild() -> void:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var prev: Array[Dictionary] = []
	var prev_valid := false
	var any := false
	for i in range(_count):
		if _filled[i] == 0:
			prev_valid = false
			continue
		var ring := _ring(i)
		if prev_valid:
			for k in range(PROFILE_POINTS - 1):
				var a: Dictionary = prev[k]
				var b: Dictionary = prev[k + 1]
				var c: Dictionary = ring[k + 1]
				var d: Dictionary = ring[k]
				_tri(st, a, b, c)
				_tri(st, a, c, d)
				any = true
		prev = ring
		prev_valid = true
	if not any:
		mesh = null
		return
	st.generate_normals()
	mesh = st.commit()


func _ring(i: int) -> Array[Dictionary]:
	var s_m := (float(i) * SPACING_MM - seam_length_mm * 0.5) / 1000.0
	var w := _width[i] / 1000.0
	var h := _height[i] / 1000.0
	var z0 := _lateral[i] / 1000.0
	var ripple := 1.0 + 0.08 * sin(float(i) * 1.9)
	var col := Color(_temp[i], 0.0, float(_flag[i]), 1.0)
	var ring: Array[Dictionary] = []
	for k in range(PROFILE_POINTS):
		var t := float(k) / float(PROFILE_POINTS - 1)
		var u := 2.0 * t - 1.0
		var y := BASE_LIFT_M + h * ripple * pow(maxf(1.0 - u * u, 0.0), 0.7)
		ring.append({"p": Vector3(s_m, y, z0 + u * w * 0.5), "c": col, "uv": Vector2(float(i), t)})
	return ring


func _tri(st: SurfaceTool, a: Dictionary, b: Dictionary, c: Dictionary) -> void:
	for v in [a, b, c]:
		var vert: Dictionary = v
		st.set_color(vert["c"])
		st.set_uv(vert["uv"])
		st.add_vertex(vert["p"])
