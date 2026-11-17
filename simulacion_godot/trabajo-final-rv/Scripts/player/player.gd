class_name Player
extends CharacterBody3D
## Operario en primera persona: movimiento, cámara y careta.
## La interacción con objetos vive en PlayerInteractor; el flujo del ejercicio
## en ExerciseController. Modos:
##   FREE    -> caminar y mirar libremente (preparación del equipo).
##   STATION -> posicionado frente a la probeta; sin movimiento ni mirada libre.

signal mode_changed(new_mode: int)

enum Mode { FREE, STATION }

const SPEED := 5.0
const JUMP_VELOCITY := 5.0
const CROUCH_SPEED := 2.5
const STANDING_HEIGHT := 1.8
const CROUCH_HEIGHT := 1.0
const CROUCH_TRANSITION_SPEED := 10.0
const CAMERA_CROUCH_DROP := 0.7
const MOUSE_SENSITIVITY := 0.002
const MAX_PITCH := 1.3963  # 80°
const STATION_FOV := 55.0

@onready var collision_shape: CollisionShape3D = $CollisionShape3D
@onready var camera_pivot: Node3D = $CameraPivot
@onready var camera: Camera3D = $CameraPivot/Camera3D
@onready var interactor: PlayerInteractor = $CameraPivot/Camera3D/Interactor
@onready var mask_hud: MaskHud = $MaskHud

var mode: int = Mode.FREE
var is_crouching: bool = false

var _standing_camera_y: float = 2.0
var _station_tween: Tween
var _default_fov: float = 75.0


func _ready() -> void:
	collision_layer = PhysicsLayers.PLAYER
	collision_mask = PhysicsLayers.WORLD
	_standing_camera_y = camera_pivot.position.y
	_default_fov = camera.fov
	capture_mouse(true)


func capture_mouse(captured: bool) -> void:
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED if captured else Input.MOUSE_MODE_VISIBLE


func _unhandled_input(event: InputEvent) -> void:
	if mode == Mode.FREE and event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		var motion := event as InputEventMouseMotion
		rotate_y(-motion.relative.x * MOUSE_SENSITIVITY)
		camera_pivot.rotate_x(-motion.relative.y * MOUSE_SENSITIVITY)
		camera_pivot.rotation.x = clampf(camera_pivot.rotation.x, -MAX_PITCH, MAX_PITCH)
	if event.is_action_pressed("toggle_mask"):
		mask_hud.toggle()


func _physics_process(delta: float) -> void:
	if mode != Mode.FREE:
		return
	_update_crouch(delta)

	if not is_on_floor():
		velocity += get_gravity() * delta
	if Input.is_action_just_pressed("jump") and is_on_floor() and not is_crouching:
		velocity.y = JUMP_VELOCITY

	var speed := CROUCH_SPEED if is_crouching else SPEED
	var input_dir := Input.get_vector("left", "right", "forward", "back")
	var direction := (transform.basis * Vector3(input_dir.x, 0.0, input_dir.y)).normalized()
	if direction != Vector3.ZERO:
		velocity.x = direction.x * speed
		velocity.z = direction.z * speed
	else:
		velocity.x = move_toward(velocity.x, 0.0, speed)
		velocity.z = move_toward(velocity.z, 0.0, speed)
	move_and_slide()


## Lleva al operario a la posición de soldadura (pies, cabeza y mirada del spot).
## Devuelve el Tween para poder esperar a que termine.
func enter_station(spot: WeldingSpot, duration: float = 0.8) -> Tween:
	mode = Mode.STATION
	velocity = Vector3.ZERO
	interactor.set_active(false)

	var stand := spot.stand_point.global_position
	var head := spot.head_point.global_position
	var look := spot.look_target.global_position
	var flat := Vector3(look.x - stand.x, 0.0, look.z - stand.z)
	var target_yaw := atan2(-flat.x, -flat.z)
	var head_local := Basis(Vector3.UP, target_yaw).inverse() * (head - stand)
	var horizontal := Vector2(look.x - head.x, look.z - head.z).length()
	var target_pitch := atan2(look.y - head.y, maxf(horizontal, 0.001))
	var start_yaw := rotation.y

	if _station_tween != null:
		_station_tween.kill()
	_station_tween = create_tween().set_parallel(true).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
	_station_tween.tween_property(self, "global_position", stand, duration)
	_station_tween.tween_method(func(t: float) -> void: rotation.y = lerp_angle(start_yaw, target_yaw, t), 0.0, 1.0, duration)
	_station_tween.tween_property(camera_pivot, "position", head_local, duration)
	_station_tween.tween_property(camera_pivot, "rotation:x", target_pitch, duration)
	_station_tween.tween_property(camera, "fov", STATION_FOV, duration)
	mode_changed.emit(mode)
	return _station_tween


func _update_crouch(delta: float) -> void:
	var wants_crouch := Input.is_action_pressed("crouch")
	if not wants_crouch and is_crouching:
		# No levantarse si hay un techo bajo.
		if test_move(global_transform, Vector3.UP * (STANDING_HEIGHT - CROUCH_HEIGHT)):
			wants_crouch = true
	is_crouching = wants_crouch

	var weight := minf(CROUCH_TRANSITION_SPEED * delta, 1.0)
	var target_cam_y := _standing_camera_y - CAMERA_CROUCH_DROP if is_crouching else _standing_camera_y
	camera_pivot.position.y = lerpf(camera_pivot.position.y, target_cam_y, weight)

	var capsule := collision_shape.shape as CapsuleShape3D
	if capsule != null:
		var target_height := CROUCH_HEIGHT if is_crouching else STANDING_HEIGHT
		capsule.height = lerpf(capsule.height, target_height, weight)
		collision_shape.position.y = capsule.height * 0.5
