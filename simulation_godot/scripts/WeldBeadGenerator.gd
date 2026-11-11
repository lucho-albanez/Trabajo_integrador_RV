class_name WeldBeadGenerator
extends Node3D

## ==============================================================================
## WeldBeadGenerator.gd - Generador Procedimental del Cordón de Soldadura 3D
## ==============================================================================
## Modela en tiempo real la geometría del cordón de soldadura SMAW sobre la chapa.
## Ajusta el ancho, sobre-espesor y convexidad según los parámetros de avance.

@export_group("Dimensiones del Cordón (mm)")
@export var base_width_mm: float = 6.0
@export var base_height_mm: float = 2.5
@export var min_point_distance_mm: float = 1.2 ## Distancia mínima entre perfiles sucesivos

@export_group("Materiales")
@export var weld_material: Material

var _mesh_instance: MeshInstance3D
var _immediate_mesh: ImmediateMesh
var _points: Array[Vector3] = []
var _normals: Array[Vector3] = []
var _quality_scores: Array[float] = []

const RADIAL_SEGMENTS: int = 6

func _ready() -> void:
	_immediate_mesh = ImmediateMesh.new()
	_mesh_instance = MeshInstance3D.new()
	_mesh_instance.mesh = _immediate_mesh
	add_child(_mesh_instance)

	if weld_material:
		_mesh_instance.material_override = weld_material
	else:
		_create_default_material()

func _create_default_material() -> void:
	var mat = StandardMaterial3D.new()
	mat.albedo_color = Color(0.25, 0.25, 0.28, 1.0) # Acero gris oscuro con escoria
	mat.metallic = 0.8
	mat.roughness = 0.45
	mat.emission_enabled = true
	mat.emission = Color(1.0, 0.4, 0.05) # Resplandor térmico anaranjado
	mat.emission_energy_multiplier = 0.8
	_mesh_instance.material_override = mat

func add_bead_point(pos: Vector3, normal: Vector3, quality_score: float, _delta: float) -> void:
	var local_pos = to_local(pos)

	if _points.size() > 0:
		var last_pos = _points[_points.size() - 1]
		var dist_mm = last_pos.distance_to(local_pos) * 1000.0
		if dist_mm < min_point_distance_mm:
			return # No saturar con vértices innecesarios si la antorcha no se movió

	_points.append(local_pos)
	_normals.append(normal.normalized())
	_quality_scores.append(quality_score)

	_rebuild_mesh()

func _rebuild_mesh() -> void:
	if _points.size() < 2:
		return

	_immediate_mesh.clear_surfaces()
	_immediate_mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES)

	for i in range(_points.size() - 1):
		var p0 = _points[i]
		var p1 = _points[i + 1]
		var n0 = _normals[i]
		var n1 = _normals[i + 1]
		var score0 = _quality_scores[i]
		var score1 = _quality_scores[i + 1]

		# Dirección de avance del cordón
		var forward = (p1 - p0).normalized()
		var right0 = forward.cross(n0).normalized()
		var right1 = forward.cross(n1).normalized()

		# Modulación del tamaño según la calidad (a mejor técnica, cordón más parejo)
		var scale0 = clampf(score0 / 100.0, 0.5, 1.2)
		var scale1 = clampf(score1 / 100.0, 0.5, 1.2)

		var half_w0 = (base_width_mm * 0.001 * 0.5) * scale0
		var h0 = (base_height_mm * 0.001) * scale0
		var half_w1 = (base_width_mm * 0.001 * 0.5) * scale1
		var h1 = (base_height_mm * 0.001) * scale1

		# Generar perfil semicilíndrico triangulado entre p0 y p1
		for s in range(RADIAL_SEGMENTS):
			var a0 = float(s) / float(RADIAL_SEGMENTS) * PI
			var a1 = float(s + 1) / float(RADIAL_SEGMENTS) * PI

			var v0_left = p0 + (-right0 * cos(a0) * half_w0) + (n0 * sin(a0) * h0)
			var v0_right = p0 + (-right0 * cos(a1) * half_w0) + (n0 * sin(a1) * h0)
			var v1_left = p1 + (-right1 * cos(a0) * half_w1) + (n1 * sin(a0) * h1)
			var v1_right = p1 + (-right1 * cos(a1) * half_w1) + (n1 * sin(a1) * h1)

			# Triángulo 1
			_immediate_mesh.surface_set_normal(n0)
			_immediate_mesh.surface_add_vertex(v0_left)
			_immediate_mesh.surface_set_normal(n1)
			_immediate_mesh.surface_add_vertex(v1_left)
			_immediate_mesh.surface_set_normal(n0)
			_immediate_mesh.surface_add_vertex(v0_right)

			# Triángulo 2
			_immediate_mesh.surface_set_normal(n0)
			_immediate_mesh.surface_add_vertex(v0_right)
			_immediate_mesh.surface_set_normal(n1)
			_immediate_mesh.surface_add_vertex(v1_left)
			_immediate_mesh.surface_set_normal(n1)
			_immediate_mesh.surface_add_vertex(v1_right)

	_immediate_mesh.surface_end()

## Limpia la probeta metálica para una nueva práctica
func clear_bead() -> void:
	_points.clear()
	_normals.clear()
	_quality_scores.clear()
	if _immediate_mesh:
		_immediate_mesh.clear_surfaces()
	print("[WeldBeadGenerator] Chapa limpiada para nueva práctica.")
