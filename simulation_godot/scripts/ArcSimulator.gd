class_name ArcSimulator
extends Node3D

## ==============================================================================
## ArcSimulator.gd - Motor Físico del Arco Eléctrico SMAW y Evaluación Técnica
## ==============================================================================
## Evalúa en tiempo real: longitud de arco, ángulo de avance, ángulo de trabajo,
## velocidad de avance y calidad de deposición. Controla VFX y feedback háptico.

signal arc_ignited()
signal arc_extinguished()
signal arc_quality_updated(score: float, metrics: Dictionary)

@export_group("Referencias de Nodos")
@export var torch: TorchController
@export var serial_manager: SerialManager
@export var weld_bead_generator: Node3D # WeldBeadGenerator
@export var arc_light: OmniLight3D
@export var sparks_particles: GPUParticles3D
@export var smoke_particles: GPUParticles3D

@export_group("Parámetros de Calibración de Soldadura (Norma AWS/ISO)")
@export var optimal_distance_min_mm: float = 1.5
@export var optimal_distance_max_mm: float = 3.5
@export var max_arc_distance_mm: float = 6.0
@export var optimal_travel_angle_deg: float = 18.0 ## Ángulo de arrastre recomendado (15° - 20°)
@export var optimal_work_angle_deg: float = 90.0    ## 90° para junta a tope en posición plana
@export var optimal_speed_min_mm_s: float = 3.0
@export var optimal_speed_max_mm_s: float = 6.0

# Estado del arco
var is_arc_active: bool = false
var is_electrode_stuck: bool = false

# Mediciones actuales
var current_arc_distance_mm: float = 0.0
var current_travel_angle_deg: float = 0.0
var current_work_angle_deg: float = 0.0
var current_travel_speed_mm_s: float = 0.0
var current_quality_score: float = 0.0

var _last_contact_point: Vector3 = Vector3.ZERO
var _has_previous_point: bool = false
var _haptic_sync_timer: float = 0.0

func _ready() -> void:
	if not arc_light:
		arc_light = get_node_or_null("ArcLight")
	if not sparks_particles:
		sparks_particles = get_node_or_null("SparksParticles")
	if not smoke_particles:
		smoke_particles = get_node_or_null("SmokeParticles")

	_set_arc_visuals(false)

func _physics_process(delta: float) -> void:
	if not torch:
		return

	var tip_pos = torch.get_tip_global_position()
	var forward_dir = torch.get_tip_forward_vector()

	# Lanzar Raycast desde la punta del electrodo hacia adelante
	var space_state = get_world_3d().direct_space_state
	var ray_length = max_arc_distance_mm * 0.001 * 2.5 # Convertido a metros (margen de búsqueda)
	var ray_query = PhysicsRayQueryParameters3D.create(tip_pos, tip_pos + forward_dir * ray_length)
	ray_query.collide_with_areas = false
	ray_query.collide_with_bodies = true

	var hit = space_state.intersect_ray(ray_query)

	if hit.is_empty():
		# No hay chapa en el cono cercano
		_handle_arc_state(false, false, 999.0, delta)
	else:
		var hit_point: Vector3 = hit.position
		var hit_normal: Vector3 = hit.normal
		var dist_meters = tip_pos.distance_to(hit_point)
		current_arc_distance_mm = dist_meters * 1000.0

		# 1. Evaluar si el electrodo está físicamente tocando la pieza (< 0.8 mm)
		var is_touching = (current_arc_distance_mm <= 0.8)

		# 2. Cebado o mantenimiento de arco
		# El arco se enciende si toca la pieza con gatillo o si ya estaba cebado y está dentro del rango
		var should_ignite = false
		if is_touching and torch.is_trigger_pressed:
			should_ignite = true
		elif is_arc_active and current_arc_distance_mm <= max_arc_distance_mm:
			should_ignite = true

		if is_touching and is_arc_active:
			# Electrodo pegado (cortocircuito)
			is_electrode_stuck = true
		else:
			is_electrode_stuck = false

		_handle_arc_state(should_ignite, is_electrode_stuck, current_arc_distance_mm, delta)

		if is_arc_active and not is_electrode_stuck:
			# Posicionar los efectos visuales exactamente en el charco de soldadura
			global_position = hit_point
			_evaluate_welding_parameters(hit_point, hit_normal, forward_dir, delta)

			# Desgastar electrodo
			torch.burn_electrode(delta)

			# Depositar cordón procedimental
			if weld_bead_generator and weld_bead_generator.has_method("add_bead_point"):
				weld_bead_generator.call("add_bead_point", hit_point, hit_normal, current_quality_score, delta)

	# Parpadeo estocástico del arco eléctrico para realismo óptico
	if is_arc_active and arc_light:
		arc_light.light_energy = randf_range(5.0, 12.0)

	# Sincronización de háptico de retorno con el ESP32 a 20 Hz
	_sync_haptic_to_esp32(delta)

