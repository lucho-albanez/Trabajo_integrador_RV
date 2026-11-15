@tool
class_name WeldingCable
extends MeshInstance3D

@export var start_node_path: NodePath
@export var end_node_path: NodePath

@export var cable_radius: float = 0.012 # Grosor del cable (1.2 cm)
@export var cable_resolution: int = 18  # Segmentos a lo largo de la curva
@export var cable_radial_segments: int = 6 # Lados del cilindro
@export var sag_factor: float = 0.35     # Cuánto cuelga el cable por gravedad

@export var cable_color: Color = Color(0.1, 0.1, 0.1):
	set(val):
		cable_color = val
		if _cable_material:
			_cable_material.albedo_color = cable_color

var _start_node: Node3D
var _end_node: Node3D
var _immediate_mesh: ImmediateMesh
var _cable_material: StandardMaterial3D


func _init():
	if mesh == null:
		_immediate_mesh = ImmediateMesh.new()
		mesh = _immediate_mesh
	elif mesh is ImmediateMesh:
		_immediate_mesh = mesh
	else:
		_immediate_mesh = ImmediateMesh.new()
		mesh = _immediate_mesh


func _get_configuration_warnings() -> PackedStringArray:
	# Suprime el aviso de MeshInstance3D en el editor ya que generamos la malla procedimentalmente
	return PackedStringArray()


func _ready():
	if _immediate_mesh == null:
		_immediate_mesh = ImmediateMesh.new()
		mesh = _immediate_mesh
	
	_cable_material = StandardMaterial3D.new()
	_cable_material.albedo_color = cable_color
	_cable_material.roughness = 0.7
	material_override = _cable_material
	
	if not Engine.is_editor_hint():
		_resolve_nodes()


func _resolve_nodes():
	if not start_node_path.is_empty():
		_start_node = get_node_or_null(start_node_path)
	if not end_node_path.is_empty():
		_end_node = get_node_or_null(end_node_path)


func _process(_delta):
	# Solo simular en ejecución, no en el editor para evitar cálculos innecesarios
	if Engine.is_editor_hint():
		return

	if _start_node == null or _end_node == null:
		_resolve_nodes()
		if _start_node == null or _end_node == null:
			return

	if not _start_node.is_inside_tree() or not _end_node.is_inside_tree():
		return

	_generate_cable()


func _generate_cable():
	var p_start = _start_node.global_position
	var p_end = _end_node.global_position
	
	var dist = p_start.distance_to(p_end)
	if dist < 0.01:
		return
		
	# Punto medio con caída por gravedad
	var p_mid = (p_start + p_end) * 0.5
	var sag = min(dist * sag_factor, 1.8)
	p_mid.y -= sag
	
	# Raycast físico hacia el suelo/mesa para evitar que atraviese superficies sólidas
	var world_3d = get_world_3d()
	if world_3d:
		var space_state = world_3d.direct_space_state
		var ray_query = PhysicsRayQueryParameters3D.create(p_mid + Vector3(0, sag * 1.2, 0), p_mid - Vector3(0, 0.5, 0))
		var hit = space_state.intersect_ray(ray_query)
		if hit:
			var min_y = hit.position.y + cable_radius * 1.5
			if p_mid.y < min_y:
				p_mid.y = min_y
	
	# Calcular puntos a lo largo de la curva cuadrática
	var curve_points: Array[Vector3] = []
	for i in range(cable_resolution + 1):
		var t = float(i) / float(cable_resolution)
		var p = (1.0 - t) * (1.0 - t) * p_start + 2.0 * (1.0 - t) * t * p_mid + t * t * p_end
		curve_points.append(to_local(p))
	
	# Construir la geometría 3D
	_immediate_mesh.clear_surfaces()
	_immediate_mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
	
	var ring_vertices: Array = []
	for i in range(curve_points.size()):
		var p = curve_points[i]
		var forward = Vector3.FORWARD
		if i < curve_points.size() - 1:
			forward = (curve_points[i + 1] - p).normalized()
		elif i > 0:
			forward = (p - curve_points[i - 1]).normalized()
			
		var up = Vector3.UP
		if abs(forward.dot(up)) > 0.95:
			up = Vector3.RIGHT
		var right = forward.cross(up).normalized()
		up = right.cross(forward).normalized()
		
		var ring: Array[Vector3] = []
		for j in range(cable_radial_segments):
			var angle = float(j) / float(cable_radial_segments) * TAU
			var offset = (right * cos(angle) + up * sin(angle)) * cable_radius
			ring.append(p + offset)
		ring_vertices.append(ring)
		
	# Conectar anillos mediante triángulos
	for i in range(ring_vertices.size() - 1):
		var r1 = ring_vertices[i]
		var r2 = ring_vertices[i + 1]
		for j in range(cable_radial_segments):
			var next_j = (j + 1) % cable_radial_segments
			
			var v1 = r1[j]
			var v2 = r1[next_j]
			var v3 = r2[next_j]
			var v4 = r2[j]
			
			_immediate_mesh.surface_add_vertex(v1)
			_immediate_mesh.surface_add_vertex(v2)
			_immediate_mesh.surface_add_vertex(v3)
			
			_immediate_mesh.surface_add_vertex(v1)
			_immediate_mesh.surface_add_vertex(v3)
			_immediate_mesh.surface_add_vertex(v4)
			
	_immediate_mesh.surface_end()
