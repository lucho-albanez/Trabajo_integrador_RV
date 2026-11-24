class_name Player
extends CharacterBody3D
## Operario en primera persona. NO se controla con teclado: durante la preparación
## el ejercicio lo guía de tarea en tarea (walk_to) y luego lo posiciona frente a la
## probeta (enter_station). La interacción con objetos vive en PlayerInteractor y el
## flujo del ejercicio en ExerciseController / SetupSequence.
## Modos:
##   GUIDED  -> se desplaza solo a donde indica la secuencia de preparación.
##   STATION -> posicionado frente a la probeta para soldar.

signal mode_changed(new_mode: int)

enum Mode { GUIDED, STATION }

const WALK_SPEED_M_S := 2.2
const MIN_MOVE_S := 0.8
const MAX_MOVE_S := 3.0
const STATION_FOV := 55.0

@onready var camera_pivot: Node3D = $CameraPivot
@onready var camera: Camera3D = $CameraPivot/Camera3D
@onready var interactor: PlayerInteractor = $CameraPivot/Camera3D/Interactor
@onready var mask_hud: MaskHud = $MaskHud

var mode: int = Mode.GUIDED

var _station_tween: Tween
var _default_fov: float = 75.0
var _standing_camera_y: float = 2.0


func _ready() -> void:
	collision_layer = PhysicsLayers.PLAYER
	collision_mask = PhysicsLayers.WORLD
	_standing_camera_y = camera_pivot.position.y
	_default_fov = camera.fov
	capture_mouse(true)


func capture_mouse(captured: bool) -> void:
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED if captured else Input.MOUSE_MODE_VISIBLE


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("toggle_mask"):
		mask_hud.toggle()


## Camina hasta `stand` (posición de los pies) y termina mirando `look_target`.
## Devuelve el Tween para poder esperar a que termine.
func walk_to(stand: Vector3, look_target: Vector3, duration: float = -1.0) -> Tween:
	if duration < 0.0:
		duration = clampf(global_position.distance_to(stand) / WALK_SPEED_M_S, MIN_MOVE_S, MAX_MOVE_S)
	var head_local := Vector3(0.0, _standing_camera_y, 0.0)
	return _move_to(stand, head_local, look_target, _default_fov, duration)


## Lleva al operario a la posición de soldadura (pies, cabeza y mirada del spot).
func enter_station(spot: WeldingSpot, duration: float = 0.8) -> Tween:
	var stand := spot.stand_point.global_position
	var yaw := _yaw_towards(stand, spot.look_target.global_position)
	var head_local := Basis(Vector3.UP, yaw).inverse() * (spot.head_point.global_position - stand)
	var tween := _move_to(stand, head_local, spot.look_target.global_position, STATION_FOV, duration, spot.head_point.global_position)
	mode = Mode.STATION
	mode_changed.emit(mode)
	return tween


func _move_to(stand: Vector3, head_local: Vector3, look_target: Vector3, fov: float, duration: float, head_world: Vector3 = Vector3.INF) -> Tween:
	velocity = Vector3.ZERO
	interactor.set_active(false)
	var target_yaw := _yaw_towards(stand, look_target)
	var head := head_world if head_world != Vector3.INF else stand + head_local
	var horizontal := Vector2(look_target.x - head.x, look_target.z - head.z).length()
	var target_pitch := atan2(look_target.y - head.y, maxf(horizontal, 0.001))
	var start_yaw := rotation.y

	if _station_tween != null:
		_station_tween.kill()
	_station_tween = create_tween().set_parallel(true).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
	_station_tween.tween_property(self, "global_position", stand, duration)
	_station_tween.tween_method(func(t: float) -> void: rotation.y = lerp_angle(start_yaw, target_yaw, t), 0.0, 1.0, duration)
	_station_tween.tween_property(camera_pivot, "position", head_local, duration)
	_station_tween.tween_property(camera_pivot, "rotation:x", target_pitch, duration)
	_station_tween.tween_property(camera, "fov", fov, duration)
	return _station_tween


static func _yaw_towards(from: Vector3, to: Vector3) -> float:
	var flat := Vector3(to.x - from.x, 0.0, to.z - from.z)
	if flat.length() < 0.001:
		return 0.0
	return atan2(-flat.x, -flat.z)
