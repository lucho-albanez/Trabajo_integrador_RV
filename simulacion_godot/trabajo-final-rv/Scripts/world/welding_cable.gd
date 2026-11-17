class_name WeldingCable
extends MeshInstance3D
## Cable de soldadura procedural entre dos nodos (curva con caída por gravedad).
## Solo regenera la malla cuando los extremos se mueven.

@export var start_node: Node3D
@export var end_node: Node3D

@export var cable_radius: float = 0.012          # 1,2 cm
@export var cable_resolution: int = 18           # segmentos a lo largo de la curva
@export var cable_radial_segments: int = 6       # lados de la sección
@export var sag_factor: float = 0.35             # cuánto cuelga el cable
@export var cable_color: Color = Color(0.1, 0.1, 0.1):
	set(value):
		cable_color = value
		if _material != null:
			_material.albedo_color = value

const MOVE_EPSILON := 0.001

var _immediate_mesh: ImmediateMesh
var _material: StandardMaterial3D
var _ground_y: float = -INF
var _last_start: Vector3 = Vector3(INF, INF, INF)
var _last_end: Vector3 = Vector3(INF, INF, INF)
var _last_ground_y: float = INF


func _ready() -> void:
	_immediate_mesh = ImmediateMesh.new()
	mesh = _immediate_mesh
	_material = StandardMaterial3D.new()
	_material.albedo_color = cable_color
	_material.roughness = 0.7
	material_override = _material
	cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF


func _physics_process(_delta: float) -> void:
	if not _endpoints_ready():
		return
	# Evita que el cable atraviese mesas y piso: raycast vertical en el punto medio.
	var p_start := start_node.global_position
	var p_end := end_node.global_position
	var mid := (p_start + p_end) * 0.5
	var sag := minf(p_start.distance_to(p_end) * sag_factor, 1.8)
	var space := get_world_3d().direct_space_state
	var query := PhysicsRayQueryParameters3D.create(
		mid + Vector3(0.0, sag * 1.2 + 0.3, 0.0), mid - Vector3(0.0, 2.0, 0.0), PhysicsLayers.WORLD)
	var hit := space.intersect_ray(query)
	_ground_y = hit.position.y if not hit.is_empty() else -INF


func _process(_delta: float) -> void:
	if not _endpoints_ready():
		return
	var p_start := start_node.global_position
	var p_end := end_node.global_position
	if p_start.distance_to(_last_start) < MOVE_EPSILON and p_end.distance_to(_last_end) < MOVE_EPSILON \
			and absf(_ground_y - _last_ground_y) < MOVE_EPSILON:
		return
	_last_start = p_start
	_last_end = p_end
	_last_ground_y = _ground_y
	_generate(p_start, p_end)


func _endpoints_ready() -> bool:
	return start_node != null and end_node != null \
		and start_node.is_inside_tree() and end_node.is_inside_tree()


func _generate(p_start: Vector3, p_end: Vector3) -> void:
	var dist := p_start.distance_to(p_end)
	if dist < 0.01:
		return
	var p_mid := (p_start + p_end) * 0.5
	p_mid.y -= minf(dist * sag_factor, 1.8)
	if _ground_y > -INF:
		p_mid.y = maxf(p_mid.y, _ground_y + cable_radius * 1.5)

	var points: Array[Vector3] = []
	for i in range(cable_resolution + 1):
		var t := float(i) / float(cable_resolution)
		var p := (1.0 - t) * (1.0 - t) * p_start + 2.0 * (1.0 - t) * t * p_mid + t * t * p_end
		points.append(to_local(p))

	var rings: Array = []
	var normals: Array = []
	for i in range(points.size()):
		var p := points[i]
		var forward := Vector3.FORWARD
		if i < points.size() - 1:
			forward = (points[i + 1] - p).normalized()
		elif i > 0:
			forward = (p - points[i - 1]).normalized()
		var up := Vector3.UP
		if absf(forward.dot(up)) > 0.95:
			up = Vector3.RIGHT
		var right := forward.cross(up).normalized()
		up = right.cross(forward).normalized()
		var ring: Array[Vector3] = []
		var ring_n: Array[Vector3] = []
		for j in range(cable_radial_segments):
			var angle := float(j) / float(cable_radial_segments) * TAU
			var dir := right * cos(angle) + up * sin(angle)
			ring.append(p + dir * cable_radius)
			ring_n.append(dir)
		rings.append(ring)
		normals.append(ring_n)

	_immediate_mesh.clear_surfaces()
	_immediate_mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
	for i in range(rings.size() - 1):
		var r1: Array = rings[i]
		var r2: Array = rings[i + 1]
		var n1: Array = normals[i]
		var n2: Array = normals[i + 1]
		for j in range(cable_radial_segments):
			var k := (j + 1) % cable_radial_segments
			_add_vertex(r1[j], n1[j])
			_add_vertex(r1[k], n1[k])
			_add_vertex(r2[k], n2[k])
			_add_vertex(r1[j], n1[j])
			_add_vertex(r2[k], n2[k])
			_add_vertex(r2[j], n2[j])
	_immediate_mesh.surface_end()


func _add_vertex(v: Vector3, n: Vector3) -> void:
	_immediate_mesh.surface_set_normal(n)
	_immediate_mesh.surface_add_vertex(v)