func _handle_arc_state(active: bool, stuck: bool, distance_mm: float, _delta: float) -> void:
	if active and not is_arc_active:
		is_arc_active = true
		_set_arc_visuals(true)
		arc_ignited.emit()
		print("[ArcSimulator] ¡Arco Eléctrico Cebado!")
	elif not active and is_arc_active:
		is_arc_active = false
		is_electrode_stuck = false
		_set_arc_visuals(false)
		_has_previous_point = false
		arc_extinguished.emit()
		print("[ArcSimulator] Arco Extinguido.")

func _evaluate_welding_parameters(hit_point: Vector3, hit_normal: Vector3, electrode_dir: Vector3, delta: float) -> void:
	# 1. Velocidad de desplazamiento (mm/s)
	if _has_previous_point and delta > 0.0:
		var displacement = _last_contact_point.distance_to(hit_point)
		current_travel_speed_mm_s = (displacement * 1000.0) / delta
	else:
		current_travel_speed_mm_s = (optimal_speed_min_mm_s + optimal_speed_max_mm_s) * 0.5
		_has_previous_point = true

	_last_contact_point = hit_point

	# 2. Ángulos técnicos de soldadura respecto a la normal de la chapa
	# Ángulo de inclinación general respecto a la normal vertical
	var angle_to_normal_deg = rad_to_deg(acos(clampf(electrode_dir.dot(-hit_normal), -1.0, 1.0)))
	current_travel_angle_deg = angle_to_normal_deg
	current_work_angle_deg = 90.0 - angle_to_normal_deg # Aproximación planar

	# 3. Puntuación de calidad (0 a 100%)
	var dist_score = _calculate_gaussian_score(current_arc_distance_mm, (optimal_distance_min_mm + optimal_distance_max_mm) * 0.5, 1.0)
	var angle_score = _calculate_gaussian_score(current_travel_angle_deg, optimal_travel_angle_deg, 6.0)
	var speed_score = _calculate_gaussian_score(current_travel_speed_mm_s, (optimal_speed_min_mm_s + optimal_speed_max_mm_s) * 0.5, 2.0)

	current_quality_score = (dist_score * 0.45) + (angle_score * 0.30) + (speed_score * 0.25)
	current_quality_score = clampf(current_quality_score * 100.0, 0.0, 100.0)

	var metrics = {
		"distance_mm": current_arc_distance_mm,
		"travel_angle_deg": current_travel_angle_deg,
		"work_angle_deg": current_work_angle_deg,
		"speed_mm_s": current_travel_speed_mm_s,
		"score": current_quality_score,
		"is_stuck": is_electrode_stuck
	}
	arc_quality_updated.emit(current_quality_score, metrics)

func _calculate_gaussian_score(value: float, target: float, tolerance: float) -> float:
	var diff = value - target
	return exp(- (diff * diff) / (2.0 * tolerance * tolerance))

func _set_arc_visuals(enabled: bool) -> void:
	if arc_light:
		arc_light.visible = enabled
	if sparks_particles:
		sparks_particles.emitting = enabled
	if smoke_particles:
		smoke_particles.emitting = enabled

func _sync_haptic_to_esp32(delta: float) -> void:
	_haptic_sync_timer += delta
	if _haptic_sync_timer < 0.05: # 20 Hz
		return
	_haptic_sync_timer = 0.0

	if not serial_manager:
		return

	if is_electrode_stuck:
		serial_manager.send_haptic_override(255) # 100% vibración cortocircuito
	elif is_arc_active:
		if current_arc_distance_mm >= optimal_distance_min_mm and current_arc_distance_mm <= optimal_distance_max_mm:
			serial_manager.send_haptic_override(75) # 30% ronroneo óptimo
		else:
			serial_manager.send_haptic_override(120) # Advertencia de arco inestable
	else:
		serial_manager.send_haptic_override(0) # Apagado
