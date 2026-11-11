class_name TorchController
extends Node3D

## ==============================================================================
## TorchController.gd - Controlador de la Pinza Porta-Electrodo SMAW 3D
## ==============================================================================
## Recibe la orientación del ESP32, aplica filtrado espacial suave por cuaterniones,
## gestiona el consumo dinámico de la varilla de soldadura y proyecta la punta.

@export_group("Nodos de la Herramienta")
@export var serial_manager: SerialManager
@export var electrode_mesh: MeshInstance3D
@export var electrode_tip_marker: Marker3D

@export_group("Dinámica de Soldadura")
@export var initial_electrode_length_mm: float = 200.0
@export var burn_rate_mm_per_sec: float = 1.8  ## Velocidad de consumo del electrodo al soldar
@export var slerp_speed: float = 24.0           ## Velocidad de interpolación angular

var current_electrode_length_mm: float = 200.0
var _target_quaternion: Quaternion = Quaternion.IDENTITY
var _current_quaternion: Quaternion = Quaternion.IDENTITY
var _last_distance_mm: float = 50.0
var is_trigger_pressed: bool = false

# Offset angular de calibración entre el sensor MPU6050 y el modelo 3D
var _calibration_offset_quat: Quaternion = Quaternion.IDENTITY

func _ready() -> void:
	current_electrode_length_mm = initial_electrode_length_mm
	_target_quaternion = quaternion
	_current_quaternion = quaternion

	if not electrode_tip_marker:
		electrode_tip_marker = $ElectrodeTip

	if serial_manager:
		serial_manager.telemetry_received.connect(_on_telemetry_received)
	else:
		push_warning("[TorchController] No se asignó SerialManager; buscando en la raíz de escena...")
		var sm = get_tree().root.find_child("SerialManager", true, false)
		if sm:
			serial_manager = sm as SerialManager
			serial_manager.telemetry_received.connect(_on_telemetry_received)

func _on_telemetry_received(data: Dictionary) -> void:
	if data.has("quat"):
		var raw_quat: Quaternion = data["quat"]
		# El MPU6050 reporta (X, Y, Z, W). Mapeamos al sistema de coordenadas de Godot (-Z hacia adelante, Y arriba)
		# Aplicamos corrección de ejes para que el agarre físico coincida con la postura natural de la mano
		var godot_quat = Quaternion(-raw_quat.x, -raw_quat.z, -raw_quat.y, raw_quat.w)
		_target_quaternion = godot_quat.normalized()

	if data.has("distance_tip_mm"):
		_last_distance_mm = data["distance_tip_mm"]

	if data.has("trigger_pressed"):
		is_trigger_pressed = data["trigger_pressed"]

func _physics_process(delta: float) -> void:
	# Interpolación esférica (SLERP) para suavizar cualquier micro-ruido del sensor a 60-120 FPS
	_current_quaternion = _current_quaternion.slerp(_target_quaternion, clampf(slerp_speed * delta, 0.0, 1.0))
	quaternion = _current_quaternion

	# Control de consumo de electrodo durante el arco
	_update_electrode_burn(delta)

## Reduce progresivamente la longitud de la varilla mientras el arco esté encendido
func burn_electrode(delta: float) -> void:
	if current_electrode_length_mm > 25.0: # Deja un residuo mínimo de colilla
		current_electrode_length_mm -= burn_rate_mm_per_sec * delta
		_apply_electrode_scaling()

func _update_electrode_burn(_delta: float) -> void:
	# Escalado del modelo 3D de la varilla
	_apply_electrode_scaling()

func _apply_electrode_scaling() -> void:
	if electrode_mesh:
		var scale_factor = current_electrode_length_mm / initial_electrode_length_mm
		electrode_mesh.scale.y = clampf(scale_factor, 0.12, 1.0)
		# Desplazar la punta proporcionalmente
		if electrode_tip_marker:
			electrode_tip_marker.position.y = - (current_electrode_length_mm * 0.001)

func reset_new_electrode() -> void:
	current_electrode_length_mm = initial_electrode_length_mm
	_apply_electrode_scaling()
	print("[TorchController] Nuevo electrodo colocado (Longitud: ", initial_electrode_length_mm, " mm)")

func get_tip_global_position() -> Vector3:
	if electrode_tip_marker:
		return electrode_tip_marker.global_position
	return global_position

func get_tip_forward_vector() -> Vector3:
	if electrode_tip_marker:
		return -electrode_tip_marker.global_transform.basis.y.normalized()
	return -global_transform.basis.z.normalized()
