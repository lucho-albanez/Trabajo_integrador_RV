class_name FirstPersonPlayer
extends CharacterBody3D

## ==============================================================================
## FirstPersonPlayer.gd - Controlador de Operario en Primera Persona (FPV)
## ==============================================================================
## Simula la postura y visión del soldador frente a la mesa de trabajo.
## Incluye movimiento suave, rotación de cabeza con ratón y anclaje visual de la pinza.

@export_group("Movimiento")
@export var walk_speed: float = 1.6
@export var sprint_speed: float = 2.8
@export var mouse_sensitivity: float = 0.002
@export var gravity: float = 9.8

@export_group("Referencias de Nodos")
@export var head: Node3D
@export var camera: Camera3D
@export var torch_anchor: Marker3D
@export var helmet_overlay: ColorRect

var _is_mouse_captured: bool = true
var _is_helmet_down: bool = true

func _ready() -> void:
	if not head:
		head = $Head
	if not camera and head:
		camera = head.get_node_or_null("Camera3D")
	if not torch_anchor and head:
		torch_anchor = head.get_node_or_null("TorchAnchor")
	if not helmet_overlay:
		helmet_overlay = get_node_or_null("UI/HelmetOverlay")

	Input.set_mouse_mode(Input.MOUSE_MODE_CAPTURED)

func _unhandled_input(event: InputEvent) -> void:
	# Captura o liberación del ratón con tecla ESC
	if event is InputEventKey and event.is_pressed() and event.keycode == KEY_ESCAPE:
		if _is_mouse_captured:
			Input.set_mouse_mode(Input.MOUSE_MODE_VISIBLE)
			_is_mouse_captured = false
		else:
			Input.set_mouse_mode(Input.MOUSE_MODE_CAPTURED)
			_is_mouse_captured = true

	# Control de vista de cabeza con el ratón
	if _is_mouse_captured and event is InputEventMouseMotion:
		rotate_y(-event.relative.x * mouse_sensitivity)
		if head:
			head.rotate_x(-event.relative.y * mouse_sensitivity)
			# Limitar cabeceo vertical para mirar la chapa en la mesa cómodamente (-80° a +70°)
			head.rotation.x = clampf(head.rotation.x, deg_to_rad(-80.0), deg_to_rad(70.0))

	# Alternar visor de la careta de soldar (tecla F)
	if event is InputEventKey and event.is_action_pressed("toggle_mask"):
		toggle_welding_helmet()

func _physics_process(delta: float) -> void:
	# Aplicar gravedad
	if not is_on_floor():
		velocity.y -= gravity * delta
	else:
		velocity.y = 0.0

	# Movimiento WASD en plano horizontal
	var input_dir = Vector2.ZERO
	if Input.is_action_pressed("move_forward"):  input_dir.y -= 1.0
	if Input.is_action_pressed("move_backward"): input_dir.y += 1.0
	if Input.is_action_pressed("move_left"):     input_dir.x -= 1.0
	if Input.is_action_pressed("move_right"):    input_dir.x += 1.0
	input_dir = input_dir.normalized()

	var current_speed = sprint_speed if Input.is_key_pressed(KEY_SHIFT) else walk_speed
	var direction = (transform.basis * Vector3(input_dir.x, 0, input_dir.y)).normalized()

	if direction != Vector3.ZERO:
		velocity.x = direction.x * current_speed
		velocity.z = direction.z * current_speed
	else:
		velocity.x = move_toward(velocity.x, 0, current_speed * 10.0 * delta)
		velocity.z = move_toward(velocity.z, 0, current_speed * 10.0 * delta)

	move_and_slide()

func toggle_welding_helmet() -> void:
	_is_helmet_down = !_is_helmet_down
	if helmet_overlay:
		helmet_overlay.visible = _is_helmet_down
	print("[Player] Careta de soldador: ", "BAJADA (Filtro DIN 11 Activo)" if _is_helmet_down else "LEVANTADA")

func set_helmet_state(down: bool) -> void:
	_is_helmet_down = down
	if helmet_overlay:
		helmet_overlay.visible = _is_helmet_down
